from io import BytesIO
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
from app.models import Event, GuessChart, PreviewBundle, Submission, User
from app.modules.guess_game.importer import parse_archive
from app.modules.preview.service import build_preview_bundle, manifest_payload


@pytest.fixture(autouse=True)
def reset_db_and_preview_settings():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed_defaults(db)
    settings = get_settings()
    old = (
        settings.preview_enabled,
        settings.preview_player_url,
        settings.preview_player_origin,
    )
    settings.preview_enabled = True
    settings.preview_player_url = "https://preview.przppz.club/majdata/test/player.html"
    settings.preview_player_origin = "https://preview.przppz.club"
    shutil.rmtree(settings.uploads_dir, ignore_errors=True)
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    yield
    settings.preview_enabled, settings.preview_player_url, settings.preview_player_origin = old


def _archive_bytes() -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        archive.writestr(
            "nested/maidata.txt",
            "&title=Preview\n&artist=Artist\n&lv_4=13\n&lv_5=14\n"
            "&inote_4=(120){1},\n&inote_5=(120){1},",
        )
        archive.writestr("nested/bg.jpg", b"jpeg")
        archive.writestr("nested/track.mp3", (bytes.fromhex("FFFB9064") + bytes(413)) * 2)
        archive.writestr("nested/bg.mp4", b"optional-video")
    return buffer.getvalue()


def _create_ready_preview() -> tuple[int, int]:
    settings = get_settings()
    source_path = settings.uploads_dir / "preview-source.zip"
    source_path.write_bytes(_archive_bytes())
    parsed = parse_archive(source_path)
    with SessionLocal() as db:
        event = db.scalar(select(Event).where(Event.is_current.is_(True)))
        admin = db.scalar(select(User).where(User.user_code == "admin"))
        assert event is not None and admin is not None
        storage_path = str(source_path.relative_to(settings.data_dir)).replace("\\", "/")
        submission = Submission(
            event_id=event.id,
            user_id=admin.id,
            source_song_id=None,
            source_kind="exhibition",
            track="exhibition",
            file_name="preview-source.zip",
            storage_path=storage_path,
            file_size=source_path.stat().st_size,
        )
        db.add(submission)
        db.flush()
        for slot, level in ((4, "13"), (5, "14")):
            db.add(
                GuessChart(
                    event_id=event.id,
                    title="Preview",
                    author="Artist",
                    designer="Designer",
                    level=level,
                    lane="exhibition",
                    guess_group_key="preview||artist",
                    source_submission_type="exhibition",
                    source_submission_id=submission.id,
                    source_level_slot=str(slot),
                    cover_path="",
                    storage_path=storage_path,
                    is_self_selected=False,
                )
            )
        build_preview_bundle(
            db,
            event_id=event.id,
            source_type="submission",
            source_id=submission.id,
            source_storage_path=storage_path,
            parsed=parsed,
        )
        db.commit()
        chart_id = db.scalar(
            select(GuessChart.id).where(GuessChart.source_submission_id == submission.id)
        )
        assert chart_id is not None
        return submission.id, chart_id


def test_preview_builds_versioned_local_assets_and_signed_urls():
    submission_id, _ = _create_ready_preview()
    with SessionLocal() as db:
        bundle = db.scalar(
            select(PreviewBundle).where(PreviewBundle.source_id == submission_id)
        )
        assert bundle is not None and bundle.status == "ready"
        assert bundle.maidata_key and "/preview/submission/" in bundle.maidata_key
        assert bundle.background_key and bundle.background_key.endswith("/bg.jpg")
        assert bundle.video_key and bundle.video_key.endswith("/video.mp4")
        payload = manifest_payload(db, bundle, base_url="http://testserver")
    assert [level["slot"] for level in payload["levels"]] == [4, 5]
    assert payload["assets"]["track_url"].startswith("http://testserver/api/v1/preview-assets/")

    with TestClient(app) as client:
        asset_path = re.sub(r"^http://testserver", "", payload["assets"]["maidata_url"])
        response = client.get(asset_path)
    assert response.status_code == 200
    assert b"&title=Preview" in response.content
    assert response.headers["cache-control"].startswith("private")


def test_guess_manifest_returns_only_the_visible_chart_difficulty():
    _, chart_id = _create_ready_preview()
    with TestClient(app) as client:
        response = client.get(f"/api/v1/guess-game/charts/{chart_id}/preview-manifest")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "ready"
    assert payload["selected_level_slot"] == 4
    assert [(level["slot"], level["difficulty_index"]) for level in payload["levels"]] == [(4, 3)]
