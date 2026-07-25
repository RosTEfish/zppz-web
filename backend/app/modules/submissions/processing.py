from __future__ import annotations

from datetime import datetime, timedelta
import json
import logging
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models import (
    Event,
    PreviewBundle,
    Song,
    Submission,
    SubmissionProcessingJob,
    SubmissionUploadIntent,
    User,
)
from app.modules.banlist.service import enforce_song_allowed
from app.modules.common import serialize_submissions
from app.modules.downloads import content_disposition
from app.modules.guess_game.importer import (
    ArchiveParseError,
    PreparedArchive,
    build_public_package_from_files,
    prepare_archive,
)
from app.modules.object_storage import get_object_store, materialized_object
from app.modules.preview.service import (
    attach_preview_video_from_files,
    build_preview_core_from_files,
    create_processing_bundle,
    mark_preview_bundle_failed,
)
from app.modules.submissions.service import (
    drain_storage_deletions,
    enqueue_storage_deletion,
)


logger = logging.getLogger(__name__)
LEASE_SECONDS = 20 * 60
RETRY_DELAYS = (30, 120, 600)
ACTIVE_JOB_STATUSES = ("queued", "processing")


class ActiveProcessingJobConflict(Exception):
    """Another unfinished job already owns the same submission target."""


class ProcessingJobCancelled(Exception):
    """The job was cancelled while the worker was outside a transaction."""


STAGE_MESSAGES = {
    "uploaded": "压缩包已上传，等待后台校验",
    "validating": "正在校验并解析谱面",
    "accepted": "投稿已接收，正在准备预览素材",
    "preview_core": "正在准备静态预览",
    "public_package": "正在生成谱面下载公开包",
    "video": "正在准备视频背景",
    "cleanup": "正在完成资源切换",
    "complete": "后台资源处理完成",
}


def _public_validation_message(exc: ArchiveParseError | HTTPException) -> str:
    message = str(exc.detail if isinstance(exc, HTTPException) else exc)
    if "解析失败:" in message:
        return "压缩包解析失败，请检查文件格式和内容后重新上传"
    return message[:500]


def _timings(job: SubmissionProcessingJob) -> dict[str, float | int]:
    try:
        value = json.loads(job.stage_timings_json or "{}")
        return value if isinstance(value, dict) else {}
    except json.JSONDecodeError:
        return {}


def _record_stage(
    db: Session,
    job: SubmissionProcessingJob,
    stage: str,
    started: float | None = None,
    *,
    bytes_processed: int | None = None,
    metric_name: str | None = None,
) -> None:
    db.refresh(job)
    if job.status != "processing":
        raise ProcessingJobCancelled
    job.stage = stage
    job.lease_until = datetime.utcnow() + timedelta(seconds=LEASE_SECONDS)
    if started is not None:
        values = _timings(job)
        metric = metric_name or stage
        values[f"{metric}_seconds"] = round(perf_counter() - started, 3)
        if bytes_processed is not None:
            values[f"{metric}_bytes"] = int(bytes_processed)
        job.stage_timings_json = json.dumps(values, separators=(",", ":"))
    db.commit()


def _job_submission(db: Session, job: SubmissionProcessingJob) -> dict | None:
    if not job.result_submission_id:
        return None
    row = db.get(Submission, job.result_submission_id)
    if not row:
        return None
    return serialize_submissions(db, [row])[0]


def serialize_processing_job(db: Session, job: SubmissionProcessingJob) -> dict:
    intent = db.get(SubmissionUploadIntent, job.upload_intent_id) if job.upload_intent_id else None
    submission = _job_submission(db, job)
    file_name = intent.file_name if intent else (submission or {}).get("file_name", "投稿资源")
    file_size = intent.file_size if intent else int((submission or {}).get("file_size", 0))
    message = job.error_message if job.status == "failed" else STAGE_MESSAGES.get(job.stage, "后台处理中")
    return {
        "id": job.id,
        "intent_id": job.upload_intent_id,
        "status": job.status,
        "stage": job.stage,
        "message": message,
        "file_name": file_name,
        "file_size": file_size,
        "source_song_id": job.source_song_id,
        "replace_submission_id": job.replace_submission_id,
        "submission": submission,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
    }


