import os
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["ADMIN_SEED_PASSWORD"] = "change-me-please"

import anyio  # noqa: E402
import httpx  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import func, select  # noqa: E402

from app.core.client_ip import resolve_client_ip  # noqa: E402
from app.core.config import resolve_secure_cookies  # noqa: E402
from app.db.bootstrap import seed_defaults  # noqa: E402
from app.db.session import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Event, UserSession  # noqa: E402
from app.modules.auth import rate_limit  # noqa: E402


REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def reset_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed_defaults(db)


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def _login(client: TestClient, user_code: str, password: str, headers: dict | None = None):
    return client.post(
        "/api/v1/auth/login",
        json={"user_code": user_code, "password": password},
        headers=headers,
    )


def test_untrusted_peer_ignores_spoofed_forwarded_for(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(rate_limit, "LOGIN_FAILURE_LIMIT", 2)
    monkeypatch.setattr(rate_limit, "LOGIN_IP_FAILURE_LIMIT", 100)

    assert _login(client, "admin", "wrong", {"X-Forwarded-For": "203.0.113.10"}).status_code == 401
    assert _login(client, "admin", "wrong", {"X-Forwarded-For": "203.0.113.11"}).status_code == 401
    blocked = _login(client, "admin", "wrong", {"X-Forwarded-For": "203.0.113.12"})
    assert blocked.status_code == 429

    # A direct retry without the spoofed header shares the same peer bucket.
    assert _login(client, "admin", "wrong").status_code == 429


def test_trusted_proxy_uses_rightmost_untrusted_forwarded_ip(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(rate_limit, "LOGIN_FAILURE_LIMIT", 2)
    monkeypatch.setattr(rate_limit, "LOGIN_IP_FAILURE_LIMIT", 100)

    async def attempt(forwarded: str) -> httpx.Response:
        transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 50000))
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as http:
            return await http.post(
                "/api/v1/auth/login",
                json={"user_code": "admin", "password": "wrong-password"},
                headers={"X-Forwarded-For": forwarded},
            )

    assert anyio.run(attempt, "198.51.100.1, 203.0.113.10").status_code == 401
    assert anyio.run(attempt, "198.51.100.2, 203.0.113.10").status_code == 401
    assert anyio.run(attempt, "198.51.100.3, 203.0.113.10").status_code == 429
    # Leftmost spoof must not become the bucket. A different appended client is a new budget.
    assert anyio.run(attempt, "198.51.100.3, 203.0.113.11").status_code == 401


def test_forwarded_for_parser_does_not_trust_untrusted_peers():
    trusted = "127.0.0.1,::1"
    assert resolve_client_ip("203.0.113.8", "198.51.100.9", "198.51.100.9", trusted) == "203.0.113.8"
    assert resolve_client_ip("127.0.0.1", "1.1.1.1, 203.0.113.10", None, trusted) == "203.0.113.10"
    assert resolve_client_ip("127.0.0.1", None, "203.0.113.10", trusted) == "203.0.113.10"
    assert resolve_client_ip("127.0.0.1", None, None, trusted) == "127.0.0.1"
    assert resolve_client_ip("::1", "203.0.113.10", None, trusted) == "203.0.113.10"


