from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.security import require_role
from app.db.session import get_db
from app.models import User
from app.modules.events.service import get_current_event, update_current_event
from app.schemas import EventRead, EventUpdate


router = APIRouter(prefix="/events", tags=["events"])
admin_router = APIRouter(prefix="/admin/events", tags=["admin-events"])


@router.get("/current", response_model=EventRead)
def current_event(db: Session = Depends(get_db)):
    return get_current_event(db)


@admin_router.put("/current", response_model=EventRead)
def admin_update_current_event(
    payload: EventUpdate,
    _: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    return update_current_event(db, payload)

