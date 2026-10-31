"""Admin submission routes."""

from __future__ import annotations

from urllib.parse import urlencode

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import require_role
from app.db.session import get_db
from app.models import (
    PreviewBundle,
    Submission,
    SubmissionProcessingJob,
    SubmissionUploadIntent,
    User,
)
from app.modules.common import serialize_submissions
from app.modules.downloads import (
    DOWNLOAD_TOKEN_PATTERN,
    file_download_response,
    parse_csv_ids,
)
from app.modules.events.service import get_current_event
from app.modules.guess_game.importer import delete_cover_paths
from app.modules.object_storage import get_object_store
from app.modules.submissions.batch_zip import _prepare_submission_zip
from app.modules.submissions.service import (
    absolute_storage_path,
    drain_storage_deletions,
    enqueue_storage_deletion,
)
from app.modules.submissions.support import (
    MAX_BATCH_FILES,
    _backfill_readme_flags,
    _create_upload_intent,
    _delete_submission,
    _intent_response,
    _legacy_upload_metadata,
    _normalize_track,
    _parse_tracks,
    _put_legacy_upload,
    _stage_delete_submission,
    _submission_options,
)
from app.modules.submissions.upload import _complete_intent, _confirm_and_enqueue_intent
from app.schemas import (
    AdminStoredFileRead,
    AdminSubmissionProcessingJobRead,
    AdminSubmissionUploadIntentCreate,
    BatchDeleteRequest,
    BatchDeleteResponse,
    DownloadPreparation,
    PaginatedStoredFilesRead,
    SubmissionUploadIntentRead,
)


