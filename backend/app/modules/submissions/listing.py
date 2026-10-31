"""Participant submission list and target routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.security import get_current_user
from app.db.session import get_db
from app.models import (
    DrawAssignment,
    Song,
    Submission,
    User,
)
from app.modules.common import serialize_song, serialize_submissions
from app.modules.draw.service import ensure_global_draw
from app.modules.events.phase_policy import get_phase_status
from app.modules.events.service import get_current_event
from app.modules.submissions.support import (
    _require_participant,
    _submission_options,
)
from app.schemas import (
    StoredFileRead,
    SubmissionTargetsResponse,
)


def submission_targets(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    _require_participant(user)
    event = get_current_event(db)
    if get_phase_status(db, event).can("submission"):
        ensure_global_draw(db)
    assigned_song_ids = select(DrawAssignment.song_id).where(
        DrawAssignment.event_id == event.id,
        DrawAssignment.assigned_to_id == user.id,
        DrawAssignment.status == "active",
    )
    songs = list(
        db.scalars(
            select(Song)
            .options(selectinload(Song.submitter).selectinload(User.roles))
            .where(
                Song.event_id == event.id,
                or_(Song.submitted_by_id == user.id, Song.id.in_(assigned_song_ids)),
            )
            .order_by(Song.created_at.asc(), Song.id.asc())
        ).all()
    )
    submissions = list(
        db.scalars(
            select(Submission)
            .options(*_submission_options())
            .where(Submission.event_id == event.id, Submission.user_id == user.id)
        ).all()
    )
    by_song_id = {row.source_song_id: row for row in submissions if row.source_song_id is not None}
    submission_payloads = {
        row.id: payload for row, payload in zip(submissions, serialize_submissions(db, submissions), strict=False)
    }
    return {
        "is_open": get_phase_status(db, event).can("submission"),
        "targets": [
            {
                "song": serialize_song(song),
                "source_kind": "self" if song.submitted_by_id == user.id else "assigned",
                "submission": submission_payloads[by_song_id[song.id].id] if song.id in by_song_id else None,
            }
            for song in songs
        ],
    }


def my_submissions(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[dict]:
    _require_participant(user)
    event = get_current_event(db)
    rows = db.scalars(
        select(Submission)
        .options(*_submission_options())
        .where(Submission.event_id == event.id, Submission.user_id == user.id)
        .order_by(Submission.created_at.desc())
    ).all()
    return serialize_submissions(db, rows)


def register_listing_routes(router: APIRouter) -> None:
    router.get("/targets", response_model=SubmissionTargetsResponse)(submission_targets)
    router.get("", response_model=list[StoredFileRead])(my_submissions)
