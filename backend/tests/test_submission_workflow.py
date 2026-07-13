from io import BytesIO
from pathlib import Path
import re
import shutil
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import get_settings
from app.db.bootstrap import seed_defaults
from app.db.session import Base, SessionLocal, engine
from app.main import app
from app.models import DrawAssignment, Event, GuessAuthorGuess, GuessChart, GuessComment, GuessVote, Song, Submission, User
from app.modules.downloads import DownloadEntry, prepare_streaming_zip


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
    playable = "\n".join(
        f"&inote_{slot}=(120){{1}},"
        for slot in re.findall(r"(?im)^\s*&lv_([1-7])\s*=", levels)
    )
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        archive.writestr("nested/maidata.txt", f"&title={title}\n&artist=Artist\n{levels}\n{playable}")
        archive.writestr("nested/bg.png", b"cover")
        archive.writestr("nested/track.mp3", (bytes.fromhex("FFFB9064") + bytes(413)) * 2)
    return buffer.getvalue()


def test_streaming_zip_yields_before_the_source_is_fully_read(tmp_path: Path):
    source = tmp_path / "large-source.zip"
    source.write_bytes(b"x" * (2 * 1024 * 1024))
    prepared = prepare_streaming_zip(
        [DownloadEntry(path=source, archive_name="source.zip")],
        file_name="submissions.zip",
    )

    chunks = iter(prepared.stream)
    first_chunk = next(chunks)
    assert first_chunk.startswith(b"PK")
    assert len(first_chunk) < prepared.file_size

    payload = first_chunk + b"".join(chunks)
    assert len(payload) == prepared.file_size
    with ZipFile(BytesIO(payload)) as archive:
        assert archive.read("source.zip") == source.read_bytes()


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


def set_manual_phase(phase: str | None) -> None:
    with SessionLocal() as db:
        event = db.scalar(select(Event).where(Event.is_current.is_(True)))
        event.settings.phase_mode = "manual" if phase else "auto"
        event.settings.manual_phase = phase
        db.commit()


def public_chart_for_submission(client: TestClient, submission_id: int) -> dict:
    with SessionLocal() as db:
        chart_id = db.scalar(select(GuessChart.id).where(GuessChart.source_submission_id == submission_id))
    return next(row for row in client.get("/api/v1/guess-game/charts").json() if row["id"] == chart_id)


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
    set_manual_phase("guess")
    first_chart = public_chart_for_submission(client, first.json()["id"])
    assert client.post("/api/v1/guess-game/vote", json={"chart_id": first_chart["id"], "vote_type": "love"}).status_code == 200
    assert client.post(
        f"/api/v1/guess-game/charts/{first_chart['id']}/comments",
        json={"content": "保留这条评论"},
    ).status_code == 200
    set_manual_phase(None)

    invalid = client.post(
        "/api/v1/submissions",
        data={"song_id": own_id, "track": "j"},
        files={"file": ("invalid.zip", b"not-a-zip", "application/zip")},
    )
    assert invalid.status_code == 422
    assert client.get("/api/v1/submissions/j-track").json()["submission"]["id"] == first.json()["id"]

    second = client.post(
        "/api/v1/submissions",
        data={"song_id": own_id, "track": "j"},
        files={"file": ("j2.zip", archive_bytes("Other J", "&lv_4=13"), "application/zip")},
    )
    assert second.status_code == 409
    assert "J" in second.json()["detail"]

    targets_after = client.get("/api/v1/submissions/targets").json()["targets"]
    tracks = {
        row["song"]["id"]: row["submission"]["track"] if row["submission"] else None
        for row in targets_after
    }
    assert tracks == {assigned_id: "j", own_id: None}
    set_manual_phase("guess")
    old_chart = next(row for row in client.get("/api/v1/guess-game/charts").json() if row["id"] == first_chart["id"])
    assert old_chart["lane"] == "j"
    assert old_chart["source_submission_type"] == "j"
    assert old_chart["love_votes"] == 1
    comments = client.get(f"/api/v1/guess-game/charts/{first_chart['id']}/comments").json()
    assert [row["content"] for row in comments] == ["保留这条评论"]


