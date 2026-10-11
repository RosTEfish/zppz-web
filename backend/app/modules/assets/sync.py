"""Sync repo-bundled static assets into the runtime data directory."""

from __future__ import annotations

import filecmp
import io
import shutil
from pathlib import Path

from PIL import Image

from app.core.config import get_settings

RASTER_SUFFIXES = {".png", ".jpg", ".jpeg"}


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


def sync_background_file(source: Path) -> None:
    """Copy a background asset, converting raster images to WebP for faster delivery."""
    settings = get_settings()
    directory = settings.assets_dir / "backgrounds"
    directory.mkdir(parents=True, exist_ok=True)
    suffix = source.suffix.lower()

    if suffix in RASTER_SUFFIXES:
        target = directory / f"{source.stem}.webp"
        image = Image.open(source)
        if image.mode not in {"RGB", "RGBA"}:
            image = image.convert("RGBA" if "A" in image.getbands() else "RGB")
        buffer = io.BytesIO()
        image.save(buffer, format="WEBP", quality=82, method=6)
        payload = buffer.getvalue()
        if not (target.is_file() and target.read_bytes() == payload):
            target.write_bytes(payload)
        _purge_stale_rasters(directory, source.stem, target)
        return

    target = directory / source.name
    _copy_if_changed(source, target)
    if suffix == ".webp":
        _purge_stale_rasters(directory, source.stem, target)


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
