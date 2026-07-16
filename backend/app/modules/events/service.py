from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.core.security import has_admin_access
from app.models import DrawAssignment, Event, EventPhase, EventSetting, Song, SwapRound, User
from app.modules.events.phase_policy import PHASES, get_phase_status, phase_status_payload
from app.schemas import EventPhasesUpdate, EventUpdate


def get_current_event(db: Session) -> Event:
    event = db.info.get("current_event")
    if event is None:
        event = db.scalar(
            select(Event)
            .options(joinedload(Event.settings), selectinload(Event.phases))
            .where(Event.is_current.is_(True))
        )
    if not event:
        event = Event(name="这谱谱这 #5", slug="zppz-current", is_current=True)
        event.settings = EventSetting()
        db.add(event)
        db.commit()
        db.refresh(event)
    db.info["current_event"] = event
    if not event.settings:
        event.settings = EventSetting(event_id=event.id)
        db.commit()
        db.refresh(event)
    return event


def update_current_event(db: Session, payload: EventUpdate) -> Event:
    event = get_current_event(db)
    submissions_will_be_open = get_phase_status(db, event).can("submission")
    if submissions_will_be_open:
        assert_submission_ready(
            db,
            event.id,
            participant_limit=payload.participant_song_limit,
            audience_limit=payload.audience_song_limit,
            draw_songs_per_participant=payload.draw_songs_per_participant,
        )
    event.name = payload.name
    settings = event.settings
    settings.participant_song_limit = payload.participant_song_limit
    settings.audience_song_limit = payload.audience_song_limit
    settings.draw_songs_per_participant = payload.draw_songs_per_participant
    settings.true_love_vote_limit_below_14 = payload.true_love_vote_limit_below_14
    settings.true_love_vote_limit_at_least_14 = payload.true_love_vote_limit_at_least_14
    settings.funny_vote_limit = payload.funny_vote_limit
    settings.announcement_text = payload.announcement_text
    db.commit()
    db.refresh(event)
    return event


def _utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _utc_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _validate_phase_rows(payload: EventPhasesUpdate) -> list[tuple[str, datetime, datetime]]:
    if len(payload.phases) > len(PHASES):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Too many phase windows")
    names: set[str] = set()
    rows: list[tuple[str, datetime, datetime]] = []
    for item in payload.phases:
        starts_at = _utc_naive(item.starts_at)
        ends_at = _utc_naive(item.ends_at)
        if item.phase in names:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Duplicate phase window: {item.phase}",
            )
        if starts_at >= ends_at:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid time window for phase: {item.phase}",
            )
        names.add(item.phase)
        rows.append((item.phase, starts_at, ends_at))
    rows.sort(key=lambda row: (row[1], row[2]))
    for previous, current in zip(rows, rows[1:]):
        if current[1] < previous[2]:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Phase windows overlap: {previous[0]} and {current[0]}",
            )
    return rows


def get_phase_schedule(db: Session, event: Event | None = None) -> dict:
    event = event or get_current_event(db)
    status_payload = phase_status_payload(get_phase_status(db, event))
    return {
        "event_id": event.id,
        "phase_mode": event.settings.phase_mode,
        "manual_phase": event.settings.manual_phase,
        "timezone": "Asia/Shanghai",
        "server_time": datetime.now(timezone.utc),
        "phases": [
            {
                "id": row.id,
                "phase": row.phase,
                "starts_at": _utc_aware(row.starts_at),
                "ends_at": _utc_aware(row.ends_at),
            }
            for row in sorted(event.phases, key=lambda item: (item.starts_at, item.ends_at))
            if row.phase in PHASES
        ],
        **status_payload,
    }