def test_login_ip_budget_blocks_account_spraying(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(rate_limit, "LOGIN_FAILURE_LIMIT", 8)
    monkeypatch.setattr(rate_limit, "LOGIN_IP_FAILURE_LIMIT", 3)

    for name in ("one", "two", "three"):
        rate_limit.record_login_failure("203.0.113.10", name, now=1)

    assert rate_limit.login_retry_after("203.0.113.10", "four", now=1) is not None
    assert rate_limit.login_retry_after("203.0.113.11", "four", now=1) is None
    assert rate_limit.login_retry_after("127.0.0.1", "four", now=1, enforce_ip_budget=False) is None


def test_registration_is_rate_limited_per_ip(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(rate_limit, "REGISTER_LIMIT", 2)

    def register(code: str):
        return client.post(
            "/api/v1/auth/register",
            json={"user_code": code, "qq_id": code, "password": "secret123", "identity": "audience"},
        )

    assert register("reg-one").status_code == 201
    assert register("reg-two").status_code == 201
    blocked = register("reg-three")
    assert blocked.status_code == 429
    assert blocked.json()["detail"] == "尝试次数过多，请稍后再试"
    assert int(blocked.headers["Retry-After"]) >= 1


def test_registration_budget_does_not_lock_the_proxy_address(monkeypatch: pytest.MonkeyPatch):
    """Loopback-only deployments must not share one registration bucket."""
    monkeypatch.setattr(rate_limit, "REGISTER_LIMIT", 1)

    async def register(code: str) -> httpx.Response:
        transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 50000))
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as http:
            return await http.post(
                "/api/v1/auth/register",
                json={"user_code": code, "qq_id": code, "password": "secret123", "identity": "audience"},
            )

    assert anyio.run(register, "proxy-reg-one").status_code == 201
    assert anyio.run(register, "proxy-reg-two").status_code == 201


def test_password_change_failures_are_rate_limited(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(rate_limit, "PASSWORD_FAILURE_LIMIT", 2)
    assert _login(client, "admin", "change-me-please").status_code == 200

    first = client.post(
        "/api/v1/auth/change-password",
        json={"old_password": "wrong-password", "new_password": "new-secret-456"},
    )
    second = client.post(
        "/api/v1/auth/change-password",
        json={"old_password": "wrong-password", "new_password": "new-secret-456"},
    )
    blocked = client.post(
        "/api/v1/auth/change-password",
        json={"old_password": "wrong-password", "new_password": "new-secret-456"},
    )
    assert first.status_code == 400
    assert second.status_code == 400
    assert blocked.status_code == 429
    assert blocked.json()["detail"] == "尝试次数过多，请稍后再试"


def test_logout_revokes_server_session(client: TestClient):
    login = _login(client, "admin", "change-me-please")
    assert login.status_code == 200
    token = client.cookies.get("zppz_session")
    assert token

    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(UserSession)) == 1

    assert client.post("/api/v1/auth/logout").status_code == 200
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(UserSession)) == 0

    client.cookies.set("zppz_session", token)
    assert client.get("/api/v1/auth/me").status_code == 401
    replay = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert replay.status_code == 401


