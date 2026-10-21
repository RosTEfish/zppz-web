from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.client_ip import client_ip_budget_applies, resolve_client_ip
from app.core.config import get_settings
from app.core.security import (
    clear_session_cookie,
    ensure_roles,
    get_current_session,
    get_current_user,
    hash_password,
    issue_session,
    revoke_request_session,
    sync_identity_role,
    USER_IDENTITIES,
    user_payload,
    verify_password,
)
from app.db.session import get_db
from app.models import User, UserSession
from app.modules.auth.rate_limit import (
    clear_login_failures,
    clear_password_change_failures,
    login_retry_after,
    password_change_retry_after,
    record_login_failure,
    record_password_change_failure,
    record_registration,
    registration_retry_after,
)
from app.modules.events.phase_policy import get_phase_status, registration_window_closed
from app.schemas import AuthResponse, ChangePasswordRequest, LoginRequest, RegisterRequest, UpdateProfileRequest


router = APIRouter(prefix="/auth", tags=["auth"])


def _client_context(request: Request) -> tuple[str, bool]:
    peer = request.client.host if request.client else None
    trusted = get_settings().trusted_proxies
    client_ip = resolve_client_ip(
        peer,
        request.headers.get("x-forwarded-for"),
        request.headers.get("x-real-ip"),
        trusted,
    )
    return client_ip, client_ip_budget_applies(client_ip, trusted)


def _reject_if_limited(retry_after: int | None) -> None:
    if retry_after is None:
        return
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="尝试次数过多，请稍后再试",
        headers={"Retry-After": str(retry_after)},
    )


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, request: Request, response: Response, db: Session = Depends(get_db)) -> dict:
    client_ip, enforce_ip_budget = _client_context(request)
    # Skip the shared budget while every request still looks like the proxy.
    # Otherwise a loopback-only deployment locks registration for the whole site.
    if enforce_ip_budget:
        _reject_if_limited(registration_retry_after(client_ip))
        record_registration(client_ip)
    if payload.identity not in USER_IDENTITIES:
        raise HTTPException(status_code=400, detail="身份只能是 participant、audience 或 guest")
    if db.scalar(select(User).where(User.user_code == payload.user_code)):
        raise HTTPException(status_code=409, detail="这个参赛 ID 已被注册")
    roles = ensure_roles(db)
    identity = "guest" if registration_window_closed(db) else payload.identity
    user = User(
        user_code=payload.user_code.strip(),
        qq_id=payload.qq_id.strip(),
        password_hash=hash_password(payload.password),
        identity=identity,
        display_name=payload.user_code.strip(),
        roles=[roles[identity]],
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    issue_session(response, db, user)
    return {"user": user_payload(user)}


@router.post("/login", response_model=AuthResponse)
def login(payload: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)) -> dict:
    client_ip, enforce_ip_budget = _client_context(request)
    _reject_if_limited(login_retry_after(client_ip, payload.user_code, enforce_ip_budget=enforce_ip_budget))
    user = db.scalar(select(User).where(User.user_code == payload.user_code))
    if not user or not verify_password(payload.password, user.password_hash):
        record_login_failure(client_ip, payload.user_code, enforce_ip_budget=enforce_ip_budget)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="账号或密码不正确")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账号已停用")
    clear_login_failures(client_ip, payload.user_code)
    issue_session(response, db, user)
    return {"user": user_payload(user)}


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)) -> dict:
    revoke_request_session(db, request)
    clear_session_cookie(response)
    return {"message": "已退出登录"}


@router.get("/me", response_model=AuthResponse)
def me(user: User = Depends(get_current_user)) -> dict:
    return {"user": user_payload(user)}


@router.put("/me", response_model=AuthResponse)
def update_me(
    payload: UpdateProfileRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    if payload.identity != user.identity and get_phase_status(db).active_phase != "registration":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="仅报名阶段可以修改参赛身份")
    roles = ensure_roles(db, commit=False)
    user.display_name = payload.display_name
    sync_identity_role(user, payload.identity, roles)
    db.commit()
    db.refresh(user)
    return {"user": user_payload(user)}


@router.post("/change-password")
def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    current_session: UserSession = Depends(get_current_session),
    db: Session = Depends(get_db),
) -> dict:
    client_ip, enforce_ip_budget = _client_context(request)
    user = current_session.user
    _reject_if_limited(
        password_change_retry_after(client_ip, user.user_code, enforce_ip_budget=enforce_ip_budget)
    )
    if not verify_password(payload.old_password, user.password_hash):
        record_password_change_failure(client_ip, user.user_code, enforce_ip_budget=enforce_ip_budget)
        raise HTTPException(status_code=400, detail="旧密码不正确")
    clear_password_change_failures(client_ip, user.user_code)
    user.password_hash = hash_password(payload.new_password)
    db.execute(
        delete(UserSession).where(
            UserSession.user_id == user.id,
            UserSession.id != current_session.id,
        )
    )
    db.commit()
    return {"message": "密码已更新"}
