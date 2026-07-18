from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
import shutil
import tempfile
from urllib.parse import urlencode
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import RedirectResponse
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.core.security import get_current_user, is_owner, require_role
from app.db.session import get_db
from app.models import DrawAssignment, GuessChart, ImportIssue, Song, Submission, SubmissionUploadIntent, User
from app.modules.banlist.service import enforce_song_allowed
from app.modules.common import serialize_song, serialize_submission
from app.modules.downloads import (
    DOWNLOAD_TOKEN_PATTERN,
    content_disposition,
    DownloadEntry,
    PreparedZip,
    file_download_response,
    parse_csv_ids,
    prepare_streaming_zip,
    safe_download_name,
)
from app.modules.draw.service import ensure_global_draw
from app.modules.events.service import get_current_event
from app.modules.events.phase_policy import get_phase_status
from app.modules.guess_game.importer import (
    ArchiveParseError,
    ParsedArchive,
    build_public_package,
    delete_cover_paths,
    delete_source_charts,
    parse_stored_archive,
    parse_archive,
    sync_parsed_source,
    write_public_package,
)
from app.modules.object_storage import get_object_store, materialized_object
from app.modules.submissions.service import (
    absolute_storage_path,
    archive_content_type,
    delete_stored_file,
    drain_storage_deletions,
    drain_storage_deletions_in_background,
    enqueue_storage_deletion,
    save_upload,
    validate_upload_metadata,
)
from app.schemas import (
    AdminSubmissionUploadIntentCreate,
    BatchDeleteRequest,
    BatchDeleteResponse,
    DownloadPreparation,
    StoredFileRead,
    SubmissionTargetsResponse,
    SubmissionTrackUpdate,
    SubmissionUploadIntentCreate,
    SubmissionUploadIntentRead,
)


router = APIRouter(prefix="/submissions", tags=["submissions"])
admin_router = APIRouter(prefix="/admin/submissions", tags=["admin-submissions"])

MAX_BATCH_FILES = 500
MAX_BATCH_SOURCE_BYTES = 10 * 1024 * 1024 * 1024


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
        expires_at=datetime.utcnow() + timedelta(seconds=get_settings().upload_intent_ttl_seconds),
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
        pass
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
    enqueue_storage_deletion(db, storage_path)
    enqueue_storage_deletion(db, public_storage_path)
    db.commit()
    drain_storage_deletions(db)
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
    if get_phase_status(db, event).can("submission"):
        ensure_global_draw(db)
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


