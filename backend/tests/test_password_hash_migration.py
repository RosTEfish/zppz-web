import os

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["ADMIN_SEED_PASSWORD"] = "change-me-please"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.core.security import ensure_roles, hash_password, verify_and_update_password, verify_password  # noqa: E402
from app.db.bootstrap import seed_defaults  # noqa: E402
from app.db.session import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import User  # noqa: E402

# Generated with passlib 1.7.4, the hasher that produced stored passwords.
# v=2: HMAC-SHA256 keyed by the 22-character bcrypt salt, standard Base64, then bcrypt.
# v=1: SHA-256 of the UTF-8 password, standard Base64, then bcrypt.
# The r=12 string is the example in the passlib bcrypt_sha256 docs (password "password").
LEGACY_BCRYPT_2B = "$2b$04$W1vMpZb09cFHMyzA7AYD2OysHeQo2o9sqF5ZIJe8eSZ4AO3ipasfq"
LEGACY_BCRYPT_2A = "$2a$04$FOu/Tpeg7qNde/YcDA1S8ONdjAw0zd4qphLkiM7tAlcLEaSeWsd1y"
PASSLIB_BCRYPT_SHA256_V2 = "$bcrypt-sha256$v=2,t=2b,r=4$EDJ48AaOtkhYDdlHWxtpMO$oADsn4LmtxWoY9BgkZyBeSKUddIdHyu"
PASSLIB_BCRYPT_SHA256_V2_DOCS = "$bcrypt-sha256$v=2,t=2b,r=12$n79VH.0Q2TMWmt3Oqt9uku$Kq4Noyk3094Y2QlB8NdRT8SvGiI4ft2"
PASSLIB_BCRYPT_SHA256_V1 = "$bcrypt-sha256$2b,4$tMyvWlBgnT7fFtCUHwRlIu$1U/czUh/B1YZgfj3TbKkPKczEoHyUn."
PASSWORD = "secret123"


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


def _insert_user(user_code: str, password_hash: str) -> int:
    with SessionLocal() as db:
        roles = ensure_roles(db)
        user = User(
            user_code=user_code,
            qq_id=user_code,
            password_hash=password_hash,
            identity="participant",
            display_name=user_code,
            roles=[roles["participant"]],
        )
        db.add(user)
        db.commit()
        return user.id


def _stored_hash(user_code: str) -> str:
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.user_code == user_code))
        assert user is not None
        return user.password_hash


def test_new_hash_is_argon2id_and_verifies():
    stored = hash_password(PASSWORD)
    assert stored.startswith("$argon2id$")
    assert len(stored) <= 255
    valid, updated = verify_and_update_password(PASSWORD, stored)
    assert valid is True
    assert updated is None
    assert verify_password(PASSWORD, stored) is True


@pytest.mark.parametrize(
    ("stored_hash", "password"),
    [
        (LEGACY_BCRYPT_2B, PASSWORD),
        (LEGACY_BCRYPT_2A, "legacy-plain"),
    ],
)
def test_legacy_plain_bcrypt_verifies_and_upgrades(stored_hash: str, password: str):
    valid, updated = verify_and_update_password(password, stored_hash)
    assert valid is True
    assert updated is not None
    assert updated.startswith("$argon2id$")
    assert verify_password(password, updated) is True


@pytest.mark.parametrize(
    ("stored_hash", "password"),
    [
        (PASSLIB_BCRYPT_SHA256_V2, PASSWORD),
        (PASSLIB_BCRYPT_SHA256_V2_DOCS, "password"),
        (PASSLIB_BCRYPT_SHA256_V1, PASSWORD),
    ],
)
def test_passlib_bcrypt_sha256_verifies_and_upgrades(stored_hash: str, password: str):
    assert verify_password(password, stored_hash) is True
    valid, updated = verify_and_update_password(password, stored_hash)
    assert valid is True
    assert updated is not None
    assert updated.startswith("$argon2id$")
    assert verify_password(password, updated) is True


def test_wrong_password_rejects_argon2_bcrypt_and_bcrypt_sha256():
    stored_hashes = [
        hash_password(PASSWORD),
        LEGACY_BCRYPT_2B,
        LEGACY_BCRYPT_2A,
        PASSLIB_BCRYPT_SHA256_V2,
        PASSLIB_BCRYPT_SHA256_V2_DOCS,
        PASSLIB_BCRYPT_SHA256_V1,
    ]
    for stored_hash in stored_hashes:
        assert verify_password("not-the-password", stored_hash) is False
        valid, updated = verify_and_update_password("not-the-password", stored_hash)
        assert valid is False
        assert updated is None


@pytest.mark.parametrize(
    ("stored_hash", "user_code", "password"),
    [
        (LEGACY_BCRYPT_2B, "legacy-2b", PASSWORD),
        (LEGACY_BCRYPT_2A, "legacy-2a", "legacy-plain"),
        (PASSLIB_BCRYPT_SHA256_V2, "legacy-sha", PASSWORD),
        (PASSLIB_BCRYPT_SHA256_V1, "legacy-v1", PASSWORD),
    ],
)
def test_login_upgrades_legacy_hash_and_rejects_wrong_password(
    client: TestClient, stored_hash: str, user_code: str, password: str
):
    _insert_user(user_code, stored_hash)
    rejected = client.post("/api/v1/auth/login", json={"user_code": user_code, "password": "not-the-password"})
    assert rejected.status_code == 401
    assert _stored_hash(user_code) == stored_hash

    accepted = client.post("/api/v1/auth/login", json={"user_code": user_code, "password": password})
    assert accepted.status_code == 200, accepted.text
    upgraded = _stored_hash(user_code)
    assert upgraded.startswith("$argon2id$")
    assert upgraded != stored_hash

    client.post("/api/v1/auth/logout")
    again = client.post("/api/v1/auth/login", json={"user_code": user_code, "password": password})
    assert again.status_code == 200, again.text
    assert _stored_hash(user_code) == upgraded


def test_register_change_password_and_admin_reset_store_argon2id_only(client: TestClient):
    registered = client.post(
        "/api/v1/auth/register",
        json={"user_code": "new-user", "qq_id": "new-user", "password": PASSWORD, "identity": "participant"},
    )
    assert registered.status_code == 201, registered.text
    assert _stored_hash("new-user").startswith("$argon2id$")

    _insert_user("legacy-change", PASSLIB_BCRYPT_SHA256_V2)
    client.post("/api/v1/auth/logout")
    login = client.post("/api/v1/auth/login", json={"user_code": "legacy-change", "password": PASSWORD})
    assert login.status_code == 200, login.text
    changed = client.post(
        "/api/v1/auth/change-password",
        json={"old_password": PASSWORD, "new_password": "new-secret-456"},
    )
    assert changed.status_code == 200, changed.text
    changed_hash = _stored_hash("legacy-change")
    assert changed_hash.startswith("$argon2id$")
    assert verify_password("new-secret-456", changed_hash) is True

    client.post("/api/v1/auth/logout")
    admin = client.post("/api/v1/auth/login", json={"user_code": "admin", "password": "change-me-please"})
    assert admin.status_code == 200, admin.text
    target_id = _insert_user("reset-me", LEGACY_BCRYPT_2B)
    reset = client.post(
        "/api/v1/admin/users/reset-password",
        json={"user_id": target_id, "new_password": "reset-secret-789"},
    )
    assert reset.status_code == 200, reset.text
    reset_hash = _stored_hash("reset-me")
    assert reset_hash.startswith("$argon2id$")
    assert verify_password("reset-secret-789", reset_hash) is True