def admin_list_submissions(
    tracks: str | None = Query(None),
    track: str | None = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    _: User = Depends(require_role("admin", "pool_editor")),
    db: Session = Depends(get_db),
) -> dict:
    event = get_current_event(db)
    filters = [Submission.event_id == event.id]
    selected_tracks = _parse_tracks(tracks, track)
    if selected_tracks is not None:
        filters.append(Submission.track.in_(selected_tracks))
    total = db.scalar(select(func.count()).select_from(Submission).where(*filters)) or 0
    stmt = (
        select(Submission)
        .options(*_submission_options())
        .where(*filters)
        .order_by(Submission.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    items = list(db.scalars(stmt).all())
    _backfill_readme_flags(db, items)
    return {
        "items": serialize_submissions(db, items, include_private=True),
        "total": int(total),
        "limit": limit,
        "offset": offset,
    }


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


def complete_admin_submission_upload_intent(
    intent_id: str,
    admin: User = Depends(require_role("admin", "pool_editor")),
    db: Session = Depends(get_db),
) -> dict:
    intent = db.get(SubmissionUploadIntent, intent_id)
    if not intent or intent.user_id != admin.id or not intent.is_admin:
        raise HTTPException(status_code=404, detail="上传意图不存在")
    return _confirm_and_enqueue_intent(db, intent, enforce_phase=False)


def admin_submission_upload_intent_status(
    intent_id: str,
    admin: User = Depends(require_role("admin", "pool_editor")),
    db: Session = Depends(get_db),
) -> dict:
    from app.modules.submissions.processing import serialize_processing_job

    intent = db.get(SubmissionUploadIntent, intent_id)
    if not intent or intent.user_id != admin.id or not intent.is_admin:
        raise HTTPException(status_code=404, detail="上传意图不存在")
    job = db.scalar(
        select(SubmissionProcessingJob).where(
            SubmissionProcessingJob.upload_intent_id == intent.id
        )
    )
    if not job:
        raise HTTPException(status_code=409, detail="上传文件尚未确认入队")
    return serialize_processing_job(db, job, include_private=True)


def admin_submission_processing_jobs(
    _: User = Depends(require_role("admin", "pool_editor")),
    db: Session = Depends(get_db),
) -> list[dict]:
    from app.modules.submissions.processing import list_visible_jobs, serialize_processing_jobs

    event = get_current_event(db)
    return serialize_processing_jobs(
        db,
        list_visible_jobs(db, event_id=event.id, include_all_users=True),
        include_private=True,
    )


def cancel_admin_submission_upload_intent(
    intent_id: str,
    admin: User = Depends(require_role("admin", "pool_editor")),
    db: Session = Depends(get_db),
):
    intent = db.get(SubmissionUploadIntent, intent_id)
    if not intent or intent.user_id != admin.id or not intent.is_admin:
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


def rebuild_submission_resources(
    submission_id: int,
    admin: User = Depends(require_role("admin", "pool_editor")),
    db: Session = Depends(get_db),
) -> dict:
    from app.modules.submissions.processing import (
        enqueue_resource_rebuild,
        serialize_processing_job,
    )

    event = get_current_event(db)
    row = db.get(Submission, submission_id)
    if not row or row.event_id != event.id:
        raise HTTPException(status_code=404, detail="投稿不存在")
    bundle = db.scalar(
        select(PreviewBundle).where(
            PreviewBundle.event_id == event.id,
            PreviewBundle.source_type == "submission",
            PreviewBundle.source_id == row.id,
        )
    )
    can_rebuild = (
        row.public_package_status == "failed"
        or bundle is None
        or bundle.status in {"failed", "unsupported"}
        or bundle.video_status == "failed"
    )
    if not can_rebuild:
        raise HTTPException(status_code=409, detail="当前投稿资源没有需要重建的失败项")
    return serialize_processing_job(db, enqueue_resource_rebuild(db, row, admin.id), include_private=True)


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
    return serialize_submissions(db, [_complete_intent(intent, admin, db, background_tasks)], include_private=True)[0]


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


def admin_download_zip(
    ids: str | None = Query(None),
    tracks: str | None = Query(None),
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
    rows, _, _ = _select_admin_downloads(db, event.id, ids, tracks, track)
    return _prepare_submission_zip(rows, "submissions.zip").response(download_token)


def admin_download_metadata(
    ids: str | None = Query(None),
    tracks: str | None = Query(None),
    track: str | None = Query(None),
    _: User = Depends(require_role("admin", "pool_editor")),
    db: Session = Depends(get_db),
) -> dict:
    event = get_current_event(db)
    rows, selected_ids, selected_tracks = _select_admin_downloads(db, event.id, ids, tracks, track)
    prepared = _prepare_submission_zip(rows, "submissions.zip")
    params: dict[str, str] = {}
    if selected_ids is not None:
        params["ids"] = ",".join(str(item) for item in selected_ids)
    if selected_tracks is not None:
        params["tracks"] = ",".join(selected_tracks)
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
    tracks: str | None,
    track: str | None = None,
) -> tuple[list[Submission], list[int] | None, list[str] | None]:
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
    selected_tracks = _parse_tracks(tracks, track)
    if selected_tracks is not None:
        stmt = stmt.where(Submission.track.in_(selected_tracks))
    rows = list(db.scalars(stmt.order_by(Submission.id.asc())).all())
    if not rows:
        raise HTTPException(status_code=404, detail="没有可下载的投稿")
    return rows, selected_ids, selected_tracks


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


def register_admin_routes(admin_router: APIRouter) -> None:
    admin_router.get("", response_model=PaginatedStoredFilesRead)(admin_list_submissions)
    admin_router.post("/{submission_id}/upload-intents", response_model=SubmissionUploadIntentRead)(create_admin_submission_upload_intent)
    admin_router.post("/upload-intents/{intent_id}/complete", response_model=AdminSubmissionProcessingJobRead)(complete_admin_submission_upload_intent)
    admin_router.get("/upload-intents/{intent_id}/status", response_model=AdminSubmissionProcessingJobRead)(admin_submission_upload_intent_status)
    admin_router.get("/processing-jobs", response_model=list[AdminSubmissionProcessingJobRead])(admin_submission_processing_jobs)
    admin_router.delete("/upload-intents/{intent_id}", status_code=204)(cancel_admin_submission_upload_intent)
    admin_router.post("/{submission_id}/resources/rebuild", response_model=AdminSubmissionProcessingJobRead)(rebuild_submission_resources)
    admin_router.post("/batch-delete", response_model=BatchDeleteResponse)(admin_batch_delete_submissions)
    admin_router.post("/{submission_id}/replace", response_model=AdminStoredFileRead, deprecated=True)(admin_replace_submission)
    admin_router.delete("/{submission_id}")(admin_delete_submission)
    admin_router.get("/download.zip")(admin_download_zip)
    admin_router.get("/download-metadata", response_model=DownloadPreparation)(admin_download_metadata)
    admin_router.get("/{submission_id}/download")(admin_download_submission)
    admin_router.get("/{submission_id}/download-metadata", response_model=DownloadPreparation)(admin_download_submission_metadata)
