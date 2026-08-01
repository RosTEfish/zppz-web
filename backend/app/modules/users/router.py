from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.security import OWNER_ROLE, ensure_roles, hash_password, is_owner, require_role, sync_identity_role, user_payload
from app.db.session import get_db
from app.models import Role, User
from app.schemas import AdminUserUpdate, ResetPasswordRequest, UserRead


router = APIRouter(prefix="/admin/users", tags=["admin-users"])


@router.get("", response_model=list[UserRead])
def list_users(_: User = Depends(require_role("admin")), db: Session = Depends(get_db)) -> list[dict]:
    users = db.scalars(select(User).options(selectinload(User.roles)).order_by(User.created_at.desc())).all()
    return [user_payload(user) for user in users]


@router.put("/{user_id}", response_model=UserRead)
def update_user(
    user_id: int,
    payload: AdminUserUpdate,
    actor: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> dict:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    target_is_owner = user.has_role(OWNER_ROLE)
    target_is_admin = user.has_role("admin")
    requested_roles = {str(role) for role in payload.roles}
    requested_is_owner = OWNER_ROLE in requested_roles
    requested_is_admin = "admin" in requested_roles

    # Owner assignment/replacement is intentionally backend CLI-only.
    if requested_is_owner != target_is_owner:
        raise HTTPException(status_code=403, detail="owner role can only be changed by the backend CLI")
    if target_is_owner and payload.is_active != user.is_active:
        raise HTTPException(status_code=403, detail="owner account status can only be changed by the backend CLI")
    if not is_owner(actor):
        if requested_is_admin != target_is_admin:
            raise HTTPException(status_code=403, detail="only the owner can change administrator roles")
        if (target_is_admin or target_is_owner) and payload.is_active != user.is_active:
            raise HTTPException(status_code=403, detail="only the owner can change privileged account status")

    removes_active_admin = user.is_active and target_is_admin and (
        "admin" not in payload.roles or not payload.is_active
    )
    if removes_active_admin:
        another_active_admin = db.scalar(
            select(User.id)
            .join(User.roles)
            .where(Role.name.in_(("admin", OWNER_ROLE)), User.is_active.is_(True), User.id != user.id)
            .limit(1)
        )
        if another_active_admin is None:
            raise HTTPException(status_code=409, detail="至少需要保留一名启用中的管理员")
    roles = ensure_roles(db)
    user.display_name = payload.display_name
    user.is_active = payload.is_active
    requested_names = {
        str(name)
        for name in payload.roles
        if str(name) in roles and str(name) not in {OWNER_ROLE, "participant", "audience"}
    }
    if target_is_owner:
        requested_names.add(OWNER_ROLE)
    user.roles = [role for name, role in roles.items() if name in requested_names]
    sync_identity_role(user, payload.identity, roles)
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
