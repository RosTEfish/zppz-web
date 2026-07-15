from __future__ import annotations

from pathlib import Path
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.core.security import get_current_user, require_role
from app.db.session import get_db
from app.models import DrawAssignment, GuessChart, ImportIssue, Song, Submission, User
from app.modules.banlist.service import enforce_song_allowed
from app.modules.common import serialize_song, serialize_submission
from app.modules.downloads import (
    DownloadEntry,
    PreparedZip,
    file_download_response,
    parse_csv_ids,
    prepare_streaming_zip,
    safe_download_name,
)
from app.modules.events.service import get_current_event
from app.modules.events.phase_policy import get_phase_status
from app.modules.guess_game.importer import (
    ArchiveParseError,
    ParsedArchive,
    delete_cover_paths,
    delete_source_charts,
    parse_stored_archive,
    sync_parsed_source,
    write_public_package,
)
from app.modules.submissions.service import absolute_storage_path, delete_stored_file, save_upload
from app.schemas import BatchDeleteRequest, BatchDeleteResponse, DownloadPreparation, StoredFileRead, SubmissionTargetsResponse, SubmissionTrackUpdate


router = APIRouter(prefix="/submissions", tags=["submissions"])
admin_router = APIRouter(prefix="/admin/submissions", tags=["admin-submissions"])

MAX_BATCH_FILES = 500
MAX_BATCH_SOURCE_BYTES = 10 * 1024 * 1024 * 1024


def _validated_upload(storage_path: str) -> ParsedArchive:
    try:
        return parse_stored_archive(storage_path)
    except ArchiveParseError as exc:
        delete_stored_file(storage_path)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception:
        delete_stored_file(storage_path)
        raise


def _require_participant(user: User) -> None:
    if user.identity != "participant":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="仅参赛者可以上传投稿")


def _require_submission_phase(db: Session, event) -> None:
    if not get_phase_status(db, event).can("submission"):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="投稿尚未开放")


def _normalize_track(track: str | None, fallback: str = "normal") -> str:
    value = (track or fallback).strip().lower()
    if value not in {"normal", "j", "exhibition"}:
        raise HTTPException(status_code=422, detail="投稿类型必须为 normal、j 或 exhibition")
    return value


def _eligible_song(db: Session, event_id: int, user: User, song_id: int) -> tuple[Song, str]:
    song = db.scalar(
        select(Song)
        .options(selectinload(Song.submitter).selectinload(User.roles))
        .where(Song.id == song_id, Song.event_id == event_id)
    )
    if not song:
        raise HTTPException(status_code=404, detail="候选曲目不存在")
    if song.submitted_by_id == user.id:
        return song, "self"
    assignment = db.scalar(
        select(DrawAssignment.id).where(
            DrawAssignment.event_id == event_id,
            DrawAssignment.assigned_to_id == user.id,
            DrawAssignment.song_id == song.id,
            DrawAssignment.status == "active",
        )
    )
    if not assignment:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="该曲目不在你的投稿候选中")
    return song, "assigned"


def _move_submission_track(db: Session, row: Submission, next_track: str) -> None:
    previous_track = row.track
    if previous_track == next_track:
        return
    row.track = next_track
    for chart in db.scalars(
        select(GuessChart).where(
            GuessChart.event_id == row.event_id,
            GuessChart.source_submission_type == previous_track,
            GuessChart.source_submission_id == row.id,
        )
    ).all():
        chart.source_submission_type = next_track
        chart.lane = next_track
    for issue in db.scalars(
        select(ImportIssue).where(
            ImportIssue.event_id == row.event_id,
            ImportIssue.source_type == previous_track,
            ImportIssue.source_id == row.id,
        )
    ).all():
        issue.source_type = next_track


def _demote_existing_j_track(db: Session, event_id: int, user_id: int, exclude_id: int | None = None) -> None:
    db.scalar(select(User.id).where(User.id == user_id).with_for_update())
    stmt = select(Submission).where(
        Submission.event_id == event_id,
        Submission.user_id == user_id,
        Submission.track == "j",
    )
    if exclude_id is not None:
        stmt = stmt.where(Submission.id != exclude_id)
    existing = db.scalar(stmt.with_for_update())
    if existing:
        raise HTTPException(status_code=409, detail="每位参赛者只能提交一个 J 投稿包")


