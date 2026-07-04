from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

from fastapi.responses import FileResponse, StreamingResponse
from zipstream import ZIP_STORED, ZipStream


DOWNLOAD_HEADERS = {
    "Cache-Control": "private, no-store",
    "Content-Encoding": "identity",
    "X-Accel-Buffering": "no",
}


@dataclass(frozen=True)
class DownloadEntry:
    path: Path
    archive_name: str


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
        stream.add_path(entry.path, entry.archive_name)
    if report:
        stream.add(report, "_下载报告.txt")
    return PreparedZip(stream=stream, file_name=file_name, file_size=len(stream))


def file_download_response(path: Path, file_name: str) -> FileResponse:
    return FileResponse(path, filename=file_name, headers=DOWNLOAD_HEADERS)
