"""Shared submission helpers used by the route modules and the processing worker."""

from __future__ import annotations

import shutil
import tempfile
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.core.security import is_owner
from app.core.time import utc_now_naive
from app.models import (
    DrawAssignment,
    GuessChart,
    ImportIssue,
    Song,
    Submission,
    SubmissionProcessingJob,
    SubmissionUploadIntent,
    User,
)
from app.modules.banlist.service import enforce_song_allowed
from app.modules.events.phase_policy import get_phase_status
from app.modules.guess_game.importer import (
    ArchiveParseError,
    ParsedArchive,
    archive_has_readme,
    delete_cover_paths,
    delete_source_charts,
    parse_stored_archive,
    sync_parsed_source,
    write_public_package,
)
from app.modules.object_storage import get_object_store, materialized_object
from app.modules.preview.service import build_preview_bundle, commit_preview_nonfatal, delete_preview_bundle
from app.modules.submissions.service import (
    archive_content_type,
    delete_stored_file,
    drain_storage_deletions,
    enqueue_storage_deletion,
    save_upload,
    validate_upload_metadata,
)

MAX_BATCH_FILES = 500
MAX_BATCH_SOURCE_BYTES = 10 * 1024 * 1024 * 1024
_TRACK_VALUES = ("normal", "j", "exhibition")

def _can_manage_submissions(user: User) -> bool:
    return is_owner(user) or user.has_role("admin") or user.has_role("pool_editor")


def _intent_response(intent: SubmissionUploadIntent) -> dict:
    store = get_object_store()
    return {
        "id": intent.id,
        "upload_url": store.create_upload_url(intent.id, intent.content_type, intent.object_key),
        "method": "PUT",
        "headers": {"Content-Type": intent.content_type},
        "expires_at": intent.expires_at,
    }


def _create_upload_intent(
    db: Session,
    *,
    event_id: int,
    user: User,
    song_id: int | None,
    submission_id: int | None,
    track: str,
    file_name: str,
    file_size: int,
    content_type: str,
    acknowledge_ban_warning: bool,
    is_admin: bool,
) -> SubmissionUploadIntent:
    safe_file_name = Path(file_name.replace("\\", "/")).name.strip()
    if not safe_file_name or any(ord(character) < 32 for character in safe_file_name):
        raise HTTPException(status_code=422, detail="投稿文件名无效")
    suffix = validate_upload_metadata(safe_file_name, file_size, content_type)
    now = utc_now_naive()
    active_intent_statuses = ("pending", "uploaded", "processing")
    in_progress = None
    if submission_id is not None:
        in_progress = db.scalar(
            select(SubmissionUploadIntent.id).where(
                SubmissionUploadIntent.event_id == event_id,
                SubmissionUploadIntent.replace_submission_id == submission_id,
                SubmissionUploadIntent.status.in_(active_intent_statuses),
                or_(
                    SubmissionUploadIntent.status != "pending",
                    SubmissionUploadIntent.expires_at > now,
                ),
            )
        )
    elif song_id is not None:
        in_progress = db.scalar(
            select(SubmissionUploadIntent.id).where(
                SubmissionUploadIntent.event_id == event_id,
                SubmissionUploadIntent.user_id == user.id,
                SubmissionUploadIntent.source_song_id == song_id,
                SubmissionUploadIntent.replace_submission_id.is_(None),
                SubmissionUploadIntent.status.in_(active_intent_statuses),
                or_(
                    SubmissionUploadIntent.status != "pending",
                    SubmissionUploadIntent.expires_at > now,
                ),
            )
        )
    if in_progress:
        raise HTTPException(
            status_code=409,
            detail="上一份投稿仍在服务器处理中，请等待完成并刷新页面后再替换",
        )
    if track == "j":
        active_j = db.scalar(
            select(SubmissionProcessingJob.id)
            .join(
                SubmissionUploadIntent,
                SubmissionUploadIntent.id == SubmissionProcessingJob.upload_intent_id,
            )
            .where(
                SubmissionProcessingJob.event_id == event_id,
                SubmissionProcessingJob.user_id == user.id,
                SubmissionProcessingJob.status.in_(("queued", "processing")),
                SubmissionUploadIntent.track == "j",
            )
        )
        if active_j:
            raise HTTPException(status_code=409, detail="已有一个 J 投稿正在后台处理，请等待完成")
    intent_id = uuid4().hex
    intent = SubmissionUploadIntent(
        id=intent_id,
        event_id=event_id,
        user_id=user.id,
        source_song_id=song_id,
        replace_submission_id=submission_id,
        track=track,
        file_name=safe_file_name,
        file_size=file_size,
        content_type=content_type,
        object_key=f"pending/events/{event_id}/users/{user.id}/{intent_id}{suffix}",
        acknowledge_ban_warning=acknowledge_ban_warning,
        is_admin=is_admin,
        expires_at=utc_now_naive() + timedelta(seconds=get_settings().upload_intent_ttl_seconds),
    )
    db.add(intent)
    db.commit()
    return intent


def _legacy_upload_metadata(file: UploadFile) -> tuple[str, int, str]:
    file_name = Path(file.filename or "upload").name
    content_type = archive_content_type(file_name)
    file.file.seek(0, 2)
    file_size = file.file.tell()
    file.file.seek(0)
    validate_upload_metadata(file_name, file_size, content_type)
    return file_name, file_size, content_type


