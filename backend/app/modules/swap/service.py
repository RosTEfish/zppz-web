from __future__ import annotations

from datetime import datetime, timezone
import random
from secrets import token_hex

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models import (
    DrawAssignment,
    Event,
    EventPhase,
    Song,
    Submission,
    SwapExcludedSong,
    SwapRequest,
    SwapRequestItem,
    SwapRound,
    User,
)
from app.modules.draw.service import ensure_global_draw
from app.modules.events.phase_policy import get_phase_status
from app.modules.events.service import get_current_event


def _begin_write_transaction(db: Session) -> None:
    if db.get_bind().dialect.name != "sqlite":
        return
    db.rollback()
    db.connection().exec_driver_sql("BEGIN IMMEDIATE")


def _stage2_window(db: Session, event_id: int) -> tuple[datetime, datetime]:
    phase = db.scalar(select(EventPhase).where(EventPhase.event_id == event_id, EventPhase.phase == "submission_2"))
    if not phase:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="尚未配置 Stage2 时间")
    return phase.starts_at, phase.ends_at


def _round_options():
    return (
        selectinload(SwapRound.requests)
        .selectinload(SwapRequest.items)
        .selectinload(SwapRequestItem.original_assignment)
        .selectinload(DrawAssignment.assigned_to)
        .selectinload(User.roles),
        selectinload(SwapRound.requests)
        .selectinload(SwapRequest.items)
        .selectinload(SwapRequestItem.original_assignment)
        .selectinload(DrawAssignment.song)
        .selectinload(Song.submitter)
        .selectinload(User.roles),
        selectinload(SwapRound.requests)
        .selectinload(SwapRequest.items)
        .selectinload(SwapRequestItem.replacement_assignment)
        .selectinload(DrawAssignment.assigned_to)
        .selectinload(User.roles),
        selectinload(SwapRound.requests)
        .selectinload(SwapRequest.items)
        .selectinload(SwapRequestItem.replacement_assignment)
        .selectinload(DrawAssignment.song)
        .selectinload(Song.submitter)
        .selectinload(User.roles),
        selectinload(SwapRound.requests).selectinload(SwapRequest.user).selectinload(User.roles),
    )


def get_swap_rounds(db: Session, event_id: int) -> list[SwapRound]:
    return list(
        db.scalars(
            select(SwapRound)
            .options(*_round_options())
            .where(SwapRound.event_id == event_id)
            .order_by(SwapRound.round_number.desc(), SwapRound.id.desc())
        ).all()
    )


def get_swap_round(db: Session, event_id: int) -> SwapRound | None:
    return next(iter(get_swap_rounds(db, event_id)), None)


def _latest_continuous_round(db: Session, event_id: int) -> SwapRound | None:
    return db.scalar(
        select(SwapRound)
        .where(SwapRound.event_id == event_id, SwapRound.round_kind == "continuous")
        .order_by(SwapRound.round_number.desc(), SwapRound.id.desc())
        .limit(1)
    )


def ensure_continuous_round(db: Session, event_id: int) -> SwapRound:
    existing = _latest_continuous_round(db, event_id)
    stage2_start, stage2_end = _stage2_window(db, event_id)
    if existing and existing.status == "open":
        existing.starts_at = stage2_start
        existing.roll_ends_at = stage2_end
        return existing

    max_round = db.scalar(select(func.max(SwapRound.round_number)).where(SwapRound.event_id == event_id)) or 0
    row = SwapRound(
        event_id=event_id,
        round_number=int(max_round) + 1,
        starts_at=stage2_start,
        # Keep the legacy column as the original-style timestamp while the new
        # effective deadline lives in roll_ends_at.
        ends_at=stage2_end,
        roll_ends_at=stage2_end,
        round_kind="continuous",
        status="open",
        random_seed=token_hex(24),
    )
    db.add(row)
    db.flush()
    return row


def active_assignments_for_user(db: Session, event_id: int, user_id: int) -> list[DrawAssignment]:
    return list(
        db.scalars(
            select(DrawAssignment)
            .options(selectinload(DrawAssignment.song).selectinload(Song.submitter).selectinload(User.roles))
            .where(
                DrawAssignment.event_id == event_id,
                DrawAssignment.assigned_to_id == user_id,
                DrawAssignment.status == "active",
            )
            .order_by(DrawAssignment.created_at.asc(), DrawAssignment.id.asc())
        ).all()
    )


def roll_for_user(db: Session, user: User, assignment_ids: list[int]) -> tuple[SwapRound, SwapRequest]:
    try:
        return _roll_for_user_once(db, user, assignment_ids)
    except HTTPException:
        db.rollback()
        raise


