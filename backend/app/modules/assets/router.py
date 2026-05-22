from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.core.config import get_settings


router = APIRouter(prefix="/assets", tags=["assets"])


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
    return FileResponse(file, media_type="application/pdf", filename=file.name)


@router.get("/banlist")
def banlist() -> dict:
    file = latest_file("banlists", {".xlsx", ".xls", ".csv"})
    return {"available": bool(file), "file_name": file.name if file else "", "url": "/api/v1/assets/banlist/download" if file else ""}


@router.get("/banlist/download")
def download_banlist():
    file = latest_file("banlists", {".xlsx", ".xls", ".csv"})
    if not file:
        raise HTTPException(status_code=404, detail="暂无 banlist 文件")
    return FileResponse(file, filename=file.name)


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
    return FileResponse(file)

