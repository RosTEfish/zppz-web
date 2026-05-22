from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.models import GuessAuthorCandidate, GuessAuthorGuess, GuessChart, GuessComment, GuessVote, User
from app.modules.events.service import get_current_event


def vote_limit_for(db: Session, vote_type: str) -> int:
    settings = get_current_event(db).settings
    if vote_type == "love":
        return settings.true_love_vote_limit
    if vote_type == "funny":
        return settings.funny_vote_limit
    raise HTTPException(status_code=400, detail="投票类型只能是 love 或 funny")


def put_vote(db: Session, user_id: int, chart_id: int, vote_type: str) -> None:
    if not db.get(GuessChart, chart_id):
        raise HTTPException(status_code=404, detail="谱面不存在")
    if db.scalar(select(GuessVote).where(GuessVote.chart_id == chart_id, GuessVote.user_id == user_id, GuessVote.vote_type == vote_type)):
        return
    limit = vote_limit_for(db, vote_type)
    used = db.scalar(select(func.count()).select_from(GuessVote).where(GuessVote.user_id == user_id, GuessVote.vote_type == vote_type)) or 0
    if used >= limit:
        raise HTTPException(status_code=400, detail=f"你的 {vote_type} 投票额度已用完")
    db.add(GuessVote(chart_id=chart_id, user_id=user_id, vote_type=vote_type))
    db.commit()


def remove_vote(db: Session, user_id: int, chart_id: int, vote_type: str) -> None:
    row = db.scalar(select(GuessVote).where(GuessVote.chart_id == chart_id, GuessVote.user_id == user_id, GuessVote.vote_type == vote_type))
    if row:
        db.delete(row)
        db.commit()


def list_comments(db: Session, chart_id: int) -> list[GuessComment]:
    return list(
        db.scalars(
            select(GuessComment)
            .options(joinedload(GuessComment.user).joinedload(User.roles))
            .where(GuessComment.chart_id == chart_id)
            .order_by(GuessComment.created_at.desc())
        ).all()
    )


def set_author_candidates(db: Session, rows: list[dict]) -> int:
    event = get_current_event(db)
    db.query(GuessAuthorCandidate).filter(GuessAuthorCandidate.event_id == event.id).delete()
    for row in rows:
        db.add(GuessAuthorCandidate(event_id=event.id, user_id=int(row["user_id"]), display_id=str(row.get("display_id") or "")))
    db.commit()
    return len(rows)

