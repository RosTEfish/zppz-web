from io import BytesIO
from pathlib import Path
import shutil
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import get_settings
from app.db.bootstrap import seed_defaults
from app.db.session import Base, SessionLocal, engine
from app.main import app
from app.models import DrawAssignment, Event, GuessChart, Song, Submission, User


@pytest.fixture(autouse=True)
def reset_db_and_files():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed_defaults(db)
    settings = get_settings()
    shutil.rmtree(settings.uploads_dir, ignore_errors=True)
    shutil.rmtree(settings.assets_dir / "guess-covers", ignore_errors=True)
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    (settings.assets_dir / "guess-covers").mkdir(parents=True, exist_ok=True)


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def archive_bytes(title: str = "Song", levels: str = "&lv_4=13\n&lv_5=14") -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        archive.writestr("nested/maidata.txt", f"&title={title}\n&artist=Artist\n{levels}")
        archive.writestr("nested/bg.png", b"cover")
    return buffer.getvalue()


def register(client: TestClient, code: str, identity: str = "participant") -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={"user_code": code, "qq_id": code, "password": "secret123", "identity": identity},
    )
    assert response.status_code == 201, response.text


def login(client: TestClient, code: str, password: str = "secret123") -> None:
    response = client.post("/api/v1/auth/login", json={"user_code": code, "password": password})
    assert response.status_code == 200, response.text


def login_admin(client: TestClient) -> None:
    login(client, "admin", "change-me-please")


def create_candidate_rows() -> tuple[int, int, int]:
    with SessionLocal() as db:
        event = db.scalar(select(Event).where(Event.is_current.is_(True)))
        player = db.scalar(select(User).where(User.user_code == "player"))
        owner = db.scalar(select(User).where(User.user_code == "owner"))
        own = Song(event_id=event.id, submitted_by_id=player.id, song_name="Own", artist="Artist", song_type="A")
        assigned = Song(event_id=event.id, submitted_by_id=owner.id, song_name="Assigned", artist="Artist", song_type="B")
        db.add_all([own, assigned])
        db.flush()
        db.add(DrawAssignment(event_id=event.id, assigned_to_id=player.id, song_id=assigned.id))
        db.commit()
        return event.id, own.id, assigned.id


def test_targets_phase_gate_and_j_limit(client: TestClient):
    register(client, "owner")
    register(client, "player")
    _, own_id, assigned_id = create_candidate_rows()

    targets = client.get("/api/v1/submissions/targets")
    assert targets.status_code == 200
    assert {(row["song"]["id"], row["source_kind"]) for row in targets.json()["targets"]} == {
        (own_id, "self"),
        (assigned_id, "assigned"),
    }
    closed = client.post(
        "/api/v1/submissions",
        data={"song_id": own_id, "track": "normal"},
        files={"file": ("closed.zip", archive_bytes(), "application/zip")},
    )
    assert closed.status_code == 409

    with SessionLocal() as db:
        event = db.scalar(select(Event).where(Event.is_current.is_(True)))
        event.settings.submissions_open = True
        db.commit()
    first = client.post(
        "/api/v1/submissions",
        data={"song_id": assigned_id, "track": "j"},
        files={"file": ("j.zip", archive_bytes("J Song", "&lv_6=15"), "application/zip")},
    )
    assert first.status_code == 200, first.text
    second = client.post(
        "/api/v1/submissions",
        data={"song_id": own_id, "track": "j"},
        files={"file": ("j2.zip", archive_bytes("Other J", "&lv_4=13"), "application/zip")},
    )
    assert second.status_code == 409


def test_admin_open_validation_and_draw_lock(client: TestClient):
    register(client, "owner")
    register(client, "player")
    event_id, _, assigned_id = create_candidate_rows()
    with SessionLocal() as db:
        assignment = db.scalar(select(DrawAssignment).where(DrawAssignment.event_id == event_id))
        db.delete(assignment)
        db.commit()
    login_admin(client)
    event = client.get("/api/v1/events/current").json()
    payload = {"name": event["name"], **event["settings"], "submissions_open": True}
    rejected = client.put("/api/v1/admin/events/current", json=payload)
    assert rejected.status_code == 400
    with SessionLocal() as db:
        player = db.scalar(select(User).where(User.user_code == "player"))
        db.add(DrawAssignment(event_id=event_id, assigned_to_id=player.id, song_id=assigned_id))
        owner = db.scalar(select(User).where(User.user_code == "owner"))
        owner_song = Song(event_id=event_id, submitted_by_id=player.id, song_name="For Owner", artist="Artist", song_type="C")
        db.add(owner_song)
        db.flush()
        db.add(DrawAssignment(event_id=event_id, assigned_to_id=owner.id, song_id=owner_song.id))
        db.commit()
    opened = client.put("/api/v1/admin/events/current", json=payload)
    assert opened.status_code == 200, opened.text
    blocked = client.post("/api/v1/admin/draw")
    assert blocked.status_code == 409


