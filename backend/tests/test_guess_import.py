from io import BytesIO
from pathlib import Path
import re
import shutil
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
import py7zr
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.config import get_settings
from app.db.bootstrap import backfill_guess_chart_metadata, seed_defaults
from app.db.session import Base, SessionLocal, engine
from app.main import app
from app.models import Event, GuessAuthorCandidate, GuessAuthorGuess, GuessChart, GuessComment, GuessVote, ImportIssue, Song, Submission, User
from app.modules.guess_game.importer import ArchiveParseError, parse_archive, write_public_package


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


def archive_bytes(maidata: str, encoding: str = "utf-8", cover: bytes | None = b"cover") -> bytes:
    playable = "\n".join(
        f"&inote_{slot}=(120){{1}},"
        for slot in re.findall(r"(?im)^\s*&lv_([1-7])\s*=", maidata)
        if not re.search(rf"(?im)^\s*&inote_{slot}\s*=", maidata)
    )
    if playable:
        maidata = f"{maidata}\n{playable}"
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        archive.writestr("nested/maidata.txt", maidata.encode(encoding))
        archive.writestr("nested/track.mp3", (bytes.fromhex("FFFB9064") + bytes(413)) * 2)
        if cover is not None:
            archive.writestr("nested/bg.png", cover)
    return buffer.getvalue()


def register(client: TestClient, code: str = "player1") -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={"user_code": code, "qq_id": code, "password": "secret123", "identity": "participant"},
    )
    assert response.status_code == 201, response.text


def login_admin(client: TestClient) -> None:
    response = client.post("/api/v1/auth/login", json={"user_code": "admin", "password": "change-me-please"})
    assert response.status_code == 200, response.text


def upload(client: TestClient, content: bytes, name: str = "chart.zip"):
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.user_code == "player1"))
        event = db.scalar(select(Event).where(Event.is_current.is_(True)))
        song = db.scalar(select(Song).where(Song.event_id == event.id, Song.submitted_by_id == user.id))
        if not song:
            song = Song(event_id=event.id, submitted_by_id=user.id, song_name="Candidate", artist="Artist", song_type="A")
            db.add(song)
            db.flush()
        event.settings.phase_mode = "manual"
        event.settings.manual_phase = "submission_1"
        db.commit()
        song_id = song.id
    return client.post(
        "/api/v1/submissions",
        data={"song_id": str(song_id), "track": "normal"},
        files={"file": (name, content, "application/zip")},
    )


def test_parser_supports_nested_files_multiple_levels_and_fallback_encodings(tmp_path: Path):
    cases = [
        ("&title=中文标题\n&artist=作者\n&lv_4=【13+】\n&lv_5=14", "gbk", "中文标题"),
        ("&title=テスト\n&artist=作家\n&lv_3=[12]", "shift_jis", "テスト"),
    ]
    for index, (maidata, encoding, expected_title) in enumerate(cases):
        path = tmp_path / f"case-{index}.zip"
        path.write_bytes(archive_bytes(maidata, encoding))
        parsed = parse_archive(path)
        assert parsed.title == expected_title
        assert parsed.levels[0].level in {"13+", "12"}
        assert parsed.cover_bytes == b"cover"


def test_parser_resolves_global_and_per_level_designers(tmp_path: Path):
    path = tmp_path / "designers.zip"
    path.write_bytes(
        archive_bytes(
            "&title=Designer Test\n"
            "&artist=Artist\n"
            "&DeS=Global Designer\n"
            "&des4=Specific Designer\n"
            "&des5=\n"
            "&lv_4=13\n"
            "&lv_5=14\n"
            "&lv_6=14+"
        )
    )

    parsed = parse_archive(path)
    designers = {level.slot: level.designer for level in parsed.levels}

    assert designers == {"4": "Specific Designer", "5": "Global Designer", "6": "Global Designer"}

    missing = tmp_path / "missing-designer.zip"
    missing.write_bytes(archive_bytes("&title=No Designer\n&artist=Artist\n&lv_4=13"))
    assert parse_archive(missing).levels[0].designer == ""