def test_secure_cookies_follow_https_unless_explicit(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("SECURE_COOKIES", raising=False)
    monkeypatch.setenv("PUBLIC_BASE_URL", "http://localhost:8000")
    assert resolve_secure_cookies() is False
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://www.przppz.club")
    monkeypatch.delenv("SECURE_COOKIES", raising=False)
    assert resolve_secure_cookies() is True
    monkeypatch.setenv("SECURE_COOKIES", "false")
    assert resolve_secure_cookies() is False
    monkeypatch.setenv("SECURE_COOKIES", "true")
    monkeypatch.setenv("PUBLIC_BASE_URL", "http://localhost:8000")
    assert resolve_secure_cookies() is True


def test_login_cookie_is_secure_for_https_deployments(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("SECURE_COOKIES", raising=False)
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://www.przppz.club")
    response = _login(client, "admin", "change-me-please")
    assert response.status_code == 200
    assert "secure" in response.headers["set-cookie"].lower()


def test_explicit_false_keeps_insecure_cookies_for_local_http(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SECURE_COOKIES", "false")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://www.przppz.club")
    response = _login(client, "admin", "change-me-please")
    assert response.status_code == 200
    assert "secure" not in response.headers["set-cookie"].lower()


def _register(client: TestClient, code: str, identity: str = "participant") -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={"user_code": code, "qq_id": f"qq-{code}", "password": "secret123", "identity": identity},
    )
    assert response.status_code == 201, response.text


def _assert_public_person(payload: dict) -> None:
    assert set(payload) == {"display_name"}
    assert payload["display_name"]


def test_public_song_and_draw_hide_qq_and_roles_but_admin_keeps_them(client: TestClient):
    _register(client, "pool-owner", "audience")
    for name in ("hidden-qq", "hidden-qq-2"):
        created = client.post(
            "/api/v1/song-pool/me",
            json={"song_name": name, "artist": "artist", "remark": "note", "song_type": "A"},
        )
        assert created.status_code == 200, created.text
        _assert_public_person(created.json()["submitter"])

    mine = client.get("/api/v1/song-pool/me")
    assert mine.status_code == 200
    _assert_public_person(mine.json()[0]["submitter"])

    _register(client, "player-one")
    with SessionLocal() as db:
        event = db.scalar(select(Event).where(Event.is_current.is_(True)))
        event.settings.phase_mode = "manual"
        event.settings.manual_phase = "submission_1"
        event.settings.participant_song_limit = 0
        event.settings.audience_song_limit = 0
        db.commit()

    assert _login(client, "admin", "change-me-please").status_code == 200
    admin_songs = client.get("/api/v1/admin/song-pool")
    assert admin_songs.status_code == 200, admin_songs.text
    admin_submitter = admin_songs.json()[0]["submitter"]
    assert admin_submitter["qq_id"] == "qq-pool-owner"
    assert "roles" in admin_submitter

    drawn = client.post("/api/v1/admin/draw")
    assert drawn.status_code == 200, drawn.text
    admin_row = next(row for row in drawn.json() if row["assigned_to"]["user_code"] == "player-one")
    assert admin_row["assigned_to"]["qq_id"] == "qq-player-one"
    assert admin_row["song"]["submitter"]["qq_id"] == "qq-pool-owner"

    assert _login(client, "player-one", "secret123").status_code == 200
    public_draw = client.get("/api/v1/draw/results")
    assert public_draw.status_code == 200, public_draw.text
    assert public_draw.json()
    for row in public_draw.json():
        _assert_public_person(row["assigned_to"])
        _assert_public_person(row["song"]["submitter"])

    me = client.get("/api/v1/auth/me")
    assert me.json()["user"]["qq_id"] == "qq-player-one"
    assert "participant" in me.json()["user"]["roles"]


def test_public_comments_hide_qq_and_roles(client: TestClient):
    _register(client, "commenter")
    with SessionLocal() as db:
        from app.models import GuessChart

        event = db.scalar(select(Event).where(Event.is_current.is_(True)))
        event.settings.phase_mode = "manual"
        event.settings.manual_phase = "guess"
        chart = GuessChart(
            event_id=event.id,
            title="visible",
            author="author",
            designer="designer",
            level="13",
            lane="4k",
            guess_group_key="group",
            source_submission_type="j",
            source_level_slot="1",
        )
        db.add(chart)
        db.commit()
        chart_id = chart.id

    posted = client.post(f"/api/v1/guess-game/charts/{chart_id}/comments", json={"content": "hello"})
    assert posted.status_code == 200, posted.text
    _assert_public_person(posted.json()["user"])
    listed = client.get(f"/api/v1/guess-game/charts/{chart_id}/comments")
    assert listed.status_code == 200
    _assert_public_person(listed.json()[0]["user"])


def test_nginx_and_deploy_defaults_cover_production():
    nginx = (REPO_ROOT / "infra/nginx/default.conf").read_text(encoding="utf-8")
    headers = (REPO_ROOT / "infra/nginx/security-headers.conf").read_text(encoding="utf-8")
    assert "include /etc/nginx/security-headers.conf;" in nginx
    assert "Strict-Transport-Security" in headers
    assert "X-Content-Type-Options" in headers and "nosniff" in headers
    assert "Referrer-Policy" in headers
    assert "Content-Security-Policy" in headers
    assert "wasm-unsafe-eval" in headers
    assert "preview.przppz.club" in headers
    assert "'unsafe-inline'" in headers
    deploy = (REPO_ROOT / "scripts/deploy_remote.sh").read_text(encoding="utf-8")
    assert "SECURE_COOKIES=true" in deploy
    assert "--no-proxy-headers" in deploy
    assert "--no-proxy-headers" in (REPO_ROOT / "scripts/run_web_with_worker.sh").read_text(encoding="utf-8")