def update_phase_schedule(db: Session, payload: EventPhasesUpdate) -> dict:
    event = get_current_event(db)
    rows = _validate_phase_rows(payload)
    db.scalar(
        select(EventSetting)
        .where(EventSetting.event_id == event.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    db.expire(event, ["phases"])
    existing_by_phase = {row.phase: row for row in event.phases}
    requested_phases = {phase for phase, _, _ in rows}
    for row in list(event.phases):
        if row.phase not in requested_phases:
            event.phases.remove(row)
    for phase, starts_at, ends_at in rows:
        row = existing_by_phase.get(phase)
        if row is None:
            event.phases.append(
                EventPhase(event_id=event.id, phase=phase, starts_at=starts_at, ends_at=ends_at)
            )
        else:
            row.starts_at = starts_at
            row.ends_at = ends_at
    event.settings.phase_mode = payload.phase_mode
    event.settings.manual_phase = payload.manual_phase if payload.phase_mode == "manual" else None
    db.flush()
    swap_window = next((row for row in rows if row[0] == "swap"), None)
    open_swap_round = db.scalar(
        select(SwapRound).where(SwapRound.event_id == event.id, SwapRound.status == "open")
    )
    if open_swap_round and swap_window:
        open_swap_round.starts_at = swap_window[1]
        open_swap_round.ends_at = swap_window[2]
    db.commit()
    event = get_current_event(db)
    return get_phase_schedule(db, event)


def incomplete_song_pool_users(
    db: Session,
    event_id: int,
    *,
    participant_limit: int,
    audience_limit: int,
) -> list[tuple[User, int, int]]:
    users = list(
        db.scalars(
            select(User)
            .where(User.is_active.is_(True))
            .order_by(User.user_code.asc())
        ).all()
    )
    song_counts = dict(
        db.execute(
            select(Song.submitted_by_id, func.count(Song.id))
            .where(Song.event_id == event_id)
            .group_by(Song.submitted_by_id)
        ).all()
    )
    incomplete: list[tuple[User, int, int]] = []
    for user in users:
        limit = participant_limit if user.identity == "participant" else audience_limit
        count = int(song_counts.get(user.id, 0))
        if count < limit:
            incomplete.append((user, count, limit))
    return incomplete


def assert_song_pool_complete(
    db: Session,
    event_id: int,
    *,
    participant_limit: int,
    audience_limit: int,
) -> None:
    incomplete = incomplete_song_pool_users(
        db,
        event_id,
        participant_limit=participant_limit,
        audience_limit=audience_limit,
    )
    if not incomplete:
        return
    preview = "、".join(f"{user.user_code}（{count}/{limit}）" for user, count, limit in incomplete[:10])
    suffix = f" 等 {len(incomplete)} 人" if len(incomplete) > 10 else ""
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=f"以下账号尚未投满曲池：{preview}{suffix}",
    )


def assert_submission_ready(
    db: Session,
    event_id: int,
    *,
    participant_limit: int,
    audience_limit: int,
    draw_songs_per_participant: int,
) -> None:
    assert_song_pool_complete(
        db,
        event_id,
        participant_limit=participant_limit,
        audience_limit=audience_limit,
    )
    participants = [
        user
        for user in db.scalars(
            select(User)
            .options(selectinload(User.roles))
            .where(User.identity == "participant", User.is_active.is_(True))
            .order_by(User.user_code)
        ).all()
        if not has_admin_access(user)
    ]
    assignment_counts = dict(
        db.execute(
            select(DrawAssignment.assigned_to_id, func.count(DrawAssignment.id))
            .where(DrawAssignment.event_id == event_id, DrawAssignment.status == "active")
            .group_by(DrawAssignment.assigned_to_id)
        ).all()
    )
    missing = [
        participant.user_code
        for participant in participants
        if assignment_counts.get(participant.id, 0) < draw_songs_per_participant
    ]
    if missing:
        preview = "、".join(missing[:8])
        suffix = "等" if len(missing) > 8 else ""
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"以下参赛者尚未完成抽签：{preview}{suffix}",
        )


def assert_song_limit(db: Session, user_id: int, identity: str) -> None:
    from app.models import Song

    event = get_current_event(db)
    limit = event.settings.participant_song_limit if identity == "participant" else event.settings.audience_song_limit
    count = db.scalar(select(func.count()).select_from(Song).where(Song.event_id == event.id, Song.submitted_by_id == user_id))
    if (count or 0) >= limit:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"当前身份最多可提交 {limit} 首曲目")