def test_track_switch_without_upload_and_j_replace_does_not_duplicate_charts(client: TestClient):
    register(client, "owner")
    register(client, "player")
    _, own_id, assigned_id = create_candidate_rows()
    with SessionLocal() as db:
        event = db.scalar(select(Event).where(Event.is_current.is_(True)))
        event.settings.submissions_open = True
        db.commit()

    own = client.post(
        "/api/v1/submissions",
        data={"song_id": own_id, "track": "normal"},
        files={"file": ("test1.zip", archive_bytes("test1", "&lv_4=13"), "application/zip")},
    )
    assigned = client.post(
        "/api/v1/submissions",
        data={"song_id": assigned_id, "track": "normal"},
        files={"file": ("test2.zip", archive_bytes("test2", "&lv_5=14"), "application/zip")},
    )
    assert own.status_code == assigned.status_code == 200
    own_id_submission = own.json()["id"]
    assigned_id_submission = assigned.json()["id"]
    set_manual_phase("guess")
    charts = client.get("/api/v1/guess-game/charts").json()
    assert len(charts) == 2
    own_chart = public_chart_for_submission(client, own_id_submission)
    assert client.post(
        "/api/v1/guess-game/vote",
        json={"chart_id": own_chart["id"], "vote_type": "love"},
    ).status_code == 200
    set_manual_phase(None)
    with SessionLocal() as db:
        original_storage = db.get(Submission, own_id_submission).storage_path

    switched = client.patch(f"/api/v1/submissions/{own_id_submission}/track", json={"track": "j"})
    assert switched.status_code == 200, switched.text
    with SessionLocal() as db:
        assert db.get(Submission, own_id_submission).storage_path == original_storage
    targets = client.get("/api/v1/submissions/targets").json()["targets"]
    assert {row["song"]["id"]: row["submission"]["track"] for row in targets} == {
        own_id: "j",
        assigned_id: "normal",
    }
    set_manual_phase("guess")
    switched_charts = client.get("/api/v1/guess-game/charts").json()
    assert len(switched_charts) == 2
    assert next(row for row in switched_charts if row["id"] == own_chart["id"])["lane"] == "j"

    set_manual_phase(None)
    assert client.patch(f"/api/v1/submissions/{own_id_submission}/track", json={"track": "normal"}).status_code == 200
    assert client.patch(f"/api/v1/submissions/{assigned_id_submission}/track", json={"track": "j"}).status_code == 200
    replaced = client.post(
        f"/api/v1/submissions/{own_id_submission}/replace",
        data={"track": "normal"},
        files={"file": ("test1-new.zip", archive_bytes("test1-new", "&lv_4=13+"), "application/zip")},
    )
    assert replaced.status_code == 200, replaced.text
    set_manual_phase("guess")
    final_charts = client.get("/api/v1/guess-game/charts").json()
    assert len(final_charts) == 2
    with SessionLocal() as db:
        own_chart_ids = set(db.scalars(select(GuessChart.id).where(GuessChart.source_submission_id == own_id_submission)).all())
        assigned_chart_ids = set(db.scalars(select(GuessChart.id).where(GuessChart.source_submission_id == assigned_id_submission)).all())
    final_own = [row for row in final_charts if row["id"] in own_chart_ids]
    final_assigned = [row for row in final_charts if row["id"] in assigned_chart_ids]
    assert len(final_own) == len(final_assigned) == 1
    assert final_own[0]["id"] == own_chart["id"]
    assert final_own[0]["title"] == "test1-new"
    assert final_own[0]["lane"] == "normal"
    assert final_own[0]["love_votes"] == 1
    assert final_assigned[0]["lane"] == "j"


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
    payload = {"name": event["name"], **event["settings"], "participant_song_limit": 0, "audience_song_limit": 0, "submissions_open": True}
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
    set_manual_phase("guess")
    chart_ids = [row["id"] for row in client.get("/api/v1/guess-game/charts").json()]
    metadata = client.get(f"/api/v1/guess-game/charts/download-metadata?ids={','.join(map(str, chart_ids))}")
    assert metadata.status_code == 200, metadata.text
    assert metadata.json()["download_url"].endswith(f"ids={'%2C'.join(map(str, chart_ids))}")
    assert metadata.json()["file_size"] > 0
    response = client.get(f"/api/v1/guess-game/charts/download.zip?ids={','.join(map(str, chart_ids))}")
    assert response.status_code == 200
    assert response.headers["content-encoding"] == "identity"
    assert response.headers["x-accel-buffering"] == "no"
    assert int(response.headers["content-length"]) == len(response.content)
    with ZipFile(BytesIO(response.content)) as archive:
        archive_names = archive.namelist()
        assert len([name for name in archive_names if name.endswith(".zip")]) == 1
        assert all("source.zip" not in name for name in archive_names)
    assert "_下载报告.txt" in archive_names

    login_admin(client)
    submission_id = uploaded.json()["id"]
    single_metadata = client.get(f"/api/v1/admin/submissions/{submission_id}/download-metadata")
    assert single_metadata.status_code == 200
    assert single_metadata.json()["file_size"] == uploaded.json()["file_size"]
    batch_metadata = client.get(f"/api/v1/admin/submissions/download-metadata?ids={submission_id}")
    assert batch_metadata.status_code == 200
    admin_download = client.get(batch_metadata.json()["download_url"])
    assert admin_download.status_code == 200
    assert admin_download.headers["content-encoding"] == "identity"
    assert int(admin_download.headers["content-length"]) == len(admin_download.content)