def enqueue_upload_job(db: Session, intent: SubmissionUploadIntent) -> SubmissionProcessingJob:
    existing = db.scalar(
        select(SubmissionProcessingJob).where(
            SubmissionProcessingJob.upload_intent_id == intent.id
        )
    )
    if existing:
        return existing
    now = datetime.utcnow()
    target_conditions = []
    if intent.replace_submission_id is not None:
        target_conditions.append(
            SubmissionProcessingJob.replace_submission_id == intent.replace_submission_id
        )
    elif intent.source_song_id is not None:
        target_conditions.append(SubmissionProcessingJob.source_song_id == intent.source_song_id)
    else:
        target_conditions.append(SubmissionProcessingJob.source_song_id.is_(None))
        target_conditions.append(SubmissionProcessingJob.replace_submission_id.is_(None))
    for previous in db.scalars(
        select(SubmissionProcessingJob).where(
            SubmissionProcessingJob.event_id == intent.event_id,
            SubmissionProcessingJob.user_id == intent.user_id,
            SubmissionProcessingJob.status == "failed",
            SubmissionProcessingJob.superseded_at.is_(None),
            *target_conditions,
        )
    ).all():
        previous.superseded_at = now
    job = SubmissionProcessingJob(
        id=uuid4().hex,
        upload_intent_id=intent.id,
        event_id=intent.event_id,
        user_id=intent.user_id,
        job_type="upload",
        source_song_id=intent.source_song_id,
        replace_submission_id=intent.replace_submission_id,
        source_storage_path=intent.object_key,
        status="queued",
        stage="uploaded",
        next_attempt_at=now,
    )
    intent.status = "uploaded"
    intent.error_message = ""
    db.add(job)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        exact = db.scalar(
            select(SubmissionProcessingJob).where(
                SubmissionProcessingJob.upload_intent_id == intent.id
            )
        )
        if exact:
            return exact
        raise ActiveProcessingJobConflict from exc
    db.refresh(job)
    return job


def enqueue_resource_rebuild(db: Session, row: Submission, user_id: int) -> SubmissionProcessingJob:
    existing = db.scalar(
        select(SubmissionProcessingJob).where(
            SubmissionProcessingJob.status.in_(ACTIVE_JOB_STATUSES),
            or_(
                SubmissionProcessingJob.result_submission_id == row.id,
                SubmissionProcessingJob.replace_submission_id == row.id,
            ),
        )
    )
    if existing:
        return existing
    job = SubmissionProcessingJob(
        id=uuid4().hex,
        event_id=row.event_id,
        user_id=user_id,
        job_type="resources_rebuild",
        source_song_id=row.source_song_id,
        replace_submission_id=row.id,
        result_submission_id=row.id,
        source_storage_path=row.storage_path,
        source_version=Path(row.storage_path).stem,
        status="queued",
        stage="accepted",
        next_attempt_at=datetime.utcnow(),
    )
    row.public_package_status = "processing"
    row.public_package_message = ""
    create_processing_bundle(
        db,
        event_id=row.event_id,
        source_type="submission",
        source_id=row.id,
        source_storage_path=row.storage_path,
        force=True,
    )
    db.add(job)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(
            select(SubmissionProcessingJob).where(
                SubmissionProcessingJob.status.in_(ACTIVE_JOB_STATUSES),
                or_(
                    SubmissionProcessingJob.result_submission_id == row.id,
                    SubmissionProcessingJob.replace_submission_id == row.id,
                ),
            )
        )
        if existing:
            return existing
        raise
    db.refresh(job)
    return job


