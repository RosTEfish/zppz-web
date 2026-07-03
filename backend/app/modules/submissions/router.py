from __future__ import annotations

import re
import tempfile
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.background import BackgroundTasks
from fastapi.responses import FileResponse
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.security import get_current_user, require_role
from app.db.session import get_db
from app.models import DrawAssignment, GuessChart, ImportIssue, Song, Submission, User
from app.modules.common import serialize_song, serialize_submission
from app.modules.events.service import get_current_event
from app.modules.guess_game.importer import (
    ArchiveParseError,
    ParsedArchive,
    delete_cover_paths,
    delete_source_charts,
    parse_stored_archive,
    sync_parsed_source,
)
from app.modules.submissions.service import absolute_storage_path, delete_stored_file, save_upload
from app.schemas import StoredFileRead, SubmissionTargetsResponse


router = APIRouter(prefix="/submissions", tags=["submissions"])
admin_router = APIRouter(prefix="/admin/submissions", tags=["admin-submissions"])

MAX_BATCH_FILES = 500
MAX_BATCH_SOURCE_BYTES = 10 * 1024 * 1024 * 1024


def _validated_upload(storage_path: str) -> ParsedArchive:
    try:
        return parse_stored_archive(storage_path)
    except ArchiveParseError as exc:
        delete_stored_file(storage_path)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        delete_stored_file(storage_path)
        raise


def _require_participant(user: User) -> None:
    if user.identity != "participant":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="仅参赛者可以上传投稿")


def _require_submissions_open(event) -> None:
    if not event.settings.submissions_open:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="投稿尚未开放")


def _normalize_track(track: str | None, fallback: str = "normal") -> str:
    value = (track or fallback).strip().lower()
    if value not in {"normal", "j"}:
        raise HTTPException(status_code=400, detail="投稿赛道必须为 normal 或 j")
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
        )
    )
    if not assignment:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="该曲目不在你的投稿候选中")
    return song, "assigned"


def _ensure_j_track_available(db: Session, event_id: int, user_id: int, exclude_id: int | None = None) -> None:
    stmt = select(Submission).where(
        Submission.event_id == event_id,
        Submission.user_id == user_id,
        Submission.track == "j",
    )
    if exclude_id is not None:
        stmt = stmt.where(Submission.id != exclude_id)
    existing = db.scalar(stmt)
    if existing:
        song_name = existing.source_song.song_name if existing.source_song else existing.file_name
        raise HTTPException(status_code=409, detail=f"每位参赛者最多一份 J 稿，当前 J 稿为：{song_name}")


def _sync_and_commit(db: Session, row: Submission, parsed: ParsedArchive, old_track: str | None = None) -> None:
    result = None
    previous_track = old_track or row.track
    try:
        if previous_track != row.track:
            for chart in db.scalars(
                select(GuessChart).where(
                    GuessChart.event_id == row.event_id,
                    GuessChart.source_submission_type == previous_track,
                    GuessChart.source_submission_id == row.id,
                )
            ).all():
                chart.source_submission_type = row.track
            for issue in db.scalars(
                select(ImportIssue).where(
                    ImportIssue.event_id == row.event_id,
                    ImportIssue.source_type == previous_track,
                    ImportIssue.source_id == row.id,
                )
            ).all():
                issue.source_type = row.track

        result = sync_parsed_source(
            db,
            event_id=row.event_id,
            source_type=row.track,
            source_id=row.id,
            file_name=row.file_name,
            storage_path=row.storage_path,
            parsed=parsed,
            is_self_selected=row.source_kind == "self",
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
    song: Song,
    source_kind: str,
    track: str,
    file: UploadFile,
) -> Submission:
    existing = db.scalar(
        select(Submission).where(
            Submission.event_id == event_id,
            Submission.user_id == user.id,
            Submission.source_song_id == song.id,
        )
    )
    if existing:
        raise HTTPException(status_code=409, detail="该候选已有投稿，请使用替换功能")
    if track == "j":
        _ensure_j_track_available(db, event_id, user.id)

    storage_path, size = save_upload(file, f"events/{event_id}/submissions/{user.id}")
    parsed = _validated_upload(storage_path)
    row = Submission(
        event_id=event_id,
        user_id=user.id,
        source_song_id=song.id,
        source_kind=source_kind,
        track=track,
        file_name=file.filename or "upload",
        storage_path=storage_path,
        file_size=size,
    )
    try:
        db.add(row)
        db.flush()
        _sync_and_commit(db, row, parsed)
    except Exception:
        db.rollback()
        delete_stored_file(storage_path)
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
) -> Submission:
    next_track = _normalize_track(track, row.track)
    if next_track == "j":
        _ensure_j_track_available(db, row.event_id, row.user_id, row.id)
    new_storage_path, size = save_upload(file, f"events/{row.event_id}/submissions/{row.user_id}")
    parsed = _validated_upload(new_storage_path)
    old_storage_path = row.storage_path
    old_track = row.track
    row.file_name = file.filename or "upload"
    row.storage_path = new_storage_path
    row.file_size = size
    row.track = next_track
    if source_kind:
        row.source_kind = source_kind
    try:
        _sync_and_commit(db, row, parsed, old_track=old_track)
    except Exception:
        delete_stored_file(new_storage_path)
        raise
    delete_stored_file(old_storage_path)
    db.refresh(row)
    return row


