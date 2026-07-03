from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.core.config import get_settings


router = APIRouter(prefix="/assets", tags=["assets"])
DOWNLOAD_CACHE_HEADERS = {"Cache-Control": "public, max-age=300"}
BACKGROUND_CACHE_HEADERS = {"Cache-Control": "public, max-age=86400"}
IMMUTABLE_CACHE_HEADERS = {"Cache-Control": "public, max-age=31536000, immutable"}


def latest_file(folder: str, suffixes: set[str]) -> Path | None:
    directory = get_settings().assets_dir / folder
    files = sorted((item for item in directory.iterdir() if item.is_file() and item.suffix.lower() in suffixes), key=lambda item: item.stat().st_mtime, reverse=True)
    return files[0] if files else None


@router.get("/rule")
def rule_detail() -> dict:
    file = latest_file("rules", {".pdf"})
    return {"available": bool(file), "file_name": file.name if file else "", "url": "/api/v1/assets/rule/download" if file else ""}


@router.get("/rule/download")
def download_rule():
    file = latest_file("rules", {".pdf"})
    if not file:
        raise HTTPException(status_code=404, detail="暂无规则文件")
    return FileResponse(file, media_type="application/pdf", filename=file.name, headers=DOWNLOAD_CACHE_HEADERS)


@router.get("/rule/view")
def view_rule():
    file = latest_file("rules", {".pdf"})
    if not file:
        raise HTTPException(status_code=404, detail="暂无规则文件")
    return FileResponse(file, media_type="application/pdf", headers=DOWNLOAD_CACHE_HEADERS)


@router.get("/banlist")
def banlist() -> dict:
    file = latest_file("banlists", {".xlsx", ".xls", ".csv"})
    return {"available": bool(file), "file_name": file.name if file else "", "url": "/api/v1/assets/banlist/download" if file else ""}


@router.get("/banlist/download")
def download_banlist():
    file = latest_file("banlists", {".xlsx", ".xls", ".csv"})
    if not file:
        raise HTTPException(status_code=404, detail="暂无 banlist 文件")
    return FileResponse(file, filename=file.name, headers=DOWNLOAD_CACHE_HEADERS)


@router.get("/backgrounds")
def backgrounds() -> list[dict]:
    directory = get_settings().assets_dir / "backgrounds"
    return [
        {"file_name": item.name, "url": f"/api/v1/assets/backgrounds/{item.name}"}
        for item in sorted(directory.iterdir())
        if item.is_file() and item.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".gif"}
    ]


@router.get("/backgrounds/{file_name}")
def background_file(file_name: str):
    safe = Path(file_name).name
    file = get_settings().assets_dir / "backgrounds" / safe
    if not file.exists():
        raise HTTPException(status_code=404, detail="背景不存在")
    return FileResponse(file, headers=BACKGROUND_CACHE_HEADERS)


@router.get("/guess-covers/{file_name}")
def guess_cover(file_name: str):
    safe = Path(file_name).name
    file = get_settings().assets_dir / "guess-covers" / safe
    if safe != file_name or not file.is_file() or file.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}:
        raise HTTPException(status_code=404, detail="猜谱封面不存在")
    return FileResponse(file, headers=IMMUTABLE_CACHE_HEADERS)
