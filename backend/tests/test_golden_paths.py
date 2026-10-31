"""API golden paths against the real app, database, and local object store.

These walks follow the HTTP routes the frontend actually calls. Edge cases stay
in the module tests. Browser rendering and the preview player are out of scope.
"""

import re
import shutil
from datetime import UTC, datetime, timedelta
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.core.config import get_settings
from app.db.bootstrap import seed_defaults
from app.db.session import Base, SessionLocal, engine
from app.main import app
from app.models import GuessChart
from app.modules.submissions.processing import claim_next_job, process_job

PLAYER_PASSWORD = "secret123"
ADMIN_PASSWORD = "change-me-please"
DOWNLOAD_TOKEN = "0123456789abcdef0123456789abcdef"


def _png_cover() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (4, 4), "#2374d8").save(buffer, format="PNG")
    return buffer.getvalue()


PNG_COVER = _png_cover()


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


def chart_zip(title: str) -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        archive.writestr(
            "nested/maidata.txt",
            f"&title={title}\n&artist=Artist\n&lv_4=13\n&inote_4=(120){{1}},\n",
        )
        archive.writestr("nested/bg.png", PNG_COVER)
        archive.writestr("nested/track.mp3", (bytes.fromhex("FFFB9064") + bytes(413)) * 2)
    return buffer.getvalue()


def register(client: TestClient, code: str, identity: str = "participant") -> dict:
    response = client.post(
        "/api/v1/auth/register",
        json={"user_code": code, "qq_id": code, "password": PLAYER_PASSWORD, "identity": identity},
    )
    assert response.status_code == 201, response.text
    return response.json()["user"]


