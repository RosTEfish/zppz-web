from zipfile import ZIP_DEFLATED, ZipFile
import io

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.security import get_current_user, require_role
from app.db.session import get_db
from app.models import JTrackSubmission, Submission, User
from app.modules.common import serialize_submission
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
from app.schemas import StoredFileRead


router = APIRouter(prefix="/submissions", tags=["submissions"])
admin_router = APIRouter(prefix="/admin/submissions", tags=["admin-submissions"])


def _validated_upload(storage_path: str) -> ParsedArchive:
    try:
        return parse_stored_archive(storage_path)
    except ArchiveParseError as exc:
        delete_stored_file(storage_path)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        delete_stored_file(storage_path)
        raise


def _sync_and_commit(
    db: Session,
    *,
    event_id: int,
    source_type: str,
    source_id: int,
    file_name: str,
    storage_path: str,
    parsed: ParsedArchive,
) -> None:
    result = None
    try:
        result = sync_parsed_source(
            db,
            event_id=event_id,
            source_type=source_type,
            source_id=source_id,
            file_name=file_name,
            storage_path=storage_path,
            parsed=parsed,
        )
        db.commit()
    except Exception:
        db.rollback()
        if result and result.new_cover_path and result.new_cover_path not in result.previous_cover_paths:
            delete_cover_paths({result.new_cover_path})
        raise
    assert result is not None
    delete_cover_paths(result.stale_cover_paths)


def _create_submission(db: Session, event_id: int, user: User, file: UploadFile) -> Submission:
    storage_path, size = save_upload(file, f"events/{event_id}/submissions/{user.id}")
    parsed = _validated_upload(storage_path)
    row = Submission(
        event_id=event_id,
        user_id=user.id,
        file_name=file.filename or "upload",
        storage_path=storage_path,
        file_size=size,
    )
    try:
        db.add(row)
        db.flush()
        _sync_and_commit(
            db,
            event_id=event_id,
            source_type="normal",
            source_id=row.id,
            file_name=row.file_name,
            storage_path=row.storage_path,
            parsed=parsed,
        )
    except Exception:
        db.rollback()
        delete_stored_file(storage_path)
        raise
    db.refresh(row)
    row.user = user
    return row


def _replace_submission(db: Session, row: Submission, file: UploadFile) -> Submission:
    new_storage_path, size = save_upload(file, f"events/{row.event_id}/submissions/{row.user_id}")
    parsed = _validated_upload(new_storage_path)
    old_storage_path = row.storage_path
    row.file_name = file.filename or "upload"
    row.storage_path = new_storage_path
    row.file_size = size
    try:
        _sync_and_commit(
            db,
            event_id=row.event_id,
            source_type="normal",
            source_id=row.id,
            file_name=row.file_name,
            storage_path=row.storage_path,
            parsed=parsed,
        )
    except Exception:
        delete_stored_file(new_storage_path)
        raise
    delete_stored_file(old_storage_path)
    db.refresh(row)
    return row


def _delete_submission(db: Session, row: Submission) -> None:
    storage_path = row.storage_path
    _, cover_paths = delete_source_charts(db, row.event_id, "normal", row.id)
    db.delete(row)
    db.commit()
    delete_stored_file(storage_path)
    delete_cover_paths(cover_paths)


