from __future__ import annotations

from collections import Counter
from pathlib import Path
import re
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.core.security import get_current_user, get_optional_user, require_role, user_payload
from app.db.session import get_db
from app.models import (
    AdminGuessArchive,
    GuessAuthorCandidate,
    GuessAuthorGuess,
    GuessChart,
    GuessComment,
    ImportIssue,
    JTrackSubmission,
    Song,
    Submission,
    User,
)
from app.modules.common import serialize_chart, serialize_charts
from app.modules.downloads import DownloadEntry, PreparedZip, file_download_response, prepare_streaming_zip
from app.modules.events.service import get_current_event
from app.modules.guess_game.importer import (
    ArchiveParseError,
    delete_cover_paths,
    parse_stored_archive,
    rebuild_event_charts,
    sync_parsed_source,
)
from app.modules.guess_game.service import list_comments, put_vote, remove_vote, set_author_candidates
from app.modules.guess_game.stats import build_guess_stats
from app.modules.submissions.service import absolute_storage_path, delete_stored_file, save_upload
from app.schemas import (
    AuthorCandidatesUpdate,
    AuthorGuessRequest,
    BatchDeleteRequest,
    BatchDeleteResponse,
    CommentCreate,
    DownloadPreparation,
    GuessChartCreate,
    GuessChartRead,
    GuessCommentRead,
    VoteRequest,
)


router = APIRouter(prefix="/guess-game", tags=["guess-game"])
admin_router = APIRouter(prefix="/admin/guess-game", tags=["admin-guess-game"])

MAX_BATCH_FILES = 500
MAX_BATCH_SOURCE_BYTES = 10 * 1024 * 1024 * 1024


@router.get("/charts/download.zip")
def download_charts_zip(
    ids: str = Query(...),
    db: Session = Depends(get_db),
):
    event = get_current_event(db)
    charts, missing_ids, _ = _select_chart_downloads(db, event.id, ids)
    return _prepare_chart_zip(db, charts, missing_ids).response()


@router.get("/charts/download-metadata", response_model=DownloadPreparation)
def download_charts_metadata(
    ids: str = Query(...),
    db: Session = Depends(get_db),
) -> dict:
    event = get_current_event(db)
    charts, missing_ids, chart_ids = _select_chart_downloads(db, event.id, ids)
    prepared = _prepare_chart_zip(db, charts, missing_ids)
    query = urlencode({"ids": ",".join(str(item) for item in chart_ids)})
    return {
        "download_url": f"{get_settings().api_prefix}/guess-game/charts/download.zip?{query}",
        "file_name": prepared.file_name,
        "file_size": prepared.file_size,
    }


def _select_chart_downloads(
    db: Session,
    event_id: int,
    ids: str,
) -> tuple[list[GuessChart], list[int], list[int]]:
    chart_ids = _parse_ids(ids)
    rows = list(
        db.scalars(
            select(GuessChart).where(GuessChart.event_id == event_id, GuessChart.id.in_(chart_ids))
        ).all()
    )
    by_id = {row.id: row for row in rows}
    ordered = [by_id[chart_id] for chart_id in chart_ids if chart_id in by_id]
    missing_ids = [chart_id for chart_id in chart_ids if chart_id not in by_id]
    return ordered, missing_ids, chart_ids


@router.get("/charts/{chart_id}/download")
def download_chart(chart_id: int, db: Session = Depends(get_db)):
    event = get_current_event(db)
    chart = db.scalar(select(GuessChart).where(GuessChart.id == chart_id, GuessChart.event_id == event.id))
    if not chart:
        raise HTTPException(status_code=404, detail="谱面不存在")
    source = _resolve_archive(db, chart)
    if not source:
        raise HTTPException(status_code=404, detail="该谱面没有可下载的投稿文件")
    path, file_name, _ = source
    if not path.is_file():
        raise HTTPException(status_code=404, detail="投稿文件不存在")
    return file_download_response(path, _safe_zip_name(f"{chart.title}_{chart.level}_{file_name}", file_name))


