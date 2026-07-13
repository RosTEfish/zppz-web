from fastapi import HTTPException
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session, selectinload

from app.models import GuessAuthorCandidate, GuessChart, GuessComment, GuessVote, User
from app.modules.events.service import get_current_event
from app.modules.guess_game.vote_quota import love_vote_bucket, love_vote_quota


def vote_limit_for(db: Session, vote_type: str, level: str = "") -> int:
    settings = get_current_event(db).settings
    if vote_type == "love":
        bucket = love_vote_bucket(level)
        return (
            settings.true_love_vote_limit_below_14
            if bucket == "below_14"
            else settings.true_love_vote_limit_at_least_14
        )
    if vote_type == "funny":
        return settings.funny_vote_limit
    raise HTTPException(status_code=400, detail="投票类型只能是 love 或 funny")


def put_vote(db: Session, user_id: int, chart_id: int, vote_type: str) -> None:
    event = get_current_event(db)
    # Serialize quota-changing writes for the same account on PostgreSQL.
    # SQLite ignores FOR UPDATE; the production concurrency guarantee targets
    # PostgreSQL because SQLite does not provide row-level locks.
    db.scalar(select(User.id).where(User.id == user_id).with_for_update())
    chart = db.scalar(
        select(GuessChart).where(GuessChart.id == chart_id, GuessChart.event_id == event.id)
    )
    if not chart:
        raise HTTPException(status_code=404, detail="谱面不存在")
    if db.scalar(
        select(GuessVote).where(
            GuessVote.chart_id == chart_id,
            GuessVote.user_id == user_id,
            GuessVote.vote_type == vote_type,
        )
    ):
        return
    if vote_type == "love":
        bucket = love_vote_bucket(chart.level)
        quota = love_vote_quota(db, user_id, event)
        limit = vote_limit_for(db, vote_type, chart.level)
        used = quota[bucket]["used"]
    elif vote_type == "funny":
        limit = vote_limit_for(db, vote_type)
        used = db.scalar(
            select(func.count())
            .select_from(GuessVote)
            .join(GuessChart, GuessChart.id == GuessVote.chart_id)
            .where(
                GuessChart.event_id == event.id,
                GuessChart.source_submission_type != "exhibition",
                GuessVote.user_id == user_id,
                GuessVote.vote_type == "funny",
            )
        ) or 0
    else:
        raise HTTPException(status_code=400, detail="投票类型只能是 love 或 funny")
    if used >= limit:
        if vote_type == "love":
            label = "<14 真爱票" if bucket == "below_14" else "≥14 真爱票"
        else:
            label = "欢乐票"
        raise HTTPException(status_code=400, detail=f"你的 {label}额度已用完")
    db.add(GuessVote(chart_id=chart_id, user_id=user_id, vote_type=vote_type))
    db.commit()


def remove_vote(db: Session, user_id: int, chart_id: int, vote_type: str) -> None:
    row = db.scalar(select(GuessVote).where(GuessVote.chart_id == chart_id, GuessVote.user_id == user_id, GuessVote.vote_type == vote_type))
    if row:
        db.delete(row)
        db.commit()


def vote_state(db: Session, user_id: int, chart_id: int) -> dict:
    rows = db.execute(
        select(
            GuessVote.vote_type,
            func.count(GuessVote.id),
            func.max(case((GuessVote.user_id == user_id, 1), else_=0)),
        )
        .where(GuessVote.chart_id == chart_id)
        .group_by(GuessVote.vote_type)
    ).all()
    counts = {"love": 0, "funny": 0}
    my_votes: list[str] = []
    for vote_type, count, selected in rows:
        vote_type = str(vote_type)
        counts[vote_type] = int(count)
        if selected:
            my_votes.append(vote_type)
    return {
        "vote_counts": counts,
        "my_votes": sorted(my_votes),
        "love_vote_quota": love_vote_quota(db, user_id),
    }


def list_comments(db: Session, chart_id: int) -> list[GuessComment]:
    return list(
        db.scalars(
            select(GuessComment)
            .options(selectinload(GuessComment.user).selectinload(User.roles))
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