def _sync_and_commit(
    db: Session,
    row: Submission,
    parsed: ParsedArchive,
    *,
    match_source_type: str | None = None,
) -> None:
    result = None
    try:
        result = sync_parsed_source(
            db,
            event_id=row.event_id,
            source_type=row.track,
            source_id=row.id,
            file_name=row.file_name,
            storage_path=row.storage_path,
            parsed=parsed,
            is_self_selected=row.source_kind == "self",
            match_source_type=match_source_type,
        )
        db.commit()
    except Exception:
        db.rollback()
        if result and result.new_cover_path and result.new_cover_path not in result.previous_cover_paths:
            delete_cover_paths({result.new_cover_path})
        raise
    assert result is not None
    delete_cover_paths(result.stale_cover_paths)


def _create_submission(
    db: Session,
    *,
    event_id: int,
    user: User,
    song: Song | None,
    source_kind: str,
    track: str,
    file: UploadFile,
    acknowledge_ban_warning: bool = False,
) -> Submission:
    if song is not None:
        enforce_song_allowed(db, song.song_name, song.artist, acknowledge_ban_warning)
    existing = db.scalar(
        select(Submission).where(
            Submission.event_id == event_id,
            Submission.user_id == user.id,
            Submission.source_song_id == song.id,
        )
    ) if song is not None else None
    if existing:
        raise HTTPException(status_code=409, detail="该候选已有投稿，请使用替换功能")
    storage_path, size = save_upload(file, f"events/{event_id}/submissions/{user.id}")
    parsed = _validated_upload(storage_path)
    public_storage_path: str | None = None
    row = Submission(
        event_id=event_id,
        user_id=user.id,
        source_song_id=song.id if song is not None else None,
        source_kind=source_kind,
        track=track,
        file_name=file.filename or "upload",
        storage_path=storage_path,
        file_size=size,
    )
    try:
        if track == "j":
            _demote_existing_j_track(db, event_id, user.id)
        db.add(row)
        db.flush()
        row.track_duration_seconds = parsed.track_duration_seconds
        public_storage_path = write_public_package(event_id, row.id, parsed)
        row.public_storage_path = public_storage_path
        _sync_and_commit(db, row, parsed)
    except IntegrityError as exc:
        db.rollback()
        delete_stored_file(storage_path)
        if public_storage_path:
            delete_stored_file(public_storage_path)
        if track == "j":
            raise HTTPException(status_code=409, detail="J 赛道切换冲突，请刷新页面后重试") from exc
        raise
    except Exception:
        db.rollback()
        delete_stored_file(storage_path)
        if public_storage_path:
            delete_stored_file(public_storage_path)
        raise
    db.refresh(row)
    row.user = user
    row.source_song = song
    return row


def _replace_submission(
    db: Session,
    row: Submission,
    file: UploadFile,
    *,
    track: str | None = None,
    source_kind: str | None = None,
    acknowledge_ban_warning: bool = False,
) -> Submission:
    next_track = _normalize_track(track, row.track)
    new_storage_path, size = save_upload(file, f"events/{row.event_id}/submissions/{row.user_id}")
    parsed = _validated_upload(new_storage_path)
    old_storage_path = row.storage_path
    old_public_storage_path = row.public_storage_path
    old_track = row.track
    new_public_storage_path: str | None = None
    try:
        if next_track == "j":
            _demote_existing_j_track(db, row.event_id, row.user_id, row.id)
        row.track = next_track
        row.file_name = file.filename or "upload"
        row.storage_path = new_storage_path
        row.file_size = size
        row.track_duration_seconds = parsed.track_duration_seconds
        new_public_storage_path = write_public_package(row.event_id, row.id, parsed)
        row.public_storage_path = new_public_storage_path
        if source_kind:
            row.source_kind = source_kind
        _sync_and_commit(db, row, parsed, match_source_type=old_track)
    except IntegrityError as exc:
        db.rollback()
        delete_stored_file(new_storage_path)
        if new_public_storage_path:
            delete_stored_file(new_public_storage_path)
        if next_track == "j":
            raise HTTPException(status_code=409, detail="J 赛道切换冲突，请刷新页面后重试") from exc
        raise
    except Exception:
        db.rollback()
        delete_stored_file(new_storage_path)
        if new_public_storage_path:
            delete_stored_file(new_public_storage_path)
        raise
    delete_stored_file(old_storage_path)
    if old_public_storage_path:
        delete_stored_file(old_public_storage_path)
    db.refresh(row)
    return row