def test_parser_rejects_missing_required_fields_and_cover(tmp_path: Path):
    missing_title = tmp_path / "invalid.zip"
    missing_title.write_bytes(archive_bytes("&artist=artist\n&lv_4=13"))
    with pytest.raises(ArchiveParseError, match="title"):
        parse_archive(missing_title)

    no_cover = tmp_path / "no-cover.zip"
    no_cover.write_bytes(archive_bytes("&title=Song\n&artist=Artist\n&lv_4=13", cover=None))
    with pytest.raises(ArchiveParseError, match="bg"):
        parse_archive(no_cover)


def test_parser_reads_only_required_7z_members(tmp_path: Path):
    path = tmp_path / "chart.7z"
    with py7zr.SevenZipFile(path, "w") as archive:
        archive.writestr("&title=Seven\n&artist=Artist\n&lv_4=13+\n&inote_4=(120){1},", "nested/maidata.txt")
        archive.writestr(b"cover", "nested/bg.jpg")
        archive.writestr((bytes.fromhex("FFFB9064") + bytes(413)) * 2, "nested/track.mp3")
    parsed = parse_archive(path)
    assert parsed.title == "Seven"
    assert [(level.slot, level.level) for level in parsed.levels] == [("4", "13+")]
    assert parsed.cover_suffix == ".jpg"
    assert parsed.cover_bytes == b"cover"


@pytest.mark.parametrize("video_name", ["mv.mp4", "pv.mp4"])
def test_public_package_uses_member_references_and_preserves_selected_files(
    tmp_path: Path,
    video_name: str,
):
    path = tmp_path / "streamed.zip"
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        archive.writestr(
            "nested/maidata.txt",
            "&title=Streamed\n&artist=Artist\n&des=Designer\n&lv_4=13\n&inote_4=(120){1},",
        )
        archive.writestr("nested/track.mp3", (bytes.fromhex("FFFB9064") + bytes(413)) * 2)
        archive.writestr("nested/bg.png", b"cover")
        archive.writestr(f"nested/{video_name}", b"video-payload")

    parsed = parse_archive(path)
    assert parsed.archive_path == path
    assert [(item.output_name, item.member_name) for item in parsed.public_files] == [
        ("maidata.txt", "nested/maidata.txt"),
        ("track.mp3", "nested/track.mp3"),
        ("bg.png", "nested/bg.png"),
        (video_name, f"nested/{video_name}"),
    ]

    relative = write_public_package(1, 1, parsed)
    with ZipFile(get_settings().data_dir / relative) as archive:
        assert archive.read(video_name) == b"video-payload"
        assert b"&des=Designer" in archive.read("maidata.txt")


def test_public_package_reopens_zip_members_with_backslash_names(tmp_path: Path):
    path = tmp_path / "backslash-members.zip"
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        archive.writestr(
            "nested/maidata.txt",
            "&title=Backslash\n&artist=Artist\n&lv_4=13\n&inote_4=(120){1},",
        )
        archive.writestr("nested/track.mp3", (bytes.fromhex("FFFB9064") + bytes(413)) * 2)
        archive.writestr("nested/bg.png", b"cover")
    # Python normalizes names written on Windows. Patch both local and central
    # directory records to exercise archives produced by tools that keep '\\'.
    path.write_bytes(buffer.getvalue().replace(b"nested/", b"nested\\"))

    parsed = parse_archive(path)
    assert [item.member_name for item in parsed.public_files] == [
        "nested\\maidata.txt",
        "nested\\track.mp3",
        "nested\\bg.png",
    ]
    relative = write_public_package(1, 2, parsed)
    with ZipFile(get_settings().data_dir / relative) as archive:
        assert archive.namelist() == ["maidata.txt", "track.mp3", "bg.png"]
        assert archive.read("bg.png") == b"cover"


def test_upload_creates_charts_and_serves_cover(client: TestClient):
    register(client)
    response = upload(client, archive_bytes("&title=Song\n&artist=Artist\n&des=Global\n&des5=Expert\n&lv_4=13+\n&lv_5=14"))
    assert response.status_code == 200, response.text

    with SessionLocal() as db:
        event = db.scalar(select(Event).where(Event.is_current.is_(True)))
        event.settings.phase_mode = "manual"
        event.settings.manual_phase = "guess"
        db.commit()
        imported = list(db.scalars(select(GuessChart)).all())
        assert {(row.source_level_slot, row.level) for row in imported} == {("4", "13+"), ("5", "14")}
        assert {row.source_level_slot: row.designer for row in imported} == {"4": "Global", "5": "Expert"}

    charts = client.get("/api/v1/guess-game/charts")
    assert charts.status_code == 200
    assert {row["level"] for row in charts.json()} == {"13+", "14"}
    assert {row["source_level_slot"]: row["designer"] for row in charts.json()} == {"4": "Global", "5": "Expert"}
    assert {row["source_level_slot"] for row in charts.json()} == {"4", "5"}
    cover_path = charts.json()[0]["cover_path"]
    assert cover_path.startswith("/api/v1/guess-game/charts/")
    assert "/cover?v=" in cover_path
    assert client.get(cover_path).status_code == 200


