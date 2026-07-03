import os
from collections import Counter

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["ADMIN_SEED_PASSWORD"] = "change-me-please"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.db.bootstrap import seed_defaults  # noqa: E402
from app.db.session import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import DrawAssignment, Song, User  # noqa: E402
from app.modules.events.service import get_current_event  # noqa: E402


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


def register_user(client: TestClient, user_code: str, identity: str = "participant") -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={"user_code": user_code, "qq_id": user_code, "password": "secret123", "identity": identity},
    )
    assert response.status_code == 201, response.text


def login_user(client: TestClient, user_code: str) -> None:
    response = client.post("/api/v1/auth/login", json={"user_code": user_code, "password": "secret123"})
    assert response.status_code == 200, response.text


def add_song_for(submitter_code: str, song_name: str) -> int:
    with SessionLocal() as db:
        event = get_current_event(db)
        submitter = db.scalar(select(User).where(User.user_code == submitter_code))
        assert submitter is not None
        song = Song(event_id=event.id, submitted_by_id=submitter.id, song_name=song_name, artist="artist", song_type="A", remark="")
        db.add(song)
        db.commit()
        return song.id


def assignment_count_for(user_code: str) -> int:
    with SessionLocal() as db:
        event = get_current_event(db)
        user = db.scalar(select(User).where(User.user_code == user_code))
        assert user is not None
        return len(db.scalars(select(DrawAssignment).where(DrawAssignment.event_id == event.id, DrawAssignment.assigned_to_id == user.id)).all())


def test_register_login_and_me(client: TestClient):
    register_user(client, "player1")

    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["user"]["identity"] == "participant"


def test_song_pool_requires_auth(client: TestClient):
    response = client.get("/api/v1/song-pool/me")
    assert response.status_code == 401


def test_rule_can_be_viewed_inline(client: TestClient):
    response = client.get("/api/v1/assets/rule/view")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert "attachment" not in response.headers.get("content-disposition", "")
    assert response.content.startswith(b"%PDF")

    banlist = client.get("/api/v1/assets/banlist/download")
    assert banlist.status_code == 200
    assert "attachment" in banlist.headers.get("content-disposition", "")
    assert banlist.content.startswith(b"PK")


def test_admin_role_management_keeps_an_active_admin(client: TestClient):
    register_user(client, "deputy")
    response = client.post("/api/v1/auth/login", json={"user_code": "admin", "password": "change-me-please"})
    assert response.status_code == 200, response.text

    users = client.get("/api/v1/admin/users").json()
    admin = next(user for user in users if user["user_code"] == "admin")
    deputy = next(user for user in users if user["user_code"] == "deputy")
    admin_payload = {
        "identity": admin["identity"],
        "roles": [role for role in admin["roles"] if role != "admin"],
        "display_name": admin["display_name"],
        "is_active": True,
    }

    blocked = client.put(f"/api/v1/admin/users/{admin['id']}", json=admin_payload)
    assert blocked.status_code == 409
    assert blocked.json()["detail"] == "至少需要保留一名启用中的管理员"

    promoted = client.put(
        f"/api/v1/admin/users/{deputy['id']}",
        json={
            "identity": deputy["identity"],
            "roles": [*deputy["roles"], "admin"],
            "display_name": deputy["display_name"],
            "is_active": True,
        },
    )
    assert promoted.status_code == 200, promoted.text
    assert promoted.json()["is_admin"] is True

    demoted = client.put(f"/api/v1/admin/users/{admin['id']}", json=admin_payload)
    assert demoted.status_code == 200, demoted.text
    assert demoted.json()["is_admin"] is False


def test_self_draw_requires_auth_and_participant(client: TestClient):
    response = client.post("/api/v1/draw/me")
    assert response.status_code == 401

    register_user(client, "viewer1", "audience")
    response = client.post("/api/v1/draw/me")
    assert response.status_code == 403


def test_participant_self_draw_creates_assignment(client: TestClient):
    register_user(client, "player1")
    register_user(client, "player2")
    add_song_for("player2", "other-song")

    login_user(client, "player1")
    response = client.post("/api/v1/draw/me")

    assert response.status_code == 200, response.text
    rows = response.json()
    assert len(rows) == 1
    assert rows[0]["assigned_to"]["user_code"] == "player1"
    assert rows[0]["song"]["song_name"] == "other-song"


def test_self_redraw_replaces_existing_assignment(client: TestClient):
    register_user(client, "player1")
    register_user(client, "player2")
    register_user(client, "player3")
    add_song_for("player2", "song-a")
    add_song_for("player3", "song-b")

    login_user(client, "player1")
    first = client.post("/api/v1/draw/me")
    second = client.post("/api/v1/draw/me")

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert len(second.json()) == 1
    assert assignment_count_for("player1") == 1


def test_self_draws_do_not_duplicate_songs_between_participants(client: TestClient):
    register_user(client, "player1")
    register_user(client, "player2")
    add_song_for("player1", "player1-song")
    add_song_for("player2", "player2-song")

    login_user(client, "player1")
    first = client.post("/api/v1/draw/me")
    login_user(client, "player2")
    second = client.post("/api/v1/draw/me")

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    song_ids = {first.json()[0]["song"]["id"], second.json()[0]["song"]["id"]}
    assert len(song_ids) == 2


def test_self_draw_prefers_non_self_song(client: TestClient):
    register_user(client, "player1")
    register_user(client, "player2")
    add_song_for("player1", "self-song")
    add_song_for("player2", "other-song")

    login_user(client, "player1")
    response = client.post("/api/v1/draw/me")

    assert response.status_code == 200, response.text
    assert response.json()[0]["song"]["song_name"] == "other-song"


def test_self_draw_empty_or_exhausted_pool_returns_error(client: TestClient):
    register_user(client, "player1")
    login_user(client, "player1")
    empty = client.post("/api/v1/draw/me")
    assert empty.status_code == 400
    assert empty.json()["detail"] == "曲池为空"

    register_user(client, "player2")
    register_user(client, "owner1")
    add_song_for("owner1", "only-song")

    login_user(client, "player2")
    occupied = client.post("/api/v1/draw/me")
    assert occupied.status_code == 200, occupied.text

    login_user(client, "player1")
    exhausted = client.post("/api/v1/draw/me")
    assert exhausted.status_code == 400
    assert exhausted.json()["detail"] == "剩余曲库为空，请稍后再试"
    assert assignment_count_for("player1") == 0


def test_ten_users_can_refresh_repeatedly_without_duplicate_or_extra_assignments(client: TestClient):
    user_codes = [f"player{i}" for i in range(10)]
    for user_code in user_codes:
        register_user(client, user_code)
        add_song_for(user_code, f"{user_code}-song-a")
        add_song_for(user_code, f"{user_code}-song-b")

    for _round in range(5):
        for user_code in user_codes:
            login_user(client, user_code)
            response = client.post("/api/v1/draw/me")
            assert response.status_code == 200, response.text
            assert len(response.json()) == 1

    with SessionLocal() as db:
        assignments = db.scalars(select(DrawAssignment)).all()
        assigned_user_counts = Counter(item.assigned_to_id for item in assignments)
        song_ids = [item.song_id for item in assignments]

    assert len(assignments) == 10
    assert set(assigned_user_counts.values()) == {1}
    assert len(song_ids) == len(set(song_ids))
