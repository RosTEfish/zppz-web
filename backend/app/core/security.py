from datetime import datetime, timedelta
import hashlib
import secrets
from threading import Lock
from time import monotonic

from fastapi import Depends, HTTPException, Request, Response, status
from passlib.context import CryptContext
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, joinedload

from app.core.config import get_settings
from app.db.session import get_db
from app.models import Role, User, UserSession


pwd_context = CryptContext(schemes=["bcrypt_sha256", "bcrypt"], deprecated="auto")
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
    return pwd_context.hash(password)


def verify_password(password: str, stored_hash: str) -> bool:
    return pwd_context.verify(password, stored_hash)


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
    response.delete_cookie(get_settings().session_cookie_name, path="/")


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
