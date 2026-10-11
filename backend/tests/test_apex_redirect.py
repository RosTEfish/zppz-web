import os

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["ADMIN_SEED_PASSWORD"] = "change-me-please"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db.bootstrap import seed_defaults  # noqa: E402
from app.db.session import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402


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


def test_apex_host_redirects_to_www(client: TestClient):
    response = client.get(
        "/guess?tab=1",
        headers={"Host": "przppz.club"},
        follow_redirects=False,
    )
    assert response.status_code == 301
    assert response.headers["location"] == "https://www.przppz.club/guess?tab=1"


def test_www_host_is_not_redirected(client: TestClient):
    response = client.get("/health", headers={"Host": "www.przppz.club"}, follow_redirects=False)
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_localhost_health_is_not_redirected(client: TestClient):
    response = client.get("/health", headers={"Host": "127.0.0.1:8000"}, follow_redirects=False)
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
