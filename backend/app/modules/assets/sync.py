"""Sync repo-bundled static assets into the runtime data directory."""

from __future__ import annotations

import filecmp
import io
import shutil
from pathlib import Path

from PIL import Image

from app.core.config import get_settings

RASTER_SUFFIXES = {".png", ".jpg", ".jpeg"}
BRAND_THUMB_MAX_PX = 128


def _copy_if_changed(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_file() and filecmp.cmp(source, target, shallow=False):
        return
    shutil.copy2(source, target)


def _purge_stale_rasters(directory: Path, stem: str, keep: Path) -> None:
    for suffix in (*RASTER_SUFFIXES, ".webp"):
        candidate = directory / f"{stem}{suffix}"
        if candidate.exists() and candidate.resolve() != keep.resolve():
            candidate.unlink()


def _is_square_role(stem: str) -> bool:
    lowered = stem.lower()
    return lowered == "square" or lowered.endswith("_square")


def _write_webp(image: Image.Image, target: Path, *, quality: int = 82) -> None:
    buffer = io.BytesIO()
    image.save(buffer, format="WEBP", quality=quality, method=6)
    payload = buffer.getvalue()
    if not (target.is_file() and target.read_bytes() == payload):
        target.write_bytes(payload)


def _ensure_rgb(image: Image.Image) -> Image.Image:
    if image.mode in {"RGB", "RGBA"}:
        return image
    return image.convert("RGBA" if "A" in image.getbands() else "RGB")


def _write_brand_thumb(image: Image.Image, directory: Path, stem: str) -> None:
    """Small square mark for AppBar / drawer logos (avoids shipping 800px for 32px UI)."""
    if not _is_square_role(stem):
        return
    thumb = _ensure_rgb(image).copy()
    thumb.thumbnail((BRAND_THUMB_MAX_PX, BRAND_THUMB_MAX_PX), Image.Resampling.LANCZOS)
    _write_webp(thumb, directory / f"{stem}.thumb.webp", quality=80)


def sync_background_file(source: Path) -> None:
    """Copy a background asset, converting raster images to WebP for faster delivery."""
    settings = get_settings()
    directory = settings.assets_dir / "backgrounds"
    directory.mkdir(parents=True, exist_ok=True)
    suffix = source.suffix.lower()
    # Generated thumbs are derived from the square role asset; never treat as sources.
    if ".thumb" in source.stem.lower():
        return

    if suffix in RASTER_SUFFIXES:
        target = directory / f"{source.stem}.webp"
        image = _ensure_rgb(Image.open(source))
        _write_webp(image, target)
        _purge_stale_rasters(directory, source.stem, target)
        _write_brand_thumb(image, directory, source.stem)
        return

    target = directory / source.name
    _copy_if_changed(source, target)
    if suffix == ".webp":
        _purge_stale_rasters(directory, source.stem, target)
        with Image.open(source) as image:
            _write_brand_thumb(image, directory, source.stem)


def sync_bundled_assets() -> None:
    # backend/app/modules/assets/sync.py → repo root is parents[4]
    repo_root = Path(__file__).resolve().parents[4]
    for source, target in (
        (repo_root / "ruleDetail", "rules"),
        (repo_root / "banlist", "banlists"),
        (repo_root / "bg", "backgrounds"),
    ):
        for file in sorted(source.glob("*.*")):
            if not file.is_file():
                continue
            if target == "backgrounds":
                sync_background_file(file)
            else:
                from app.modules.submissions.service import copy_asset_from_repo

                copy_asset_from_repo(file, target)
