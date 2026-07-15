from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.core.security import require_role
from app.core.cache import set_public_api_cache
from app.db.session import get_db
from app.models import User
from app.modules.events.service import (
    get_current_event,
    get_phase_schedule,
    update_current_event,
    update_phase_schedule,
)
from app.schemas import EventPhasesRead, EventPhasesUpdate, EventRead, EventUpdate


router = APIRouter(tags=["events"])
admin_router = APIRouter(tags=["admin-events"])


@router.get("/events/current", response_model=EventRead)
def current_event(response: Response, db: Session = Depends(get_db)):
    set_public_api_cache(response)
    return get_current_event(db)


@router.get("/event/phases", response_model=EventPhasesRead)
def event_phases(response: Response, db: Session = Depends(get_db)):
    set_public_api_cache(response)
    return get_phase_schedule(db)


@admin_router.put("/admin/events/current", response_model=EventRead)
def admin_update_current_event(
    payload: EventUpdate,
    _: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    return update_current_event(db, payload)


@admin_router.put("/admin/event/phases", response_model=EventPhasesRead)
def admin_update_event_phases(
    payload: EventPhasesUpdate,
    _: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    return update_phase_schedule(db, payload)