def login(client: TestClient, code: str, password: str = PLAYER_PASSWORD) -> dict:
    response = client.post("/api/v1/auth/login", json={"user_code": code, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["user"]


def login_admin(client: TestClient) -> dict:
    return login(client, "admin", ADMIN_PASSWORD)


def create_song(client: TestClient, song_name: str) -> int:
    response = client.post(
        "/api/v1/song-pool/me",
        json={"song_name": song_name, "artist": "Path Artist", "song_type": "A", "remark": ""},
    )
    assert response.status_code == 200, response.text
    assert response.json()["song_name"] == song_name
    return response.json()["id"]


def tighten_song_limits(client: TestClient) -> None:
    current = client.get("/api/v1/events/current")
    assert current.status_code == 200, current.text
    event = current.json()
    settings = event["settings"]
    saved = client.put(
        "/api/v1/admin/events/current",
        json={
            "name": event["name"],
            "participant_song_limit": 1,
            "audience_song_limit": 0,
            "draw_songs_per_participant": settings["draw_songs_per_participant"],
            "true_love_vote_limit_below_14": settings["true_love_vote_limit_below_14"],
            "true_love_vote_limit_at_least_14": settings["true_love_vote_limit_at_least_14"],
            "funny_vote_limit": settings["funny_vote_limit"],
            "announcement_text": settings["announcement_text"],
        },
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["settings"]["participant_song_limit"] == 1


def set_manual_phase(client: TestClient, phase: str) -> dict:
    now = datetime.now(UTC).replace(microsecond=0)
    phases = [
        {
            "phase": "registration",
            "starts_at": (now - timedelta(days=2)).isoformat(),
            "ends_at": (now - timedelta(days=1)).isoformat(),
        }
    ]
    if phase != "registration":
        phases.append(
            {
                "phase": phase,
                "starts_at": now.isoformat(),
                "ends_at": (now + timedelta(days=1)).isoformat(),
            }
        )
    response = client.put(
        "/api/v1/admin/event/phases",
        json={"phase_mode": "manual", "manual_phase": phase, "phases": phases},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["phase_mode"] == "manual"
    assert body["manual_phase"] == phase
    assert body["active_phase"] == phase
    return body


def run_next_processing_job() -> str:
    with SessionLocal() as db:
        job_id = claim_next_job(db)
    assert job_id is not None, "upload complete did not enqueue a processing job"
    process_job(job_id)
    return job_id


def submit_chart(client: TestClient, *, player_code: str = "charter", title: str = "Golden Path Ballad") -> dict:
    """Song pool, open submission, then the production upload-intent and worker path."""
    register(client, player_code)
    song_id = create_song(client, title)
    listed = client.get("/api/v1/song-pool/me")
    assert listed.status_code == 200, listed.text
    assert [row["id"] for row in listed.json()] == [song_id]

    login_admin(client)
    create_song(client, "Admin Pool Song")
    tighten_song_limits(client)
    set_manual_phase(client, "submission_1")

    login(client, player_code)
    targets = client.get("/api/v1/submissions/targets")
    assert targets.status_code == 200, targets.text
    body = targets.json()
    assert body["is_open"] is True
    own = next(item for item in body["targets"] if item["source_kind"] == "self")
    assert own["song"]["id"] == song_id
    assert own["submission"] is None
    assert len([item for item in body["targets"] if item["source_kind"] == "assigned"]) == 1

    payload = chart_zip(title)
    created = client.post(
        "/api/v1/submissions/upload-intents",
        json={
            "song_id": song_id,
            "track": "normal",
            "file_name": "golden.zip",
            "file_size": len(payload),
            "content_type": "application/zip",
        },
    )
    assert created.status_code == 200, created.text
    intent = created.json()
    uploaded = client.put(intent["upload_url"], content=payload, headers=intent["headers"])
    assert uploaded.status_code == 204, uploaded.text
    started = client.post(f"/api/v1/submissions/upload-intents/{intent['id']}/complete")
    assert started.status_code == 200, started.text
    assert started.json()["status"] == "queued"
    assert started.json()["submission"] is None
    visible = client.get("/api/v1/submissions/processing-jobs")
    assert visible.status_code == 200, visible.text
    assert [job["id"] for job in visible.json()] == [started.json()["id"]]

    run_next_processing_job()
    completed = client.get(f"/api/v1/submissions/upload-intents/{intent['id']}/status")
    assert completed.status_code == 200, completed.text
    assert completed.json()["status"] == "completed", completed.text
    submission = completed.json()["submission"]
    assert submission["file_name"] == "golden.zip"
    assert submission["track"] == "normal"
    idle = client.get("/api/v1/submissions/processing-jobs")
    assert idle.status_code == 200, idle.text
    assert idle.json() == []
    return {"song_id": song_id, "submission": submission, "payload": payload, "title": title, "player_code": player_code}


def test_golden_register_login_logout_session(client: TestClient):
    anonymous = client.get("/api/v1/auth/me")
    assert anonymous.status_code == 401
    assert anonymous.json()["detail"] == "请先登录"

    registered = client.post(
        "/api/v1/auth/register",
        json={"user_code": "golden-player", "qq_id": "golden-player", "password": PLAYER_PASSWORD, "identity": "participant"},
    )
    assert registered.status_code == 201, registered.text
    user = registered.json()["user"]
    assert user["user_code"] == "golden-player"
    assert user["identity"] == "participant"
    assert user["display_name"] == "golden-player"
    assert "participant" in user["roles"]
    assert "httponly" in registered.headers["set-cookie"].lower()
    session_token = client.cookies.get("zppz_session")
    assert session_token

    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200, me.text
    assert me.json()["user"]["id"] == user["id"]
    bootstrap = client.get("/api/v1/bootstrap")
    assert bootstrap.status_code == 200, bootstrap.text
    assert bootstrap.json()["user"]["user_code"] == "golden-player"
    assert bootstrap.json()["event"]["is_current"] is True

    logged_out = client.post("/api/v1/auth/logout")
    assert logged_out.status_code == 200, logged_out.text
    assert logged_out.json()["message"] == "已退出登录"
    client.cookies.clear()
    signed_out = client.get("/api/v1/auth/me")
    assert signed_out.status_code == 401
    assert signed_out.json()["detail"] == "请先登录"
    client.cookies.set("zppz_session", session_token)
    replayed = client.get("/api/v1/auth/me")
    assert replayed.status_code == 401
    assert replayed.json()["detail"] == "登录状态已过期"
    client.cookies.clear()

    rejected = client.post(
        "/api/v1/auth/login",
        json={"user_code": "golden-player", "password": "wrong-password"},
    )
    assert rejected.status_code == 401
    assert rejected.json()["detail"] == "账号或密码不正确"
    assert client.get("/api/v1/auth/me").status_code == 401

    restored = login(client, "golden-player")
    assert restored["user_code"] == "golden-player"
    assert client.get("/api/v1/auth/me").json()["user"]["id"] == user["id"]


def test_golden_submit_list_and_download_chart(client: TestClient):
    submitted = submit_chart(client)
    submission = submitted["submission"]
    payload = submitted["payload"]

    mine = client.get("/api/v1/submissions")
    assert mine.status_code == 200, mine.text
    assert [row["id"] for row in mine.json()] == [submission["id"]]
    targets = client.get("/api/v1/submissions/targets")
    assert targets.status_code == 200, targets.text
    own = next(item for item in targets.json()["targets"] if item["source_kind"] == "self")
    assert own["submission"]["id"] == submission["id"]

    hidden = client.get("/api/v1/guess-game/charts")
    assert hidden.status_code == 200, hidden.text
    assert hidden.json() == []

    metadata = client.get(f"/api/v1/submissions/{submission['id']}/download-metadata")
    assert metadata.status_code == 200, metadata.text
    assert metadata.json()["file_name"] == "golden.zip"
    assert metadata.json()["file_size"] == len(payload)
    downloaded = client.get(metadata.json()["download_url"])
    assert downloaded.status_code == 200, downloaded.text
    assert downloaded.content == payload
    assert downloaded.headers["content-encoding"] == "identity"
    assert downloaded.headers["x-accel-buffering"] == "no"

    blocked = client.get(f"/api/v1/admin/submissions/download-metadata?ids={submission['id']}")
    assert blocked.status_code == 403
    assert blocked.json()["detail"] == "没有权限执行此操作"

    login_admin(client)
    stats = client.get("/api/v1/admin/stats")
    assert stats.status_code == 200, stats.text
    assert stats.json()["songs"] == 2
    assert stats.json()["assignments"] == 2
    assert stats.json()["submissions"] == 1
    assert stats.json()["guess_charts"] == 1
    batch = client.get(f"/api/v1/admin/submissions/download-metadata?ids={submission['id']}")
    assert batch.status_code == 200, batch.text
    assert batch.json()["file_name"] == "submissions.zip"
    assert batch.json()["file_size"] > 0
    archive_response = client.get(f"{batch.json()['download_url']}&download_token={DOWNLOAD_TOKEN}")
    assert archive_response.status_code == 200, archive_response.text
    assert archive_response.headers["content-encoding"] == "identity"
    assert archive_response.headers["x-accel-buffering"] == "no"
    assert int(archive_response.headers["content-length"]) == len(archive_response.content)
    with ZipFile(BytesIO(archive_response.content)) as archive:
        names = archive.namelist()
        assert len(names) == 1
        assert names[0].startswith(f"normal_{submitted['player_code']}_")
        assert archive.read(names[0]) == payload

    register(client, "outsider", "participant")
    assert client.get("/api/v1/auth/me").json()["user"]["identity"] == "guest"
    missing = client.get(f"/api/v1/submissions/{submission['id']}/download-metadata")
    assert missing.status_code == 404
    assert missing.json()["detail"] == "投稿不存在"

    login(client, submitted["player_code"])
    assert [row["id"] for row in client.get("/api/v1/submissions").json()] == [submission["id"]]


def test_golden_love_vote_within_quota(client: TestClient):
    register(client, "voter", "audience")
    submitted = submit_chart(client)
    title = submitted["title"]

    login_admin(client)
    opened = set_manual_phase(client, "guess")
    assert opened["capabilities"]["quality_vote"] is True
    assert opened["capabilities"]["submission"] is False

    login(client, "voter")
    quota = client.get("/api/v1/guess-game/vote-quota")
    assert quota.status_code == 200, quota.text
    assert quota.json() == {
        "below_14": {"used": 0, "limit": 3, "remaining": 3},
        "at_least_14": {"used": 0, "limit": 3, "remaining": 3},
    }
    charts = client.get("/api/v1/guess-game/charts")
    assert charts.status_code == 200, charts.text
    chart = next(row for row in charts.json() if row["title"] == title)
    assert chart["level"] == "13"
    assert chart["love_vote_bucket"] == "below_14"
    assert chart["can_vote"] is True
    assert chart["my_votes"] == []
    assert chart["love_votes"] == 0

    voted = client.post("/api/v1/guess-game/vote", json={"chart_id": chart["id"], "vote_type": "love"})
    assert voted.status_code == 200, voted.text
    assert voted.json()["message"] == "已投票"
    assert voted.json()["my_votes"] == ["love"]
    assert voted.json()["vote_counts"] == {"love": 0, "funny": 0}
    assert voted.json()["love_vote_quota"] == {
        "below_14": {"used": 1, "limit": 3, "remaining": 2},
        "at_least_14": {"used": 0, "limit": 3, "remaining": 3},
    }
    confirmed = client.get("/api/v1/guess-game/vote-quota")
    assert confirmed.json() == voted.json()["love_vote_quota"]
    listed = client.get("/api/v1/guess-game/charts")
    assert listed.status_code == 200, listed.text
    voted_chart = next(row for row in listed.json() if row["id"] == chart["id"])
    assert voted_chart["my_votes"] == ["love"]
    assert voted_chart["love_votes"] == 0

    client.post("/api/v1/auth/logout")
    public = client.get("/api/v1/guess-game/charts")
    assert public.status_code == 200, public.text
    assert next(row for row in public.json() if row["id"] == chart["id"])["my_votes"] == []

    with SessionLocal() as db:
        stored = db.get(GuessChart, chart["id"])
        assert stored is not None
        assert stored.source_submission_id == submitted["submission"]["id"]


def test_golden_admin_phase_status_and_contest_signals(client: TestClient):
    public = client.get("/api/v1/event/phases")
    assert public.status_code == 200, public.text
    assert public.json()["phase_mode"] == "auto"
    assert public.json()["manual_phase"] is None
    assert public.json()["active_phase"] == "registration"
    assert public.json()["phases"] == []
    assert public.json()["capabilities"]["song_pool_edit"] is True
    assert public.json()["capabilities"]["submission"] is False
    assert public.json()["capabilities"]["quality_vote"] is False

    anonymous_metrics = client.get("/api/v1/admin/metrics")
    assert anonymous_metrics.status_code == 401
    assert anonymous_metrics.json()["detail"] == "请先登录"

    register(client, "watcher")
    forbidden = client.get("/api/v1/admin/metrics")
    assert forbidden.status_code == 403
    assert forbidden.json()["detail"] == "没有权限执行此操作"
    assert client.get("/api/v1/admin/stats").status_code == 403

    login_admin(client)
    submission = set_manual_phase(client, "submission_1")
    assert submission["capabilities"]["submission"] is True
    assert submission["capabilities"]["quality_vote"] is False
    visible = client.get("/api/v1/event/phases")
    assert visible.status_code == 200, visible.text
    assert visible.json()["active_phase"] == "submission_1"
    bootstrap = client.get("/api/v1/bootstrap")
    assert bootstrap.status_code == 200, bootstrap.text
    assert bootstrap.json()["phases"]["active_phase"] == "submission_1"
    assert bootstrap.json()["phases"]["capabilities"]["submission"] is True

    metrics = client.get("/api/v1/admin/metrics")
    assert metrics.status_code == 200, metrics.text
    assert metrics.headers["cache-control"] == "no-store"
    body = metrics.text
    assert 'zppz_contest_stage{stage="submission_1"} 1' in body
    assert 'stage="guess"' not in body
    assert 'zppz_submission_jobs{status="queued"} 0' in body
    assert 'zppz_submission_jobs{status="failed"} 0' in body
    assert 'zppz_webhook_deliveries{status="failed"} 0' in body
    assert 'zppz_webhook_endpoints{status="failing"} 0' in body
    assert len(re.findall(r"^zppz_contest_stage\{", body, flags=re.MULTILINE)) == 1

    guess = set_manual_phase(client, "guess")
    assert guess["capabilities"]["quality_vote"] is True
    assert guess["capabilities"]["author_guess"] is True
    assert guess["capabilities"]["submission"] is False
    assert client.get("/api/v1/event/phases").json()["active_phase"] == "guess"
    later = client.get("/api/v1/admin/metrics")
    assert later.status_code == 200, later.text
    assert 'zppz_contest_stage{stage="guess"} 1' in later.text
    assert 'stage="submission_1"' not in later.text

    stats = client.get("/api/v1/admin/stats")
    assert stats.status_code == 200, stats.text
    assert stats.json() == {
        "users": 2,
        "songs": 0,
        "assignments": 0,
        "submissions": 0,
        "guess_charts": 0,
    }
