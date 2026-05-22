import os

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["ADMIN_SEED_PASSWORD"] = "change-me-please"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


client = TestClient(app)


def test_register_login_and_me():
    response = client.post("/api/v1/auth/register", json={"user_code": "player1", "qq_id": "123", "password": "secret123", "identity": "participant"})
    assert response.status_code == 201
    assert response.json()["user"]["user_code"] == "player1"

    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["user"]["identity"] == "participant"


def test_song_pool_requires_auth():
    response = client.get("/api/v1/song-pool/me")
    assert response.status_code in {200, 401}

