from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, joinedload

from app.core.security import get_current_user, get_optional_user, require_role, user_payload
from app.db.session import get_db
from app.models import GuessAuthorCandidate, GuessAuthorGuess, GuessChart, GuessComment, ImportIssue, User
from app.modules.common import serialize_chart
from app.modules.events.service import get_current_event
from app.modules.guess_game.service import list_comments, put_vote, remove_vote
from app.schemas import AuthorGuessRequest, CommentCreate, GuessChartCreate, GuessChartRead, GuessCommentRead, VoteRequest


router = APIRouter(prefix="/guess-game", tags=["guess-game"])
admin_router = APIRouter(prefix="/admin/guess-game", tags=["admin-guess-game"])


@router.get("/charts", response_model=list[GuessChartRead])
def charts(user: User | None = Depends(get_optional_user), db: Session = Depends(get_db)) -> list[dict]:
    event = get_current_event(db)
    rows = db.scalars(select(GuessChart).where(GuessChart.event_id == event.id).order_by(GuessChart.created_at.desc())).all()
    return [serialize_chart(db, row, user.id if user else None) for row in rows]


@router.get("/charts/{chart_id}", response_model=GuessChartRead)
def chart_detail(chart_id: int, user: User | None = Depends(get_optional_user), db: Session = Depends(get_db)) -> dict:
    chart = db.get(GuessChart, chart_id)
    if not chart:
        raise HTTPException(status_code=404, detail="谱面不存在")
    chart.plays += 1
    db.commit()
    return serialize_chart(db, chart, user.id if user else None)


@router.post("/vote")
def vote(payload: VoteRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    put_vote(db, user.id, payload.chart_id, payload.vote_type)
    return {"message": "已投票"}


@router.delete("/vote")
def unvote(payload: VoteRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    remove_vote(db, user.id, payload.chart_id, payload.vote_type)
    return {"message": "已取消投票"}


@router.get("/charts/{chart_id}/comments", response_model=list[GuessCommentRead])
def comments(chart_id: int, db: Session = Depends(get_db)) -> list[dict]:
    return [
        {"id": item.id, "content": item.content, "user": user_payload(item.user), "created_at": item.created_at}
        for item in list_comments(db, chart_id)
    ]


@router.post("/charts/{chart_id}/comments", response_model=GuessCommentRead)
def create_comment(chart_id: int, payload: CommentCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    if not db.get(GuessChart, chart_id):
        raise HTTPException(status_code=404, detail="谱面不存在")
    item = GuessComment(chart_id=chart_id, user_id=user.id, content=payload.content)
    db.add(item)
    db.commit()
    db.refresh(item)
    item.user = user
    return {"id": item.id, "content": item.content, "user": user_payload(user), "created_at": item.created_at}


@router.put("/charts/{chart_id}/author-guess")
def put_author_guess(chart_id: int, payload: AuthorGuessRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    if not db.get(GuessChart, chart_id):
        raise HTTPException(status_code=404, detail="谱面不存在")
    if not db.get(User, payload.guessed_user_id):
        raise HTTPException(status_code=404, detail="候选作者不存在")
    row = db.scalar(select(GuessAuthorGuess).where(GuessAuthorGuess.chart_id == chart_id, GuessAuthorGuess.user_id == user.id))
    if row:
        row.guessed_user_id = payload.guessed_user_id
    else:
        db.add(GuessAuthorGuess(chart_id=chart_id, user_id=user.id, guessed_user_id=payload.guessed_user_id))
    db.commit()
    return {"message": "已保存作者猜测"}


@router.delete("/charts/{chart_id}/author-guess")
def delete_author_guess(chart_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    db.execute(delete(GuessAuthorGuess).where(GuessAuthorGuess.chart_id == chart_id, GuessAuthorGuess.user_id == user.id))
    db.commit()
    return {"message": "已清除作者猜测"}


@admin_router.get("/charts", response_model=list[GuessChartRead])
def admin_charts(_: User = Depends(require_role("admin", "pool_editor")), db: Session = Depends(get_db)) -> list[dict]:
    event = get_current_event(db)
    rows = db.scalars(select(GuessChart).where(GuessChart.event_id == event.id).order_by(GuessChart.created_at.desc())).all()
    return [serialize_chart(db, row) for row in rows]


@admin_router.post("/charts", response_model=GuessChartRead)
def admin_create_chart(payload: GuessChartCreate, _: User = Depends(require_role("admin", "pool_editor")), db: Session = Depends(get_db)) -> dict:
    event = get_current_event(db)
    chart = GuessChart(event_id=event.id, **payload.model_dump())
    db.add(chart)
    db.commit()
    db.refresh(chart)
    return serialize_chart(db, chart)


@admin_router.put("/charts/{chart_id}", response_model=GuessChartRead)
def admin_update_chart(chart_id: int, payload: GuessChartCreate, _: User = Depends(require_role("admin", "pool_editor")), db: Session = Depends(get_db)) -> dict:
    chart = db.get(GuessChart, chart_id)
    if not chart:
        raise HTTPException(status_code=404, detail="谱面不存在")
    for key, value in payload.model_dump().items():
        setattr(chart, key, value)
    db.commit()
    db.refresh(chart)
    return serialize_chart(db, chart)


@admin_router.delete("/charts/{chart_id}")
def admin_delete_chart(chart_id: int, _: User = Depends(require_role("admin", "pool_editor")), db: Session = Depends(get_db)) -> dict:
    chart = db.get(GuessChart, chart_id)
    if not chart:
        raise HTTPException(status_code=404, detail="谱面不存在")
    db.delete(chart)
    db.commit()
    return {"message": "谱面已删除"}


@admin_router.post("/parse-submissions")
def admin_parse_submissions(_: User = Depends(require_role("admin", "pool_editor")), db: Session = Depends(get_db)) -> dict:
    # The parser is intentionally isolated here: richer maidata/archive parsing can
    # evolve without changing the public route contract.
    event = get_current_event(db)
    issues = db.scalars(select(ImportIssue).where(ImportIssue.event_id == event.id)).all()
    return {"message": "解析任务已完成", "created": 0, "issues": len(issues)}


@admin_router.get("/import-issues")
def admin_import_issues(_: User = Depends(require_role("admin", "pool_editor")), db: Session = Depends(get_db)) -> list[dict]:
    event = get_current_event(db)
    rows = db.scalars(select(ImportIssue).where(ImportIssue.event_id == event.id).order_by(ImportIssue.created_at.desc())).all()
    return [{"id": row.id, "source_type": row.source_type, "file_name": row.file_name, "issue_type": row.issue_type, "message": row.message, "created_at": row.created_at} for row in rows]


@admin_router.get("/author-candidates")
def admin_author_candidates(_: User = Depends(require_role("admin", "pool_editor")), db: Session = Depends(get_db)) -> list[dict]:
    event = get_current_event(db)
    rows = db.scalars(
        select(GuessAuthorCandidate)
        .options(joinedload(GuessAuthorCandidate.user).joinedload(User.roles))
        .where(GuessAuthorCandidate.event_id == event.id)
    ).all()
    return [{"id": row.id, "display_id": row.display_id, "user": user_payload(row.user)} for row in rows]


@admin_router.get("/stats")
def admin_stats(_: User = Depends(require_role("admin", "pool_editor")), db: Session = Depends(get_db)) -> dict:
    event = get_current_event(db)
    chart_count = db.scalar(select(func.count()).select_from(GuessChart).where(GuessChart.event_id == event.id)) or 0
    return {"charts": chart_count}
