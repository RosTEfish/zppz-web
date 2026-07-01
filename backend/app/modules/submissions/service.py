from pathlib import Path
import shutil
from uuid import uuid4

from fastapi import HTTPException, UploadFile

from app.core.config import get_settings


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
    with target.open("wb") as out:
        while True:
            chunk = file.file.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > settings.max_upload_mb * 1024 * 1024:
                raise HTTPException(status_code=413, detail=f"文件不能超过 {settings.max_upload_mb} MB")
            out.write(chunk)
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
    if source.exists() and not target.exists():
        shutil.copy2(source, target)
