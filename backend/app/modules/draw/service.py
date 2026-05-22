import random

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, joinedload

from app.models import DrawAssignment, Song, User
from app.modules.events.service import get_current_event


def run_draw(db: Session, allow_redraw: bool = True) -> list[DrawAssignment]:
    event = get_current_event(db)
    existing = db.scalars(select(DrawAssignment).where(DrawAssignment.event_id == event.id)).first()
    if existing and not allow_redraw:
        raise HTTPException(status_code=400, detail="本赛事已经抽签，当前设置不允许重抽")

    participants = db.scalars(select(User).where(User.identity == "participant", User.is_active.is_(True))).all()
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


def get_draw_results(db: Session, user_id: int | None = None) -> list[DrawAssignment]:
    event = get_current_event(db)
    stmt = (
        select(DrawAssignment)
        .options(
            joinedload(DrawAssignment.assigned_to).joinedload(User.roles),
            joinedload(DrawAssignment.song).joinedload(Song.submitter).joinedload(User.roles),
        )
        .where(DrawAssignment.event_id == event.id)
        .order_by(DrawAssignment.created_at.desc())
    )
    if user_id:
        stmt = stmt.where(DrawAssignment.assigned_to_id == user_id)
    return list(db.scalars(stmt).all())