def list_visible_jobs(
    db: Session,
    *,
    event_id: int,
    user_id: int | None = None,
    include_all_users: bool = False,
) -> list[SubmissionProcessingJob]:
    conditions = [
        SubmissionProcessingJob.event_id == event_id,
        SubmissionProcessingJob.superseded_at.is_(None),
        SubmissionProcessingJob.status.in_(("queued", "processing", "failed")),
    ]
    if not include_all_users and user_id is not None:
        conditions.append(SubmissionProcessingJob.user_id == user_id)
    return list(
        db.scalars(
            select(SubmissionProcessingJob)
            .where(*conditions)
            .order_by(SubmissionProcessingJob.created_at.desc())
        ).all()
    )


def claim_next_job(db: Session) -> str | None:
    now = datetime.utcnow()
    candidate = db.scalar(
        select(SubmissionProcessingJob.id)
        .where(
            SubmissionProcessingJob.superseded_at.is_(None),
            or_(
                (
                    (SubmissionProcessingJob.status == "queued")
                    & or_(
                        SubmissionProcessingJob.next_attempt_at.is_(None),
                        SubmissionProcessingJob.next_attempt_at <= now,
                    )
                ),
                (
                    (SubmissionProcessingJob.status == "processing")
                    & (SubmissionProcessingJob.lease_until < now)
                ),
            ),
        )
        .order_by(SubmissionProcessingJob.created_at.asc())
        .limit(1)
    )
    if not candidate:
        return None
    result = db.execute(
        update(SubmissionProcessingJob)
        .where(
            SubmissionProcessingJob.id == candidate,
            or_(
                SubmissionProcessingJob.status == "queued",
                (
                    (SubmissionProcessingJob.status == "processing")
                    & (SubmissionProcessingJob.lease_until < now)
                ),
            ),
        )
        .values(
            status="processing",
            attempts=SubmissionProcessingJob.attempts + 1,
            lease_until=now + timedelta(seconds=LEASE_SECONDS),
            error_code="",
            error_message="",
        )
    )
    db.commit()
    return candidate if result.rowcount == 1 else None


def _source_context(
    db: Session,
    job: SubmissionProcessingJob,
) -> tuple[SubmissionUploadIntent | None, Submission | None, User, Event]:
    intent = db.get(SubmissionUploadIntent, job.upload_intent_id) if job.upload_intent_id else None
    row = db.get(Submission, job.result_submission_id) if job.result_submission_id else None
    user = db.get(User, job.user_id)
    event = db.get(Event, job.event_id)
    if not user or not event:
        raise ArchiveParseError("投稿所属用户或赛事不存在")
    if job.job_type == "upload" and not intent:
        raise ArchiveParseError("上传记录不存在")
    if job.job_type == "resources_rebuild" and not row:
        raise ArchiveParseError("待重建投稿不存在")
    return intent, row, user, event


