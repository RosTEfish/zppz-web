from pathlib import Path
import filecmp
import logging
import shutil
from threading import Lock
from uuid import uuid4

from fastapi import HTTPException, UploadFile
from sqlalchemy import select

from app.core.config import get_settings
from app.models import StorageDeletion
from app.modules.object_storage import get_object_store


ARCHIVE_CONTENT_TYPES = {
    ".zip": "application/zip",
    ".7z": "application/x-7z-compressed",
    ".rar": "application/vnd.rar",
}

logger = logging.getLogger(__name__)
_STORAGE_CLEANUP_LOCK = Lock()


def archive_content_type(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    content_type = ARCHIVE_CONTENT_TYPES.get(suffix)
    if not content_type:
        raise HTTPException(status_code=400, detail=f"不支持的文件类型：{suffix or '无扩展名'}")
    return content_type


def validate_upload_metadata(filename: str, size: int, content_type: str) -> str:
    settings = get_settings()
    expected = archive_content_type(filename)
    if size <= 0:
        raise HTTPException(status_code=422, detail="文件不能为空")
    if size > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"文件不能超过 {settings.max_upload_mb} MB")
    if content_type != expected:
        raise HTTPException(status_code=422, detail=f"文件 Content-Type 必须为 {expected}")
    return Path(filename).suffix.lower()


def enqueue_storage_deletion(db, object_key: str | None) -> None:
    if not object_key:
        return
    existing = db.query(StorageDeletion).filter(StorageDeletion.object_key == object_key).first()
    if not existing:
        db.add(StorageDeletion(object_key=object_key))


def drain_storage_deletions(db, *, limit: int = 200) -> int:
    store = get_object_store()
    deleted = 0
    rows = list(
        db.scalars(
            select(StorageDeletion)
            .order_by(StorageDeletion.id.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
        ).all()
    )
    for row in rows:
        try:
            store.delete(row.object_key)
        except Exception as exc:
            row.attempts += 1
            row.last_error = str(exc)[:500]
        else:
            db.delete(row)
            deleted += 1
    db.commit()
    return deleted


def drain_storage_deletions_in_background() -> int:
    """Drain a bounded deletion batch without retaining a request-scoped session."""
    if not _STORAGE_CLEANUP_LOCK.acquire(blocking=False):
        return 0
    try:
        from app.db.session import SessionLocal

        with SessionLocal() as db:
            return drain_storage_deletions(db)
    except Exception:
        logger.exception("Background object-storage cleanup failed")
        return 0
    finally:
        _STORAGE_CLEANUP_LOCK.release()


def validate_extension(filename: str) -> None:
    suffix = Path(filename).suffix.lower().lstrip(".")
    if suffix not in get_settings().allowed_extensions:
        raise HTTPException(status_code=400, detail=f"不支持的文件类型：{suffix or '无扩展名'}")


def save_upload(file: UploadFile, folder: str) -> tuple[str, int]:
    settings = get_settings()
    validate_extension(file.filename or "")
    target_dir = settings.uploads_dir / folder
    target_dir.mkdir(parents=True, exist_ok=True)
    safe_name = Path(file.filename or "upload.bin").name
    target = target_dir / f"{uuid4().hex}_{safe_name}"
    size = 0
    try:
        with target.open("wb") as out:
            while True:
                chunk = file.file.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > settings.max_upload_mb * 1024 * 1024:
                    raise HTTPException(status_code=413, detail=f"文件不能超过 {settings.max_upload_mb} MB")
                out.write(chunk)
    except Exception:
        target.unlink(missing_ok=True)
        raise
    return str(target.relative_to(settings.data_dir)).replace("\\", "/"), size


def absolute_storage_path(relative_path: str) -> Path:
    return get_settings().data_dir / relative_path


def delete_stored_file(relative_path: str) -> None:
    settings = get_settings()
    data_dir = settings.data_dir.resolve()
    path = (data_dir / relative_path).resolve()
    try:
        path.relative_to(data_dir)
    except ValueError:
        return
    try:
        if path.is_file():
            path.unlink()
    except OSError:
        return


def copy_asset_from_repo(source: Path, target_folder: str) -> None:
    settings = get_settings()
    target = settings.assets_dir / target_folder / source.name
    if not source.is_file():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_file() and filecmp.cmp(source, target, shallow=False):
        return
    shutil.copy2(source, target)
