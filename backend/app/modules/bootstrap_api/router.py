from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.security import get_optional_user, user_payload
from app.db.session import get_db
from app.models import User
from app.modules.events.service import get_current_event
from app.schemas import BootstrapRead


router = APIRouter(tags=["bootstrap"])


@router.get("/bootstrap", response_model=BootstrapRead)
def bootstrap(
    user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
) -> dict:
    return {
        "event": get_current_event(db),
        "user": user_payload(user) if user else None,
    }
