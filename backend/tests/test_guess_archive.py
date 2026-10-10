from pathlib import Path
import shutil

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.db.bootstrap import seed_defaults
from app.db.session import Base, SessionLocal, engine
from app.main import app
from app.models import Event, GuessChart, Submission, User
from app.modules.events.service import ROTATE_CONFIRMATION


@pytest.fixture(autouse=True)
def reset_database():
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


def login_admin(client: TestClient) -> None:
    response = client.post("/api/v1/auth/login", json={"user_code": "admin", "password": "change-me-please"})
    assert response.status_code == 200, response.text


def _write_file(relative: str, content: bytes = b"archive-bytes") -> Path:
    path = get_settings().data_dir / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def _seed_current_chart_with_packages(*, designer: str = "谱师甲") -> dict[str, int | str]:
    with SessionLocal() as db:
        event = db.scalar(select(Event).where(Event.is_current.is_(True)))
        assert event
        user = db.scalar(select(User).where(User.user_code == "admin"))
        assert user
        original_rel = f"events/{event.id}/submissions/{user.id}/original.zip"
        public_rel = f"events/{event.id}/submissions/1/public/public.zip"
        _write_file(original_rel, b"original-package")
        _write_file(public_rel, b"public-package")
        cover_name = "archive-cover.png"
        cover_path = get_settings().assets_dir / "guess-covers" / cover_name
        cover_path.write_bytes(
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
            b"\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x01\x01\x01\x00\x18\xdd\x8d\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        submission = Submission(
            event_id=event.id,
            user_id=user.id,
            source_song_id=None,
            source_kind="exhibition",
            track="exhibition",
            file_name="original.zip",
            storage_path=original_rel,
            public_storage_path=public_rel,
            public_file_size=len(b"public-package"),
            public_package_status="ready",
            public_package_message="",
            file_size=len(b"original-package"),
            review_status="approved",
        )
        db.add(submission)
        db.flush()
        chart = GuessChart(
            event_id=event.id,
            title="归档曲",
            author="曲师",
            designer=designer,
            level="13",
            lane="exhibition",
            guess_group_key="archive-song",
            source_submission_type="exhibition",
            source_submission_id=submission.id,
            source_level_slot="4",
            cover_path=f"/api/v1/assets/guess-covers/{cover_name}",
            storage_path="",
            is_self_selected=False,
            plays=3,
        )
        db.add(chart)
        db.commit()
        return {
            "event_id": event.id,
            "event_name": event.name,
            "chart_id": chart.id,
            "submission_id": submission.id,
            "original_rel": original_rel,
            "public_rel": public_rel,
            "cover_name": cover_name,
        }


def test_rotate_archives_event_and_purges_public_packages(client: TestClient):
    seeded = _seed_current_chart_with_packages()
    login_admin(client)

    response = client.post(
        "/api/v1/admin/events/rotate",
        json={
            "name": "这谱谱这 #6",
            "slug": "zppz-6",
            "confirmation": ROTATE_CONFIRMATION,
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["purged_public_packages"] == 1
    assert body["archived_event"]["id"] == seeded["event_id"]
    assert body["archived_event"]["is_current"] is False
    assert body["current_event"]["name"] == "这谱谱这 #6"
    assert body["current_event"]["is_current"] is True

    current = client.get("/api/v1/events/current")
    assert current.status_code == 200
    assert current.json()["slug"] == "zppz-6"

    with SessionLocal() as db:
        submission = db.get(Submission, seeded["submission_id"])
        assert submission is not None
        assert submission.public_storage_path is None
        assert submission.public_package_status == "purged"
        assert submission.storage_path == seeded["original_rel"]
        chart = db.get(GuessChart, seeded["chart_id"])
        assert chart is not None
        assert chart.event_id == seeded["event_id"]

    assert not (get_settings().data_dir / seeded["public_rel"]).exists()
    assert (get_settings().data_dir / seeded["original_rel"]).is_file()


def test_archive_lists_cover_and_original_download(client: TestClient):
    seeded = _seed_current_chart_with_packages(designer="谱师乙")
    login_admin(client)
    rotate = client.post(
        "/api/v1/admin/events/rotate",
        json={"name": "这谱谱这 #6", "slug": "zppz-6", "confirmation": ROTATE_CONFIRMATION},
    )
    assert rotate.status_code == 200, rotate.text

    editions = client.get("/api/v1/guess-archive/editions")
    assert editions.status_code == 200
    assert editions.json() == [
        {
            "id": seeded["event_id"],
            "name": seeded["event_name"],
            "slug": "zppz-current",
            "chart_count": 1,
        }
    ]

    charts = client.get("/api/v1/guess-archive/charts")
    assert charts.status_code == 200
    payload = charts.json()
    assert len(payload) == 1
    assert payload[0]["id"] == seeded["chart_id"]
    assert payload[0]["event_id"] == seeded["event_id"]
    assert payload[0]["designer"] == "谱师乙"
    assert payload[0]["can_download"] is True
    assert payload[0]["cover_path"].startswith(f"/api/v1/guess-archive/charts/{seeded['chart_id']}/cover")

    cover = client.get(payload[0]["cover_path"])
    assert cover.status_code == 200

    download = client.get(f"/api/v1/guess-archive/charts/{seeded['chart_id']}/download")
    assert download.status_code == 200
    assert download.content == b"original-package"

    # Live guess APIs only see the new empty current event.
    live = client.get("/api/v1/guess-game/charts")
    assert live.status_code == 200
    assert live.json() == []

    live_download = client.get(f"/api/v1/guess-game/charts/{seeded['chart_id']}/download")
    assert live_download.status_code == 404

    vote = client.post("/api/v1/guess-game/vote", json={"chart_id": seeded["chart_id"], "vote_type": "love"})
    assert vote.status_code in {403, 404, 409}


def test_rotate_rejects_bad_confirmation_and_duplicate_slug(client: TestClient):
    login_admin(client)
    bad = client.post(
        "/api/v1/admin/events/rotate",
        json={"name": "这谱谱这 #6", "slug": "zppz-6", "confirmation": "wrong"},
    )
    assert bad.status_code == 400

    ok = client.post(
        "/api/v1/admin/events/rotate",
        json={"name": "这谱谱这 #6", "slug": "zppz-6", "confirmation": ROTATE_CONFIRMATION},
    )
    assert ok.status_code == 200, ok.text

    dup = client.post(
        "/api/v1/admin/events/rotate",
        json={"name": "这谱谱这 #7", "slug": "zppz-6", "confirmation": ROTATE_CONFIRMATION},
    )
    assert dup.status_code == 409
