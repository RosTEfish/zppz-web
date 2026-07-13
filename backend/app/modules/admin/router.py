from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import clear_session_cookie, require_role
from app.db.session import get_db
from app.models import DrawAssignment, GuessChart, Song, Submission, User
from app.modules.events.service import get_current_event
from app.modules.admin.service import RESET_CONFIRMATION, reset_all_data
from app.schemas import AdminResetRequest, AdminResetResponse


router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/reset", response_model=AdminResetResponse)
def reset_database(
    payload: AdminResetRequest,
    response: Response,
    _: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> dict:
    if payload.confirmation != RESET_CONFIRMATION:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"请输入准确的确认词：{RESET_CONFIRMATION}",
        )
    result = reset_all_data(db)
    clear_session_cookie(response)
    return result


@router.get("/stats")
def admin_dashboard(_: User = Depends(require_role("admin", "pool_editor")), db: Session = Depends(get_db)) -> dict:
    event = get_current_event(db)
    return {
        "users": db.scalar(select(func.count()).select_from(User)) or 0,
        "songs": db.scalar(select(func.count()).select_from(Song).where(Song.event_id == event.id)) or 0,
        "assignments": db.scalar(select(func.count()).select_from(DrawAssignment).where(DrawAssignment.event_id == event.id)) or 0,
        "submissions": db.scalar(select(func.count()).select_from(Submission).where(Submission.event_id == event.id)) or 0,
        "guess_charts": db.scalar(select(func.count()).select_from(GuessChart).where(GuessChart.event_id == event.id)) or 0,
    }
