from __future__ import annotations

from datetime import datetime, timezone
import random

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session, selectinload

from app.core.security import SONG_POOL_IDENTITIES
from app.models import DrawAssignment, Event, JTrackSubmission, Song, Submission, User
from app.modules.events.phase_policy import get_phase_status
from app.modules.events.service import assert_song_pool_complete, get_current_event


DRAW_RETRY_ATTEMPTS = 3
DRAW_RETRY_DELAY_SECONDS = 0.04
DRAW_CATEGORIES = ("A", "B", "C")


def run_draw(db: Session, allow_redraw: bool = True) -> list[DrawAssignment]:
    """Run the administrator-facing global allocation.

    The old endpoint name is retained for the API surface, but allocation is now
    always global and never performed per participant.
    """
    for attempt in range(DRAW_RETRY_ATTEMPTS):
        try:
            return _run_global_draw_once(db, allow_redraw=allow_redraw)
        except IntegrityError:
            db.rollback()
            if attempt == DRAW_RETRY_ATTEMPTS - 1:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="全局分配发生并发冲突，请重试") from None
        except OperationalError as exc:
            db.rollback()
            if not _is_retryable_operational_error(exc):
                raise
            if attempt == DRAW_RETRY_ATTEMPTS - 1:
                raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="分配请求过于密集，请稍后重试") from exc
        except HTTPException:
            db.rollback()
            raise

    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="全局分配失败，请重试")


def ensure_global_draw(db: Session) -> None:
    """Lazily create the initial global allocation after registration closes.

    This is called by draw-dependent reads and writes rather than from a request
    middleware, so cached public event metadata remains side-effect free.
    """
    event = get_current_event(db)
    if not _draw_is_due(event, db):
        return

    if _has_complete_allocation(db, event):
        return

    phase = get_phase_status(db, event)
    if phase.active_phase == "submission_2" and _has_active_allocation(db, event):
        # Stage2 participants may intentionally return songs without drawing
        # replacements, so an incomplete active allocation is expected.
        return

    run_draw(db, allow_redraw=False)


def draw_for_user(db: Session, user: User) -> list[DrawAssignment]:
    """Compatibility guard for stale clients that still try personal drawing."""
    raise HTTPException(status_code=status.HTTP_410_GONE, detail="个人抽取已取消，请等待全局分配")