def _promote_submission(
    db: Session,
    job: SubmissionProcessingJob,
    intent: SubmissionUploadIntent,
    prepared: PreparedArchive,
    user: User,
    event: Event,
) -> tuple[Submission, str | None, str | None]:
    # Import locally to avoid coupling API route import order to the worker.
    from app.modules.submissions.router import (
        _demote_existing_j_track,
        _eligible_song,
        _sync_and_commit,
    )

    row = db.get(Submission, intent.replace_submission_id) if intent.replace_submission_id else None
    if intent.replace_submission_id and (not row or row.event_id != event.id):
        raise ArchiveParseError("待替换投稿不存在")
    if row and not intent.is_admin and row.user_id != user.id:
        raise ArchiveParseError("待替换投稿不存在")

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
    if song:
        enforce_song_allowed(
            db,
            song.song_name,
            song.artist,
            intent.acknowledge_ban_warning,
        )

    if intent.track == "j":
        _demote_existing_j_track(db, event.id, row.user_id if row else user.id, row.id if row else None)
    old_source = row.storage_path if row else None
    old_public = row.public_storage_path if row else None
    old_track = row.track if row else None
    if row is None:
        row = Submission(
            event_id=event.id,
            user_id=user.id,
            source_song_id=song.id if song else None,
            source_kind=source_kind,
            track=intent.track,
            file_name=intent.file_name,
            storage_path=intent.object_key,
            file_size=intent.file_size,
            public_package_status="processing",
        )
        db.add(row)
        db.flush()
    elif not intent.is_admin and row.source_song_id is None and intent.track != "exhibition":
        raise ArchiveParseError("独立场外投稿不能改为普通或 J 投稿")

    suffix = Path(intent.file_name).suffix.lower()
    final_source = f"events/{event.id}/submissions/{row.id}/source/{uuid4().hex}{suffix}"
    get_object_store().copy(
        intent.object_key,
        final_source,
        content_type=intent.content_type,
        content_disposition=content_disposition(intent.file_name),
    )
    row.track = intent.track
    row.file_name = intent.file_name
    row.storage_path = final_source
    row.file_size = intent.file_size
    row.track_duration_seconds = prepared.parsed.track_duration_seconds
    row.source_kind = source_kind
    row.public_storage_path = None
    row.public_file_size = None
    row.public_package_status = "processing"
    row.public_package_message = ""
    create_processing_bundle(
        db,
        event_id=event.id,
        source_type="submission",
        source_id=row.id,
        source_storage_path=final_source,
        force=True,
    )
    _sync_and_commit(db, row, prepared.parsed, match_source_type=old_track)

    intent.result_submission_id = row.id
    job.result_submission_id = row.id
    job.source_storage_path = final_source
    job.source_version = Path(final_source).stem
    job.accepted_at = datetime.utcnow()
    job.stage = "accepted"
    db.commit()
    if old_source and old_source != final_source:
        enqueue_storage_deletion(db, old_source)
    if old_public:
        enqueue_storage_deletion(db, old_public)
    db.commit()
    return row, old_source, old_public


def _publish_core_preview(
    db: Session,
    job: SubmissionProcessingJob,
    row: Submission,
    prepared: PreparedArchive,
) -> None:
    try:
        bundle = build_preview_core_from_files(
            db,
            event_id=row.event_id,
            source_type="submission",
            source_id=row.id,
            source_storage_path=row.storage_path,
            files=prepared.files,
        )
        db.commit()
        logger.info("Core preview ready for submission=%s job=%s", row.id, job.id)
    except ArchiveParseError as exc:
        db.rollback()
        bundle = db.scalar(
            select(PreviewBundle).where(
                PreviewBundle.source_type == "submission",
                PreviewBundle.source_id == row.id,
            )
        )
        if bundle and bundle.source_storage_path == row.storage_path:
            status = "unsupported" if "暂不支持在线预览" in str(exc) else "failed"
            mark_preview_bundle_failed(
                db,
                bundle,
                status=status,
                error_code="unsupported_format" if status == "unsupported" else "preview_build_failed",
                error_message=str(exc)[:500] if status == "unsupported" else "预览素材生成失败",
            )
            db.commit()
    except Exception:
        db.rollback()
        bundle = db.scalar(
            select(PreviewBundle).where(
                PreviewBundle.source_type == "submission",
                PreviewBundle.source_id == row.id,
            )
        )
        if bundle and bundle.source_storage_path == row.storage_path:
            mark_preview_bundle_failed(
                db,
                bundle,
                status="failed",
                error_code="preview_build_failed",
                error_message="预览素材生成失败，请稍后重试",
            )
            db.commit()
        logger.exception("Core preview upload failed for submission=%s job=%s", row.id, job.id)


