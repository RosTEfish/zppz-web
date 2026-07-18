from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import get_current_user, require_role
from app.db.session import get_db
from app.models import JTrackSubmission, Submission, User
from app.modules.common import serialize_song
from app.modules.draw.service import draw_for_user, get_draw_results, run_draw
from app.modules.events.phase_policy import get_phase_status
from app.modules.events.service import get_current_event
from app.schemas import DrawAssignmentRead


router = APIRouter(prefix="/draw", tags=["draw"])
admin_router = APIRouter(prefix="/admin/draw", tags=["admin-draw"])


def serialize_assignment(item) -> dict:
    from app.core.security import user_payload

    return {
        "id": item.id,
        "assigned_to": user_payload(item.assigned_to),
        "song": serialize_song(item.song),
        "status": item.status,
        "draw_kind": item.draw_kind,
        "replaces_assignment_id": item.replaces_assignment_id,
        "created_at": item.created_at,
    }


@router.get("/results", response_model=list[DrawAssignmentRead])
def my_draw_results(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[dict]:
    return [serialize_assignment(item) for item in get_draw_results(db, user.id)]


@router.post("/me", response_model=list[DrawAssignmentRead])
def draw_my_songs(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[dict]:
    return [serialize_assignment(item) for item in draw_for_user(db, user)]


@admin_router.post("", response_model=list[DrawAssignmentRead])
def admin_run_draw(_: User = Depends(require_role("admin")), db: Session = Depends(get_db)) -> list[dict]:
    return [serialize_assignment(item) for item in run_draw(db)]


@admin_router.get("/results", response_model=list[DrawAssignmentRead])
def admin_draw_results(_: User = Depends(require_role("admin", "pool_editor")), db: Session = Depends(get_db)) -> list[dict]:
    return [serialize_assignment(item) for item in get_draw_results(db)]


@admin_router.get("/stats")
def admin_draw_stats(_: User = Depends(require_role("admin", "pool_editor")), db: Session = Depends(get_db)) -> dict:
    event = get_current_event(db)
    rows = get_draw_results(db)
    assigned_user_ids = {item.assigned_to_id for item in rows}
    has_submission = bool(
        db.scalar(select(Submission.id).where(Submission.event_id == event.id).limit(1))
        or db.scalar(select(JTrackSubmission.id).where(JTrackSubmission.event_id == event.id).limit(1))
    )
    return {
        "assignments": len(rows),
        "assigned_users": len(assigned_user_ids),
        "has_submission": has_submission,
        "can_redraw": get_phase_status(db, event).active_phase == "submission_1" and not has_submission,
    }