def _delete_submission(db: Session, row: Submission) -> None:
    storage_path, public_storage_path, cover_paths = _stage_delete_submission(db, row)
    db.commit()
    delete_stored_file(storage_path)
    if public_storage_path:
        delete_stored_file(public_storage_path)
    delete_cover_paths(cover_paths)


def _stage_delete_submission(db: Session, row: Submission) -> tuple[str, str | None, set[str]]:
    _, cover_paths = delete_source_charts(db, row.event_id, row.track, row.id)
    storage_path = row.storage_path
    db.delete(row)
    return storage_path, row.public_storage_path, cover_paths


def _submission_options():
    return (
        selectinload(Submission.user).selectinload(User.roles),
        selectinload(Submission.source_song).selectinload(Song.submitter).selectinload(User.roles),
    )


@router.get("/targets", response_model=SubmissionTargetsResponse)
def submission_targets(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    _require_participant(user)
    event = get_current_event(db)
    assigned_song_ids = select(DrawAssignment.song_id).where(
        DrawAssignment.event_id == event.id,
        DrawAssignment.assigned_to_id == user.id,
        DrawAssignment.status == "active",
    )
    songs = list(
        db.scalars(
            select(Song)
            .options(selectinload(Song.submitter).selectinload(User.roles))
            .where(
                Song.event_id == event.id,
                or_(Song.submitted_by_id == user.id, Song.id.in_(assigned_song_ids)),
            )
            .order_by(Song.created_at.asc(), Song.id.asc())
        ).all()
    )
    submissions = list(
        db.scalars(
            select(Submission)
            .options(*_submission_options())
            .where(Submission.event_id == event.id, Submission.user_id == user.id)
        ).all()
    )
    by_song_id = {row.source_song_id: row for row in submissions if row.source_song_id is not None}
    return {
        "is_open": get_phase_status(db, event).can("submission"),
        "targets": [
            {
                "song": serialize_song(song),
                "source_kind": "self" if song.submitted_by_id == user.id else "assigned",
                "submission": serialize_submission(by_song_id[song.id]) if song.id in by_song_id else None,
            }
            for song in songs
        ],
    }


@router.get("", response_model=list[StoredFileRead])
def my_submissions(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[dict]:
    _require_participant(user)
    event = get_current_event(db)
    rows = db.scalars(
        select(Submission)
        .options(*_submission_options())
        .where(Submission.event_id == event.id, Submission.user_id == user.id)
        .order_by(Submission.created_at.desc())
    ).all()
    return [serialize_submission(row) for row in rows]


@router.post("", response_model=StoredFileRead)
def upload_submission(
    song_id: int | None = Form(None),
    track: str = Form("normal"),
    file: UploadFile = File(...),
    acknowledge_ban_warning: bool = Form(False),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    _require_participant(user)
    event = get_current_event(db)
    _require_submission_phase(db, event)
    normalized_track = _normalize_track(track)
    if normalized_track == "exhibition":
        song, source_kind = (None, "exhibition") if song_id is None else _eligible_song(db, event.id, user, song_id)
    else:
        if song_id is None:
            raise HTTPException(status_code=422, detail="普通和 J 投稿必须关联候选曲目")
        song, source_kind = _eligible_song(db, event.id, user, song_id)
    row = _create_submission(
        db,
        event_id=event.id,
        user=user,
        song=song,
        source_kind=source_kind,
        track=normalized_track,
        file=file,
        acknowledge_ban_warning=acknowledge_ban_warning,
    )
    return serialize_submission(row)


@router.post("/{submission_id}/replace", response_model=StoredFileRead)
def replace_submission(
    submission_id: int,
    file: UploadFile = File(...),
    track: str | None = Form(None),
    acknowledge_ban_warning: bool = Form(False),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    _require_participant(user)
    event = get_current_event(db)
    _require_submission_phase(db, event)
    row = db.scalar(select(Submission).options(*_submission_options()).where(Submission.id == submission_id))
    if not row or row.user_id != user.id or row.event_id != event.id:
        raise HTTPException(status_code=404, detail="投稿不存在")
    if row.source_song_id is None:
        if row.track != "exhibition":
            raise HTTPException(status_code=409, detail="非场外投稿缺少关联曲目")
        if track is not None and _normalize_track(track) != "exhibition":
            raise HTTPException(status_code=422, detail="独立场外投稿不能改为普通或 J 投稿")
        song, source_kind = None, "exhibition"
    else:
        song, source_kind = _eligible_song(db, event.id, user, row.source_song_id)
    if song is not None:
        enforce_song_allowed(db, song.song_name, song.artist, acknowledge_ban_warning)
    row = _replace_submission(
        db,
        row,
        file,
        track=track,
        source_kind=source_kind,
        acknowledge_ban_warning=acknowledge_ban_warning,
    )
    row.user = user
    row.source_song = song
    return serialize_submission(row)


@router.patch("/{submission_id}/track", response_model=StoredFileRead)
def update_submission_track(
    submission_id: int,
    payload: SubmissionTrackUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    _require_participant(user)
    event = get_current_event(db)
    _require_submission_phase(db, event)
    row = db.scalar(
        select(Submission)
        .options(*_submission_options())
        .where(Submission.id == submission_id)
    )
    if not row or row.user_id != user.id or row.event_id != event.id or row.source_song_id is None:
        raise HTTPException(status_code=404, detail="投稿不存在")
    song, source_kind = _eligible_song(db, event.id, user, row.source_song_id)
    next_track = _normalize_track(payload.track)
    if next_track != "exhibition" and row.source_song_id is None:
        raise HTTPException(status_code=422, detail="普通和 J 投稿必须关联候选曲目")
    try:
        if next_track == "j":
            _demote_existing_j_track(db, event.id, user.id, row.id)
        _move_submission_track(db, row, next_track)
        row.source_kind = source_kind
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="J 赛道切换冲突，请刷新页面后重试") from exc
    except Exception:
        db.rollback()
        raise
    row = db.scalar(
        select(Submission)
        .options(*_submission_options())
        .where(Submission.id == submission_id)
    )
    assert row is not None
    row.user = user
    row.source_song = song
    return serialize_submission(row)


# Compatibility endpoints for clients that previously treated J submissions separately.
@router.get("/j-track")
def my_j_track(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    _require_participant(user)
    event = get_current_event(db)
    row = db.scalar(
        select(Submission)
        .options(*_submission_options())
        .where(Submission.event_id == event.id, Submission.user_id == user.id, Submission.track == "j")
    )
    return {"submission": serialize_submission(row) if row else None}


@router.delete("/j-track")
def delete_j_track(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    _require_participant(user)
    event = get_current_event(db)
    _require_submission_phase(db, event)
    row = db.scalar(
        select(Submission).where(
            Submission.event_id == event.id,
            Submission.user_id == user.id,
            Submission.track == "j",
        )
    )
    if not row:
        raise HTTPException(status_code=404, detail="J 赛道投稿不存在")
    _delete_submission(db, row)
    return {"message": "J 赛道投稿已删除"}


@router.delete("/{submission_id}")
def delete_submission(submission_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    _require_participant(user)
    event = get_current_event(db)
    _require_submission_phase(db, event)
    row = db.get(Submission, submission_id)
    if not row or row.user_id != user.id or row.event_id != event.id:
        raise HTTPException(status_code=404, detail="投稿不存在")
    _delete_submission(db, row)
    return {"message": "投稿已删除"}


@admin_router.get("", response_model=list[StoredFileRead])
def admin_list_submissions(
    track: str | None = Query(None),
    _: User = Depends(require_role("admin", "pool_editor")),
    db: Session = Depends(get_db),
) -> list[dict]:
    event = get_current_event(db)
    stmt = (
        select(Submission)
        .options(*_submission_options())
        .where(Submission.event_id == event.id)
        .order_by(Submission.created_at.desc())
    )
    if track:
        stmt = stmt.where(Submission.track == _normalize_track(track))
    return [serialize_submission(row) for row in db.scalars(stmt).all()]


@admin_router.post("/batch-delete", response_model=BatchDeleteResponse)
def admin_batch_delete_submissions(
    payload: BatchDeleteRequest,
    _: User = Depends(require_role("admin", "pool_editor")),
    db: Session = Depends(get_db),
) -> dict:
    event = get_current_event(db)
    submission_ids = list(dict.fromkeys(payload.ids))
    rows = list(
        db.scalars(
            select(Submission)
            .where(Submission.event_id == event.id, Submission.id.in_(submission_ids))
            .order_by(Submission.id.asc())
        ).all()
    )
    found_ids = {row.id for row in rows}
    missing_ids = [submission_id for submission_id in submission_ids if submission_id not in found_ids]
    if missing_ids:
        raise HTTPException(status_code=404, detail=f"投稿不存在：{', '.join(map(str, missing_ids))}")
    storage_paths: set[str] = set()
    public_storage_paths: set[str] = set()
    cover_paths: set[str] = set()
    try:
        for row in rows:
            storage_path, public_storage_path, row_cover_paths = _stage_delete_submission(db, row)
            storage_paths.add(storage_path)
            if public_storage_path:
                public_storage_paths.add(public_storage_path)
            cover_paths.update(row_cover_paths)
        db.commit()
    except Exception:
        db.rollback()
        raise
    for storage_path in storage_paths:
        delete_stored_file(storage_path)
    for storage_path in public_storage_paths:
        delete_stored_file(storage_path)
    delete_cover_paths(cover_paths)
    return {"deleted": len(rows), "message": f"已删除 {len(rows)} 份投稿"}


@admin_router.post("/{submission_id}/replace", response_model=StoredFileRead)
def admin_replace_submission(
    submission_id: int,
    file: UploadFile = File(...),
    track: str | None = Form(None),
    _: User = Depends(require_role("admin", "pool_editor")),
    db: Session = Depends(get_db),
) -> dict:
    event = get_current_event(db)
    row = db.scalar(select(Submission).options(*_submission_options()).where(Submission.id == submission_id))
    if not row or row.event_id != event.id:
        raise HTTPException(status_code=404, detail="投稿不存在")
    row = _replace_submission(db, row, file, track=track)
    row.user = db.get(User, row.user_id)
    return serialize_submission(row)


@admin_router.delete("/{submission_id}")
def admin_delete_submission(
    submission_id: int,
    _: User = Depends(require_role("admin", "pool_editor")),
    db: Session = Depends(get_db),
) -> dict:
    event = get_current_event(db)
    row = db.get(Submission, submission_id)
    if not row or row.event_id != event.id:
        raise HTTPException(status_code=404, detail="投稿不存在")
    _delete_submission(db, row)
    return {"message": "投稿已删除"}


@admin_router.get("/download.zip")
def admin_download_zip(
    ids: str | None = Query(None),
    track: str | None = Query(None),
    _: User = Depends(require_role("admin", "pool_editor")),
    db: Session = Depends(get_db),
):
    event = get_current_event(db)
    rows, _, _ = _select_admin_downloads(db, event.id, ids, track)
    return _prepare_submission_zip(rows, "submissions.zip").response()


@admin_router.get("/download-metadata", response_model=DownloadPreparation)
def admin_download_metadata(
    ids: str | None = Query(None),
    track: str | None = Query(None),
    _: User = Depends(require_role("admin", "pool_editor")),
    db: Session = Depends(get_db),
) -> dict:
    event = get_current_event(db)
    rows, selected_ids, selected_track = _select_admin_downloads(db, event.id, ids, track)
    prepared = _prepare_submission_zip(rows, "submissions.zip")
    params: dict[str, str] = {}
    if selected_ids is not None:
        params["ids"] = ",".join(str(item) for item in selected_ids)
    if selected_track:
        params["track"] = selected_track
    query = urlencode(params)
    base_url = f"{get_settings().api_prefix}/admin/submissions/download.zip"
    return {
        "download_url": f"{base_url}?{query}" if query else base_url,
        "file_name": prepared.file_name,
        "file_size": prepared.file_size,
    }


def _select_admin_downloads(
    db: Session,
    event_id: int,
    ids: str | None,
    track: str | None,
) -> tuple[list[Submission], list[int] | None, str | None]:
    stmt = select(Submission).options(*_submission_options()).where(Submission.event_id == event_id)
    selected_ids = parse_csv_ids(
        ids,
        required=False,
        max_items=MAX_BATCH_FILES,
        empty_detail="请至少选择一份投稿",
        limit_detail=f"一次最多下载 {MAX_BATCH_FILES} 份投稿",
    )
    if selected_ids is not None:
        stmt = stmt.where(Submission.id.in_(selected_ids))
    selected_track = _normalize_track(track) if track else None
    if selected_track:
        stmt = stmt.where(Submission.track == selected_track)
    rows = list(db.scalars(stmt.order_by(Submission.id.asc())).all())
    if not rows:
        raise HTTPException(status_code=404, detail="没有可下载的投稿")
    return rows, selected_ids, selected_track


@admin_router.get("/{submission_id}/download")
def admin_download_submission(
    submission_id: int,
    _: User = Depends(require_role("admin", "pool_editor")),
    db: Session = Depends(get_db),
):
    event = get_current_event(db)
    row = db.get(Submission, submission_id)
    if not row or row.event_id != event.id:
        raise HTTPException(status_code=404, detail="投稿不存在")
    path = absolute_storage_path(row.storage_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="投稿文件不存在")
    return file_download_response(path, row.file_name)


@admin_router.get("/{submission_id}/download-metadata", response_model=DownloadPreparation)
def admin_download_submission_metadata(
    submission_id: int,
    _: User = Depends(require_role("admin", "pool_editor")),
    db: Session = Depends(get_db),
) -> dict:
    event = get_current_event(db)
    row = db.get(Submission, submission_id)
    if not row or row.event_id != event.id:
        raise HTTPException(status_code=404, detail="投稿不存在")
    path = absolute_storage_path(row.storage_path)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="投稿文件不存在")
    return {
        "download_url": f"{get_settings().api_prefix}/admin/submissions/{submission_id}/download",
        "file_name": row.file_name,
        "file_size": path.stat().st_size,
    }


def _prepare_submission_zip(rows: list[Submission], filename: str) -> PreparedZip:
    if len(rows) > MAX_BATCH_FILES:
        raise HTTPException(status_code=413, detail=f"一次最多下载 {MAX_BATCH_FILES} 份投稿")
    existing: list[tuple[Submission, Path]] = []
    missing: list[Submission] = []
    total_size = 0
    for row in rows:
        path = absolute_storage_path(row.storage_path)
        if not path.is_file():
            missing.append(row)
            continue
        total_size += path.stat().st_size
        if total_size > MAX_BATCH_SOURCE_BYTES:
            raise HTTPException(status_code=413, detail="所选投稿原文件总量不能超过 10 GiB")
        existing.append((row, path))
    if not existing:
        raise HTTPException(status_code=404, detail="所选投稿文件均不存在")

    entries: list[DownloadEntry] = []
    used_names: set[str] = set()
    for row, path in existing:
        user_code = row.user.user_code if row.user else str(row.user_id)
        song_name = row.source_song.song_name if row.source_song else "未关联曲目"
        base = safe_download_name(
            f"{row.track}_{user_code}_{song_name}_{row.id}_{row.file_name}",
            f"submission_{row.id}{path.suffix}",
        )
        name = base
        counter = 2
        while name.casefold() in used_names:
            stem, suffix = Path(base).stem, Path(base).suffix
            name = f"{stem}_{counter}{suffix}"
            counter += 1
        used_names.add(name.casefold())
        entries.append(DownloadEntry(path=path, archive_name=name))
    report = ""
    if missing:
        report = "以下投稿文件不存在：\n" + "\n".join(f"- ID {row.id}: {row.file_name}" for row in missing)
    return prepare_streaming_zip(entries, file_name=filename, report=report)
