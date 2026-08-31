from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import get_optional_user, user_payload
from app.core.cache import ANONYMOUS_BOOTSTRAP_CACHE_CONTROL
from app.db.session import get_db
from app.models import GuessChart, User
from app.modules.events.service import get_current_event, get_phase_schedule
from app.modules.events.phase_policy import apply_chart_visibility_filter, get_phase_status
from app.schemas import BootstrapRead


router = APIRouter(tags=["bootstrap"])


@router.get("/bootstrap", response_model=BootstrapRead)
def bootstrap(
    response: Response,
    user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
) -> dict:
    response.headers["Vary"] = "Cookie"
    response.headers["Cache-Control"] = "private, no-store" if user else ANONYMOUS_BOOTSTRAP_CACHE_CONTROL
    event = get_current_event(db)
    phase_status = get_phase_status(db, event)
    availability_stmt = apply_chart_visibility_filter(
        select(GuessChart.id).where(GuessChart.event_id == event.id),
        phase_status,
    )
    return {
        "event": event,
        "user": user_payload(user) if user else None,
        "phases": get_phase_schedule(db, event),
        "guess_availability": {"available": db.scalar(availability_stmt.limit(1)) is not None},
    }
