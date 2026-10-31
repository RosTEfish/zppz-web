"""Upload-intent, local content, and processing-job routes."""

from __future__ import annotations

import tempfile
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import get_current_user
from app.core.time import as_utc, utc_now
from app.db.session import get_db
from app.models import (
    Song,
    Submission,
    SubmissionProcessingJob,
    SubmissionUploadIntent,
    User,
)
from app.modules.banlist.service import enforce_song_allowed
from app.modules.downloads import content_disposition
from app.modules.events.service import get_current_event
from app.modules.guess_game.importer import (
    ArchiveParseError,
    build_public_package,
    parse_archive,
)
from app.modules.object_storage import get_object_store, materialized_object
from app.modules.preview.service import build_preview_bundle, commit_preview_nonfatal
from app.modules.submissions.service import (
    drain_storage_deletions_in_background,
    enqueue_storage_deletion,
)
from app.modules.submissions.support import (
    _can_manage_submissions,
    _create_upload_intent,
    _demote_existing_j_track,
    _eligible_song,
    _intent_response,
    _normalize_track,
    _reject_intent,
    _require_participant,
    _require_submission_phase,
    _submission_options,
    _sync_and_commit,
)
from app.schemas import (
    SubmissionProcessingJobRead,
    SubmissionUploadIntentCreate,
    SubmissionUploadIntentRead,
)


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
    if intent.status not in {"pending", "processing"} or (
        intent.status == "pending" and as_utc(intent.expires_at) < utc_now()
    ):
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
    if intent.status not in {"pending", "processing"} or (
        intent.status == "pending" and as_utc(intent.expires_at) < utc_now()
    ):
        try:
            get_object_store().delete(intent.object_key)
        except Exception:  # noqa: S110
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
                row.public_package_status = "ready"
                row.public_package_message = ""
                row.file_size = info.size
                row.track_duration_seconds = parsed.track_duration_seconds
                row.has_readme = parsed.has_readme
                row.source_kind = source_kind
                intent.status = "completed"
                intent.result_submission_id = row.id
                _sync_and_commit(db, row, parsed, match_source_type=old_track)
                if get_settings().preview_enabled:
                    preview_bundle = build_preview_bundle(
                        db,
                        event_id=event.id,
                        source_type="submission",
                        source_id=row.id,
                        source_storage_path=final_source,
                        parsed=parsed,
                    )
                    commit_preview_nonfatal(db, preview_bundle)
            except Exception:
                db.rollback()
                for key in created_keys:
                    try:
                        store.delete(key)
                    except Exception:  # noqa: S110
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
        except Exception:  # noqa: S110
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


def _confirm_and_enqueue_intent(
    db: Session,
    intent: SubmissionUploadIntent,
    *,
    enforce_phase: bool,
) -> dict:
    from app.modules.submissions.processing import (
        ActiveProcessingJobConflict,
        enqueue_upload_job,
        serialize_processing_job,
    )

    existing = db.scalar(
        select(SubmissionProcessingJob).where(
            SubmissionProcessingJob.upload_intent_id == intent.id
        )
    )
    if existing:
        return serialize_processing_job(db, existing, include_private=bool(intent.is_admin))
    if intent.status != "pending" or as_utc(intent.expires_at) < utc_now():
        if intent.status == "pending":
            intent.status = "expired"
            db.commit()
        raise HTTPException(status_code=410, detail="上传意图已失效，请重新选择文件")
    event = get_current_event(db)
    if intent.event_id != event.id:
        raise HTTPException(status_code=409, detail="投稿赛事已经变更")
    if enforce_phase:
        _require_submission_phase(db, event)
    try:
        info = get_object_store().head(intent.object_key)
    except Exception as exc:
        raise HTTPException(status_code=409, detail="R2 中尚未找到完整上传文件，请重试") from exc
    if info.size != intent.file_size:
        _reject_intent(db, intent, "R2 对象大小与上传声明不一致")
    if get_object_store().backend == "r2" and info.content_type != intent.content_type:
        _reject_intent(db, intent, "R2 对象 Content-Type 与上传声明不一致")
    try:
        job = enqueue_upload_job(db, intent)
    except ActiveProcessingJobConflict:
        _reject_intent(db, intent, "同一投稿目标已有后台任务，请等待完成后重试", 409)
    return serialize_processing_job(db, job, include_private=bool(intent.is_admin))


def complete_submission_upload_intent(
    intent_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    intent = db.get(SubmissionUploadIntent, intent_id)
    if not intent or intent.user_id != user.id or intent.is_admin:
        raise HTTPException(status_code=404, detail="上传意图不存在")
    return _confirm_and_enqueue_intent(db, intent, enforce_phase=True)


def submission_upload_intent_status(
    intent_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    from app.modules.submissions.processing import serialize_processing_job

    intent = db.get(SubmissionUploadIntent, intent_id)
    if not intent or intent.user_id != user.id or intent.is_admin:
        raise HTTPException(status_code=404, detail="上传意图不存在")
    job = db.scalar(
        select(SubmissionProcessingJob).where(
            SubmissionProcessingJob.upload_intent_id == intent.id
        )
    )
    if not job:
        raise HTTPException(status_code=409, detail="上传文件尚未确认入队")
    return serialize_processing_job(db, job)


def submission_processing_jobs(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    from app.modules.submissions.processing import list_visible_jobs, serialize_processing_jobs

    event = get_current_event(db)
    return serialize_processing_jobs(db, list_visible_jobs(db, event_id=event.id, user_id=user.id))


def cancel_submission_processing_job(
    job_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    from app.modules.submissions.processing import cancel_processing_job, serialize_processing_job

    event = get_current_event(db)
    job = db.get(SubmissionProcessingJob, job_id)
    if not job or job.event_id != event.id or job.user_id != user.id:
        raise HTTPException(status_code=404, detail="后台任务不存在")
    cancelled = cancel_processing_job(db, job)
    return serialize_processing_job(db, cancelled)


def cancel_submission_upload_intent(
    intent_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    intent = db.get(SubmissionUploadIntent, intent_id)
    if not intent or intent.user_id != user.id or intent.is_admin:
        raise HTTPException(status_code=404, detail="上传意图不存在")
    if db.scalar(
        select(SubmissionProcessingJob.id).where(
            SubmissionProcessingJob.upload_intent_id == intent.id
        )
    ):
        raise HTTPException(status_code=409, detail="文件已经进入后台处理，无法取消")
    if intent.status != "pending":
        raise HTTPException(status_code=409, detail="上传已经确认，无法取消")
    intent.status = "cancelled"
    db.commit()
    try:
        get_object_store().delete(intent.object_key)
    except Exception:
        enqueue_storage_deletion(db, intent.object_key)
        db.commit()


def register_upload_routes(router: APIRouter) -> None:
    router.post("/upload-intents", response_model=SubmissionUploadIntentRead)(create_submission_upload_intent)
    router.put("/upload-intents/{intent_id}/content", status_code=204)(upload_intent_local_content)
    router.post("/upload-intents/{intent_id}/complete", response_model=SubmissionProcessingJobRead)(complete_submission_upload_intent)
    router.get("/upload-intents/{intent_id}/status", response_model=SubmissionProcessingJobRead)(submission_upload_intent_status)
    router.get("/processing-jobs", response_model=list[SubmissionProcessingJobRead])(submission_processing_jobs)
    router.post("/processing-jobs/{job_id}/cancel", response_model=SubmissionProcessingJobRead)(cancel_submission_processing_job)
    router.delete("/upload-intents/{intent_id}", status_code=204)(cancel_submission_upload_intent)