def test_admin_song_batch_delete_is_atomic(client: TestClient):
    register(client, "player")
    with SessionLocal() as db:
        event = db.scalar(select(Event).where(Event.is_current.is_(True)))
        player = db.scalar(select(User).where(User.user_code == "player"))
        free_song = Song(event_id=event.id, submitted_by_id=player.id, song_name="Free", artist="Artist", song_type="A")
        linked_song = Song(event_id=event.id, submitted_by_id=player.id, song_name="Linked", artist="Artist", song_type="B")
        db.add_all([free_song, linked_song])
        db.flush()
        db.add(Submission(event_id=event.id, user_id=player.id, source_song_id=linked_song.id, source_kind="self", track="normal", file_name="linked.zip", storage_path="uploads/linked.zip", file_size=1))
        db.commit()
        free_id, linked_id = free_song.id, linked_song.id

    login_admin(client)
    blocked = client.post("/api/v1/admin/song-pool/batch-delete", json={"ids": [free_id, linked_id]})
    assert blocked.status_code == 409
    with SessionLocal() as db:
        assert db.get(Song, free_id) is not None
        assert db.get(Song, linked_id) is not None

    missing = client.post("/api/v1/admin/song-pool/batch-delete", json={"ids": [free_id, 99999]})
    assert missing.status_code == 404
    with SessionLocal() as db:
        assert db.get(Song, free_id) is not None

    deleted = client.post("/api/v1/admin/song-pool/batch-delete", json={"ids": [free_id, free_id]})
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["deleted"] == 1
    with SessionLocal() as db:
        assert db.get(Song, free_id) is None
        assert db.get(Song, linked_id) is not None


