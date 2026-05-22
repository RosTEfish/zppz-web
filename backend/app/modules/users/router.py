from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import ensure_roles, hash_password, require_role, user_payload
from app.db.session import get_db
from app.models import User
from app.schemas import AdminUserUpdate, ResetPasswordRequest, UserRead


router = APIRouter(prefix="/admin/users", tags=["admin-users"])


@router.get("", response_model=list[UserRead])
def list_users(_: User = Depends(require_role("admin")), db: Session = Depends(get_db)) -> list[dict]:
    return [user_payload(user) for user in db.scalars(select(User).order_by(User.created_at.desc())).all()]


@router.put("/{user_id}", response_model=UserRead)
def update_user(user_id: int, payload: AdminUserUpdate, _: User = Depends(require_role("admin")), db: Session = Depends(get_db)) -> dict:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
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

