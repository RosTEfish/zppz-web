import os
from collections import Counter
import json

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["ADMIN_SEED_PASSWORD"] = "change-me-please"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.db.bootstrap import seed_defaults, sync_permissions_file  # noqa: E402
from app.db.session import Base, SessionLocal, engine  # noqa: E402
from app.manage import set_owner  # noqa: E402
from app.main import app  # noqa: E402
from app.models import DrawAssignment, Event, Role, Song, User  # noqa: E402
from app.modules.events.service import get_current_event  # noqa: E402


@pytest.fixture(autouse=True)
def reset_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed_defaults(db)
        event = db.scalar(select(Event).where(Event.is_current.is_(True)))
        event.settings.participant_song_limit = 0
        event.settings.audience_song_limit = 0
        db.commit()


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
    password = "change-me-please" if user_code == "admin" else "secret123"
    response = client.post("/api/v1/auth/login", json={"user_code": user_code, "password": password})
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
        return len(db.scalars(select(DrawAssignment).where(DrawAssignment.event_id == event.id, DrawAssignment.assigned_to_id == user.id, DrawAssignment.status == "active")).all())


def set_manual_draw() -> None:
    with SessionLocal() as db:
        event = db.scalar(select(Event).where(Event.is_current.is_(True)))
        event.settings.phase_mode = "manual"
        event.settings.manual_phase = "submission_1"
        db.commit()


def test_register_login_and_me(client: TestClient):
    register_user(client, "player1")

    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["user"]["identity"] == "participant"
    bootstrap = client.get("/api/v1/bootstrap")
    assert bootstrap.status_code == 200
    assert bootstrap.json()["event"]["is_current"] is True
    assert bootstrap.json()["user"]["user_code"] == "player1"


def test_user_can_update_display_name_and_identity_during_registration(client: TestClient):
    register_user(client, "profile-player")

    response = client.put(
        "/api/v1/auth/me",
        json={"display_name": "  新显示名  ", "identity": "audience"},
    )

    assert response.status_code == 200, response.text
    user = response.json()["user"]
    assert user["display_name"] == "新显示名"
    assert user["identity"] == "audience"
    assert "audience" in user["roles"]
    assert "participant" not in user["roles"]


@pytest.mark.parametrize(
    "payload",
    [
        {"display_name": "   ", "identity": "participant"},
        {"display_name": "x" * 101, "identity": "participant"},
        {"display_name": "测试用户", "identity": "staff"},
    ],
)
def test_profile_update_validates_name_and_identity(client: TestClient, payload: dict):
    register_user(client, "invalid-profile")

    response = client.put("/api/v1/auth/me", json=payload)

    assert response.status_code == 422


def test_identity_change_is_locked_after_registration_but_name_change_remains_available(client: TestClient):
    register_user(client, "phase-locked")
    set_manual_draw()

    blocked = client.put(
        "/api/v1/auth/me",
        json={"display_name": "新名称", "identity": "audience"},
    )
    assert blocked.status_code == 409
    assert blocked.json()["detail"] == "仅报名阶段可以修改参赛身份"

    renamed = client.put(
        "/api/v1/auth/me",
        json={"display_name": "  仍可改名  ", "identity": "participant"},
    )
    assert renamed.status_code == 200
    assert renamed.json()["user"]["display_name"] == "仍可改名"


def test_profile_identity_change_preserves_privileged_roles(client: TestClient):
    login_user(client, "admin")

    response = client.put(
        "/api/v1/auth/me",
        json={"display_name": "赛事管理员", "identity": "audience"},
    )

    assert response.status_code == 200, response.text
    roles = set(response.json()["user"]["roles"])
    assert {"admin", "pool_editor", "audience"}.issubset(roles)
    assert "participant" not in roles