def test_j_track_upload_and_delete_sync_charts(client: TestClient):
    register(client)
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.user_code == "player1"))
        event = db.scalar(select(Event).where(Event.is_current.is_(True)))
        song = Song(event_id=event.id, submitted_by_id=user.id, song_name="J Candidate", artist="Artist", song_type="A")
        db.add(song)
        event.settings.phase_mode = "manual"
        event.settings.manual_phase = "submission_1"
        db.commit()
        song_id = song.id
    response = client.post("/api/v1/submissions", data={"song_id": song_id, "track": "j"}, files={"file": ("j-track.zip", archive_bytes("&title=J Song\n&artist=Artist\n&lv_6=15"), "application/zip")})
    assert response.status_code == 200, response.text
    with SessionLocal() as db:
        chart = db.scalar(select(GuessChart))
        assert chart is not None
        assert chart.lane == "j"
        assert chart.source_submission_type == "j"

    deleted = client.delete("/api/v1/submissions/j-track")
    assert deleted.status_code == 200, deleted.text
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(GuessChart)) == 0


def test_incremental_replace_preserves_matching_chart_interactions(client: TestClient):
    register(client)
    first = upload(
        client,
        archive_bytes(
            "&title=Old\n&artist=Artist\n&des=Old Designer\n&lv_4=13\n&lv_5=14",
            cover=b"old-cover",
        ),
    )
    assert first.status_code == 200, first.text
    submission_id = first.json()["id"]

    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.user_code == "player1"))
        slot_four = db.scalar(select(GuessChart).where(GuessChart.source_level_slot == "4"))
        assert user and slot_four
        original_chart_id = slot_four.id
        original_cover_file = get_settings().assets_dir / "guess-covers" / Path(slot_four.cover_path).name
        assert original_cover_file.is_file()
        db.add(GuessVote(chart_id=slot_four.id, user_id=user.id, vote_type="love"))
        db.add(GuessComment(chart_id=slot_four.id, user_id=user.id, content="keep"))
        db.add(GuessAuthorGuess(chart_id=slot_four.id, user_id=user.id, guessed_user_id=user.id))
        event = db.scalar(select(Event).where(Event.is_current.is_(True)))
        event.settings.phase_mode = "manual"
        event.settings.manual_phase = "guess"
        db.commit()

    first_public_chart = next(
        chart for chart in client.get("/api/v1/guess-game/charts").json() if chart["id"] == original_chart_id
    )
    first_cover_url = first_public_chart["cover_path"]
    assert client.get(first_cover_url).content == b"old-cover"

    with SessionLocal() as db:
        event = db.scalar(select(Event).where(Event.is_current.is_(True)))
        event.settings.manual_phase = "submission_1"
        db.commit()

    replacement = archive_bytes(
        "&title=Updated\n&artist=Artist\n&des=New Designer\n&des4=Slot Designer\n&lv_4=13+\n&lv_6=15",
        cover=b"new-cover",
    )
    response = client.post(
        f"/api/v1/submissions/{submission_id}/replace",
        files={"file": ("replacement.zip", replacement, "application/zip")},
    )
    assert response.status_code == 200, response.text

    with SessionLocal() as db:
        charts = {chart.source_level_slot: chart for chart in db.scalars(select(GuessChart)).all()}
        assert set(charts) == {"4", "6"}
        assert charts["4"].id == original_chart_id
        assert charts["4"].title == "Updated"
        assert charts["4"].designer == "Slot Designer"
        assert charts["6"].designer == "New Designer"
        assert db.scalar(select(func.count()).select_from(GuessVote).where(GuessVote.chart_id == original_chart_id)) == 1
        assert db.scalar(select(func.count()).select_from(GuessComment).where(GuessComment.chart_id == original_chart_id)) == 1
        assert db.scalar(select(func.count()).select_from(GuessAuthorGuess).where(GuessAuthorGuess.chart_id == original_chart_id)) == 1
        assert len({chart.cover_path for chart in charts.values()}) == 1
        event = db.scalar(select(Event).where(Event.is_current.is_(True)))
        event.settings.manual_phase = "guess"
        db.commit()

    replaced_public_chart = next(
        chart for chart in client.get("/api/v1/guess-game/charts").json() if chart["id"] == original_chart_id
    )
    replaced_cover_url = replaced_public_chart["cover_path"]
    assert replaced_cover_url != first_cover_url
    assert client.get(replaced_cover_url).content == b"new-cover"
    assert not original_cover_file.exists()