def _roll_for_user_once(db: Session, user: User, assignment_ids: list[int]) -> tuple[SwapRound, SwapRequest]:
    if user.identity != "participant":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="只有参赛者可以换曲")
    if not assignment_ids or len(set(assignment_ids)) != len(assignment_ids):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="请选择不重复的当前曲目")

    event = get_current_event(db)
    phase = get_phase_status(db, event)
    if not phase.can("swap"):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="当前不在 Stage2 换曲时间")

    ensure_global_draw(db)
    _begin_write_transaction(db)
    event = get_current_event(db)
    phase = get_phase_status(db, event)
    if not phase.can("swap"):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="当前不在 Stage2 换曲时间")

    # The event row serializes all pool mutations on PostgreSQL; SQLite is
    # serialized by BEGIN IMMEDIATE above.
    db.scalar(select(Event.id).where(Event.id == event.id).with_for_update())
    round_row = ensure_continuous_round(db, event.id)
    if round_row.status != "open" or not _round_is_open(round_row):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Stage2 换曲时间已结束")

    assignments = list(
        db.scalars(
            select(DrawAssignment)
            .options(selectinload(DrawAssignment.song))
            .where(
                DrawAssignment.id.in_(assignment_ids),
                DrawAssignment.event_id == event.id,
                DrawAssignment.assigned_to_id == user.id,
                DrawAssignment.status == "active",
            )
            .with_for_update()
        ).all()
    )
    by_id = {row.id: row for row in assignments}
    if len(by_id) != len(assignment_ids):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="部分曲目已失效，请刷新后重试")

    submitted_song_ids = set(
        db.scalars(
            select(Submission.source_song_id).where(
                Submission.event_id == event.id,
                Submission.user_id == user.id,
                Submission.source_song_id.in_([row.song_id for row in assignments]),
            )
        ).all()
    )
    if submitted_song_ids:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="已投稿曲目不能换曲，请先删除对应投稿")

    selected_ids = set(assignment_ids)
    active_assignments = list(
        db.scalars(
            select(DrawAssignment).where(
                DrawAssignment.event_id == event.id,
                DrawAssignment.status == "active",
            )
        ).all()
    )
    occupied_song_ids = {row.song_id for row in active_assignments if row.id not in selected_ids}
    songs = list(db.scalars(select(Song).where(Song.event_id == event.id)).all())
    pool = [song for song in songs if song.id not in occupied_song_ids]

    excluded_song_ids = set(
        db.scalars(
            select(SwapExcludedSong.song_id).where(
                SwapExcludedSong.event_id == event.id,
                SwapExcludedSong.user_id == user.id,
            )
        ).all()
    )
    excluded_song_ids.update(row.song_id for row in assignments)
    candidates = [
        song
        for song in pool
        if song.id not in excluded_song_ids and song.submitted_by_id != user.id
    ]
    if len(candidates) < len(assignments):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="换曲池中没有足够的新曲目")

    chosen_songs = random.SystemRandom().sample(candidates, len(assignments))
    for original in assignments:
        original.status = "returned"

    request = SwapRequest(round_id=round_row.id, user_id=user.id, status="completed", error_message="")
    db.add(request)
    db.flush()
    for position, original in enumerate(assignments):
        already_excluded = db.scalar(
            select(SwapExcludedSong.id).where(
                SwapExcludedSong.event_id == event.id,
                SwapExcludedSong.user_id == user.id,
                SwapExcludedSong.song_id == original.song_id,
            )
        )
        if already_excluded is None:
            db.add(
                SwapExcludedSong(
                    event_id=event.id,
                    user_id=user.id,
                    song_id=original.song_id,
                )
            )
        replacement = DrawAssignment(
            event_id=event.id,
            assigned_to_id=user.id,
            song_id=chosen_songs[position].id,
            status="active",
            draw_kind="swap",
            replaces_assignment_id=original.id,
        )
        db.add(replacement)
        db.flush()
        db.add(
            SwapRequestItem(
                request_id=request.id,
                original_assignment_id=original.id,
                replacement_assignment_id=replacement.id,
                position=position,
            )
        )

    db.commit()
    rounds = get_swap_rounds(db, event.id)
    current = next((row for row in rounds if row.id == round_row.id), None)
    if current is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="换曲记录读取失败")
    saved_request = next((row for row in current.requests if row.id == request.id), None)
    if saved_request is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="换曲结果读取失败")
    return current, saved_request


def _round_is_open(round_row: SwapRound) -> bool:
    end = round_row.roll_ends_at or round_row.ends_at
    return _utc_naive(end) > datetime.utcnow()


def _utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)
