from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models import Event


PHASES = (
    "registration",
    "submission_1",
    "submission_2",
    "guess",
)


@dataclass(frozen=True)
class PhaseCapabilities:
    song_pool_edit: bool = False
    submission: bool = False
    swap: bool = False
    normal_submission_public: bool = False
    author_guess: bool = False
    quality_vote: bool = False

    def as_dict(self) -> dict[str, bool]:
        return asdict(self)


@dataclass(frozen=True)
class PhaseStatus:
    active_phase: str | None
    capabilities: PhaseCapabilities
    next_transition_at: datetime | None = None

    def can(self, capability: str) -> bool:
        if not hasattr(self.capabilities, capability):
            raise ValueError(f"Unknown phase capability: {capability}")
        return bool(getattr(self.capabilities, capability))


CAPABILITIES: dict[str, PhaseCapabilities] = {
    "registration": PhaseCapabilities(song_pool_edit=True),
    "submission_1": PhaseCapabilities(submission=True),
    "submission_2": PhaseCapabilities(submission=True, swap=True),
    "guess": PhaseCapabilities(
        normal_submission_public=True,
        author_guess=True,
        quality_vote=True,
    ),
}

INACTIVE_CAPABILITIES = PhaseCapabilities()
POST_GUESS_CAPABILITIES = PhaseCapabilities(normal_submission_public=True)
ALWAYS_PUBLIC_CHART_SOURCE_TYPES = frozenset({"admin", "j", "exhibition"})


def _utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _load_current_event(db: Session) -> Event | None:
    return db.scalar(
        select(Event)
        .options(joinedload(Event.settings), selectinload(Event.phases))
        .where(Event.is_current.is_(True))
    )


def get_phase_status(
    db: Session,
    event: Event | None = None,
    *,
    now: datetime | None = None,
) -> PhaseStatus:
    """Return the authoritative phase and capabilities for an event.

    Scheduled timestamps and the default clock are compared as naive UTC values so
    the policy behaves consistently on SQLite and PostgreSQL. An automatic event with
    no schedule is always in registration.
    """

    event = event or _load_current_event(db)
    if event is None or event.settings is None:
        return PhaseStatus("registration", CAPABILITIES["registration"])

    current_time = _utc_naive(now or datetime.now(timezone.utc))
    settings = event.settings
    rows = sorted(
        (
            (row, _utc_naive(row.starts_at), _utc_naive(row.ends_at))
            for row in event.phases
            if row.phase in PHASES
        ),
        key=lambda item: (item[1], item[2], item[0].id or 0),
    )

    if settings.phase_mode == "manual" and settings.manual_phase in PHASES:
        active_phase = settings.manual_phase
        return PhaseStatus(active_phase, CAPABILITIES[active_phase])

    if not rows:
        return PhaseStatus("registration", CAPABILITIES["registration"])

    active_phase: str | None = None
    if current_time < rows[0][1]:
        active_phase = "registration"
    else:
        for row, starts_at, ends_at in rows:
            if starts_at <= current_time < ends_at:
                active_phase = row.phase
                break

    future_boundaries = [
        boundary
        for _, starts_at, ends_at in rows
        for boundary in (starts_at, ends_at)
        if boundary > current_time
    ]
    next_transition = min(future_boundaries) if future_boundaries else None
    if next_transition is not None:
        next_transition = next_transition.replace(tzinfo=timezone.utc)
    if active_phase is not None:
        capabilities = CAPABILITIES[active_phase]
    elif any(row.phase == "guess" and ends_at <= current_time for row, _, ends_at in rows):
        capabilities = POST_GUESS_CAPABILITIES
    else:
        capabilities = INACTIVE_CAPABILITIES
    return PhaseStatus(active_phase, capabilities, next_transition)


def phase_status_payload(status: PhaseStatus) -> dict[str, Any]:
    return {
        "active_phase": status.active_phase,
        "capabilities": status.capabilities.as_dict(),
        "next_transition_at": status.next_transition_at,
    }


def is_chart_public(source_type: str, phase_status: PhaseStatus) -> bool:
    return source_type in ALWAYS_PUBLIC_CHART_SOURCE_TYPES or phase_status.can("normal_submission_public")
