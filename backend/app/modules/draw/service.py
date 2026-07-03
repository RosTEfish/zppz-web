import random
import time

from fastapi import HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session, selectinload

from app.models import DrawAssignment, JTrackSubmission, Song, Submission, User
from app.modules.events.service import get_current_event


SELF_DRAW_MAX_ATTEMPTS = 3
SELF_DRAW_RETRY_DELAY_SECONDS = 0.04


def run_draw(db: Session, allow_redraw: bool = True) -> list[DrawAssignment]:
    event = get_current_event(db)
    _assert_draw_is_mutable(db, event.id, event.settings.submissions_open)
    existing = db.scalars(select(DrawAssignment).where(DrawAssignment.event_id == event.id)).first()
    if existing and not allow_redraw:
        raise HTTPException(status_code=400, detail="本赛事已经抽签，当前设置不允许重抽")

    participants = list(
        db.scalars(
            select(User).options(selectinload(User.roles)).where(User.identity == "participant", User.is_active.is_(True))
        ).all()
    )
    songs = db.scalars(select(Song).where(Song.event_id == event.id)).all()
    if not participants:
        raise HTTPException(status_code=400, detail="没有参赛者可以抽签")
    if not songs:
        raise HTTPException(status_code=400, detail="曲池为空")

    db.execute(delete(DrawAssignment).where(DrawAssignment.event_id == event.id))
    pool = songs[:]
    random.shuffle(pool)
    created: list[DrawAssignment] = []
    cursor = 0
    per_user = event.settings.draw_songs_per_participant
    for participant in participants:
        for _ in range(per_user):
            candidates = [song for song in pool if song.submitted_by_id != participant.id]
            if not candidates:
                candidates = pool[:]
            if not candidates:
                break
            song = candidates[cursor % len(candidates)]
            pool.remove(song)
            assignment = DrawAssignment(event_id=event.id, assigned_to_id=participant.id, song_id=song.id)
            db.add(assignment)
            created.append(assignment)
            cursor += 1
            if not pool:
                break
    db.commit()
    return get_draw_results(db)


def draw_for_user(db: Session, user: User) -> list[DrawAssignment]:
    user_id = user.id
    identity = user.identity
    if identity != "participant":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="只有参赛选手可以抽取曲目")

    for attempt in range(SELF_DRAW_MAX_ATTEMPTS):
        try:
            return _draw_for_user_once(db, user_id)
        except IntegrityError:
            db.rollback()
            if attempt == SELF_DRAW_MAX_ATTEMPTS - 1:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="多人同时抽取导致曲目占用冲突，请重试") from None
            time.sleep(SELF_DRAW_RETRY_DELAY_SECONDS * (attempt + 1))
        except OperationalError as exc:
            db.rollback()
            if not _is_retryable_operational_error(exc):
                raise
            if attempt == SELF_DRAW_MAX_ATTEMPTS - 1:
                raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="抽取请求过于密集，请稍后重试") from exc
            time.sleep(SELF_DRAW_RETRY_DELAY_SECONDS * (attempt + 1))
        except HTTPException:
            db.rollback()
            raise

    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="抽取失败，请重试")


def _draw_for_user_once(db: Session, user_id: int) -> list[DrawAssignment]:
    _begin_sqlite_immediate_transaction(db)
    event = get_current_event(db)
    _assert_draw_is_mutable(db, event.id, event.settings.submissions_open)
    locked_user_id = db.scalar(select(User.id).where(User.id == user_id, User.is_active.is_(True)).with_for_update())
    if not locked_user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="账号不可用")

    song_rows = db.execute(select(Song.id, Song.submitted_by_id).where(Song.event_id == event.id)).all()
    if not song_rows:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="曲池为空")

    occupied_song_ids = set(
        db.scalars(
            select(DrawAssignment.song_id).where(
                DrawAssignment.event_id == event.id,
                DrawAssignment.assigned_to_id != user_id,
            )
        ).all()
    )
    available = [(song_id, submitted_by_id) for song_id, submitted_by_id in song_rows if song_id not in occupied_song_ids]
    if not available:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="剩余曲库为空，请稍后再试")

    draw_count = min(max(event.settings.draw_songs_per_participant, 1), len(available))
    chosen_song_ids = _choose_song_ids(available, user_id, draw_count)

    db.execute(delete(DrawAssignment).where(DrawAssignment.event_id == event.id, DrawAssignment.assigned_to_id == user_id))
    assignments = [
        DrawAssignment(event_id=event.id, assigned_to_id=user_id, song_id=song_id)
        for song_id in chosen_song_ids
    ]
    db.add_all(assignments)
    db.commit()
    return get_draw_results(db, user_id)


def _choose_song_ids(song_rows: list[tuple[int, int]], user_id: int, draw_count: int) -> list[int]:
    preferred = [row for row in song_rows if row[1] != user_id]
    fallback = [row for row in song_rows if row[1] == user_id]
    if len(preferred) >= draw_count:
        chosen = random.sample(preferred, draw_count)
    else:
        chosen = random.sample(preferred, len(preferred)) + random.sample(fallback, draw_count - len(preferred))
        random.shuffle(chosen)
    return [song_id for song_id, _submitted_by_id in chosen]


def _begin_sqlite_immediate_transaction(db: Session) -> None:
    if db.get_bind().dialect.name != "sqlite":
        return
    db.rollback()
    db.connection().exec_driver_sql("BEGIN IMMEDIATE")


def _is_retryable_operational_error(exc: OperationalError) -> bool:
    message = str(exc).lower()
    return any(fragment in message for fragment in ("database is locked", "deadlock", "lock timeout", "could not serialize"))


def _assert_draw_is_mutable(db: Session, event_id: int, submissions_open: bool) -> None:
    if submissions_open:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="投稿已开放，不能重新抽签")
    has_submission = db.scalar(select(Submission.id).where(Submission.event_id == event_id).limit(1))
    has_legacy_j = db.scalar(select(JTrackSubmission.id).where(JTrackSubmission.event_id == event_id).limit(1))
    if has_submission or has_legacy_j:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="已有投稿文件，请先清空投稿后再重新抽签")


def get_draw_results(db: Session, user_id: int | None = None) -> list[DrawAssignment]:
    event = get_current_event(db)
    stmt = (
        select(DrawAssignment)
        .options(
            selectinload(DrawAssignment.assigned_to).selectinload(User.roles),
            selectinload(DrawAssignment.song).selectinload(Song.submitter).selectinload(User.roles),
        )
        .where(DrawAssignment.event_id == event.id)
        .order_by(DrawAssignment.created_at.desc())
    )
    if user_id:
        stmt = stmt.where(DrawAssignment.assigned_to_id == user_id)
    return list(db.scalars(stmt).all())