def _run_global_draw_once(db: Session, *, allow_redraw: bool) -> list[DrawAssignment]:
    _begin_sqlite_immediate_transaction(db)
    event = get_current_event(db)
    _lock_event_row(db, event.id)
    _assert_draw_is_mutable(db, event, allow_redraw=allow_redraw)
    assert_song_pool_complete(
        db,
        event.id,
        participant_limit=event.settings.participant_song_limit,
        audience_limit=event.settings.audience_song_limit,
    )

    participants = list(
        db.scalars(
            select(User)
            .options(selectinload(User.roles))
            .where(User.identity == "participant", User.is_active.is_(True))
            .order_by(User.id.asc())
        ).all()
    )
    allocation_complete = _has_complete_allocation(db, event)
    if not allow_redraw and not allocation_complete:
        # Repair partial legacy allocations atomically and keep their rows as
        # returned history instead of silently dropping them.
        _retire_active_assignments(db, event.id)

    songs = list(
        db.scalars(
            select(Song)
            .join(User, User.id == Song.submitted_by_id)
            .where(Song.event_id == event.id, User.identity.in_(SONG_POOL_IDENTITIES))
        ).all()
    )
    if not participants:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="没有可参与全局分配的选手")
    if not songs:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="曲池为空")

    if allocation_complete:
        if not allow_redraw:
            return _load_draw_results(db)
        # Explicit administrator redraws intentionally replace only active
        # allocation rows. Historical assignment rows remain queryable.
        _retire_active_assignments(db, event.id)
    elif not allow_redraw and db.scalar(
        select(DrawAssignment.id).where(
            DrawAssignment.event_id == event.id,
            DrawAssignment.status == "active",
        )
    ):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="已有不完整分配，请由管理员手动重新全局分配")
    elif allow_redraw:
        _retire_active_assignments(db, event.id)

    per_user = max(event.settings.draw_songs_per_participant, 1)
    slots = [(participant.id, slot) for participant in participants for slot in range(per_user)]
    if len(songs) < len(slots):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="曲池曲目数量不足，无法完成全局分配")

    randomizer = random.Random()
    available_ids = [song.id for song in songs]
    song_by_id = {song.id: song for song in songs}
    candidates: dict[int, list[int]] = {}
    category_order_by_user: dict[int, list[str]] = {}
    for user_id, _slot in slots:
        if user_id not in category_order_by_user:
            category_order = list(DRAW_CATEGORIES)
            randomizer.shuffle(category_order)
            category_order_by_user[user_id] = category_order
    for slot_index, (user_id, slot) in enumerate(slots):
        choices = [song_id for song_id in available_ids if song_by_id[song_id].submitted_by_id != user_id]
        preferred_category = category_order_by_user[user_id][slot % len(DRAW_CATEGORIES)]
        preferred = [song_id for song_id in choices if song_by_id[song_id].song_type.upper() == preferred_category]
        fallback = [song_id for song_id in choices if song_by_id[song_id].song_type.upper() != preferred_category]
        randomizer.shuffle(preferred)
        randomizer.shuffle(fallback)
        # Keep the global matching algorithm as the hard constraint, while
        # ordering candidates so each participant's slots prefer A/B/C in a
        # shuffled, non-repeating cycle before falling back to other types.
        candidates[slot_index] = preferred + fallback

    song_to_slot: dict[int, int] = {}

    def assign(slot_index: int, visited: set[int]) -> bool:
        for song_id in candidates[slot_index]:
            if song_id in visited:
                continue
            visited.add(song_id)
            previous = song_to_slot.get(song_id)
            if previous is None or assign(previous, visited):
                song_to_slot[song_id] = slot_index
                return True
        return False

    slot_order = list(range(len(slots)))
    randomizer.shuffle(slot_order)
    for slot_index in slot_order:
        if not assign(slot_index, set()):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="排除自投曲目后无法完成全局分配")

    slot_to_song = {slot_index: song_id for song_id, slot_index in song_to_slot.items()}
    assignments = [
        DrawAssignment(
            event_id=event.id,
            assigned_to_id=user_id,
            song_id=slot_to_song[slot_index],
            status="active",
            draw_kind="initial",
        )
        for slot_index, (user_id, _slot) in enumerate(slots)
    ]
    db.add_all(assignments)
    db.commit()
    return _load_draw_results(db)


def _draw_is_due(event, db: Session) -> bool:
    phase = get_phase_status(db, event)
    now = datetime.utcnow()
    registration = next((row for row in event.phases if row.phase == "registration"), None)
    if registration and _utc_naive(registration.ends_at) > now:
        return False
    if _has_submission(db, event.id):
        return False
    if phase.active_phase in {"submission_1", "submission_2"}:
        return True
    if event.settings.phase_mode != "auto":
        return False
    guess = next((row for row in event.phases if row.phase == "guess"), None)
    if guess:
        return _utc_naive(guess.starts_at) > now
    scheduled_ends = [_utc_naive(row.ends_at) for row in event.phases]
    return bool(scheduled_ends) and max(scheduled_ends) > now