@router.get("", response_model=list[StoredFileRead])
def my_submissions(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[dict]:
    event = get_current_event(db)
    rows = db.scalars(
        select(Submission)
        .options(selectinload(Submission.user).selectinload(User.roles))
        .where(Submission.event_id == event.id, Submission.user_id == user.id)
        .order_by(Submission.created_at.desc())
    ).all()
    return [serialize_submission(row) for row in rows]


@router.post("", response_model=StoredFileRead)
def upload_submission(file: UploadFile = File(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    event = get_current_event(db)
    return serialize_submission(_create_submission(db, event.id, user, file))


@router.post("/{submission_id}/replace", response_model=StoredFileRead)
def replace_submission(
    submission_id: int,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    event = get_current_event(db)
    row = db.get(Submission, submission_id)
    if not row or row.user_id != user.id or row.event_id != event.id:
        raise HTTPException(status_code=404, detail="投稿不存在")
    row = _replace_submission(db, row, file)
    row.user = user
    return serialize_submission(row)


@router.get("/j-track")
def my_j_track(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    event = get_current_event(db)
    row = db.scalar(select(JTrackSubmission).where(JTrackSubmission.event_id == event.id, JTrackSubmission.user_id == user.id))
    return {"submission": None if not row else {"id": row.id, "file_name": row.file_name, "file_size": row.file_size, "created_at": row.created_at}}


@router.post("/j-track")
def upload_j_track(file: UploadFile = File(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    event = get_current_event(db)
    new_storage_path, size = save_upload(file, f"events/{event.id}/j-track/{user.id}")
    parsed = _validated_upload(new_storage_path)
    row = db.scalar(select(JTrackSubmission).where(JTrackSubmission.event_id == event.id, JTrackSubmission.user_id == user.id))
    old_storage_path = row.storage_path if row else ""
    try:
        if row:
            row.file_name = file.filename or "upload"
            row.storage_path = new_storage_path
            row.file_size = size
        else:
            row = JTrackSubmission(
                event_id=event.id,
                user_id=user.id,
                file_name=file.filename or "upload",
                storage_path=new_storage_path,
                file_size=size,
            )
            db.add(row)
            db.flush()
        _sync_and_commit(
            db,
            event_id=event.id,
            source_type="j",
            source_id=row.id,
            file_name=row.file_name,
            storage_path=row.storage_path,
            parsed=parsed,
        )
    except Exception:
        db.rollback()
        delete_stored_file(new_storage_path)
        raise
    if old_storage_path:
        delete_stored_file(old_storage_path)
    return {"submission": {"id": row.id, "file_name": row.file_name, "file_size": row.file_size, "created_at": row.created_at}}


@router.delete("/j-track")
def delete_j_track(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    event = get_current_event(db)
    row = db.scalar(select(JTrackSubmission).where(JTrackSubmission.event_id == event.id, JTrackSubmission.user_id == user.id))
    if not row:
        raise HTTPException(status_code=404, detail="J 赛道投稿不存在")
    storage_path = row.storage_path
    _, cover_paths = delete_source_charts(db, event.id, "j", row.id)
    db.delete(row)
    db.commit()
    delete_stored_file(storage_path)
    delete_cover_paths(cover_paths)
    return {"message": "J 赛道投稿已删除"}


@router.delete("/{submission_id}")
def delete_submission(submission_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    event = get_current_event(db)
    row = db.get(Submission, submission_id)
    if not row or row.user_id != user.id or row.event_id != event.id:
        raise HTTPException(status_code=404, detail="投稿不存在")
    _delete_submission(db, row)
    return {"message": "投稿已删除"}


@admin_router.get("", response_model=list[StoredFileRead])
def admin_list_submissions(_: User = Depends(require_role("admin", "pool_editor")), db: Session = Depends(get_db)) -> list[dict]:
    event = get_current_event(db)
    rows = db.scalars(
        select(Submission)
        .options(selectinload(Submission.user).selectinload(User.roles))
        .where(Submission.event_id == event.id)
        .order_by(Submission.created_at.desc())
    ).all()
    return [serialize_submission(row) for row in rows]


@admin_router.post("/{submission_id}/replace", response_model=StoredFileRead)
def admin_replace_submission(
    submission_id: int,
    file: UploadFile = File(...),
    _: User = Depends(require_role("admin", "pool_editor")),
    db: Session = Depends(get_db),
) -> dict:
    event = get_current_event(db)
    row = db.get(Submission, submission_id)
    if not row or row.event_id != event.id:
        raise HTTPException(status_code=404, detail="投稿不存在")
    row = _replace_submission(db, row, file)
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