def test_admin_submission_batch_delete_cleans_all_linked_resources(client: TestClient):
    register(client, "owner")
    register(client, "player")
    _, own_id, assigned_id = create_candidate_rows()
    with SessionLocal() as db:
        event = db.scalar(select(Event).where(Event.is_current.is_(True)))
        event.settings.submissions_open = True
        db.commit()
    first = client.post(
        "/api/v1/submissions",
        data={"song_id": own_id, "track": "normal"},
        files={"file": ("first.zip", archive_bytes("First", "&lv_4=13"), "application/zip")},
    )
    second = client.post(
        "/api/v1/submissions",
        data={"song_id": assigned_id, "track": "j"},
        files={"file": ("second.zip", archive_bytes("Second", "&lv_5=14"), "application/zip")},
    )
    assert first.status_code == second.status_code == 200
    submission_ids = [first.json()["id"], second.json()["id"]]
    set_manual_phase("guess")
    charts = client.get("/api/v1/guess-game/charts").json()
    assert client.post("/api/v1/guess-game/vote", json={"chart_id": charts[0]["id"], "vote_type": "love"}).status_code == 200
    assert client.post(f"/api/v1/guess-game/charts/{charts[0]['id']}/comments", json={"content": "cleanup"}).status_code == 200
    with SessionLocal() as db:
        rows = [db.get(Submission, item) for item in submission_ids]
        storage_files = [get_settings().data_dir / row.storage_path for row in rows]
        cover_files = [get_settings().assets_dir / "guess-covers" / Path(chart["cover_path"]).name for chart in charts]
    assert all(path.is_file() for path in storage_files)

    login_admin(client)
    missing = client.post("/api/v1/admin/submissions/batch-delete", json={"ids": [submission_ids[0], 99999]})
    assert missing.status_code == 404
    with SessionLocal() as db:
        assert db.get(Submission, submission_ids[0]) is not None

    deleted = client.post("/api/v1/admin/submissions/batch-delete", json={"ids": submission_ids})
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["deleted"] == 2
    with SessionLocal() as db:
        assert not list(db.scalars(select(Submission).where(Submission.id.in_(submission_ids))).all())
        assert not list(db.scalars(select(GuessChart).where(GuessChart.source_submission_id.in_(submission_ids))).all())
        assert db.scalar(select(GuessVote.id).limit(1)) is None
        assert db.scalar(select(GuessComment.id).limit(1)) is None
    assert all(not path.exists() for path in storage_files)
    assert all(not path.exists() for path in cover_files)


