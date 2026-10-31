"""Batch submission zip assembly."""

from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException

from app.models import Submission
from app.modules.downloads import DownloadEntry, PreparedZip, prepare_streaming_zip, safe_download_name
from app.modules.object_storage import get_object_store
from app.modules.submissions.service import absolute_storage_path
from app.modules.submissions.support import MAX_BATCH_FILES, MAX_BATCH_SOURCE_BYTES


def _prepare_submission_zip(rows: list[Submission], filename: str) -> PreparedZip:
    if len(rows) > MAX_BATCH_FILES:
        raise HTTPException(status_code=413, detail=f"一次最多下载 {MAX_BATCH_FILES} 份投稿")
    store = get_object_store()
    existing: list[tuple[Submission, int]] = []
    missing: list[Submission] = []
    total_size = 0
    for row in rows:
        try:
            info = store.head(row.storage_path)
        except Exception:
            missing.append(row)
            continue
        total_size += info.size
        if total_size > MAX_BATCH_SOURCE_BYTES:
            raise HTTPException(status_code=413, detail="所选投稿原文件总量不能超过 10 GiB")
        existing.append((row, info.size))
    if not existing:
        raise HTTPException(status_code=404, detail="所选投稿文件均不存在")

    entries: list[DownloadEntry] = []
    used_names: set[str] = set()
    for row, object_size in existing:
        user_code = row.user.user_code if row.user else str(row.user_id)
        song_name = row.source_song.song_name if row.source_song else "未关联曲目"
        base = safe_download_name(
            f"{row.track}_{user_code}_{song_name}_{row.id}_{row.file_name}",
            f"submission_{row.id}{Path(row.file_name).suffix}",
        )
        name = base
        counter = 2
        while name.casefold() in used_names:
            stem, suffix = Path(base).stem, Path(base).suffix
            name = f"{stem}_{counter}{suffix}"
            counter += 1
        used_names.add(name.casefold())
        if store.backend == "local":
            entries.append(DownloadEntry(path=absolute_storage_path(row.storage_path), archive_name=name))
        else:
            entries.append(
                DownloadEntry(
                    path=None,
                    archive_name=name,
                    data=store.chunks(row.storage_path, object_size),
                    data_size=object_size,
                )
            )
    report = ""
    if missing:
        report = "以下投稿文件不存在：\n" + "\n".join(f"- ID {row.id}: {row.file_name}" for row in missing)
    return prepare_streaming_zip(entries, file_name=filename, report=report)
