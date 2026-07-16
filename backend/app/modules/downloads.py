from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from collections.abc import Iterable
from urllib.parse import quote

from fastapi import HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from zipstream import ZIP_STORED, ZipStream


DOWNLOAD_HEADERS = {
    "Cache-Control": "private, no-store",
    "Content-Encoding": "identity",
    "X-Accel-Buffering": "no",
}


def safe_download_name(value: str, fallback: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', "_", value).strip(" .")
    return cleaned[:180] or fallback


def parse_csv_ids(
    value: str | None,
    *,
    required: bool,
    max_items: int,
    empty_detail: str,
    limit_detail: str,
) -> list[int] | None:
    if value is None or not value.strip():
        if not required:
            return None
        raise HTTPException(status_code=400, detail=empty_detail)
    try:
        result = list(dict.fromkeys(int(item.strip()) for item in value.split(",") if item.strip()))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="ids 必须是逗号分隔的数字") from exc
    if not result:
        raise HTTPException(status_code=400, detail=empty_detail)
    if len(result) > max_items:
        raise HTTPException(status_code=413, detail=limit_detail)
    return result


@dataclass(frozen=True)
class DownloadEntry:
    path: Path | None
    archive_name: str
    data: Iterable[bytes] | None = None


@dataclass(frozen=True)
class PreparedZip:
    stream: ZipStream
    file_name: str
    file_size: int

    def response(self) -> StreamingResponse:
        headers = {
            **DOWNLOAD_HEADERS,
            "Content-Disposition": content_disposition(self.file_name),
            "Content-Length": str(self.file_size),
        }
        return StreamingResponse(self.stream, media_type="application/zip", headers=headers)


def content_disposition(file_name: str) -> str:
    ascii_name = file_name.encode("ascii", "ignore").decode().replace('"', "") or "download"
    encoded = quote(file_name)
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{encoded}"


def prepare_streaming_zip(
    entries: list[DownloadEntry],
    *,
    file_name: str,
    report: str = "",
) -> PreparedZip:
    stream = ZipStream(compress_type=ZIP_STORED, sized=True)
    for entry in entries:
        if entry.path is not None:
            stream.add_path(entry.path, entry.archive_name)
        elif entry.data is not None:
            stream.add(entry.data, entry.archive_name)
        else:
            raise ValueError("download entry requires a path or data")
    if report:
        stream.add(report, "_下载报告.txt")
    return PreparedZip(stream=stream, file_name=file_name, file_size=len(stream))


def file_download_response(path: Path, file_name: str) -> FileResponse:
    return FileResponse(path, filename=file_name, headers=DOWNLOAD_HEADERS)
