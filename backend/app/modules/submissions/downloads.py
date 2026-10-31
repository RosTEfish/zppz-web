"""Single-file download routes for a participant's own submissions."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import get_current_user
from app.db.session import get_db
from app.models import (
    Submission,
    User,
)
from app.modules.downloads import file_download_response
from app.modules.events.service import get_current_event
from app.modules.object_storage import get_object_store
from app.modules.submissions.service import absolute_storage_path
from app.modules.submissions.support import _can_manage_submissions
from app.schemas import DownloadPreparation


def download_own_submission(
    submission_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    event = get_current_event(db)
    row = db.get(Submission, submission_id)
    if not row or row.event_id != event.id or (row.user_id != user.id and not _can_manage_submissions(user)):
        raise HTTPException(status_code=404, detail="投稿不存在")
    store = get_object_store()
    download_url = store.create_download_url(row.storage_path, row.file_name)
    if download_url:
        return RedirectResponse(download_url, status_code=307, headers={"Cache-Control": "private, no-store"})
    path = absolute_storage_path(row.storage_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="投稿文件不存在")
    return file_download_response(path, row.file_name)


def own_submission_download_metadata(
    submission_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    event = get_current_event(db)
    row = db.get(Submission, submission_id)
    if not row or row.event_id != event.id or (row.user_id != user.id and not _can_manage_submissions(user)):
        raise HTTPException(status_code=404, detail="投稿不存在")
    store = get_object_store()
    try:
        info = store.head(row.storage_path)
    except Exception as exc:
        raise HTTPException(status_code=404, detail="投稿文件不存在") from exc
    download_url = store.create_download_url(row.storage_path, row.file_name)
    return {
        "download_url": download_url or f"{get_settings().api_prefix}/submissions/{submission_id}/download",
        "file_name": row.file_name,
        "file_size": info.size,
    }


def register_download_routes(router: APIRouter) -> None:
    router.get("/{submission_id}/download")(download_own_submission)
    router.get("/{submission_id}/download-metadata", response_model=DownloadPreparation)(own_submission_download_metadata)
