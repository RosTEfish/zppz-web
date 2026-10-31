import base64
import hashlib
import hmac
import re
import secrets
from datetime import datetime, timedelta
from threading import Lock
from time import monotonic

import bcrypt
from fastapi import Depends, HTTPException, Request, Response, status
from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError
from pwdlib.hashers.argon2 import Argon2Hasher
from pwdlib.hashers.bcrypt import BcryptHasher
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, joinedload

from app.core.config import get_settings
from app.db.session import get_db
from app.models import Role, User, UserSession

# Argon2id is the current hasher. BcryptHasher only verifies legacy $2a$/$2b$/$2y$ hashes.
password_hash = PasswordHash((Argon2Hasher(), BcryptHasher()))
# passlib 1.7.4 bcrypt_sha256. v=2 HMACs the password with the bcrypt salt string;
# v=1 uses plain SHA-256. Both standard-base64 the 32-byte digest (44 bytes, with "=")
# and then bcrypt it. Hex was considered and rejected: 64 hex chars sit in bcrypt's
# poorly mixed tail. See passlib.handlers.bcrypt.bcrypt_sha256.
_BCRYPT_SHA256_V2_RE = re.compile(
    r"^\$bcrypt-sha256\$v=(?P<version>\d+),t=(?P<ident>2b),r=(?P<rounds>\d{1,2})"
    r"\$(?P<salt>[^$]{22})\$(?P<digest>[^$]{31})$"
)
_BCRYPT_SHA256_V1_RE = re.compile(
    r"^\$bcrypt-sha256\$(?P<ident>2[ab]),(?P<rounds>\d{1,2})\$(?P<salt>[^$]{22})\$(?P<digest>[^$]{31})$"
)
_BCRYPT_FINAL_SALT_CHARS = ".Oeu"
_session_cleanup_lock = Lock()
_last_session_cleanup = 0.0
_SESSION_CLEANUP_INTERVAL_SECONDS = 15 * 60
_SESSION_CLEANUP_BATCH_SIZE = 500
OWNER_ROLE = "owner"
ADMIN_ROLE = "admin"
OWNER_INHERITED_ROLES = {ADMIN_ROLE, "pool_editor"}
USER_IDENTITIES = frozenset({"participant", "audience", "guest"})
SONG_POOL_IDENTITIES = frozenset({"participant", "audience"})


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, stored_hash: str) -> bool:
    if stored_hash.startswith("$bcrypt-sha256$"):
        return _verify_passlib_bcrypt_sha256(password, stored_hash)
    try:
        return password_hash.verify(password, stored_hash)
    except UnknownHashError:
        return False


def verify_and_update_password(password: str, stored_hash: str) -> tuple[bool, str | None]:
    """Return whether the password matches, and an Argon2id hash when the stored hash is legacy."""
    if stored_hash.startswith("$bcrypt-sha256$"):
        if not _verify_passlib_bcrypt_sha256(password, stored_hash):
            return False, None
        return True, hash_password(password)
    try:
        return password_hash.verify_and_update(password, stored_hash)
    except UnknownHashError:
        return False, None


def _verify_passlib_bcrypt_sha256(password: str, stored_hash: str) -> bool:
    parsed = _parse_passlib_bcrypt_sha256(stored_hash)
    if parsed is None:
        return False
    version, ident, rounds, salt, digest = parsed
    prehashed = _passlib_bcrypt_sha256_secret(password, version=version, salt=salt)
    if prehashed is None:
        return False
    embedded = f"${ident}${rounds:02d}${salt}{digest}".encode("ascii")
    try:
        return bcrypt.checkpw(prehashed, embedded)
    except (ValueError, TypeError):
        return False


def _parse_passlib_bcrypt_sha256(stored_hash: str) -> tuple[int, str, int, str, str] | None:
    match = _BCRYPT_SHA256_V2_RE.fullmatch(stored_hash)
    version = 2
    if match is None:
        match = _BCRYPT_SHA256_V1_RE.fullmatch(stored_hash)
        version = 1
    if match is None:
        return None
    if version == 2 and int(match.group("version")) != 2:
        return None
    rounds_text = match.group("rounds")
    if len(rounds_text) > 1 and rounds_text.startswith("0"):
        return None
    rounds = int(rounds_text)
    if not 4 <= rounds <= 31:
        return None
    return version, match.group("ident"), rounds, match.group("salt"), match.group("digest")


def _passlib_bcrypt_sha256_secret(password: str, *, version: int, salt: str) -> bytes | None:
    secret = password.encode("utf-8")
    if b"\x00" in secret:
        return None
    if version == 1:
        digest = hashlib.sha256(secret).digest()
    else:
        try:
            salt_bytes = salt.encode("ascii")
        except UnicodeEncodeError:
            return None
        if salt[-1] not in _BCRYPT_FINAL_SALT_CHARS:
            return None
        digest = hmac.new(salt_bytes, secret, hashlib.sha256).digest()
    return base64.b64encode(digest)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def issue_session(response: Response, db: Session, user: User) -> str:
    settings = get_settings()
    token = secrets.token_urlsafe(48)
    _cleanup_expired_sessions(db)
    session = UserSession(
        user_id=user.id,
        token_hash=hash_token(token),
        expires_at=datetime.utcnow() + timedelta(hours=settings.session_expire_hours),
    )
    db.add(session)
    db.commit()
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        httponly=True,
        secure=settings.secure_cookies,
        samesite="lax",
        max_age=settings.session_expire_hours * 3600,
        path="/",
    )
    return token