def test_invalid_upload_and_replace_leave_no_partial_state(client: TestClient):
    register(client)
    invalid = upload(client, archive_bytes("&artist=Artist\n&lv_4=13"), "invalid.zip")
    assert invalid.status_code == 422
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Submission)) == 0
        assert db.scalar(select(func.count()).select_from(GuessChart)) == 0
    assert not list(get_settings().uploads_dir.rglob("*.zip"))

    first = upload(client, archive_bytes("&title=Stable\n&artist=Artist\n&lv_4=13"))
    assert first.status_code == 200
    submission_id = first.json()["id"]
    with SessionLocal() as db:
        original = db.get(Submission, submission_id)
        original_storage_path = original.storage_path
        chart_id = db.scalar(select(GuessChart.id))

    failed = client.post(
        f"/api/v1/submissions/{submission_id}/replace",
        files={"file": ("broken.zip", archive_bytes("&artist=Artist\n&lv_4=14"), "application/zip")},
    )
    assert failed.status_code == 422
    with SessionLocal() as db:
        current = db.get(Submission, submission_id)
        assert current.storage_path == original_storage_path
        assert db.scalar(select(GuessChart.id)) == chart_id


def test_admin_rebuild_reports_invalid_legacy_file_without_removing_charts(client: TestClient):
    register(client)
    created = upload(client, archive_bytes("&title=Stable\n&artist=Artist\n&lv_4=13"))
    assert created.status_code == 200
    with SessionLocal() as db:
        submission = db.get(Submission, created.json()["id"])
        chart_id = db.scalar(select(GuessChart.id))
        (get_settings().data_dir / submission.storage_path).write_bytes(b"not a zip")

    denied = client.post("/api/v1/admin/guess-game/parse-submissions")
    assert denied.status_code == 403
    login_admin(client)
    rebuilt = client.post("/api/v1/admin/guess-game/parse-submissions")
    assert rebuilt.status_code == 200, rebuilt.text
    assert rebuilt.json()["scanned"] == 1
    assert rebuilt.json()["issues"] == 1
    with SessionLocal() as db:
        assert db.scalar(select(GuessChart.id)) == chart_id
        assert db.scalar(select(func.count()).select_from(ImportIssue)) == 1