def _delete_submission(db: Session, row: Submission) -> None:
    storage_path = row.storage_path
    _, cover_paths = delete_source_charts(db, row.event_id, row.track, row.id)
    db.delete(row)
    db.commit()
    delete_stored_file(storage_path)
    delete_cover_paths(cover_paths)


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
        "is_open": event.settings.submissions_open,
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
    song_id: int = Form(...),
    track: str = Form("normal"),
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    _require_participant(user)
    event = get_current_event(db)
    _require_submissions_open(event)
    song, source_kind = _eligible_song(db, event.id, user, song_id)
    row = _create_submission(
        db,
        event_id=event.id,
        user=user,
        song=song,
        source_kind=source_kind,
        track=_normalize_track(track),
        file=file,
    )
    return serialize_submission(row)


@router.post("/{submission_id}/replace", response_model=StoredFileRead)
def replace_submission(
    submission_id: int,
    file: UploadFile = File(...),
    track: str | None = Form(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    _require_participant(user)
    event = get_current_event(db)
    _require_submissions_open(event)
    row = db.scalar(select(Submission).options(*_submission_options()).where(Submission.id == submission_id))
    if not row or row.user_id != user.id or row.event_id != event.id or row.source_song_id is None:
        raise HTTPException(status_code=404, detail="投稿不存在")
    song, source_kind = _eligible_song(db, event.id, user, row.source_song_id)
    row = _replace_submission(db, row, file, track=track, source_kind=source_kind)
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
    _require_submissions_open(event)
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
    _require_submissions_open(event)
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
    background_tasks: BackgroundTasks,
    ids: str | None = Query(None),
    track: str | None = Query(None),
    _: User = Depends(require_role("admin", "pool_editor")),
    db: Session = Depends(get_db),
):
    event = get_current_event(db)
    stmt = select(Submission).options(*_submission_options()).where(Submission.event_id == event.id)
    selected_ids = _parse_ids(ids)
    if selected_ids is not None:
        stmt = stmt.where(Submission.id.in_(selected_ids))
    if track:
        stmt = stmt.where(Submission.track == _normalize_track(track))
    rows = list(db.scalars(stmt.order_by(Submission.id.asc())).all())
    if not rows:
        raise HTTPException(status_code=404, detail="没有可下载的投稿")
    return _build_submission_zip(rows, background_tasks, "submissions.zip")


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
    return FileResponse(path, filename=row.file_name)


def _parse_ids(value: str | None) -> list[int] | None:
    if value is None or not value.strip():
        return None
    try:
        result = list(dict.fromkeys(int(item.strip()) for item in value.split(",") if item.strip()))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="ids 必须是逗号分隔的数字") from exc
    if not result:
        raise HTTPException(status_code=400, detail="请至少选择一份投稿")
    if len(result) > MAX_BATCH_FILES:
        raise HTTPException(status_code=413, detail=f"一次最多下载 {MAX_BATCH_FILES} 份投稿")
    return result


def _safe_zip_name(value: str, fallback: str) -> str:
    cleaned = re.sub(r"[\\/:*?\"<>|\x00-\x1f]+", "_", value).strip(" .")
    return cleaned[:180] or fallback


def _build_submission_zip(rows: list[Submission], background_tasks: BackgroundTasks, filename: str):
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

    temporary = tempfile.NamedTemporaryFile(prefix="zppz-submissions-", suffix=".zip", delete=False)
    temporary_path = Path(temporary.name)
    temporary.close()
    used_names: set[str] = set()
    try:
        with ZipFile(temporary_path, "w", ZIP_DEFLATED) as archive:
            for row, path in existing:
                user_code = row.user.user_code if row.user else str(row.user_id)
                song_name = row.source_song.song_name if row.source_song else "未关联曲目"
                base = _safe_zip_name(
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
                archive.write(path, arcname=name)
            if missing:
                archive.writestr(
                    "_下载报告.txt",
                    "以下投稿文件不存在：\n" + "\n".join(f"- ID {row.id}: {row.file_name}" for row in missing),
                )
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise
    background_tasks.add_task(temporary_path.unlink, missing_ok=True)
    return FileResponse(temporary_path, media_type="application/zip", filename=filename)
