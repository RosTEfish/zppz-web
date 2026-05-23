from datetime import datetime, timedelta
import hashlib
import secrets

from fastapi import Depends, HTTPException, Request, Response, status
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.db.session import get_db
from app.models import Role, User, UserSession


pwd_context = CryptContext(schemes=["bcrypt_sha256", "bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, stored_hash: str) -> bool:
    return pwd_context.verify(password, stored_hash)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def issue_session(response: Response, db: Session, user: User) -> str:
    settings = get_settings()
    token = secrets.token_urlsafe(48)
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


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = _extract_token(request)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="请先登录")
    session = db.scalar(select(UserSession).where(UserSession.token_hash == hash_token(token)))
    if not session or session.expires_at < datetime.utcnow():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录状态已过期")
    user = db.scalar(select(User).options(selectinload(User.roles)).where(User.id == session.user_id))
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="账号不可用")
    return user


def get_optional_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    token = _extract_token(request)
    if not token:
        return None
    session = db.scalar(select(UserSession).where(UserSession.token_hash == hash_token(token)))
    if not session or session.expires_at < datetime.utcnow():
        return None
    return db.scalar(select(User).options(selectinload(User.roles)).where(User.id == session.user_id))


def require_role(*roles: str):
    def dependency(user: User = Depends(get_current_user)) -> User:
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
        "is_admin": user.has_role("admin"),
        "is_pool_editor": user.has_role("pool_editor"),
    }


def ensure_roles(db: Session) -> dict[str, Role]:
    role_defs = {
        "admin": "管理员",
        "pool_editor": "曲池编辑",
        "participant": "参赛者",
        "audience": "观众",
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
        db.commit()
    return existing