@router.get("/charts/{chart_id}/download-metadata", response_model=DownloadPreparation)
def download_chart_metadata(chart_id: int, db: Session = Depends(get_db)) -> dict:
    event = get_current_event(db)
    chart = db.scalar(select(GuessChart).where(GuessChart.id == chart_id, GuessChart.event_id == event.id))
    if not chart:
        raise HTTPException(status_code=404, detail="谱面不存在")
    source = _resolve_archive(db, chart)
    if not source:
        raise HTTPException(status_code=404, detail="该谱面没有可下载的投稿文件")
    path, file_name, _ = source
    if not path.is_file():
        raise HTTPException(status_code=404, detail="投稿文件不存在")
    download_name = _safe_zip_name(f"{chart.title}_{chart.level}_{file_name}", file_name)
    return {
        "download_url": f"{get_settings().api_prefix}/guess-game/charts/{chart_id}/download",
        "file_name": download_name,
        "file_size": path.stat().st_size,
    }


@router.get("/charts", response_model=list[GuessChartRead])
def charts(user: User | None = Depends(get_optional_user), db: Session = Depends(get_db)) -> list[dict]:
    event = get_current_event(db)
    rows = db.scalars(select(GuessChart).where(GuessChart.event_id == event.id).order_by(GuessChart.created_at.desc())).all()
    return serialize_charts(db, rows, user.id if user else None)


@router.get("/charts/{chart_id}", response_model=GuessChartRead)
def chart_detail(chart_id: int, user: User | None = Depends(get_optional_user), db: Session = Depends(get_db)) -> dict:
    event = get_current_event(db)
    chart = db.scalar(select(GuessChart).where(GuessChart.id == chart_id, GuessChart.event_id == event.id))
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
    event = get_current_event(db)
    if not db.scalar(select(GuessChart.id).where(GuessChart.id == chart_id, GuessChart.event_id == event.id)):
        raise HTTPException(status_code=404, detail="谱面不存在")
    item = GuessComment(chart_id=chart_id, user_id=user.id, content=payload.content)
    db.add(item)
    db.commit()
    db.refresh(item)
    item.user = user
    return {"id": item.id, "content": item.content, "user": user_payload(user), "created_at": item.created_at}


@router.get("/designer-guesses")
def designer_guess_overview(
    user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
) -> dict:
    event = get_current_event(db)
    charts = list(
        db.scalars(
            select(GuessChart)
            .where(GuessChart.event_id == event.id)
            .order_by(GuessChart.id.asc())
        ).all()
    )
    can_view = bool(user and (user.identity == "participant" or user.has_role("admin") or user.has_role("pool_editor")))
    candidates = _selected_author_candidates(db, event.id) if can_view else []
    guessed_by_group: dict[str, int] = {}
    if user and charts:
        charts_by_id = {chart.id: chart for chart in charts}
        rows = list(
            db.scalars(
                select(GuessAuthorGuess)
                .where(
                    GuessAuthorGuess.chart_id.in_(charts_by_id),
                    GuessAuthorGuess.user_id == user.id,
                )
                .order_by(GuessAuthorGuess.updated_at.asc())
            ).all()
        )
        for row in rows:
            chart = charts_by_id.get(row.chart_id)
            if chart:
                guessed_by_group[_chart_group_identity(chart)] = row.guessed_user_id
    return {
        "can_guess": bool(user and user.identity == "participant"),
        "candidates": [{"user_id": row[0], "display_id": row[1]} for row in candidates],
        "states": [
            {
                "chart_id": chart.id,
                "guessed_user_id": guessed_by_group.get(_chart_group_identity(chart)),
            }
            for chart in charts
        ],
    }


@router.get("/charts/{chart_id}/designer-guess")
@router.get("/charts/{chart_id}/author-guess")
def author_guess_state(
    chart_id: int,
    user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
) -> dict:
    event = get_current_event(db)
    chart = db.scalar(select(GuessChart).where(GuessChart.id == chart_id, GuessChart.event_id == event.id))
    if not chart:
        raise HTTPException(status_code=404, detail="谱面不存在")
    can_view = bool(user and (user.identity == "participant" or user.has_role("admin") or user.has_role("pool_editor")))
    candidates = _selected_author_candidates(db, event.id) if can_view else []
    group_ids = _group_chart_ids(db, chart)
    current = None
    if user:
        current = db.scalar(
            select(GuessAuthorGuess)
            .where(GuessAuthorGuess.chart_id.in_(group_ids), GuessAuthorGuess.user_id == user.id)
            .order_by(GuessAuthorGuess.updated_at.desc())
        )
    return {
        "can_guess": bool(user and user.identity == "participant"),
        "candidates": [{"user_id": row[0], "display_id": row[1]} for row in candidates],
        "my_guess_user_id": current.guessed_user_id if current else None,
    }


