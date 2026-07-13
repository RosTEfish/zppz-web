from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.security import get_current_user, require_role, user_payload
from app.db.session import get_db
from app.models import DrawAssignment, SwapRound, User
from app.modules.common import serialize_song
from app.modules.events.phase_policy import get_phase_status
from app.modules.events.service import get_current_event
from app.modules.swap.service import (
    MAX_SWAP_SELECTIONS,
    active_assignments_for_user,
    finalize_swap_round,
    get_swap_round,
    save_swap_request,
    validate_swap_round,
)


router = APIRouter(prefix="/swap", tags=["swap"])
admin_router = APIRouter(prefix="/admin/swap", tags=["admin-swap"])


class SwapSelectionUpdate(BaseModel):
    assignment_ids: list[int] = Field(min_length=1, max_length=MAX_SWAP_SELECTIONS)


def _assignment_payload(row: DrawAssignment | None) -> dict | None:
    if not row:
        return None
    return {
        "id": row.id,
        "song": serialize_song(row.song),
        "status": row.status,
        "draw_kind": row.draw_kind,
        "created_at": row.created_at,
    }


def _my_payload(db: Session, user: User, round_row: SwapRound | None = None) -> dict:
    event = get_current_event(db)
    phase = get_phase_status(db, event)
    round_row = round_row or get_swap_round(db, event.id)
    request = next((row for row in (round_row.requests if round_row else []) if row.user_id == user.id), None)
    selected = {item.original_assignment_id for item in request.items} if request else set()
    active = active_assignments_for_user(db, event.id, user.id) if user.identity == "participant" else []
    results = []
    if request:
        results = [
            {
                "original": _assignment_payload(item.original_assignment),
                "replacement": _assignment_payload(item.replacement_assignment),
            }
            for item in request.items
        ]
    return {
        "is_open": phase.can("swap") and (not round_row or round_row.status == "open"),
        "active_phase": phase.active_phase,
        "max_selections": MAX_SWAP_SELECTIONS,
        "round": {
            "id": round_row.id,
            "status": round_row.status,
            "starts_at": round_row.starts_at,
            "ends_at": round_row.ends_at,
            "finalized_at": round_row.finalized_at,
        } if round_row else None,
        "request": {
            "id": request.id,
            "status": request.status,
            "assignment_ids": [item.original_assignment_id for item in request.items],
        } if request else None,
        "assignments": [
            {**_assignment_payload(row), "selected": row.id in selected}
            for row in active
        ],
        "results": results,
    }


def _audit_payload(round_row: SwapRound | None) -> dict:
    if not round_row:
        return {"message": "暂无换曲批次", "round": None, "requests": []}
    return {
        "message": "换曲数据已更新" if round_row.status == "finalized" else "换曲批次处理中",
        "round": {
            "id": round_row.id,
            "status": round_row.status,
            "starts_at": round_row.starts_at,
            "ends_at": round_row.ends_at,
            "random_seed": round_row.random_seed,
            "finalized_at": round_row.finalized_at,
        },
        "requests": [
            {
                "id": request.id,
                "user": user_payload(request.user),
                "status": request.status,
                "error_message": request.error_message,
                "items": [
                    {
                        "position": item.position,
                        "original": _assignment_payload(item.original_assignment),
                        "replacement": _assignment_payload(item.replacement_assignment),
                    }
                    for item in request.items
                ],
            }
            for request in round_row.requests
        ],
    }


@router.get("/me")
def my_swap(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    return _my_payload(db, user)


@router.put("/me")
def update_my_swap(
    payload: SwapSelectionUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    round_row = save_swap_request(db, user, payload.assignment_ids)
    return _my_payload(db, user, round_row)


@admin_router.post("/validate")
def admin_validate_swap(_: User = Depends(require_role("admin")), db: Session = Depends(get_db)) -> dict:
    return validate_swap_round(db)


@admin_router.post("/finalize")
def admin_finalize_swap(_: User = Depends(require_role("admin")), db: Session = Depends(get_db)) -> dict:
    return _audit_payload(finalize_swap_round(db))


@admin_router.get("/audit")
def admin_swap_audit(
    _: User = Depends(require_role("admin", "pool_editor")),
    db: Session = Depends(get_db),
) -> dict:
    event = get_current_event(db)
    return _audit_payload(get_swap_round(db, event.id))