def test_admin_chart_batch_delete_is_atomic_and_preserves_submission_archive(client: TestClient):
    settings = get_settings()
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    retained_file = settings.uploads_dir / "retained-source.zip"
    retained_file.write_bytes(b"source")
    with SessionLocal() as db:
        event = db.scalar(select(Event).where(Event.is_current.is_(True)))
        admin = db.scalar(select(User).where(User.user_code == "admin"))
        song = Song(event_id=event.id, submitted_by_id=admin.id, song_name="Retained", artist="Artist", song_type="A")
        db.add(song)
        db.flush()
        storage_path = str(retained_file.relative_to(settings.data_dir)).replace("\\", "/")
        submission = Submission(event_id=event.id, user_id=admin.id, source_song_id=song.id, source_kind="self", track="normal", file_name="retained-source.zip", storage_path=storage_path, file_size=retained_file.stat().st_size)
        db.add(submission)
        db.flush()
        chart = GuessChart(event_id=event.id, title="Retained", author="Artist", designer="Designer", level="13", lane="normal", guess_group_key="retained", source_submission_type="normal", source_submission_id=submission.id, source_level_slot="4", cover_path="", storage_path=storage_path, is_self_selected=True, plays=0)
        db.add(chart)
        db.commit()
        submission_id, retained_chart_id = submission.id, chart.id

    login_admin(client)
    retained_delete = client.post("/api/v1/admin/guess-game/charts/batch-delete", json={"ids": [retained_chart_id]})
    assert retained_delete.status_code == 200, retained_delete.text
    assert retained_file.is_file()
    with SessionLocal() as db:
        assert db.get(Submission, submission_id) is not None

    imported = client.post(
        "/api/v1/admin/guess-game/charts/import",
        files={"file": ("manual.zip", archive_bytes("Manual"), "application/zip")},
    )
    assert imported.status_code == 200, imported.text
    chart_ids = [chart["id"] for chart in imported.json()["charts"]]
    archive_path = settings.data_dir / imported.json()["charts"][0]["storage_path"]
    cover_path = settings.assets_dir / "guess-covers" / Path(imported.json()["charts"][0]["cover_path"]).name

    missing = client.post("/api/v1/admin/guess-game/charts/batch-delete", json={"ids": [chart_ids[0], 99999]})
    assert missing.status_code == 404
    with SessionLocal() as db:
        assert db.get(GuessChart, chart_ids[0]) is not None
    assert archive_path.is_file()

    deleted = client.post("/api/v1/admin/guess-game/charts/batch-delete", json={"ids": chart_ids})
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["deleted"] == len(chart_ids)
    assert not archive_path.exists()
    assert not cover_path.exists()


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
    register(client, "viewer", "audience")
    register(client, "disabled")
    with SessionLocal() as db:
        event = db.scalar(select(Event).where(Event.is_current.is_(True)))
        owner = db.scalar(select(User).where(User.user_code == "owner"))
        guesser = db.scalar(select(User).where(User.user_code == "guesser"))
        disabled = db.scalar(select(User).where(User.user_code == "disabled"))
        disabled.is_active = False
        owner_song = Song(event_id=event.id, submitted_by_id=owner.id, song_name="Owner Song", artist="Artist", song_type="A")
        guesser_song = Song(event_id=event.id, submitted_by_id=guesser.id, song_name="Guesser Song", artist="Artist", song_type="B")
        db.add_all([owner_song, guesser_song])
        event.settings.submissions_open = True
        db.commit()
        owner_song_id = owner_song.id
        owner_user_id = owner.id

    login(client, "owner")
    uploaded = client.post(
        "/api/v1/submissions",
        data={"song_id": owner_song_id, "track": "normal"},
        files={"file": ("owner.zip", archive_bytes("Owner Work"), "application/zip")},
    )
    assert uploaded.status_code == 200, uploaded.text
    set_manual_phase("guess")
    chart_ids = [row["id"] for row in client.get("/api/v1/guess-game/charts").json()]

    assert client.post("/api/v1/auth/logout").status_code == 200
    public_overview = client.get("/api/v1/guess-game/designer-guesses").json()
    assert public_overview["can_guess"] is False
    assert public_overview["candidates"] == []

    login_admin(client)
    admin_candidates = client.get("/api/v1/admin/guess-game/author-candidates")
    assert admin_candidates.status_code == 200, admin_candidates.text
    candidates_by_code = {row["user"]["user_code"]: row for row in admin_candidates.json()}
    assert set(candidates_by_code) == {"admin", "owner", "guesser"}
    assert all("selected" in row for row in candidates_by_code.values())
    configured = client.put(
        "/api/v1/admin/guess-game/author-candidates",
        json={"rows": [{"user_id": owner_user_id, "display_id": "P01"}]},
    )
    assert configured.status_code == 200, configured.text

    login(client, "guesser")
    overview = client.get("/api/v1/guess-game/designer-guesses")
    assert overview.status_code == 200, overview.text
    assert overview.json()["can_guess"] is True
    display_ids = {item["display_id"] for item in overview.json()["candidates"]}
    assert display_ids == {"P01"}
    assert {item["chart_id"] for item in overview.json()["states"]} == set(chart_ids)
    assert {item["guessed_user_id"] for item in overview.json()["states"]} == {None}
    owner_id = next(item["user_id"] for item in overview.json()["candidates"] if item["display_id"] == "P01")
    saved = client.put(f"/api/v1/guess-game/charts/{chart_ids[0]}/designer-guess", json={"guessed_user_id": owner_id})
    assert saved.status_code == 200
    grouped = client.get("/api/v1/guess-game/designer-guesses").json()
    assert {item["guessed_user_id"] for item in grouped["states"] if item["chart_id"] in chart_ids} == {owner_id}
    sibling_state = client.get(f"/api/v1/guess-game/charts/{chart_ids[1]}/author-guess").json()
    assert sibling_state["my_guess_user_id"] == owner_id
    assert client.delete(f"/api/v1/guess-game/charts/{chart_ids[0]}/designer-guess").status_code == 200
    cleared = client.get("/api/v1/guess-game/designer-guesses").json()
    assert {item["guessed_user_id"] for item in cleared["states"] if item["chart_id"] in chart_ids} == {None}
    assert client.put(f"/api/v1/guess-game/charts/{chart_ids[0]}/author-guess", json={"guessed_user_id": owner_id}).status_code == 200

    login_admin(client)
    stats = client.get("/api/v1/admin/guess-game/stats?scope=all")
    assert stats.status_code == 200, stats.text
    assert stats.json()["overview"]["counted_guesses"] == 1
    assert stats.json()["overview"]["correct_guesses"] == 1
    owner_stats = next(row for row in stats.json()["author_stats"] if row["user"]["user_code"] == "owner")
    assert owner_stats["received_guesses"] == 1
    assert owner_stats["received_correct"] == 1
    assert owner_stats["being_guessed_probability"] == 100.0

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
