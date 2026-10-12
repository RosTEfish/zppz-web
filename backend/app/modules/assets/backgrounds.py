"""Shared helpers for event background asset listing and delivery."""

from __future__ import annotations

from pathlib import Path

from app.core.config import get_settings

BACKGROUND_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
# Longer TTL: filenames are stable between deploys; sync overwrites in place.
BACKGROUND_CACHE_HEADERS = {
    "Cache-Control": "public, max-age=604800, stale-while-revalidate=86400",
    "Content-Encoding": "identity",
}


def backgrounds_dir() -> Path:
    return get_settings().assets_dir / "backgrounds"


def list_background_assets() -> list[dict[str, str]]:
    directory = backgrounds_dir()
    if not directory.is_dir():
        return []
    return [
        {"file_name": item.name, "url": f"/api/v1/assets/backgrounds/{item.name}"}
        for item in sorted(directory.iterdir())
        if item.is_file() and item.suffix.lower() in BACKGROUND_SUFFIXES
    ]
