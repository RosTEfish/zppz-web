"""Batch submission zip assembly."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import HTTPException

from app.models import Submission
from app.modules.downloads import DownloadEntry, PreparedZip, prepare_streaming_zip, safe_download_name
from app.modules.object_storage import get_object_store
from app.modules.submissions.service import absolute_storage_path
from app.modules.submissions.support import MAX_BATCH_FILES, MAX_BATCH_SOURCE_BYTES

# Bulk downloads can HEAD hundreds of objects. Overlap a few calls so the
# request is not a serial N+1, without opening one connection per file.
ZIP_HEAD_CONCURRENCY = 8


def _head_objects_in_order(store, keys: list[str]) -> list[tuple[bool, object]]:
    """Head each key with at most ZIP_HEAD_CONCURRENCY calls in flight.

    Results stay aligned with `keys`. A failed head is `(False, exc)` and is
    not raised, so size limits and missing-file reports still follow input order.
    """
    if not keys:
        return []
    worker_limit = min(ZIP_HEAD_CONCURRENCY, len(keys))

    def _one(key: str) -> tuple[bool, object]:
        try:
            return True, store.head(key)
        except Exception as exc:
            return False, exc

    with ThreadPoolExecutor(max_workers=worker_limit) as pool:
        futures = [pool.submit(_one, key) for key in keys]
        return [future.result() for future in futures]


def _prepare_submission_zip(rows: list[Submission], filename: str) -> PreparedZip:
    if len(rows) > MAX_BATCH_FILES:
        raise HTTPException(status_code=413, detail=f"一次最多下载 {MAX_BATCH_FILES} 份投稿")
    store = get_object_store()
    headed = _head_objects_in_order(store, [row.storage_path for row in rows])
    existing: list[tuple[Submission, int]] = []
    missing: list[Submission] = []
    total_size = 0
    for row, (found, info) in zip(rows, headed, strict=True):
        if not found:
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