@router.post("/upload-intents", response_model=SubmissionUploadIntentRead)
def create_submission_upload_intent(
    payload: SubmissionUploadIntentCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    _require_participant(user)
    event = get_current_event(db)
    _require_submission_phase(db, event)
    track = _normalize_track(payload.track)
    song: Song | None
    submission_id = payload.submission_id
    if submission_id is not None:
        row = db.scalar(select(Submission).where(Submission.id == submission_id))
        if not row or row.user_id != user.id or row.event_id != event.id:
            raise HTTPException(status_code=404, detail="投稿不存在")
        if payload.song_id is not None and payload.song_id != row.source_song_id:
            raise HTTPException(status_code=422, detail="替换投稿不能更改关联曲目")
        if row.source_song_id is None:
            if row.track != "exhibition" or track != "exhibition":
                raise HTTPException(status_code=422, detail="独立场外投稿不能改为普通或 J 投稿")
            song = None
        else:
            song, _ = _eligible_song(db, event.id, user, row.source_song_id)
    elif track == "exhibition":
        song = None if payload.song_id is None else _eligible_song(db, event.id, user, payload.song_id)[0]
    else:
        if payload.song_id is None:
            raise HTTPException(status_code=422, detail="普通和 J 投稿必须关联候选曲目")
        song, _ = _eligible_song(db, event.id, user, payload.song_id)
        duplicate = db.scalar(
            select(Submission.id).where(
                Submission.event_id == event.id,
                Submission.user_id == user.id,
                Submission.source_song_id == song.id,
            )
        )
        if duplicate:
            raise HTTPException(status_code=409, detail="该候选已有投稿，请使用替换功能")
    if song is not None:
        enforce_song_allowed(db, song.song_name, song.artist, payload.acknowledge_ban_warning)
    intent = _create_upload_intent(
        db,
        event_id=event.id,
        user=user,
        song_id=song.id if song else None,
        submission_id=submission_id,
        track=track,
        file_name=payload.file_name,
        file_size=payload.file_size,
        content_type=payload.content_type,
        acknowledge_ban_warning=payload.acknowledge_ban_warning,
        is_admin=False,
    )
    return _intent_response(intent)


@router.put("/upload-intents/{intent_id}/content", status_code=204)
async def upload_intent_local_content(
    intent_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    store = get_object_store()
    if store.backend != "local":
        raise HTTPException(status_code=404, detail="本地上传入口未启用")
    intent = db.get(SubmissionUploadIntent, intent_id)
    if not intent or intent.user_id != user.id:
        raise HTTPException(status_code=404, detail="上传意图不存在")
    if intent.is_admin and not _can_manage_submissions(user):
        raise HTTPException(status_code=403, detail="没有权限执行此操作")
    if intent.status != "pending" or intent.expires_at < datetime.utcnow():
        raise HTTPException(status_code=410, detail="上传意图已失效")
    if request.headers.get("content-type", "").split(";", 1)[0].strip() != intent.content_type:
        raise HTTPException(status_code=422, detail="上传 Content-Type 与签名不一致")
    target = store.writable_path(intent.object_key)
    written = 0
    try:
        with target.open("wb") as output:
            async for chunk in request.stream():
                written += len(chunk)
                if written > intent.file_size or written > get_settings().max_upload_mb * 1024 * 1024:
                    raise HTTPException(status_code=413, detail="上传文件大小超过声明值")
                output.write(chunk)
        if written != intent.file_size:
            raise HTTPException(status_code=422, detail="上传文件大小与声明值不一致")
    except Exception:
        target.unlink(missing_ok=True)
        raise
    return None


def _complete_intent(
    intent: SubmissionUploadIntent,
    user: User,
    db: Session,
    background_tasks: BackgroundTasks,
) -> Submission:
    if intent.result_submission_id:
        result = db.scalar(select(Submission).options(*_submission_options()).where(Submission.id == intent.result_submission_id))
        if result:
            background_tasks.add_task(drain_storage_deletions_in_background)
            return result
    if intent.status == "failed":
        raise HTTPException(status_code=422, detail=intent.error_message or "上传校验失败")
    if intent.status != "pending" or intent.expires_at < datetime.utcnow():
        try:
            get_object_store().delete(intent.object_key)
        except Exception:
            pass
        if intent.status == "pending":
            intent.status = "expired"
            db.commit()
        raise HTTPException(status_code=410, detail="上传意图已失效，请重新选择文件")

    event = get_current_event(db)
    if intent.event_id != event.id:
        raise HTTPException(status_code=409, detail="投稿赛事已经变更")
    if not intent.is_admin:
        _require_participant(user)
        _require_submission_phase(db, event)

    row = None
    if intent.replace_submission_id:
        row = db.scalar(select(Submission).options(*_submission_options()).where(Submission.id == intent.replace_submission_id))
        if not row or row.event_id != event.id:
            raise HTTPException(status_code=404, detail="待替换投稿不存在")
        if not intent.is_admin and row.user_id != user.id:
            raise HTTPException(status_code=404, detail="待替换投稿不存在")

    song: Song | None = None
    source_kind = "exhibition"
    if row and row.source_song_id is not None:
        song = db.get(Song, row.source_song_id)
        source_kind = row.source_kind
    elif intent.source_song_id is not None:
        if intent.is_admin:
            song = db.get(Song, intent.source_song_id)
            source_kind = row.source_kind if row else "self"
        else:
            song, source_kind = _eligible_song(db, event.id, user, intent.source_song_id)
    if song is not None:
        enforce_song_allowed(db, song.song_name, song.artist, intent.acknowledge_ban_warning)

    store = get_object_store()
    try:
        info = store.head(intent.object_key)
    except Exception as exc:
        raise HTTPException(status_code=409, detail="R2 中尚未找到完整上传文件，请重试") from exc
    if info.size != intent.file_size:
        _reject_intent(db, intent, "R2 对象大小与上传声明不一致")
    if store.backend == "r2" and info.content_type != intent.content_type:
        _reject_intent(db, intent, "R2 对象 Content-Type 与上传声明不一致")

    suffix = Path(intent.file_name).suffix.lower()
    try:
        with materialized_object(intent.object_key, suffix) as archive_path:
            parsed = parse_archive(archive_path)
            old_storage_path = row.storage_path if row else None
            old_public_storage_path = row.public_storage_path if row else None
            old_track = row.track if row else None
            if intent.track == "j":
                _demote_existing_j_track(db, event.id, row.user_id if row else user.id, row.id if row else None)
            if row is None:
                row = Submission(
                    event_id=event.id,
                    user_id=user.id,
                    source_song_id=song.id if song else None,
                    source_kind=source_kind,
                    track=intent.track,
                    file_name=intent.file_name,
                    storage_path=intent.object_key,
                    file_size=info.size,
                )
                db.add(row)
                db.flush()
            elif not intent.is_admin and row.source_song_id is None and intent.track != "exhibition":
                raise HTTPException(status_code=422, detail="独立场外投稿不能改为普通或 J 投稿")

            if row.id is None:
                raise RuntimeError("submission id was not allocated")
            final_source = f"events/{event.id}/submissions/{row.id}/source/{uuid4().hex}{suffix}"
            final_public = f"events/{event.id}/submissions/{row.id}/public/{uuid4().hex}.zip"
            created_keys: list[str] = []
            try:
                store.copy(
                    intent.object_key,
                    final_source,
                    content_type=intent.content_type,
                    content_disposition=content_disposition(intent.file_name),
                )
                created_keys.append(final_source)
                with tempfile.TemporaryDirectory(prefix="zppz-public-") as directory:
                    public_path = Path(directory) / "public.zip"
                    build_public_package(public_path, parsed)
                    store.put_file(
                        final_public,
                        public_path,
                        content_type="application/zip",
                        content_disposition=content_disposition("chart-package.zip"),
                    )
                    public_size = public_path.stat().st_size
                created_keys.append(final_public)
                row.track = intent.track
                row.file_name = intent.file_name
                row.storage_path = final_source
                row.public_storage_path = final_public
                row.public_file_size = public_size
                row.file_size = info.size
                row.track_duration_seconds = parsed.track_duration_seconds
                row.source_kind = source_kind
                intent.status = "completed"
                intent.result_submission_id = row.id
                _sync_and_commit(db, row, parsed, match_source_type=old_track)
            except Exception:
                db.rollback()
                for key in created_keys:
                    try:
                        store.delete(key)
                    except Exception:
                        pass
                raise
    except ArchiveParseError as exc:
        db.rollback()
        intent = db.get(SubmissionUploadIntent, intent.id)
        if intent:
            intent.status = "failed"
            intent.error_message = str(exc)[:500]
            db.commit()
        try:
            store.delete(intent.object_key)
        except Exception:
            pass
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    enqueue_storage_deletion(db, intent.object_key)
    if old_storage_path and old_storage_path != row.storage_path:
        enqueue_storage_deletion(db, old_storage_path)
    if old_public_storage_path and old_public_storage_path != row.public_storage_path:
        enqueue_storage_deletion(db, old_public_storage_path)
    db.commit()
    background_tasks.add_task(drain_storage_deletions_in_background)
    db.refresh(row)
    row.user = db.get(User, row.user_id)
    row.source_song = song
    return row


@router.post("/upload-intents/{intent_id}/complete", response_model=StoredFileRead)
def complete_submission_upload_intent(
    intent_id: str,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    intent = db.get(SubmissionUploadIntent, intent_id)
    if not intent or intent.user_id != user.id or intent.is_admin:
        raise HTTPException(status_code=404, detail="上传意图不存在")
    return serialize_submission(_complete_intent(intent, user, db, background_tasks))


@router.post("", response_model=StoredFileRead, deprecated=True)
def upload_submission(
    background_tasks: BackgroundTasks,
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
        song = None if song_id is None else _eligible_song(db, event.id, user, song_id)[0]
    else:
        if song_id is None:
            raise HTTPException(status_code=422, detail="普通和 J 投稿必须关联候选曲目")
        song, _ = _eligible_song(db, event.id, user, song_id)
    file_name, file_size, content_type = _legacy_upload_metadata(file)
    intent = _create_upload_intent(
        db,
        event_id=event.id,
        user=user,
        song_id=song.id if song else None,
        submission_id=None,
        track=normalized_track,
        file_name=file_name,
        file_size=file_size,
        content_type=content_type,
        acknowledge_ban_warning=acknowledge_ban_warning,
        is_admin=False,
    )
    _put_legacy_upload(intent, file, db)
    return serialize_submission(_complete_intent(intent, user, db, background_tasks))


@router.post("/{submission_id}/replace", response_model=StoredFileRead, deprecated=True)
def replace_submission(
    submission_id: int,
    background_tasks: BackgroundTasks,
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
        song = None
    else:
        song, _ = _eligible_song(db, event.id, user, row.source_song_id)
    if song is not None:
        enforce_song_allowed(db, song.song_name, song.artist, acknowledge_ban_warning)
    file_name, file_size, content_type = _legacy_upload_metadata(file)
    intent = _create_upload_intent(
        db,
        event_id=event.id,
        user=user,
        song_id=song.id if song else None,
        submission_id=row.id,
        track=_normalize_track(track, row.track),
        file_name=file_name,
        file_size=file_size,
        content_type=content_type,
        acknowledge_ban_warning=acknowledge_ban_warning,
        is_admin=False,
    )
    _put_legacy_upload(intent, file, db)
    return serialize_submission(_complete_intent(intent, user, db, background_tasks))


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


@admin_router.post("/{submission_id}/upload-intents", response_model=SubmissionUploadIntentRead)
def create_admin_submission_upload_intent(
    submission_id: int,
    payload: AdminSubmissionUploadIntentCreate,
    admin: User = Depends(require_role("admin", "pool_editor")),
    db: Session = Depends(get_db),
) -> dict:
    event = get_current_event(db)
    row = db.get(Submission, submission_id)
    if not row or row.event_id != event.id:
        raise HTTPException(status_code=404, detail="投稿不存在")
    track = _normalize_track(payload.track, row.track)
    if row.source_song_id is None and track != "exhibition":
        raise HTTPException(status_code=422, detail="独立场外投稿不能改为普通或 J 投稿")
    intent = _create_upload_intent(
        db,
        event_id=event.id,
        user=admin,
        song_id=row.source_song_id,
        submission_id=row.id,
        track=track,
        file_name=payload.file_name,
        file_size=payload.file_size,
        content_type=payload.content_type,
        acknowledge_ban_warning=True,
        is_admin=True,
    )
    return _intent_response(intent)


@admin_router.post("/upload-intents/{intent_id}/complete", response_model=StoredFileRead)
def complete_admin_submission_upload_intent(
    intent_id: str,
    background_tasks: BackgroundTasks,
    admin: User = Depends(require_role("admin", "pool_editor")),
    db: Session = Depends(get_db),
) -> dict:
    intent = db.get(SubmissionUploadIntent, intent_id)
    if not intent or intent.user_id != admin.id or not intent.is_admin:
        raise HTTPException(status_code=404, detail="上传意图不存在")
    return serialize_submission(_complete_intent(intent, admin, db, background_tasks))


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
        for storage_path in storage_paths | public_storage_paths:
            enqueue_storage_deletion(db, storage_path)
        db.commit()
    except Exception:
        db.rollback()
        raise
    drain_storage_deletions(db)
    delete_cover_paths(cover_paths)
    return {"deleted": len(rows), "message": f"已删除 {len(rows)} 份投稿"}


@admin_router.post("/{submission_id}/replace", response_model=StoredFileRead, deprecated=True)
def admin_replace_submission(
    submission_id: int,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    track: str | None = Form(None),
    admin: User = Depends(require_role("admin", "pool_editor")),
    db: Session = Depends(get_db),
) -> dict:
    event = get_current_event(db)
    row = db.scalar(select(Submission).options(*_submission_options()).where(Submission.id == submission_id))
    if not row or row.event_id != event.id:
        raise HTTPException(status_code=404, detail="投稿不存在")
    next_track = _normalize_track(track, row.track)
    if row.source_song_id is None and next_track != "exhibition":
        raise HTTPException(status_code=422, detail="独立场外投稿不能改为普通或 J 投稿")
    file_name, file_size, content_type = _legacy_upload_metadata(file)
    intent = _create_upload_intent(
        db,
        event_id=event.id,
        user=admin,
        song_id=row.source_song_id,
        submission_id=row.id,
        track=next_track,
        file_name=file_name,
        file_size=file_size,
        content_type=content_type,
        acknowledge_ban_warning=True,
        is_admin=True,
    )
    _put_legacy_upload(intent, file, db)
    return serialize_submission(_complete_intent(intent, admin, db, background_tasks))


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
    download_token: str | None = Query(
        None,
        min_length=32,
        max_length=32,
        pattern=DOWNLOAD_TOKEN_PATTERN,
    ),
    _: User = Depends(require_role("admin", "pool_editor")),
    db: Session = Depends(get_db),
):
    event = get_current_event(db)
    rows, _, _ = _select_admin_downloads(db, event.id, ids, track)
    return _prepare_submission_zip(rows, "submissions.zip").response(download_token)


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
    store = get_object_store()
    download_url = store.create_download_url(row.storage_path, row.file_name)
    if download_url:
        return RedirectResponse(download_url, status_code=307, headers={"Cache-Control": "private, no-store"})
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
    store = get_object_store()
    try:
        info = store.head(row.storage_path)
    except Exception as exc:
        raise HTTPException(status_code=404, detail="投稿文件不存在") from exc
    download_url = store.create_download_url(row.storage_path, row.file_name)
    return {
        "download_url": download_url or f"{get_settings().api_prefix}/admin/submissions/{submission_id}/download",
        "file_name": row.file_name,
        "file_size": info.size,
    }


def _prepare_submission_zip(rows: list[Submission], filename: str) -> PreparedZip:
    if len(rows) > MAX_BATCH_FILES:
        raise HTTPException(status_code=413, detail=f"一次最多下载 {MAX_BATCH_FILES} 份投稿")
    store = get_object_store()
    existing: list[tuple[Submission, int]] = []
    missing: list[Submission] = []
    total_size = 0
    for row in rows:
        try:
            info = store.head(row.storage_path)
        except Exception:
            missing.append(row)
            continue
        total_size += info.size
        if total_size > MAX_BATCH_SOURCE_BYTES:
            raise HTTPException(status_code=413, detail="所选投稿原文件总量不能超过 10 GiB")
        existing.append((row, info.size))
    if not existing:
        raise HTTPException(status_code=404, detail="所选投稿文件均不存在")

    entries: list[DownloadEntry] = []
    used_names: set[str] = set()
    for row, object_size in existing:
        user_code = row.user.user_code if row.user else str(row.user_id)
        song_name = row.source_song.song_name if row.source_song else "未关联曲目"
        base = safe_download_name(
            f"{row.track}_{user_code}_{song_name}_{row.id}_{row.file_name}",
            f"submission_{row.id}{Path(row.file_name).suffix}",
        )
        name = base
        counter = 2
        while name.casefold() in used_names:
            stem, suffix = Path(base).stem, Path(base).suffix
            name = f"{stem}_{counter}{suffix}"
            counter += 1
        used_names.add(name.casefold())
        if store.backend == "local":
            entries.append(DownloadEntry(path=absolute_storage_path(row.storage_path), archive_name=name))
        else:
            entries.append(
                DownloadEntry(
                    path=None,
                    archive_name=name,
                    data=store.chunks(row.storage_path, object_size),
                    data_size=object_size,
                )
            )
    report = ""
    if missing:
        report = "以下投稿文件不存在：\n" + "\n".join(f"- ID {row.id}: {row.file_name}" for row in missing)
    return prepare_streaming_zip(entries, file_name=filename, report=report)
