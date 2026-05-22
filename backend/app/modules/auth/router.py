from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import clear_session_cookie, ensure_roles, get_current_user, hash_password, issue_session, user_payload, verify_password
from app.db.session import get_db
from app.models import User
from app.schemas import AuthResponse, ChangePasswordRequest, LoginRequest, RegisterRequest


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, response: Response, db: Session = Depends(get_db)) -> dict:
    if payload.identity not in {"participant", "audience"}:
        raise HTTPException(status_code=400, detail="身份只能是 participant 或 audience")
    if db.scalar(select(User).where(User.user_code == payload.user_code)):
        raise HTTPException(status_code=409, detail="这个参赛 ID 已被注册")
    roles = ensure_roles(db)
    user = User(
        user_code=payload.user_code.strip(),
        qq_id=payload.qq_id.strip(),
        password_hash=hash_password(payload.password),
        identity=payload.identity,
        display_name=payload.user_code.strip(),
        roles=[roles[payload.identity]],
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    issue_session(response, db, user)
    return {"user": user_payload(user)}


@router.post("/login", response_model=AuthResponse)
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)) -> dict:
    user = db.scalar(select(User).where(User.user_code == payload.user_code))
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="账号或密码不正确")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账号已停用")
    issue_session(response, db, user)
    return {"user": user_payload(user)}


@router.post("/logout")
def logout(response: Response) -> dict:
    clear_session_cookie(response)
    return {"message": "已退出登录"}


@router.get("/me", response_model=AuthResponse)
def me(user: User = Depends(get_current_user)) -> dict:
    return {"user": user_payload(user)}


@router.post("/change-password")
def change_password(payload: ChangePasswordRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    if not verify_password(payload.old_password, user.password_hash):
        raise HTTPException(status_code=400, detail="旧密码不正确")
    user.password_hash = hash_password(payload.new_password)
    db.commit()
    return {"message": "密码已更新"}

