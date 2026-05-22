from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import require_role
from app.db.session import get_db
from app.models import DrawAssignment, GuessChart, Song, Submission, User
from app.modules.events.service import get_current_event


router = APIRouter(prefix="/admin", tags=["admin"])


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