def _has_complete_allocation(db: Session, event) -> bool:
    participants = list(db.scalars(select(User.id).where(User.identity == "participant", User.is_active.is_(True))).all())
    if not participants:
        return False
    per_user = max(event.settings.draw_songs_per_participant, 1)
    rows = list(
        db.execute(
            select(DrawAssignment.assigned_to_id, DrawAssignment.song_id, Song.submitted_by_id)
            .join(Song, Song.id == DrawAssignment.song_id)
            .where(DrawAssignment.event_id == event.id, DrawAssignment.status == "active")
        ).all()
    )
    if len(rows) != len(participants) * per_user:
        return False
    participant_ids = set(participants)
    counts: dict[int, int] = {}
    song_ids: set[int] = set()
    for assigned_to_id, song_id, _submitted_by_id in rows:
        if assigned_to_id not in participant_ids or song_id in song_ids:
            return False
        song_ids.add(song_id)
        counts[assigned_to_id] = counts.get(assigned_to_id, 0) + 1
    return all(counts.get(user_id, 0) == per_user for user_id in participants)


def _has_active_allocation(db: Session, event) -> bool:
    return bool(
        db.scalar(
            select(DrawAssignment.id).where(
                DrawAssignment.event_id == event.id,
                DrawAssignment.status == "active",
            ).limit(1)
        )
    )


def _has_submission(db: Session, event_id: int) -> bool:
    return bool(
        db.scalar(select(Submission.id).where(Submission.event_id == event_id).limit(1))
        or db.scalar(select(JTrackSubmission.id).where(JTrackSubmission.event_id == event_id).limit(1))
    )


def _begin_sqlite_immediate_transaction(db: Session) -> None:
    if db.get_bind().dialect.name != "sqlite":
        return
    db.rollback()
    db.connection().exec_driver_sql("BEGIN IMMEDIATE")


def _lock_event_row(db: Session, event_id: int) -> None:
    """Serialize allocation writers on databases that support row-level locks."""
    db.scalar(select(Event.id).where(Event.id == event_id).with_for_update())


def _retire_active_assignments(db: Session, event_id: int, assigned_to_id: int | None = None) -> None:
    """Keep old allocation rows as returned history instead of deleting them."""
    stmt = select(DrawAssignment.id).where(
        DrawAssignment.event_id == event_id,
        DrawAssignment.status == "active",
    )
    if assigned_to_id is not None:
        stmt = stmt.where(DrawAssignment.assigned_to_id == assigned_to_id)
    active_ids = list(db.scalars(stmt).all())
    if active_ids:
        db.execute(
            update(DrawAssignment)
            .where(DrawAssignment.id.in_(active_ids))
            .values(status="returned")
        )


def _is_retryable_operational_error(exc: OperationalError) -> bool:
    message = str(exc).lower()
    return any(fragment in message for fragment in ("database is locked", "deadlock", "lock timeout", "could not serialize"))


def _assert_draw_is_mutable(db: Session, event, *, allow_redraw: bool) -> None:
    phase = get_phase_status(db, event)
    allowed_phases = {"submission_1"} if allow_redraw else {"submission_1", "submission_2"}
    if phase.active_phase not in allowed_phases and not _draw_is_due(event, db):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="全局分配仅允许在投稿阶段开始后执行")
    if _has_submission(db, event.id):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="已有投稿，不能重新全局分配")


def _load_draw_results(db: Session, user_id: int | None = None) -> list[DrawAssignment]:
    event = get_current_event(db)
    stmt = (
        select(DrawAssignment)
        .options(
            selectinload(DrawAssignment.assigned_to).selectinload(User.roles),
            selectinload(DrawAssignment.song).selectinload(Song.submitter).selectinload(User.roles),
        )
        .where(DrawAssignment.event_id == event.id)
        .where(DrawAssignment.status == "active")
        .order_by(DrawAssignment.created_at.desc(), DrawAssignment.id.desc())
    )
    if user_id is not None:
        stmt = stmt.where(DrawAssignment.assigned_to_id == user_id)
    return list(db.scalars(stmt).all())


def get_draw_results(db: Session, user_id: int | None = None) -> list[DrawAssignment]:
    event = get_current_event(db)
    phase = get_phase_status(db, event)
    if phase.active_phase in {"submission_1", "submission_2"}:
        ensure_global_draw(db)
    return _load_draw_results(db, user_id)


def _utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)