def test_startup_backfill_updates_normal_j_and_admin_sources_once(client: TestClient):
    register(client)
    normal = upload(
        client,
        archive_bytes("&title=Normal Source\n&artist=Artist\n&des=Normal Designer\n&lv_4=13"),
        "normal.zip",
    )
    assert normal.status_code == 200, normal.text

    with SessionLocal() as db:
        event = db.scalar(select(Event).where(Event.is_current.is_(True)))
        user = db.scalar(select(User).where(User.user_code == "player1"))
        j_song = Song(event_id=event.id, submitted_by_id=user.id, song_name="J Candidate", artist="Artist", song_type="J")
        db.add(j_song)
        db.commit()
        j_song_id = j_song.id

    j_upload = client.post(
        "/api/v1/submissions",
        data={"song_id": j_song_id, "track": "j"},
        files={"file": ("j.zip", archive_bytes("&title=J Source\n&artist=Artist\n&des5=J Designer\n&lv_5=14"), "application/zip")},
    )
    assert j_upload.status_code == 200, j_upload.text

    login_admin(client)
    admin_upload = client.post(
        "/api/v1/admin/guess-game/charts/import",
        files={"file": ("admin.zip", archive_bytes("&title=Admin Source\n&artist=Artist\n&des=Admin Designer\n&lv_6=15"), "application/zip")},
    )
    assert admin_upload.status_code == 200, admin_upload.text

    with SessionLocal() as db:
        event = db.scalar(select(Event).where(Event.is_current.is_(True)))
        original_ids = {chart.title: chart.id for chart in db.scalars(select(GuessChart)).all()}
        for chart in db.scalars(select(GuessChart)).all():
            chart.designer = ""
        event.settings.guess_chart_metadata_version = 0
        db.commit()

    with SessionLocal() as db:
        backfill_guess_chart_metadata(db)

    with SessionLocal() as db:
        event = db.scalar(select(Event).where(Event.is_current.is_(True)))
        charts = {chart.title: chart for chart in db.scalars(select(GuessChart)).all()}
        assert {title: chart.designer for title, chart in charts.items()} == {
            "Normal Source": "Normal Designer",
            "J Source": "J Designer",
            "Admin Source": "Admin Designer",
        }
        assert {title: chart.id for title, chart in charts.items()} == original_ids
        assert event.settings.guess_chart_metadata_version == 1
        charts["Normal Source"].designer = "Manual Override"
        db.commit()

    with SessionLocal() as db:
        backfill_guess_chart_metadata(db)
        normal_chart = db.scalar(select(GuessChart).where(GuessChart.title == "Normal Source"))
        assert normal_chart.designer == "Manual Override"


def test_startup_backfill_failure_keeps_version_for_retry(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    from app.modules.guess_game import importer

    with SessionLocal() as db:
        event = db.scalar(select(Event).where(Event.is_current.is_(True)))
        event.settings.guess_chart_metadata_version = 0
        db.commit()

    def fail_rebuild(_db, _event_id):
        raise RuntimeError("backfill failed")

    monkeypatch.setattr(importer, "rebuild_event_charts", fail_rebuild)
    with SessionLocal() as db:
        backfill_guess_chart_metadata(db)
        event = db.scalar(select(Event).where(Event.is_current.is_(True)))
        assert event.settings.guess_chart_metadata_version == 0


def test_delete_submission_removes_only_its_charts_and_cover(client: TestClient):
    register(client)
    created = upload(client, archive_bytes("&title=Delete Me\n&artist=Artist\n&lv_4=13"))
    assert created.status_code == 200
    with SessionLocal() as db:
        cover_path = db.scalar(select(GuessChart.cover_path))
    response = client.delete(f"/api/v1/submissions/{created.json()['id']}")
    assert response.status_code == 200
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(GuessChart)) == 0
    assert client.get(cover_path).status_code == 404


def test_public_visibility_neutral_package_and_audience_author_guess(client: TestClient):
    register(client, "player1")
    normal = upload(
        client,
        archive_bytes("&title=Normal\n&artist=Artist\n&des=Visible In Package\n&lv_4=13"),
    )
    assert normal.status_code == 200, normal.text

    with SessionLocal() as db:
        event = db.scalar(select(Event).where(Event.is_current.is_(True)))
        user = db.scalar(select(User).where(User.user_code == "player1"))
        second_song = Song(event_id=event.id, submitted_by_id=user.id, song_name="J", artist="Artist", song_type="J")
        db.add(second_song)
        db.commit()
        second_song_id = second_song.id
    j_track = client.post(
        "/api/v1/submissions",
        data={"song_id": second_song_id, "track": "j"},
        files={"file": ("identity-leaking-name.zip", archive_bytes("&title=J\n&artist=Artist\n&des=J Designer\n&lv_5=14"), "application/zip")},
    )
    assert j_track.status_code == 200, j_track.text

    before_guess = client.get("/api/v1/guess-game/charts").json()
    assert [row["source_submission_type"] for row in before_guess] == ["j"]
    assert client.get("/api/v1/guess-game/availability").json() == {"available": True}
    assert before_guess[0]["designer"] == "J Designer"
    assert "source_submission_id" not in before_guess[0]
    assert "storage_path" not in before_guess[0]

    with SessionLocal() as db:
        event = db.scalar(select(Event).where(Event.is_current.is_(True)))
        player = db.scalar(select(User).where(User.user_code == "player1"))
        event.settings.phase_mode = "manual"
        event.settings.manual_phase = "guess"
        db.add(GuessAuthorCandidate(event_id=event.id, user_id=player.id, display_id="P1"))
        db.commit()
    all_charts = client.get("/api/v1/guess-game/charts").json()
    normal_chart = next(row for row in all_charts if row["source_submission_type"] == "normal")
    assert normal_chart["designer"] == "Visible In Package"

    downloaded = client.get(f"/api/v1/guess-game/charts/{normal_chart['id']}/download")
    assert downloaded.status_code == 200
    assert "identity-leaking-name" not in downloaded.headers["content-disposition"]
    with ZipFile(BytesIO(downloaded.content)) as archive:
        assert set(archive.namelist()) == {"maidata.txt", "track.mp3", "bg.png"}
        assert b"&des=Visible In Package" in archive.read("maidata.txt")

    register(client, "viewer")
    with SessionLocal() as db:
        viewer = db.scalar(select(User).where(User.user_code == "viewer"))
        viewer.identity = "audience"
        db.commit()
        player_id = db.scalar(select(User.id).where(User.user_code == "player1"))
    guessed = client.put(
        f"/api/v1/guess-game/charts/{normal_chart['id']}/author-guess",
        json={"guessed_user_id": player_id},
    )
    assert guessed.status_code == 200, guessed.text
    j_chart = next(row for row in all_charts if row["source_submission_type"] == "j")
    assert client.put(
        f"/api/v1/guess-game/charts/{j_chart['id']}/author-guess",
        json={"guessed_user_id": player_id},
    ).status_code == 403