@router.put("/charts/{chart_id}/designer-guess")
@router.put("/charts/{chart_id}/author-guess")
def put_author_guess(chart_id: int, payload: AuthorGuessRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    if user.identity != "participant":
        raise HTTPException(status_code=403, detail="仅参赛者可以猜作者")
    event = get_current_event(db)
    chart = db.scalar(select(GuessChart).where(GuessChart.id == chart_id, GuessChart.event_id == event.id))
    if not chart:
        raise HTTPException(status_code=404, detail="谱面不存在")
    candidate_ids = {row[0] for row in _selected_author_candidates(db, event.id)}
    if payload.guessed_user_id not in candidate_ids:
        raise HTTPException(status_code=400, detail="目标账号不在可猜作者名单中")
    group_ids = _group_chart_ids(db, chart)
    anchor_id = min(group_ids)
    rows = list(
        db.scalars(
            select(GuessAuthorGuess)
            .where(GuessAuthorGuess.chart_id.in_(group_ids), GuessAuthorGuess.user_id == user.id)
            .order_by(GuessAuthorGuess.updated_at.desc())
        ).all()
    )
    if rows:
        rows[0].chart_id = anchor_id
        rows[0].guessed_user_id = payload.guessed_user_id
        for extra in rows[1:]:
            db.delete(extra)
    else:
        db.add(GuessAuthorGuess(chart_id=anchor_id, user_id=user.id, guessed_user_id=payload.guessed_user_id))
    db.commit()
    return {"message": "已保存谱师猜测"}


@router.delete("/charts/{chart_id}/designer-guess")
@router.delete("/charts/{chart_id}/author-guess")
def delete_author_guess(chart_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    event = get_current_event(db)
    chart = db.scalar(select(GuessChart).where(GuessChart.id == chart_id, GuessChart.event_id == event.id))
    if not chart:
        raise HTTPException(status_code=404, detail="谱面不存在")
    group_ids = _group_chart_ids(db, chart)
    db.execute(
        delete(GuessAuthorGuess).where(
            GuessAuthorGuess.chart_id.in_(group_ids),
            GuessAuthorGuess.user_id == user.id,
        )
    )
    db.commit()
    return {"message": "已清除谱师猜测"}


@admin_router.get("/charts", response_model=list[GuessChartRead])
def admin_charts(_: User = Depends(require_role("admin", "pool_editor")), db: Session = Depends(get_db)) -> list[dict]:
    event = get_current_event(db)
    rows = db.scalars(select(GuessChart).where(GuessChart.event_id == event.id).order_by(GuessChart.created_at.desc())).all()
    return serialize_charts(db, rows)


@admin_router.post("/charts/import")
def admin_import_charts(
    file: UploadFile = File(...),
    user: User = Depends(require_role("admin", "pool_editor")),
    db: Session = Depends(get_db),
) -> dict:
    event = get_current_event(db)
    storage_path, size = save_upload(file, f"events/{event.id}/admin-guess")
    try:
        parsed = parse_stored_archive(storage_path)
    except ArchiveParseError as exc:
        delete_stored_file(storage_path)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    archive = AdminGuessArchive(
        event_id=event.id,
        uploaded_by_id=user.id,
        file_name=file.filename or "upload",
        storage_path=storage_path,
        file_size=size,
    )
    result = None
    try:
        db.add(archive)
        db.flush()
        result = sync_parsed_source(
            db,
            event_id=event.id,
            source_type="admin",
            source_id=archive.id,
            file_name=archive.file_name,
            storage_path=archive.storage_path,
            parsed=parsed,
            is_self_selected=False,
        )
        db.commit()
    except Exception:
        db.rollback()
        delete_stored_file(storage_path)
        if result and result.new_cover_path and result.new_cover_path not in result.previous_cover_paths:
            delete_cover_paths({result.new_cover_path})
        raise
    charts = list(
        db.scalars(
            select(GuessChart)
            .where(
                GuessChart.event_id == event.id,
                GuessChart.source_submission_type == "admin",
                GuessChart.source_submission_id == archive.id,
            )
            .order_by(GuessChart.source_level_slot.asc())
        ).all()
    )
    return {"archive_id": archive.id, "charts": serialize_charts(db, charts)}


@admin_router.post("/charts/batch-delete", response_model=BatchDeleteResponse)
def admin_batch_delete_charts(
    payload: BatchDeleteRequest,
    _: User = Depends(require_role("admin", "pool_editor")),
    db: Session = Depends(get_db),
) -> dict:
    event = get_current_event(db)
    chart_ids = list(dict.fromkeys(payload.ids))
    charts = list(
        db.scalars(
            select(GuessChart)
            .where(GuessChart.event_id == event.id, GuessChart.id.in_(chart_ids))
            .order_by(GuessChart.id.asc())
        ).all()
    )
    found_ids = {chart.id for chart in charts}
    missing_ids = [chart_id for chart_id in chart_ids if chart_id not in found_ids]
    if missing_ids:
        raise HTTPException(status_code=404, detail=f"谱面不存在：{', '.join(map(str, missing_ids))}")
    try:
        cover_paths, storage_paths = _stage_delete_admin_charts(db, event.id, charts)
        db.commit()
    except Exception:
        db.rollback()
        raise
    delete_cover_paths(cover_paths)
    for storage_path in storage_paths:
        delete_stored_file(storage_path)
    return {"deleted": len(charts), "message": f"已删除 {len(charts)} 张谱面"}


@admin_router.put("/charts/{chart_id}", response_model=GuessChartRead)
def admin_update_chart(chart_id: int, payload: GuessChartCreate, _: User = Depends(require_role("admin", "pool_editor")), db: Session = Depends(get_db)) -> dict:
    event = get_current_event(db)
    chart = db.scalar(select(GuessChart).where(GuessChart.id == chart_id, GuessChart.event_id == event.id))
    if not chart:
        raise HTTPException(status_code=404, detail="谱面不存在")
    for key, value in payload.model_dump().items():
        setattr(chart, key, value)
    db.commit()
    db.refresh(chart)
    return serialize_chart(db, chart)


@admin_router.delete("/charts/{chart_id}")
def admin_delete_chart(chart_id: int, _: User = Depends(require_role("admin", "pool_editor")), db: Session = Depends(get_db)) -> dict:
    event = get_current_event(db)
    chart = db.scalar(select(GuessChart).where(GuessChart.id == chart_id, GuessChart.event_id == event.id))
    if not chart:
        raise HTTPException(status_code=404, detail="谱面不存在")
    try:
        cover_paths, storage_paths = _stage_delete_admin_charts(db, event.id, [chart])
        db.commit()
    except Exception:
        db.rollback()
        raise
    delete_cover_paths(cover_paths)
    for storage_path in storage_paths:
        delete_stored_file(storage_path)
    return {"message": "谱面已删除"}


def _stage_delete_admin_charts(
    db: Session,
    event_id: int,
    charts: list[GuessChart],
) -> tuple[set[str], set[str]]:
    candidate_covers = {chart.cover_path for chart in charts if chart.cover_path}
    manual_storage_paths = {
        chart.storage_path
        for chart in charts
        if chart.source_submission_id is None and chart.storage_path
    }
    admin_source_storage: dict[int, str] = {
        int(chart.source_submission_id): chart.storage_path
        for chart in charts
        if chart.source_submission_type == "admin" and chart.source_submission_id is not None
    }
    for chart in charts:
        db.delete(chart)
    db.flush()

    cover_paths = {
        cover_path
        for cover_path in candidate_covers
        if not db.scalar(
            select(func.count()).select_from(GuessChart).where(GuessChart.cover_path == cover_path)
        )
    }
    storage_paths = {
        storage_path
        for storage_path in manual_storage_paths
        if not db.scalar(
            select(func.count()).select_from(GuessChart).where(GuessChart.storage_path == storage_path)
        )
    }
    for source_id, fallback_storage_path in admin_source_storage.items():
        remaining_source = db.scalar(
            select(func.count()).select_from(GuessChart).where(
                GuessChart.source_submission_type == "admin",
                GuessChart.source_submission_id == source_id,
            )
        ) or 0
        if remaining_source:
            continue
        archive = db.get(AdminGuessArchive, source_id)
        if archive:
            storage_paths.add(archive.storage_path)
            db.delete(archive)
        elif fallback_storage_path:
            storage_paths.add(fallback_storage_path)
        db.execute(
            delete(ImportIssue).where(
                ImportIssue.event_id == event_id,
                ImportIssue.source_type == "admin",
                ImportIssue.source_id == source_id,
            )
        )
    return cover_paths, storage_paths


@admin_router.post("/parse-submissions")
def admin_parse_submissions(_: User = Depends(require_role("admin", "pool_editor")), db: Session = Depends(get_db)) -> dict:
    event = get_current_event(db)
    return rebuild_event_charts(db, event.id).as_dict()


@admin_router.get("/import-issues")
def admin_import_issues(_: User = Depends(require_role("admin", "pool_editor")), db: Session = Depends(get_db)) -> list[dict]:
    event = get_current_event(db)
    rows = db.scalars(select(ImportIssue).where(ImportIssue.event_id == event.id).order_by(ImportIssue.created_at.desc())).all()
    return [
        {
            "id": row.id,
            "source_type": row.source_type,
            "file_name": row.file_name,
            "issue_type": row.issue_type,
            "message": row.message,
            "created_at": row.created_at,
        }
        for row in rows
    ]


@admin_router.get("/author-candidates")
def admin_author_candidates(_: User = Depends(require_role("admin", "pool_editor")), db: Session = Depends(get_db)) -> list[dict]:
    event = get_current_event(db)
    eligible = _eligible_author_users(db, event.id)
    selected = {
        row.user_id: row
        for row in db.scalars(select(GuessAuthorCandidate).where(GuessAuthorCandidate.event_id == event.id)).all()
    }
    return [
        {
            "user": user_payload(user),
            "song_count": song_count,
            "selected": True,
            "display_id": (selected[user.id].display_id.strip() or user.user_code)
            if user.id in selected
            else user.user_code,
        }
        for user, song_count in eligible
    ]


@admin_router.put("/author-candidates")
def admin_update_author_candidates(
    payload: AuthorCandidatesUpdate,
    _: User = Depends(require_role("admin", "pool_editor")),
    db: Session = Depends(get_db),
) -> dict:
    event = get_current_event(db)
    eligible = _eligible_author_users(db, event.id)
    eligible_ids = {user.id for user, _ in eligible}
    rows = [row.model_dump() for row in payload.rows]
    user_ids = [row["user_id"] for row in rows]
    if len(user_ids) != len(set(user_ids)):
        raise HTTPException(status_code=400, detail="谱师展示 ID 配置不能重复")
    if not set(user_ids).issubset(eligible_ids):
        raise HTTPException(status_code=400, detail="账号不在当前启用的观众或参赛者中")
    display_by_user_id = {
        int(row["user_id"]): str(row.get("display_id") or "").strip()
        for row in rows
    }
    resolved_display_ids = [
        display_by_user_id.get(user.id) or user.user_code
        for user, _ in eligible
    ]
    if len(resolved_display_ids) != len(set(resolved_display_ids)):
        raise HTTPException(status_code=400, detail="谱师展示 ID 不能重复")
    count = set_author_candidates(db, rows)
    return {"message": f"已保存 {count} 位谱师的展示 ID", "count": count}


@admin_router.get("/stats")
def admin_stats(
    scope: str = Query("all"),
    _: User = Depends(require_role("admin", "pool_editor")),
    db: Session = Depends(get_db),
) -> dict:
    return build_guess_stats(db, scope)


def _group_chart_ids(db: Session, chart: GuessChart) -> list[int]:
    if not chart.guess_group_key:
        return [chart.id]
    return list(
        db.scalars(
            select(GuessChart.id).where(
                GuessChart.event_id == chart.event_id,
                GuessChart.guess_group_key == chart.guess_group_key,
            )
        ).all()
    ) or [chart.id]


def _chart_group_identity(chart: GuessChart) -> str:
    return chart.guess_group_key or f"chart:{chart.id}"


def _eligible_author_users(db: Session, event_id: int) -> list[tuple[User, int]]:
    users = list(
        db.scalars(
            select(User)
            .options(selectinload(User.roles))
            .where(
                User.identity.in_(("participant", "audience")),
                User.is_active.is_(True),
            )
            .order_by(User.user_code.asc())
        ).all()
    )
    song_counts = Counter(
        dict(
            db.execute(
                select(Song.submitted_by_id, func.count(Song.id))
                .where(Song.event_id == event_id)
                .group_by(Song.submitted_by_id)
            ).all()
        )
    )
    return [(user, int(song_counts[user.id])) for user in users]


def _selected_author_candidates(db: Session, event_id: int) -> list[tuple[int, str]]:
    eligible = _eligible_author_users(db, event_id)
    display_overrides = {
        row.user_id: row.display_id.strip()
        for row in db.scalars(
            select(GuessAuthorCandidate).where(GuessAuthorCandidate.event_id == event_id)
        ).all()
    }
    return [
        (user.id, display_overrides.get(user.id) or user.user_code)
        for user, _ in eligible
    ]


def _resolve_archive(db: Session, chart: GuessChart) -> tuple[Path, str, tuple[str, int | str]] | None:
    source_id = chart.source_submission_id
    if source_id is not None and chart.source_submission_type in {"normal", "j"}:
        submission = db.get(Submission, source_id)
        if submission and submission.event_id == chart.event_id:
            return absolute_storage_path(submission.storage_path), submission.file_name, ("submission", submission.id)
        if chart.source_submission_type == "j":
            legacy = db.get(JTrackSubmission, source_id)
            if legacy and legacy.event_id == chart.event_id:
                return absolute_storage_path(legacy.storage_path), legacy.file_name, ("legacy-j", legacy.id)
    if source_id is not None and chart.source_submission_type == "admin":
        archive = db.get(AdminGuessArchive, source_id)
        if archive and archive.event_id == chart.event_id:
            return absolute_storage_path(archive.storage_path), archive.file_name, ("admin", archive.id)
    if chart.storage_path:
        return absolute_storage_path(chart.storage_path), Path(chart.storage_path).name, ("path", chart.storage_path)
    return None


def _parse_ids(value: str) -> list[int]:
    try:
        ids = list(dict.fromkeys(int(item.strip()) for item in value.split(",") if item.strip()))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="ids 必须是逗号分隔的数字") from exc
    if not ids:
        raise HTTPException(status_code=400, detail="请至少选择一张谱面")
    if len(ids) > MAX_BATCH_FILES:
        raise HTTPException(status_code=413, detail=f"一次最多选择 {MAX_BATCH_FILES} 张谱面")
    return ids


def _safe_zip_name(value: str, fallback: str) -> str:
    cleaned = re.sub(r"[\\/:*?\"<>|\x00-\x1f]+", "_", value).strip(" .")
    return cleaned[:180] or fallback


def _prepare_chart_zip(
    db: Session,
    charts: list[GuessChart],
    missing_ids: list[int],
) -> PreparedZip:
    selected: list[tuple[GuessChart, Path, str]] = []
    seen_sources: set[tuple[str, int | str]] = set()
    skipped: list[str] = [f"谱面 ID {chart_id} 不存在" for chart_id in missing_ids]
    total_size = 0
    for chart in charts:
        source = _resolve_archive(db, chart)
        if not source:
            skipped.append(f"ID {chart.id}《{chart.title}》没有投稿来源")
            continue
        path, file_name, source_key = source
        if source_key in seen_sources:
            skipped.append(f"ID {chart.id}《{chart.title}》与已选谱面共用投稿文件，已去重")
            continue
        if not path.is_file():
            skipped.append(f"ID {chart.id}《{chart.title}》投稿文件不存在")
            continue
        seen_sources.add(source_key)
        total_size += path.stat().st_size
        if total_size > MAX_BATCH_SOURCE_BYTES:
            raise HTTPException(status_code=413, detail="所选投稿原文件总量不能超过 10 GiB")
        selected.append((chart, path, file_name))
    if not selected:
        raise HTTPException(status_code=404, detail="所选谱面均无可下载文件")

    entries: list[DownloadEntry] = []
    used_names: set[str] = set()
    for chart, path, file_name in selected:
        base = _safe_zip_name(
            f"{chart.id}_{chart.title}_{chart.level}_{file_name}",
            f"chart_{chart.id}{path.suffix}",
        )
        name = base
        counter = 2
        while name.casefold() in used_names:
            name = f"{Path(base).stem}_{counter}{Path(base).suffix}"
            counter += 1
        used_names.add(name.casefold())
        entries.append(DownloadEntry(path=path, archive_name=name))
    return prepare_streaming_zip(
        entries,
        file_name="guess-charts.zip",
        report="\n".join(skipped),
    )