def test_admin_identity_update_keeps_identity_roles_in_sync(client: TestClient):
    register_user(client, "managed-user")
    login_user(client, "admin")
    users = client.get("/api/v1/admin/users").json()
    managed = next(user for user in users if user["user_code"] == "managed-user")

    response = client.put(
        f"/api/v1/admin/users/{managed['id']}",
        json={
            "identity": "audience",
            "roles": managed["roles"],
            "display_name": managed["display_name"],
            "is_active": True,
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["identity"] == "audience"
    assert "audience" in response.json()["roles"]
    assert "participant" not in response.json()["roles"]


def test_password_change_keeps_current_session_and_revokes_other_sessions(client: TestClient):
    register_user(client, "multi-session")

    with TestClient(app) as other_client:
        second_login = other_client.post(
            "/api/v1/auth/login",
            json={"user_code": "multi-session", "password": "secret123"},
        )
        assert second_login.status_code == 200

        wrong_password = client.post(
            "/api/v1/auth/change-password",
            json={"old_password": "wrong-password", "new_password": "new-secret-456"},
        )
        assert wrong_password.status_code == 400
        assert wrong_password.json()["detail"] == "旧密码不正确"
        too_short = client.post(
            "/api/v1/auth/change-password",
            json={"old_password": "secret123", "new_password": "short"},
        )
        assert too_short.status_code == 422

        changed = client.post(
            "/api/v1/auth/change-password",
            json={"old_password": "secret123", "new_password": "new-secret-456"},
        )
        assert changed.status_code == 200, changed.text
        assert client.get("/api/v1/auth/me").status_code == 200
        assert other_client.get("/api/v1/auth/me").status_code == 401

        old_login = other_client.post(
            "/api/v1/auth/login",
            json={"user_code": "multi-session", "password": "secret123"},
        )
        assert old_login.status_code == 401
        new_login = other_client.post(
            "/api/v1/auth/login",
            json={"user_code": "multi-session", "password": "new-secret-456"},
        )
        assert new_login.status_code == 200


def test_song_pool_requires_auth(client: TestClient):
    response = client.get("/api/v1/song-pool/me")
    assert response.status_code == 401


def test_rule_can_be_viewed_inline(client: TestClient):
    response = client.get("/api/v1/assets/rule/view")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["cache-control"] == "no-cache"
    assert "attachment" not in response.headers.get("content-disposition", "")
    assert response.content.startswith(b"%PDF")

    banlist = client.get("/api/v1/assets/banlist/download")
    assert banlist.status_code == 200
    assert "attachment" in banlist.headers.get("content-disposition", "")
    assert banlist.content.startswith(b"PK")


def test_owner_cli_and_role_management_keeps_an_active_admin(client: TestClient):
    register_user(client, "deputy")
    register_user(client, "member")
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

    assert admin["is_owner"] is False
    blocked = client.put(f"/api/v1/admin/users/{admin['id']}", json=admin_payload)
    assert blocked.status_code == 403
    blocked_status = client.put(
        f"/api/v1/admin/users/{admin['id']}",
        json={
            **admin_payload,
            "roles": admin["roles"],
            "is_active": False,
        },
    )
    assert blocked_status.status_code == 403

    promoted = client.put(
        f"/api/v1/admin/users/{deputy['id']}",
        json={
            "identity": deputy["identity"],
            "roles": [*deputy["roles"], "admin"],
            "display_name": deputy["display_name"],
            "is_active": True,
        },
    )
    assert promoted.status_code == 403, promoted.text

    with SessionLocal() as db:
        first = set_owner(db, "admin")
        second = set_owner(db, "deputy")
        assert first["user_code"] == "admin"
        assert second["user_code"] == "deputy"
        admin_db = db.scalar(select(User).where(User.user_code == "admin"))
        deputy_db = db.scalar(select(User).where(User.user_code == "deputy"))
        assert admin_db is not None and admin_db.has_role("admin") and not admin_db.has_role("owner")
        assert deputy_db is not None and deputy_db.has_role("owner")
        assert db.scalar(select(Role.name).where(Role.name == "owner")) == "owner"
        assert len(db.scalars(select(User).join(User.roles).where(Role.name == "owner")).all()) == 1

    login_user(client, "deputy")
    users = client.get("/api/v1/admin/users").json()
    owner = next(user for user in users if user["user_code"] == "deputy")
    member = next(user for user in users if user["user_code"] == "member")
    assert owner["is_owner"] is True
    assert owner["is_admin"] is True
    assert client.get("/api/v1/admin/stats").status_code == 200
    assert client.get("/api/v1/admin/song-pool").status_code == 200

    promoted = client.put(
        f"/api/v1/admin/users/{member['id']}",
        json={
            "identity": member["identity"],
            "roles": [*member["roles"], "admin"],
            "display_name": member["display_name"],
            "is_active": True,
        },
    )
    assert promoted.status_code == 200, promoted.text
    assert promoted.json()["is_admin"] is True

    demoted = client.put(
        f"/api/v1/admin/users/{member['id']}",
        json={
            "identity": member["identity"],
            "roles": member["roles"],
            "display_name": member["display_name"],
            "is_active": True,
        },
    )
    assert demoted.status_code == 200, demoted.text
    assert demoted.json()["is_admin"] is False

    owner_role_change = client.put(
        f"/api/v1/admin/users/{owner['id']}",
        json={
            "identity": owner["identity"],
            "roles": [role for role in owner["roles"] if role != "owner"],
            "display_name": owner["display_name"],
            "is_active": True,
        },
    )
    assert owner_role_change.status_code == 403
    owner_status_change = client.put(
        f"/api/v1/admin/users/{owner['id']}",
        json={
            "identity": owner["identity"],
            "roles": owner["roles"],
            "display_name": owner["display_name"],
            "is_active": False,
        },
    )
    assert owner_status_change.status_code == 403


def test_set_owner_is_idempotent_and_rejects_missing_or_inactive_users(client: TestClient):
    register_user(client, "inactive-owner-target")
    with SessionLocal() as db:
        first = set_owner(db, "admin")
        second = set_owner(db, "admin")
        assert first["changed"] is True
        assert second["changed"] is False

        target = db.scalar(select(User).where(User.user_code == "inactive-owner-target"))
        assert target is not None
        target.is_active = False
        db.commit()

        with pytest.raises(ValueError, match="user not found"):
            set_owner(db, "missing-owner-target")
        with pytest.raises(ValueError, match="user is inactive"):
            set_owner(db, "inactive-owner-target")

        owner_codes = set(
            db.scalars(select(User.user_code).join(User.roles).where(Role.name == "owner")).all()
        )
        assert owner_codes == {"admin"}


def test_permissions_file_cannot_grant_or_revoke_owner(client: TestClient):
    register_user(client, "owner-target")
    register_user(client, "plain-target")
    settings = get_settings()
    permissions_path = settings.data_dir / "permissions.json"
    original_permissions = permissions_path.read_bytes() if permissions_path.exists() else None
    try:
        with SessionLocal() as db:
            set_owner(db, "owner-target")
            permissions_path.write_text(
                json.dumps(
                    {
                        "users": [
                            {"user_code": "owner-target", "roles": ["participant"]},
                            {"user_code": "plain-target", "roles": ["owner"]},
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            roles = {role.name: role for role in db.scalars(select(Role)).all()}
            sync_permissions_file(db, roles)
            owner = db.scalar(select(User).where(User.user_code == "owner-target"))
            plain = db.scalar(select(User).where(User.user_code == "plain-target"))
            assert owner is not None and owner.has_role("owner")
            assert plain is not None and not plain.has_role("owner")
    finally:
        if original_permissions is None:
            permissions_path.unlink(missing_ok=True)
        else:
            permissions_path.write_bytes(original_permissions)


def test_self_draw_requires_auth_and_participant(client: TestClient):
    set_manual_draw()
    response = client.post("/api/v1/draw/me")
    assert response.status_code == 401

    register_user(client, "viewer1", "audience")
    response = client.post("/api/v1/draw/me")
    assert response.status_code == 410


def test_draw_requires_every_active_account_including_admin_to_fill_song_pool(client: TestClient):
    set_manual_draw()
    register_user(client, "player1")
    register_user(client, "viewer1", "audience")
    with SessionLocal() as db:
        event = get_current_event(db)
        event.settings.participant_song_limit = 2
        event.settings.audience_song_limit = 1
        db.commit()
    add_song_for("admin", "admin-one")
    add_song_for("player1", "player-one")
    add_song_for("player1", "player-two")

    login_user(client, "admin")
    blocked = client.post("/api/v1/admin/draw")
    assert blocked.status_code == 409
    assert "admin（1/2）" in blocked.json()["detail"]
    assert "viewer1（0/1）" in blocked.json()["detail"]

    add_song_for("admin", "admin-two")
    add_song_for("viewer1", "viewer-one")
    allowed = client.post("/api/v1/admin/draw")
    assert allowed.status_code == 200, allowed.text


def test_opening_submissions_requires_every_active_account_to_fill_song_pool(client: TestClient):
    register_user(client, "player1")
    register_user(client, "viewer1", "audience")
    response = client.post(
        "/api/v1/auth/login",
        json={"user_code": "admin", "password": "change-me-please"},
    )
    assert response.status_code == 200, response.text

    with SessionLocal() as db:
        current = db.scalar(select(Event).where(Event.is_current.is_(True)))
        current.settings.phase_mode = "manual"
        current.settings.manual_phase = "submission_1"
        db.commit()

    event = client.get("/api/v1/events/current").json()
    payload = {
        "name": event["name"],
        **event["settings"],
        "participant_song_limit": 1,
        "audience_song_limit": 1,
    }
    payload.pop("phase_mode")
    payload.pop("manual_phase")
    blocked = client.put("/api/v1/admin/events/current", json=payload)

    assert blocked.status_code == 409
    detail = blocked.json()["detail"]
    assert "admin" in detail
    assert "player1" in detail
    assert "viewer1" in detail


def test_participant_self_draw_creates_assignment(client: TestClient):
    set_manual_draw()
    register_user(client, "player1")
    register_user(client, "player2")
    add_song_for("player2", "other-song")
    add_song_for("player2", "other-song-2")
    add_song_for("player2", "other-song-3")
    add_song_for("admin", "admin-song")

    login_user(client, "admin")
    response = client.post("/api/v1/admin/draw")

    assert response.status_code == 200, response.text
    rows = response.json()
    assert {row["assigned_to"]["user_code"] for row in rows} == {"admin", "player1", "player2"}
    assert len({row["song"]["id"] for row in rows}) == 3


def test_global_redraw_includes_admin_participants(client: TestClient):
    set_manual_draw()
    register_user(client, "player1")
    add_song_for("admin", "admin-song")
    add_song_for("admin", "admin-song-2")
    add_song_for("player1", "player-song")
    add_song_for("player1", "player-song-2")
    response = client.post("/api/v1/auth/login", json={"user_code": "admin", "password": "change-me-please"})
    assert response.status_code == 200, response.text

    first = client.post("/api/v1/admin/draw")
    second = client.post("/api/v1/admin/draw")

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert {row["assigned_to"]["user_code"] for row in first.json()} == {"admin", "player1"}
    assert {row["assigned_to"]["user_code"] for row in second.json()} == {"admin", "player1"}
    with SessionLocal() as db:
        event = get_current_event(db)
        assert len(list(db.scalars(select(DrawAssignment).where(DrawAssignment.event_id == event.id)).all())) == 4


def test_global_draw_prefers_a_b_c_coverage_per_participant(client: TestClient):
    set_manual_draw()
    register_user(client, "player1")
    register_user(client, "player2")
    with SessionLocal() as db:
        event = get_current_event(db)
        event.settings.draw_songs_per_participant = 3
        users = [
            db.scalar(select(User).where(User.user_code == code))
            for code in ("admin", "player1", "player2")
        ]
        assert all(users)
        for user in users:
            for category in ("A", "B", "C"):
                db.add(
                    Song(
                        event_id=event.id,
                        submitted_by_id=user.id,
                        song_name=f"{user.user_code}-{category}",
                        artist="artist",
                        song_type=category,
                        remark="",
                    )
                )
        db.commit()

    login_user(client, "admin")
    response = client.post("/api/v1/admin/draw")
    assert response.status_code == 200, response.text

    with SessionLocal() as db:
        event = get_current_event(db)
        rows = list(
            db.scalars(
                select(DrawAssignment)
                .where(DrawAssignment.event_id == event.id, DrawAssignment.status == "active")
            ).all()
        )
        categories_by_user = {}
        for row in rows:
            song = db.get(Song, row.song_id)
            categories_by_user.setdefault(row.assigned_to_id, set()).add(song.song_type)

    assert categories_by_user
    assert all(categories == {"A", "B", "C"} for categories in categories_by_user.values())


def test_self_redraw_replaces_existing_assignment(client: TestClient):
    set_manual_draw()
    register_user(client, "player1")
    register_user(client, "player2")
    register_user(client, "player3")
    for user_code in ("player1", "player2", "player3"):
        add_song_for(user_code, f"{user_code}-song-a")
        add_song_for(user_code, f"{user_code}-song-b")

    login_user(client, "admin")
    first = client.post("/api/v1/admin/draw")
    second = client.post("/api/v1/admin/draw")

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert len(second.json()) == 4
    assert assignment_count_for("player1") == 1


def test_self_draws_do_not_duplicate_songs_between_participants(client: TestClient):
    set_manual_draw()
    register_user(client, "player1")
    register_user(client, "player2")
    add_song_for("player1", "player1-song")
    add_song_for("player1", "player1-song-2")
    add_song_for("player2", "player2-song")
    add_song_for("player2", "player2-song-2")
    add_song_for("admin", "admin-song")
    add_song_for("admin", "admin-song-2")

    login_user(client, "admin")
    first = client.post("/api/v1/admin/draw")

    assert first.status_code == 200, first.text
    song_ids = [row["song"]["id"] for row in first.json()]
    assert len(song_ids) == len(set(song_ids))


def test_self_draw_prefers_non_self_song(client: TestClient):
    set_manual_draw()
    register_user(client, "player1")
    register_user(client, "player2")
    add_song_for("player1", "self-song")
    add_song_for("player1", "self-song-2")
    add_song_for("player2", "other-song")
    add_song_for("player2", "other-song-2")
    add_song_for("admin", "admin-song")
    add_song_for("admin", "admin-song-2")

    login_user(client, "admin")
    response = client.post("/api/v1/admin/draw")

    assert response.status_code == 200, response.text
    player_row = next(row for row in response.json() if row["assigned_to"]["user_code"] == "player1")
    assert not player_row["song"]["song_name"].startswith("self-song")


def test_self_draw_empty_or_exhausted_pool_returns_error(client: TestClient):
    set_manual_draw()
    register_user(client, "player1")
    login_user(client, "player1")
    empty = client.get("/api/v1/draw/results")
    assert empty.status_code == 400
    assert empty.json()["detail"] == "曲池为空"
    assert assignment_count_for("player1") == 0


def test_ten_users_can_refresh_repeatedly_without_duplicate_or_extra_assignments(client: TestClient):
    set_manual_draw()
    user_codes = [f"player{i}" for i in range(10)]
    for user_code in user_codes:
        register_user(client, user_code)
        add_song_for(user_code, f"{user_code}-song-a")
        add_song_for(user_code, f"{user_code}-song-b")
    add_song_for("admin", "admin-song-a")
    add_song_for("admin", "admin-song-b")

    set_manual_draw()
    for user_code in user_codes:
        login_user(client, user_code)
        response = client.get("/api/v1/draw/results")
        assert response.status_code == 200, response.text
        assert len(response.json()) == 1
    login_user(client, user_codes[0])
    repeated = client.get("/api/v1/draw/results")
    assert repeated.status_code == 200

    with SessionLocal() as db:
        assignments = db.scalars(select(DrawAssignment)).all()
        assigned_user_counts = Counter(item.assigned_to_id for item in assignments)
        song_ids = [item.song_id for item in assignments]

    assert len(assignments) == 11
    assert set(assigned_user_counts.values()) == {1}
    assert len(song_ids) == len(set(song_ids))
