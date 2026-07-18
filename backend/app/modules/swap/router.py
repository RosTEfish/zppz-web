from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import get_current_user, require_role, user_payload
from app.db.session import get_db
from app.models import DrawAssignment, Submission, SwapRequest, SwapRound, User
from app.modules.common import serialize_song
from app.modules.draw.service import ensure_global_draw
from app.modules.events.phase_policy import get_phase_status
from app.modules.events.service import get_current_event
from app.modules.swap.service import active_assignments_for_user, get_swap_rounds, roll_for_user
from app.schemas import SwapSelectionUpdate


router = APIRouter(prefix="/swap", tags=["swap"])
admin_router = APIRouter(prefix="/admin/swap", tags=["admin-swap"])


def _assignment_payload(row: DrawAssignment | None, *, include_assignee: bool = False) -> dict | None:
    if not row:
        return None
    payload = {
        "id": row.id,
        "song": serialize_song(row.song),
        "status": row.status,
        "draw_kind": row.draw_kind,
        "replaces_assignment_id": row.replaces_assignment_id,
        "created_at": row.created_at,
    }
    if include_assignee:
        payload["assigned_to"] = user_payload(row.assigned_to)
    return payload


def _round_end(round_row: SwapRound) -> datetime:
    return round_row.roll_ends_at or round_row.ends_at


def _round_payload(round_row: SwapRound | None, *, roll_count: int = 0) -> dict | None:
    if round_row is None:
        return None
    return {
        "id": round_row.id,
        "status": round_row.status,
        "round_kind": round_row.round_kind,
        "starts_at": round_row.starts_at,
        "ends_at": _round_end(round_row),
        "roll_count": roll_count,
        "finalized_at": round_row.finalized_at,
    }


def _roll_payload(request: SwapRequest | None, *, include_user: bool = False) -> dict | None:
    if request is None:
        return None
    payload = {
        "id": request.id,
        "round_id": request.round_id,
        "status": request.status,
        "created_at": request.created_at,
        "items": [
            {
                "id": item.id,
                "position": item.position,
                "original": _assignment_payload(item.original_assignment, include_assignee=include_user),
                "replacement": _assignment_payload(item.replacement_assignment, include_assignee=include_user),
            }
            for item in request.items
        ],
    }
    if include_user:
        payload["user"] = user_payload(request.user)
    return payload


def _current_continuous_round(rounds: list[SwapRound]) -> SwapRound | None:
    return next((row for row in rounds if row.round_kind == "continuous"), None)


def _my_payload(db: Session, user: User, round_row: SwapRound | None = None, last_roll: SwapRequest | None = None) -> dict:
    event = get_current_event(db)
    phase = get_phase_status(db, event)
    if phase.active_phase in {"submission_1", "submission_2"}:
        ensure_global_draw(db)

    rounds = get_swap_rounds(db, event.id)
    round_row = round_row or _current_continuous_round(rounds)
    if round_row is not None and round_row.round_kind != "continuous":
        round_row = None

    if round_row is not None:
        current_round = next((row for row in rounds if row.id == round_row.id), round_row)
    else:
        current_round = None
    requests = current_round.requests if current_round else []
    user_requests = [row for row in requests if row.user_id == user.id and row.status == "completed"]
    user_requests.sort(key=lambda row: row.id)
    last_roll = last_roll or (user_requests[-1] if user_requests else None)

    active = active_assignments_for_user(db, event.id, user.id) if user.identity == "participant" else []
    submitted_song_ids = set(
        db.scalars(
            select(Submission.source_song_id).where(
                Submission.event_id == event.id,
                Submission.user_id == user.id,
                Submission.source_song_id.is_not(None),
            )
        ).all()
    )
    now = datetime.now(timezone.utc)
    is_round_open = round_row is None or (
        round_row.status == "open" and _utc_naive(_round_end(round_row)) > _utc_naive(now)
    )
    return {
        "is_open": phase.can("swap") and is_round_open,
        "active_phase": phase.active_phase,
        "round": _round_payload(round_row, roll_count=len(user_requests)),
        "assignments": [
            {
                **(_assignment_payload(row) or {}),
                "selected": False,
                "can_swap": row.song.id not in submitted_song_ids,
                "has_submission": row.song.id in submitted_song_ids,
            }
            for row in active
        ],
        "last_roll": _roll_payload(last_roll),
    }


def _audit_round_payload(round_row: SwapRound) -> dict:
    completed_count = sum(1 for request in round_row.requests if request.status == "completed")
    return {
        "id": round_row.id,
        "status": round_row.status,
        "round_kind": round_row.round_kind,
        "starts_at": round_row.starts_at,
        "ends_at": _round_end(round_row),
        "random_seed": round_row.random_seed,
        "finalized_at": round_row.finalized_at,
        "roll_count": completed_count,
    }


def _audit_payload(rounds: list[SwapRound]) -> dict:
    current = rounds[0] if rounds else None
    all_requests = [request for round_row in rounds for request in round_row.requests]
    all_requests.sort(key=lambda request: request.id, reverse=True)
    return {
        "message": "连续换曲记录" if current and current.round_kind == "continuous" else "历史换曲记录",
        "round": _audit_round_payload(current) if current else None,
        "rounds": [_audit_round_payload(row) for row in rounds],
        "requests": [_roll_payload(request, include_user=True) for request in all_requests],
    }


def _utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


@router.get("/me")
def my_swap(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    return _my_payload(db, user)


@router.post("/me/roll")
def roll_my_swap(
    payload: SwapSelectionUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    round_row, request = roll_for_user(db, user, payload.assignment_ids)
    return _my_payload(db, user, round_row, request)


def _removed_write_endpoint() -> None:
    raise HTTPException(status_code=status.HTTP_410_GONE, detail="旧式换曲申请已取消，请使用 Stage2 即时换曲")


@router.put("/me")
def legacy_update_my_swap() -> None:
    _removed_write_endpoint()


@router.delete("/me")
def legacy_cancel_my_swap() -> None:
    _removed_write_endpoint()


@admin_router.get("/audit")
def admin_swap_audit(
    _: User = Depends(require_role("admin", "pool_editor")),
    db: Session = Depends(get_db),
) -> dict:
    event = get_current_event(db)
    return _audit_payload(get_swap_rounds(db, event.id))


@admin_router.post("/validate")
def legacy_validate_swap(_: User = Depends(require_role("admin"))) -> None:
    _removed_write_endpoint()


@admin_router.post("/finalize")
def legacy_finalize_swap(_: User = Depends(require_role("admin"))) -> None:
    _removed_write_endpoint()


@admin_router.post("/requests/{request_id}/reject")
def legacy_reject_swap_request(request_id: int, _: User = Depends(require_role("admin"))) -> None:
    _removed_write_endpoint()