def clear_session_cookie(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(
        settings.session_cookie_name,
        path="/",
        secure=settings.secure_cookies,
        httponly=True,
        samesite="lax",
    )


def revoke_request_session(db: Session, request: Request) -> None:
    """Delete the presented server session so a copied cookie cannot be replayed."""
    token = _extract_token(request)
    if not token:
        return
    db.execute(delete(UserSession).where(UserSession.token_hash == hash_token(token)))
    db.commit()


def _extract_token(request: Request) -> str | None:
    settings = get_settings()
    cookie_token = request.cookies.get(settings.session_cookie_name)
    if cookie_token:
        return cookie_token
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return None


def _lookup_session(db: Session, token: str) -> UserSession | None:
    return (
        db.execute(
            select(UserSession)
            .options(joinedload(UserSession.user).joinedload(User.roles))
            .where(UserSession.token_hash == hash_token(token))
        )
        .unique()
        .scalar_one_or_none()
    )


def _cleanup_expired_sessions(db: Session) -> None:
    """Bound cleanup work on login and avoid adding writes to normal requests."""
    global _last_session_cleanup
    now = monotonic()
    if now - _last_session_cleanup < _SESSION_CLEANUP_INTERVAL_SECONDS:
        return
    if not _session_cleanup_lock.acquire(blocking=False):
        return
    try:
        now = monotonic()
        if now - _last_session_cleanup < _SESSION_CLEANUP_INTERVAL_SECONDS:
            return
        expired_ids = list(
            db.scalars(
                select(UserSession.id)
                .where(UserSession.expires_at < datetime.utcnow())
                .order_by(UserSession.expires_at.asc())
                .limit(_SESSION_CLEANUP_BATCH_SIZE)
            ).all()
        )
        if expired_ids:
            db.execute(delete(UserSession).where(UserSession.id.in_(expired_ids)))
        _last_session_cleanup = now
    finally:
        _session_cleanup_lock.release()


def get_current_session(request: Request, db: Session = Depends(get_db)) -> UserSession:
    token = _extract_token(request)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="请先登录")
    session = _lookup_session(db, token)
    if not session or session.expires_at < datetime.utcnow():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录状态已过期")
    user = session.user
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="账号不可用")
    return session


def get_current_user(session: UserSession = Depends(get_current_session)) -> User:
    return session.user


def get_optional_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    token = _extract_token(request)
    if not token:
        return None
    session = _lookup_session(db, token)
    if not session or session.expires_at < datetime.utcnow():
        return None
    return session.user if session.user.is_active else None


def is_owner(user: User) -> bool:
    return user.has_role(OWNER_ROLE)


def has_admin_access(user: User) -> bool:
    """Return whether a user has the administrative control surface."""
    return is_owner(user) or user.has_role(ADMIN_ROLE)


def require_role(*roles: str):
    def dependency(user: User = Depends(get_current_user)) -> User:
        if is_owner(user) and any(role in OWNER_INHERITED_ROLES for role in roles):
            return user
        if any(user.has_role(role) for role in roles):
            return user
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="没有权限执行此操作")

    return dependency


def public_user_payload(user: User) -> dict:
    """Name shown on public song, draw, and comment payloads."""
    name = (user.display_name or "").strip() or user.user_code
    return {"display_name": name}


def user_payload(user: User) -> dict:
    return {
        "id": user.id,
        "user_code": user.user_code,
        "qq_id": user.qq_id,
        "identity": user.identity,
        "display_name": user.display_name,
        "roles": [role.name for role in user.roles],
        "is_admin": has_admin_access(user),
        "is_owner": is_owner(user),
        "is_pool_editor": user.has_role("pool_editor") or is_owner(user),
        "is_active": user.is_active,
    }


def ensure_roles(db: Session, *, commit: bool = True) -> dict[str, Role]:
    role_defs = {
        OWNER_ROLE: "Owner",
        "admin": "管理员",
        "pool_editor": "曲池编辑",
        "participant": "参赛者",
        "audience": "观众",
        "guest": "访客",
    }
    existing = {role.name: role for role in db.scalars(select(Role)).all()}
    changed = False
    for name, label in role_defs.items():
        if name not in existing:
            role = Role(name=name, label=label)
            db.add(role)
            existing[name] = role
            changed = True
    if changed:
        db.flush()
        if commit:
            db.commit()
    return existing


def sync_identity_role(user: User, identity: str, roles: dict[str, Role]) -> None:
    """Keep the user's identity field and identity role in sync."""
    if identity not in USER_IDENTITIES:
        raise ValueError(f"Unsupported user identity: {identity}")
    user.identity = identity
    preserved_roles = [role for role in user.roles if role.name not in USER_IDENTITIES]
    user.roles = [*preserved_roles, roles[identity]]