def test_guess_availability_requires_a_public_chart(client: TestClient):
    with SessionLocal() as db:
        event = db.scalar(select(Event).where(Event.is_current.is_(True)))
        assert event
        db.add(
            GuessChart(
                event_id=event.id,
                title="Normal only",
                author="Artist",
                level="13",
                lane="normal",
                source_submission_type="normal",
            )
        )
        db.commit()

    assert client.get("/api/v1/guess-game/availability").json() == {"available": False}

    with SessionLocal() as db:
        event = db.scalar(select(Event).where(Event.is_current.is_(True)))
        assert event
        db.add(
            GuessChart(
                event_id=event.id,
                title="J public",
                author="Artist",
                level="14",
                lane="j",
                source_submission_type="j",
            )
        )
        db.commit()

    assert client.get("/api/v1/guess-game/availability").json() == {"available": True}


def test_admin_import_is_visible_on_public_guess_page_before_guess_phase(client: TestClient):
    login_admin(client)
    imported = client.post(
        "/api/v1/admin/guess-game/charts/import",
        files={
            "file": (
                "admin-public.zip",
                archive_bytes("&title=Admin Public\n&artist=Artist\n&des=Admin Designer\n&lv_4=13"),
                "application/zip",
            )
        },
    )
    assert imported.status_code == 200, imported.text
    imported_chart = imported.json()["charts"][0]

    availability = client.get("/api/v1/guess-game/availability")
    assert availability.status_code == 200, availability.text
    assert availability.json() == {"available": True}

    public_charts = client.get("/api/v1/guess-game/charts")
    assert public_charts.status_code == 200, public_charts.text
    public_chart = next(row for row in public_charts.json() if row["id"] == imported_chart["id"])
    assert public_chart["title"] == "Admin Public"
    assert public_chart["source_submission_type"] == "admin"


def test_exhibition_allows_multiple_unlinked_submissions(client: TestClient):
    register(client, "exhibitor")
    with SessionLocal() as db:
        event = db.scalar(select(Event).where(Event.is_current.is_(True)))
        event.settings.phase_mode = "manual"
        event.settings.manual_phase = "submission_1"
        db.commit()
    responses = [
        client.post(
            "/api/v1/submissions",
            data={"track": "exhibition"},
            files={"file": (f"outside-{index}.zip", archive_bytes(f"&title=Outside {index}\n&artist=Artist\n&lv_4=8"), "application/zip")},
        )
        for index in range(2)
    ]
    assert [response.status_code for response in responses] == [200, 200]
    assert all(response.json()["source_song"] is None for response in responses)
    public = client.get("/api/v1/guess-game/charts").json()
    assert {row["source_submission_type"] for row in public} == {"exhibition"}
    assert len(public) == 2
