from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models import DrawAssignment, Event, EventSetting, User
from app.schemas import EventUpdate


def get_current_event(db: Session) -> Event:
    event = db.scalar(select(Event).options(joinedload(Event.settings)).where(Event.is_current.is_(True)))
    if not event:
        event = Event(name="这谱谱这正赛", slug="zppz-current", is_current=True)
        event.settings = EventSetting()
        db.add(event)
        db.commit()
        db.refresh(event)
    if not event.settings:
        event.settings = EventSetting(event_id=event.id)
        db.commit()
        db.refresh(event)
    return event


def update_current_event(db: Session, payload: EventUpdate) -> Event:
    event = get_current_event(db)
    if payload.submissions_open:
        participants = [
            user
            for user in
            db.scalars(
                select(User)
                .options(selectinload(User.roles))
                .where(User.identity == "participant", User.is_active.is_(True))
                .order_by(User.user_code)
            ).all()
            if not user.has_role("admin")
        ]
        assignment_counts = dict(
            db.execute(
                select(DrawAssignment.assigned_to_id, func.count(DrawAssignment.id))
                .where(DrawAssignment.event_id == event.id)
                .group_by(DrawAssignment.assigned_to_id)
            ).all()
        )
        missing = [
            participant.user_code
            for participant in participants
            if assignment_counts.get(participant.id, 0) < payload.draw_songs_per_participant
        ]
        if missing:
            preview = "、".join(missing[:8])
            suffix = "等" if len(missing) > 8 else ""
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"以下参赛者尚未完成抽签：{preview}{suffix}",
            )
    event.name = payload.name
    settings = event.settings
    settings.participant_song_limit = payload.participant_song_limit
    settings.audience_song_limit = payload.audience_song_limit
    settings.draw_songs_per_participant = payload.draw_songs_per_participant
    settings.true_love_vote_limit = payload.true_love_vote_limit
    settings.funny_vote_limit = payload.funny_vote_limit
    settings.announcement_text = payload.announcement_text
    settings.registration_deadline = payload.registration_deadline
    settings.submission_deadline = payload.submission_deadline
    settings.guess_game_open_at = payload.guess_game_open_at
    settings.submissions_open = payload.submissions_open
    settings.guess_game_visible = payload.guess_game_visible
    db.commit()
    db.refresh(event)
    return event


def assert_song_limit(db: Session, user_id: int, identity: str) -> None:
    from app.models import Song

    event = get_current_event(db)
    limit = event.settings.participant_song_limit if identity == "participant" else event.settings.audience_song_limit
    count = db.scalar(select(func.count()).select_from(Song).where(Song.event_id == event.id, Song.submitted_by_id == user_id))
    if (count or 0) >= limit:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"当前身份最多可提交 {limit} 首曲目")
