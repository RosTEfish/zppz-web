from zipfile import ZIP_DEFLATED, ZipFile
import io

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.security import get_current_user, require_role
from app.db.session import get_db
from app.models import JTrackSubmission, Submission, User
from app.modules.common import serialize_submission
from app.modules.events.service import get_current_event
from app.modules.submissions.service import absolute_storage_path, save_upload
from app.schemas import StoredFileRead


router = APIRouter(prefix="/submissions", tags=["submissions"])
admin_router = APIRouter(prefix="/admin/submissions", tags=["admin-submissions"])


@router.get("", response_model=list[StoredFileRead])
def my_submissions(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[dict]:
    event = get_current_event(db)
    rows = db.scalars(
        select(Submission)
        .options(joinedload(Submission.user).joinedload(User.roles))
        .where(Submission.event_id == event.id, Submission.user_id == user.id)
        .order_by(Submission.created_at.desc())
    ).all()
    return [serialize_submission(row) for row in rows]


@router.post("", response_model=StoredFileRead)
def upload_submission(file: UploadFile, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    event = get_current_event(db)
    storage_path, size = save_upload(file, f"events/{event.id}/submissions/{user.id}")
    row = Submission(event_id=event.id, user_id=user.id, file_name=file.filename or "upload", storage_path=storage_path, file_size=size)
    db.add(row)
    db.commit()
    db.refresh(row)
    row.user = user
    return serialize_submission(row)


@router.post("/{submission_id}/replace", response_model=StoredFileRead)
def replace_submission(submission_id: int, file: UploadFile, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    row = db.get(Submission, submission_id)
    if not row or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="投稿不存在")
    storage_path, size = save_upload(file, f"events/{row.event_id}/submissions/{user.id}")
    row.file_name = file.filename or "upload"
    row.storage_path = storage_path
    row.file_size = size
    db.commit()
    db.refresh(row)
    row.user = user
    return serialize_submission(row)


@router.delete("/{submission_id}")
def delete_submission(submission_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    row = db.get(Submission, submission_id)
    if not row or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="投稿不存在")
    db.delete(row)
    db.commit()
    return {"message": "投稿已删除"}


@router.get("/j-track")
def my_j_track(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    event = get_current_event(db)
    row = db.scalar(select(JTrackSubmission).where(JTrackSubmission.event_id == event.id, JTrackSubmission.user_id == user.id))
    return {"submission": None if not row else {"id": row.id, "file_name": row.file_name, "file_size": row.file_size, "created_at": row.created_at}}


@router.post("/j-track")
def upload_j_track(file: UploadFile, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    event = get_current_event(db)
    storage_path, size = save_upload(file, f"events/{event.id}/j-track/{user.id}")
    row = db.scalar(select(JTrackSubmission).where(JTrackSubmission.event_id == event.id, JTrackSubmission.user_id == user.id))
    if row:
        row.file_name = file.filename or "upload"
        row.storage_path = storage_path
        row.file_size = size
    else:
        row = JTrackSubmission(event_id=event.id, user_id=user.id, file_name=file.filename or "upload", storage_path=storage_path, file_size=size)
        db.add(row)
    db.commit()
    return {"submission": {"id": row.id, "file_name": row.file_name, "file_size": row.file_size, "created_at": row.created_at}}


@admin_router.get("", response_model=list[StoredFileRead])
def admin_list_submissions(_: User = Depends(require_role("admin", "pool_editor")), db: Session = Depends(get_db)) -> list[dict]:
    event = get_current_event(db)
    rows = db.scalars(
        select(Submission)
        .options(joinedload(Submission.user).joinedload(User.roles))
        .where(Submission.event_id == event.id)
        .order_by(Submission.created_at.desc())
    ).all()
    return [serialize_submission(row) for row in rows]


@admin_router.get("/{submission_id}/download")
def admin_download_submission(submission_id: int, _: User = Depends(require_role("admin", "pool_editor")), db: Session = Depends(get_db)):
    row = db.get(Submission, submission_id)
    if not row:
        raise HTTPException(status_code=404, detail="投稿不存在")
    path = absolute_storage_path(row.storage_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(path, filename=row.file_name)


@admin_router.get("/download.zip")
def admin_download_zip(_: User = Depends(require_role("admin", "pool_editor")), db: Session = Depends(get_db)):
    event = get_current_event(db)
    rows = db.scalars(select(Submission).where(Submission.event_id == event.id)).all()
    buffer = io.BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as zip_file:
        for row in rows:
            path = absolute_storage_path(row.storage_path)
            if path.exists():
                zip_file.write(path, arcname=f"{row.user_id}-{row.file_name}")
    buffer.seek(0)
    return StreamingResponse(buffer, media_type="application/zip", headers={"Content-Disposition": "attachment; filename=submissions.zip"})