def _publish_public_package(
    db: Session,
    job: SubmissionProcessingJob,
    row: Submission,
    prepared: PreparedArchive,
    directory: Path,
) -> None:
    row_id = int(row.id)
    event_id = int(row.event_id)
    expected_source = str(job.source_storage_path)
    public_path = directory / "public.zip"
    final_public = f"events/{event_id}/submissions/{row_id}/public/{uuid4().hex}.zip"
    uploaded = False
    try:
        # Attribute reads above may have opened an ORM transaction after the
        # previous stage commit. Close it before compression and R2 transfer.
        db.commit()
        build_public_package_from_files(public_path, prepared.files)
        get_object_store().put_file(
            final_public,
            public_path,
            content_type="application/zip",
            content_disposition=content_disposition("chart-package.zip"),
        )
        uploaded = True
        current = db.get(Submission, row_id)
        if not current or current.storage_path != expected_source:
            get_object_store().delete(final_public)
            return
        previous = current.public_storage_path
        current.public_storage_path = final_public
        current.public_file_size = public_path.stat().st_size
        current.public_package_status = "ready"
        current.public_package_message = ""
        if previous and previous != final_public:
            enqueue_storage_deletion(db, previous)
        db.commit()
    except Exception:
        db.rollback()
        current = db.get(Submission, row_id)
        if current and current.storage_path == expected_source:
            current.public_package_status = "failed"
            current.public_package_message = "谱面下载公开包生成失败，请联系管理员重试"
            db.commit()
        elif uploaded:
            try:
                get_object_store().delete(final_public)
            except Exception:
                logger.warning("Could not remove stale public package %s", final_public)
        logger.exception("Public package failed for submission=%s job=%s", row_id, job.id)


def _publish_video(
    db: Session,
    job: SubmissionProcessingJob,
    row: Submission,
    prepared: PreparedArchive,
) -> None:
    if not prepared.video_name:
        return
    try:
        attach_preview_video_from_files(
            db,
            event_id=row.event_id,
            source_type="submission",
            source_id=row.id,
            source_storage_path=job.source_storage_path,
            files=prepared.files,
        )
        db.commit()
    except Exception:
        db.rollback()
        bundle = db.scalar(
            select(PreviewBundle).where(
                PreviewBundle.source_type == "submission",
                PreviewBundle.source_id == row.id,
            )
        )
        if bundle and bundle.source_storage_path == job.source_storage_path:
            bundle.video_status = "failed"
            bundle.video_error_message = "视频背景准备失败，预览将使用静态背景"
            db.commit()
        logger.exception("Preview video failed for submission=%s job=%s", row.id, job.id)


