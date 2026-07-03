from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.security import ensure_roles, hash_password, require_role, user_payload
from app.db.session import get_db
from app.models import Role, User
from app.schemas import AdminUserUpdate, ResetPasswordRequest, UserRead


router = APIRouter(prefix="/admin/users", tags=["admin-users"])


@router.get("", response_model=list[UserRead])
def list_users(_: User = Depends(require_role("admin")), db: Session = Depends(get_db)) -> list[dict]:
    users = db.scalars(select(User).options(selectinload(User.roles)).order_by(User.created_at.desc())).all()
    return [user_payload(user) for user in users]


@router.put("/{user_id}", response_model=UserRead)
def update_user(user_id: int, payload: AdminUserUpdate, _: User = Depends(require_role("admin")), db: Session = Depends(get_db)) -> dict:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    removes_active_admin = user.is_active and user.has_role("admin") and (
        "admin" not in payload.roles or not payload.is_active
    )
    if removes_active_admin:
        another_active_admin = db.scalar(
            select(User.id)
            .join(User.roles)
            .where(Role.name == "admin", User.is_active.is_(True), User.id != user.id)
            .limit(1)
        )
        if another_active_admin is None:
            raise HTTPException(status_code=409, detail="至少需要保留一名启用中的管理员")
    roles = ensure_roles(db)
    user.identity = payload.identity
    user.display_name = payload.display_name
    user.is_active = payload.is_active
    user.roles = [roles[name] for name in payload.roles if name in roles]
    db.commit()
    db.refresh(user)
    return user_payload(user)


@router.post("/reset-password")
def reset_password(payload: ResetPasswordRequest, _: User = Depends(require_role("admin")), db: Session = Depends(get_db)) -> dict:
    user = db.get(User, payload.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    user.password_hash = hash_password(payload.new_password)
    db.commit()
    return {"message": "密码已重置"}