def _put_legacy_upload(intent: SubmissionUploadIntent, file: UploadFile, db: Session) -> None:
    store = get_object_store()
    try:
        with tempfile.TemporaryDirectory(prefix="zppz-legacy-upload-") as directory:
            path = Path(directory) / Path(intent.file_name).name
            with path.open("wb") as output:
                shutil.copyfileobj(file.file, output, length=1024 * 1024)
            store.put_file(intent.object_key, path, content_type=intent.content_type)
    except Exception as upload_error:
        cleanup_error = None
        try:
            store.delete(intent.object_key)
        except Exception as exc:
            cleanup_error = exc
        intent.status = "failed"
        intent.error_message = str(upload_error)[:500]
        if cleanup_error:
            intent.error_message = f"{intent.error_message}; 临时对象清理失败：{cleanup_error}"[:500]
        db.commit()
        raise


def _reject_intent(db: Session, intent: SubmissionUploadIntent, detail: str, status_code: int = 422) -> None:
    intent.status = "failed"
    intent.error_message = detail[:500]
    db.commit()
    try:
        get_object_store().delete(intent.object_key)
    except Exception:
        enqueue_storage_deletion(db, intent.object_key)
        db.commit()
    raise HTTPException(status_code=status_code, detail=detail)


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
    if value not in _TRACK_VALUES:
        raise HTTPException(status_code=422, detail="投稿类型必须为 normal、j 或 exhibition")
    return value


def _parse_tracks(tracks: str | None, track: str | None = None) -> list[str] | None:
    if tracks is not None:
        selected: list[str] = []
        for item in tracks.split(","):
            value = item.strip().lower()
            if not value:
                continue
            if value not in _TRACK_VALUES:
                raise HTTPException(status_code=422, detail="投稿类型必须为 normal、j 或 exhibition")
            if value not in selected:
                selected.append(value)
        if not selected:
            raise HTTPException(status_code=422, detail="请至少选择一个赛道")
        return selected
    if track:
        return [_normalize_track(track)]
    return None


def _backfill_readme_flags(db: Session, rows: list[Submission]) -> None:
    pending = [row for row in rows if row.has_readme is None]
    changed = False
    for row in pending:
        suffix = Path(row.storage_path).suffix.lower()
        try:
            with materialized_object(row.storage_path, suffix) as path:
                row.has_readme = archive_has_readme(path)
            changed = True
        except Exception:  # noqa: S112
            continue
    if changed:
        db.commit()


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
        row.has_readme = parsed.has_readme
        public_storage_path = write_public_package(event_id, row.id, parsed)
        row.public_storage_path = public_storage_path
        row.public_package_status = "ready"
        row.public_package_message = ""
        _sync_and_commit(db, row, parsed)
        if get_settings().preview_enabled:
            preview_bundle = build_preview_bundle(
                db,
                event_id=event_id,
                source_type="submission",
                source_id=row.id,
                source_storage_path=storage_path,
                parsed=parsed,
            )
            commit_preview_nonfatal(db, preview_bundle)
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
        row.has_readme = parsed.has_readme
        new_public_storage_path = write_public_package(row.event_id, row.id, parsed)
        row.public_storage_path = new_public_storage_path
        row.public_package_status = "ready"
        row.public_package_message = ""
        if source_kind:
            row.source_kind = source_kind
        _sync_and_commit(db, row, parsed, match_source_type=old_track)
        if get_settings().preview_enabled:
            preview_bundle = build_preview_bundle(
                db,
                event_id=row.event_id,
                source_type="submission",
                source_id=row.id,
                source_storage_path=new_storage_path,
                parsed=parsed,
            )
            commit_preview_nonfatal(db, preview_bundle)
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
    enqueue_storage_deletion(db, storage_path)
    enqueue_storage_deletion(db, public_storage_path)
    db.commit()
    drain_storage_deletions(db)
    delete_cover_paths(cover_paths)


def _stage_delete_submission(db: Session, row: Submission) -> tuple[str, str | None, set[str]]:
    active_jobs = list(
        db.scalars(
            select(SubmissionProcessingJob).where(
                SubmissionProcessingJob.status.in_(("queued", "processing")),
                or_(
                    SubmissionProcessingJob.replace_submission_id == row.id,
                    SubmissionProcessingJob.result_submission_id == row.id,
                ),
            )
        ).all()
    )
    for job in active_jobs:
        job.status = "cancelled"
        job.finished_at = utc_now_naive()
        job.lease_until = None
        job.next_attempt_at = None
        job.error_code = "source_deleted"
        job.error_message = "投稿已删除，后台任务已取消"
        if job.upload_intent_id:
            intent = db.get(SubmissionUploadIntent, job.upload_intent_id)
            if intent:
                intent.status = "cancelled"
                intent.error_message = job.error_message
                enqueue_storage_deletion(db, intent.object_key)
    _, cover_paths = delete_source_charts(db, row.event_id, row.track, row.id)
    delete_preview_bundle(db, row.event_id, "submission", row.id)
    storage_path = row.storage_path
    db.delete(row)
    return storage_path, row.public_storage_path, cover_paths


def _submission_options():
    return (
        selectinload(Submission.user).selectinload(User.roles),
        selectinload(Submission.source_song).selectinload(Song.submitter).selectinload(User.roles),
    )
