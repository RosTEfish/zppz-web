import os

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["ADMIN_SEED_PASSWORD"] = "change-me-please"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db.bootstrap import seed_defaults  # noqa: E402
from app.db.session import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.modules.auth import rate_limit  # noqa: E402


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


def _login(client: TestClient, user_code: str, password: str):
    return client.post("/api/v1/auth/login", json={"user_code": user_code, "password": password})


def test_repeated_login_failures_are_limited(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(rate_limit, "LOGIN_FAILURE_LIMIT", 3)

    for _ in range(3):
        failed = _login(client, "admin", "wrong-password")
        assert failed.status_code == 401
        assert failed.json()["detail"] == "账号或密码不正确"

    blocked = _login(client, "admin", "wrong-password")
    assert blocked.status_code == 429
    assert blocked.json()["detail"] == "尝试次数过多，请稍后再试"
    assert int(blocked.headers["Retry-After"]) >= 1

    still_blocked = _login(client, "admin", "change-me-please")
    assert still_blocked.status_code == 429


def test_successful_login_clears_previous_failures(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(rate_limit, "LOGIN_FAILURE_LIMIT", 3)

    assert _login(client, "admin", "wrong-password").status_code == 401
    assert _login(client, "admin", "wrong-password").status_code == 401
    assert _login(client, "admin", "change-me-please").status_code == 200
    assert _login(client, "player-missing", "wrong-password").status_code == 401

    client.post("/api/v1/auth/logout")
    assert _login(client, "admin", "wrong-password").status_code == 401
    assert _login(client, "admin", "wrong-password").status_code == 401
    assert _login(client, "admin", "change-me-please").status_code == 200


def test_login_limit_is_scoped_to_ip_and_account(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(rate_limit, "LOGIN_FAILURE_LIMIT", 3)
    rate_limit.record_login_failure("10.0.0.1", "admin", now=0)
    rate_limit.record_login_failure("10.0.0.1", "admin", now=1)
    rate_limit.record_login_failure("10.0.0.1", "Admin", now=2)

    assert rate_limit.login_retry_after("10.0.0.1", "admin", now=2) == rate_limit.LOGIN_FAILURE_WINDOW_SECONDS - 2
    assert rate_limit.login_retry_after("10.0.0.2", "admin", now=2) is None
    assert rate_limit.login_retry_after("10.0.0.1", "other", now=2) is None

    rate_limit.clear_login_failures("10.0.0.1", " admin ")
    assert rate_limit.login_retry_after("10.0.0.1", "admin", now=2) is None


def test_login_failures_expire_with_the_window():
    for offset in range(rate_limit.LOGIN_FAILURE_LIMIT):
        rate_limit.record_login_failure("10.0.0.1", "admin", now=offset)

    blocked_at = rate_limit.LOGIN_FAILURE_LIMIT - 1
    assert rate_limit.login_retry_after("10.0.0.1", "admin", now=blocked_at) is not None
    expired_at = blocked_at + rate_limit.LOGIN_FAILURE_WINDOW_SECONDS
    assert rate_limit.login_retry_after("10.0.0.1", "admin", now=expired_at) is None