def test_chart_batch_download_deduplicates_source(client: TestClient):
    register(client, "player")
    with SessionLocal() as db:
        event = db.scalar(select(Event).where(Event.is_current.is_(True)))
        player = db.scalar(select(User).where(User.user_code == "player"))
        song = Song(event_id=event.id, submitted_by_id=player.id, song_name="Own", artist="Artist", song_type="A")
        db.add(song)
        event.settings.submissions_open = True
        db.commit()
        song_id = song.id
    uploaded = client.post(
        "/api/v1/submissions",
        data={"song_id": song_id, "track": "normal"},
        files={"file": ("source.zip", archive_bytes(), "application/zip")},
    )
    assert uploaded.status_code == 200
    chart_ids = [row["id"] for row in client.get("/api/v1/guess-game/charts").json()]
    response = client.get(f"/api/v1/guess-game/charts/download.zip?ids={','.join(map(str, chart_ids))}")
    assert response.status_code == 200
    with ZipFile(BytesIO(response.content)) as archive:
        archive_names = archive.namelist()
        assert len([name for name in archive_names if name.endswith("source.zip")]) == 1
        assert "_下载报告.txt" in archive_names


def test_song_pool_csv_updates_in_place_and_rolls_back(client: TestClient):
    register(client, "player")
    with SessionLocal() as db:
        event = db.scalar(select(Event).where(Event.is_current.is_(True)))
        player = db.scalar(select(User).where(User.user_code == "player"))
        song = Song(event_id=event.id, submitted_by_id=player.id, song_name="Before", artist="Old", song_type="A")
        db.add(song)
        db.commit()
        song_id = song.id
    login_admin(client)
    exported = client.get("/api/v1/admin/song-pool/export.csv")
    assert exported.status_code == 200
    assert exported.content.startswith(b"\xef\xbb\xbf")
    csv_body = f"曲目ID,曲名,曲师,备注,分类\n{song_id},After,New,Updated,C\n".encode("gbk")
    imported = client.post("/api/v1/admin/song-pool/import.csv", files={"file": ("songs.csv", csv_body, "text/csv")})
    assert imported.status_code == 200, imported.text
    bad_body = f"曲目ID,曲名,曲师,分类\n{song_id},Broken,Nope,A\n99999,Missing,Nope,B\n".encode()
    rejected = client.post("/api/v1/admin/song-pool/import.csv", files={"file": ("bad.csv", bad_body, "text/csv")})
    assert rejected.status_code == 400
    with SessionLocal() as db:
        song = db.get(Song, song_id)
        assert (song.song_name, song.artist, song.remark, song.song_type) == ("After", "New", "Updated", "C")


def test_admin_archive_import_and_grouped_author_stats(client: TestClient):
    register(client, "owner")
    register(client, "guesser")
    with SessionLocal() as db:
        event = db.scalar(select(Event).where(Event.is_current.is_(True)))
        owner = db.scalar(select(User).where(User.user_code == "owner"))
        guesser = db.scalar(select(User).where(User.user_code == "guesser"))
        owner_song = Song(event_id=event.id, submitted_by_id=owner.id, song_name="Owner Song", artist="Artist", song_type="A")
        guesser_song = Song(event_id=event.id, submitted_by_id=guesser.id, song_name="Guesser Song", artist="Artist", song_type="B")
        db.add_all([owner_song, guesser_song])
        event.settings.submissions_open = True
        db.commit()
        owner_song_id = owner_song.id

    login(client, "owner")
    uploaded = client.post(
        "/api/v1/submissions",
        data={"song_id": owner_song_id, "track": "normal"},
        files={"file": ("owner.zip", archive_bytes("Owner Work"), "application/zip")},
    )
    assert uploaded.status_code == 200, uploaded.text
    chart_ids = [row["id"] for row in client.get("/api/v1/guess-game/charts").json()]

    login(client, "guesser")
    state = client.get(f"/api/v1/guess-game/charts/{chart_ids[0]}/author-guess").json()
    owner_id = next(item["user_id"] for item in state["candidates"] if item["display_id"] == "owner")
    saved = client.put(f"/api/v1/guess-game/charts/{chart_ids[0]}/author-guess", json={"guessed_user_id": owner_id})
    assert saved.status_code == 200
    sibling_state = client.get(f"/api/v1/guess-game/charts/{chart_ids[1]}/author-guess").json()
    assert sibling_state["my_guess_user_id"] == owner_id

    login_admin(client)
    stats = client.get("/api/v1/admin/guess-game/stats?scope=all")
    assert stats.status_code == 200, stats.text
    assert stats.json()["overview"]["counted_guesses"] == 1
    assert stats.json()["overview"]["correct_guesses"] == 1

    imported = client.post(
        "/api/v1/admin/guess-game/charts/import",
        files={"file": ("manual.zip", archive_bytes("Manual"), "application/zip")},
    )
    assert imported.status_code == 200, imported.text
    assert len(imported.json()["charts"]) == 2
    first_manual = imported.json()["charts"][0]
    second_manual = imported.json()["charts"][1]
    storage_path = first_manual["storage_path"]
    assert (get_settings().data_dir / storage_path).is_file()
    assert client.delete(f"/api/v1/admin/guess-game/charts/{first_manual['id']}").status_code == 200
    assert (get_settings().data_dir / storage_path).is_file()
    assert client.delete(f"/api/v1/admin/guess-game/charts/{second_manual['id']}").status_code == 200
    assert not (get_settings().data_dir / storage_path).exists()