def process_job(job_id: str) -> None:
    with SessionLocal() as db:
        job = db.get(SubmissionProcessingJob, job_id)
        if not job or job.status != "processing":
            return
        try:
            intent, row, user, event = _source_context(db, job)
            source_path = job.source_storage_path
            suffix = Path(intent.file_name if intent else source_path).suffix.lower()
            _record_stage(db, job, "validating")
            download_started = perf_counter()
            with materialized_object(source_path, suffix) as archive_path:
                with TemporaryDirectory(prefix="zppz-submission-job-") as directory_text:
                    directory = Path(directory_text)
                    _record_stage(
                        db,
                        job,
                        "validating",
                        download_started,
                        bytes_processed=archive_path.stat().st_size,
                        metric_name="download",
                    )
                    parse_started = perf_counter()
                    prepared = prepare_archive(archive_path, directory / "assets")
                    _record_stage(
                        db,
                        job,
                        "validating",
                        parse_started,
                        metric_name="extract_parse",
                    )
                    if row is None:
                        assert intent is not None
                        promote_started = perf_counter()
                        row, _, _ = _promote_submission(db, job, intent, prepared, user, event)
                        _record_stage(
                            db,
                            job,
                            "accepted",
                            promote_started,
                            bytes_processed=intent.file_size,
                        )
                    else:
                        if row.storage_path != job.source_storage_path:
                            raise ArchiveParseError("投稿版本已经变更，旧任务已停止")

                    _record_stage(db, job, "preview_core")
                    preview_started = perf_counter()
                    _publish_core_preview(db, job, row, prepared)
                    core_bytes = sum(
                        path.stat().st_size
                        for name, path in prepared.files.items()
                        if name == "maidata.txt" or name.startswith("track.") or name.startswith("bg.")
                    )
                    _record_stage(
                        db,
                        job,
                        "preview_core",
                        preview_started,
                        bytes_processed=core_bytes,
                    )

                    _record_stage(db, job, "public_package")
                    package_started = perf_counter()
                    _publish_public_package(db, job, row, prepared, directory)
                    public_path = directory / "public.zip"
                    _record_stage(
                        db,
                        job,
                        "public_package",
                        package_started,
                        bytes_processed=public_path.stat().st_size if public_path.exists() else 0,
                    )

                    _record_stage(db, job, "video")
                    video_started = perf_counter()
                    _publish_video(db, job, row, prepared)
                    video_bytes = (
                        prepared.files[prepared.video_name].stat().st_size
                        if prepared.video_name
                        else 0
                    )
                    _record_stage(
                        db,
                        job,
                        "video",
                        video_started,
                        bytes_processed=video_bytes,
                    )

            _record_stage(db, job, "cleanup")
            if intent:
                enqueue_storage_deletion(db, intent.object_key)
                intent.status = "completed"
                intent.error_message = ""
            db.flush()
            drain_storage_deletions(db)
            job.status = "completed"
            job.stage = "complete"
            job.finished_at = datetime.utcnow()
            job.lease_until = None
            job.next_attempt_at = None
            job.error_code = ""
            job.error_message = ""
            db.commit()
        except ProcessingJobCancelled:
            db.rollback()
            return
        except (ArchiveParseError, HTTPException) as exc:
            db.rollback()
            current = db.get(SubmissionProcessingJob, job_id)
            if current:
                current.status = "failed"
                current.error_code = "archive_invalid"
                current.error_message = _public_validation_message(exc)
                current.finished_at = datetime.utcnow()
                current.lease_until = None
                if current.upload_intent_id:
                    upload = db.get(SubmissionUploadIntent, current.upload_intent_id)
                    if upload:
                        upload.status = "failed"
                        upload.error_message = current.error_message
                        enqueue_storage_deletion(db, upload.object_key)
                db.flush()
                drain_storage_deletions(db)
        except Exception:
            db.rollback()
            current = db.get(SubmissionProcessingJob, job_id)
            if current:
                attempt_index = max(current.attempts - 1, 0)
                if current.attempts <= len(RETRY_DELAYS):
                    current.status = "queued"
                    current.next_attempt_at = datetime.utcnow() + timedelta(
                        seconds=RETRY_DELAYS[min(attempt_index, len(RETRY_DELAYS) - 1)]
                    )
                    current.error_code = "temporary_processing_error"
                    current.error_message = "后台处理暂时失败，系统将自动重试"
                else:
                    current.status = "failed"
                    current.finished_at = datetime.utcnow()
                    current.error_code = "processing_failed"
                    current.error_message = "后台处理失败，请重新上传或联系管理员"
                    if current.upload_intent_id:
                        upload = db.get(SubmissionUploadIntent, current.upload_intent_id)
                        if upload:
                            upload.status = "failed"
                            upload.error_message = current.error_message
                            enqueue_storage_deletion(db, upload.object_key)
                current.lease_until = None
                db.flush()
                if current.status == "failed":
                    drain_storage_deletions(db)
                else:
                    db.commit()
            logger.exception("Submission processing job failed: %s", job_id)


def process_next_job() -> bool:
    with SessionLocal() as db:
        job_id = claim_next_job(db)
    if not job_id:
        return False
    process_job(job_id)
    return True


def cleanup_expired_upload_intents() -> int:
    now = datetime.utcnow()
    with SessionLocal() as db:
        rows = list(
            db.scalars(
                select(SubmissionUploadIntent)
                .where(
                    SubmissionUploadIntent.status == "pending",
                    SubmissionUploadIntent.expires_at < now,
                )
                .order_by(SubmissionUploadIntent.expires_at.asc())
                .limit(100)
            ).all()
        )
        for intent in rows:
            intent.status = "expired"
            intent.error_message = "上传意图已过期"
            enqueue_storage_deletion(db, intent.object_key)
        if not rows:
            return 0
        db.flush()
        drain_storage_deletions(db)
        return len(rows)
