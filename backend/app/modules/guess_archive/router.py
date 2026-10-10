from __future__ import annotations

from pathlib import Path
from urllib.parse import urlencode

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.cache import set_public_api_cache
from app.core.config import get_settings
from app.core.security import get_optional_user
from app.db.session import get_db
from app.models import AdminGuessArchive, Event, GuessChart, Submission, User
from app.modules.common import serialize_charts
from app.modules.downloads import (
    DOWNLOAD_TOKEN_PATTERN,
    DownloadEntry,
    PreparedZip,
    file_download_response,
    parse_csv_ids,
    prepare_streaming_zip,
    safe_download_name,
)
from app.modules.guess_game.importer import ensure_cover_thumbnail
from app.modules.object_storage import get_object_store
from app.modules.preview.router import _prepare_manifest
from app.modules.submissions.service import absolute_storage_path
from app.schemas import ArchiveEditionRead, ArchiveGuessChartRead, DownloadPreparation, PreviewManifestRead


router = APIRouter(prefix="/guess-archive", tags=["guess-archive"])

COVER_CACHE_HEADERS = {"Cache-Control": "public, max-age=31536000, immutable", "Content-Encoding": "identity"}
MAX_BATCH_FILES = 500
MAX_BATCH_SOURCE_BYTES = 10 * 1024 * 1024 * 1024


def _archived_events_with_charts(db: Session) -> list[tuple[Event, int]]:
    rows = db.execute(
        select(Event, func.count(GuessChart.id))
        .join(GuessChart, GuessChart.event_id == Event.id)
        .where(Event.is_current.is_(False))
        .group_by(Event.id)
        .order_by(Event.id.desc())
    ).all()
    return [(event, int(count)) for event, count in rows]


def _archived_chart(db: Session, chart_id: int) -> GuessChart:
    chart = db.scalar(
        select(GuessChart)
        .join(Event, Event.id == GuessChart.event_id)
        .where(GuessChart.id == chart_id, Event.is_current.is_(False))
    )
    if not chart:
        raise HTTPException(status_code=404, detail="谱面不存在")
    return chart


def _event_name_map(db: Session, event_ids: set[int]) -> dict[int, str]:
    if not event_ids:
        return {}
    return {
        event_id: name
        for event_id, name in db.execute(
            select(Event.id, Event.name).where(Event.id.in_(event_ids))
        ).all()
    }


def _submitter_label(user: User | None) -> str:
    if user is None:
        return "未知提交者"
    label = (user.display_name or "").strip() or user.user_code.strip()
    return label or "未知提交者"


def _submitter_map(
    db: Session,
    charts: list[GuessChart],
) -> dict[tuple[str, int], tuple[int | None, str]]:
    """Map (source_type, source_id) -> (submitter_user_id, submitter_label)."""
    submission_ids = {
        int(chart.source_submission_id)
        for chart in charts
        if chart.source_submission_id is not None
        and chart.source_submission_type in {"normal", "j", "exhibition"}
    }
    admin_ids = {
        int(chart.source_submission_id)
        for chart in charts
        if chart.source_submission_id is not None and chart.source_submission_type == "admin"
    }
    mapping: dict[tuple[str, int], tuple[int | None, str]] = {}
    if submission_ids:
        rows = db.execute(
            select(Submission.id, Submission.user_id, User)
            .join(User, User.id == Submission.user_id)
            .where(Submission.id.in_(submission_ids))
        ).all()
        for submission_id, user_id, user in rows:
            mapping[("submission", int(submission_id))] = (int(user_id), _submitter_label(user))
    if admin_ids:
        # Admin zip imports are not participant submissions; keep them in one bucket.
        for admin_id in admin_ids:
            mapping[("admin", int(admin_id))] = (None, "管理端导入")
    return mapping


def _archive_payloads(db: Session, charts: list[GuessChart]) -> list[dict]:
    if not charts:
        return []
    names = _event_name_map(db, {chart.event_id for chart in charts})
    submitters = _submitter_map(db, charts)
    submission_ids = {
        int(chart.source_submission_id)
        for chart in charts
        if chart.source_submission_id is not None
        and chart.source_submission_type in {"normal", "j", "exhibition"}
    }
    downloadable_submission_ids = set(
        db.scalars(
            select(Submission.id).where(
                Submission.id.in_(submission_ids),
                Submission.storage_path.is_not(None),
                Submission.storage_path != "",
            )
        ).all()
    ) if submission_ids else set()
    admin_ids = {
        int(chart.source_submission_id)
        for chart in charts
        if chart.source_submission_id is not None and chart.source_submission_type == "admin"
    }
    downloadable_admin_ids = set(
        db.scalars(select(AdminGuessArchive.id).where(AdminGuessArchive.id.in_(admin_ids))).all()
    ) if admin_ids else set()
    payloads = serialize_charts(db, charts, include_designer=True)
    preview_enabled = get_settings().preview_enabled
    for payload, chart in zip(payloads, charts):
        stem = Path(chart.cover_path).stem if chart.cover_path else ""
        can_download = False
        if chart.source_submission_type == "admin":
            can_download = chart.source_submission_id is not None and int(chart.source_submission_id) in downloadable_admin_ids
            submitter_key = ("admin", int(chart.source_submission_id)) if chart.source_submission_id is not None else None
        elif chart.source_submission_id is not None:
            can_download = int(chart.source_submission_id) in downloadable_submission_ids
            submitter_key = ("submission", int(chart.source_submission_id))
        else:
            submitter_key = None
        submitter_user_id, submitter_label = (
            submitters.get(submitter_key, (None, "未知提交者"))
            if submitter_key is not None
            else (None, "未知提交者")
        )
        payload.update(
            {
                "event_id": chart.event_id,
                "event_name": names.get(chart.event_id, ""),
                "submitter_user_id": submitter_user_id,
                "submitter_label": submitter_label,
                "cover_path": (
                    f"/api/v1/guess-archive/charts/{chart.id}/cover?v={stem}" if chart.cover_path else ""
                ),
                "cover_thumb_path": (
                    f"/api/v1/guess-archive/charts/{chart.id}/cover-thumb?v={stem}" if chart.cover_path else ""
                ),
                "love_votes": 0,
                "funny_votes": 0,
                "my_votes": [],
                "can_download": can_download,
                "can_preview": preview_enabled and chart.source_submission_id is not None,
            }
        )
    return payloads


def _resolve_original_archive(
    db: Session,
    chart: GuessChart,
) -> tuple[Path | str, str, tuple[str, int | str], int, bool] | None:
    """Resolve downloadable original package for an archived chart.

    Returns (location, file_name, source_key, file_size, remote).
    """
    source_id = chart.source_submission_id
    store = get_object_store()
    if source_id is not None and chart.source_submission_type in {"normal", "j", "exhibition"}:
        submission = db.get(Submission, source_id)
        if not submission or submission.event_id != chart.event_id or not submission.storage_path:
            return None
        file_name = Path(submission.file_name or "chart.zip").name or "chart.zip"
        source_key: tuple[str, int | str] = ("submission", int(submission.id))
        if store.backend == "r2":
            try:
                size = submission.file_size or store.head(submission.storage_path).size
            except Exception:
                return None
            return submission.storage_path, file_name, source_key, size, True
        path = absolute_storage_path(submission.storage_path)
        if not path.is_file():
            return None
        return path, file_name, source_key, path.stat().st_size, False
    if source_id is not None and chart.source_submission_type == "admin":
        archive = db.get(AdminGuessArchive, source_id)
        if not archive or archive.event_id != chart.event_id:
            return None
        path = absolute_storage_path(archive.storage_path)
        if not path.is_file():
            return None
        return path, archive.file_name, ("admin", int(archive.id)), archive.file_size, False
    if chart.storage_path:
        path = absolute_storage_path(chart.storage_path)
        if not path.is_file():
            return None
        return path, Path(chart.storage_path).name, ("path", chart.storage_path), path.stat().st_size, False
    return None


def _chart_download_name(chart: GuessChart, file_name: str, *, include_id: bool = False) -> str:
    source_label = "自选" if chart.is_self_selected else "非自选"
    prefix = f"{chart.id}_" if include_id else ""
    return safe_download_name(
        f"{prefix}{chart.title}_{chart.level}_{source_label}_{file_name}",
        f"chart_{chart.id}_{source_label}{Path(file_name).suffix}",
    )


def _select_archive_chart_downloads(
    db: Session,
    ids: str,
) -> tuple[list[GuessChart], list[int], list[int]]:
    chart_ids = parse_csv_ids(
        ids,
        required=True,
        max_items=MAX_BATCH_FILES,
        empty_detail="请至少选择一张谱面",
        limit_detail=f"一次最多选择 {MAX_BATCH_FILES} 张谱面",
    )
    assert chart_ids is not None
    rows = list(
        db.scalars(
            select(GuessChart)
            .join(Event, Event.id == GuessChart.event_id)
            .where(Event.is_current.is_(False), GuessChart.id.in_(chart_ids))
        ).all()
    )
    by_id = {row.id: row for row in rows}
    ordered = [by_id[chart_id] for chart_id in chart_ids if chart_id in by_id]
    missing_ids = [chart_id for chart_id in chart_ids if chart_id not in by_id]
    return ordered, missing_ids, chart_ids


def _named_archive_downloads(
    db: Session,
    charts: list[GuessChart],
    missing_ids: list[int],
) -> tuple[list[tuple[GuessChart, Path | str, str, int, bool, str]], list[str]]:
    selected: list[tuple[GuessChart, Path | str, str, int, bool]] = []
    seen_sources: set[tuple[str, int | str]] = set()
    skipped: list[str] = [f"谱面 ID {chart_id} 不存在或未归档" for chart_id in missing_ids]
    total_size = 0
    for chart in charts:
        source = _resolve_original_archive(db, chart)
        if not source:
            skipped.append(f"ID {chart.id}《{chart.title}》没有可用原始包")
            continue
        location, file_name, source_key, file_size, remote = source
        if source_key in seen_sources:
            skipped.append(f"ID {chart.id}《{chart.title}》与已选谱面共用原始包，已去重")
            continue
        if not remote and not Path(location).is_file():
            skipped.append(f"ID {chart.id}《{chart.title}》原始包文件不存在")
            continue
        seen_sources.add(source_key)
        total_size += file_size
        if total_size > MAX_BATCH_SOURCE_BYTES:
            raise HTTPException(status_code=413, detail="所选原始包总量不能超过 10 GiB")
        selected.append((chart, location, file_name, file_size, remote))
    if not selected:
        raise HTTPException(status_code=404, detail="所选谱面均无可下载文件")

    named: list[tuple[GuessChart, Path | str, str, int, bool, str]] = []
    used_names: set[str] = set()
    for chart, location, file_name, file_size, remote in selected:
        base = _chart_download_name(chart, file_name, include_id=True)
        name = base
        counter = 2
        while name.casefold() in used_names:
            name = f"{Path(base).stem}_{counter}{Path(base).suffix}"
            counter += 1
        used_names.add(name.casefold())
        named.append((chart, location, file_name, file_size, remote, name))
    return named, skipped


def _archive_r2_downloads(
    db: Session,
    charts: list[GuessChart],
    missing_ids: list[int],
) -> list[dict]:
    store = get_object_store()
    files: list[dict] = []
    named, _skipped = _named_archive_downloads(db, charts, missing_ids)
    for _chart, location, _file_name, file_size, remote, name in named:
        if not remote:
            raise HTTPException(status_code=409, detail="批量下载文件不在对象存储中")
        files.append(
            {
                "download_url": store.create_download_url(str(location), name),
                "file_name": name,
                "file_size": file_size,
            }
        )
    return files


def _prepare_archive_zip(
    db: Session,
    charts: list[GuessChart],
    missing_ids: list[int],
) -> PreparedZip:
    named, skipped = _named_archive_downloads(db, charts, missing_ids)
    entries: list[DownloadEntry] = []
    for _chart, location, _file_name, file_size, remote, name in named:
        if remote:
            entries.append(
                DownloadEntry(
                    path=None,
                    archive_name=name,
                    data=get_object_store().chunks(str(location), file_size),
                    data_size=file_size,
                )
            )
        else:
            entries.append(DownloadEntry(path=Path(location), archive_name=name))
    return prepare_streaming_zip(entries, file_name="archive-charts.zip", report="\n".join(skipped))


def _chart_cover_file(chart: GuessChart) -> Path:
    file_name = Path(chart.cover_path).name
    return get_settings().assets_dir / "guess-covers" / file_name


def _require_cover_file(chart: GuessChart) -> Path:
    file = _chart_cover_file(chart)
    if not file.name or not file.is_file() or file.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
        raise HTTPException(status_code=404, detail="谱面封面不存在")
    return file


@router.get("/editions", response_model=list[ArchiveEditionRead])
def list_editions(response: Response, db: Session = Depends(get_db)) -> list[dict]:
    set_public_api_cache(response)
    return [
        {"id": event.id, "name": event.name, "slug": event.slug, "chart_count": count}
        for event, count in _archived_events_with_charts(db)
    ]


@router.get("/charts", response_model=list[ArchiveGuessChartRead])
def list_charts(
    response: Response,
    event_id: int | None = Query(None),
    submitter_user_id: int | None = Query(None),
    db: Session = Depends(get_db),
) -> list[dict]:
    set_public_api_cache(response)
    stmt = (
        select(GuessChart)
        .join(Event, Event.id == GuessChart.event_id)
        .where(Event.is_current.is_(False))
        .order_by(Event.id.desc(), GuessChart.id.asc())
    )
    if event_id is not None:
        stmt = stmt.where(GuessChart.event_id == event_id)
    charts = list(db.scalars(stmt).all())
    payloads = _archive_payloads(db, charts)
    if submitter_user_id is not None:
        payloads = [row for row in payloads if row.get("submitter_user_id") == submitter_user_id]
    return payloads


@router.get("/charts/download.zip")
def download_charts_zip(
    ids: str = Query(...),
    download_token: str | None = Query(
        None,
        min_length=32,
        max_length=32,
        pattern=DOWNLOAD_TOKEN_PATTERN,
    ),
    db: Session = Depends(get_db),
):
    charts, missing_ids, _ = _select_archive_chart_downloads(db, ids)
    return _prepare_archive_zip(db, charts, missing_ids).response(download_token)


@router.get("/charts/download-metadata", response_model=DownloadPreparation)
def download_charts_metadata(
    ids: str = Query(...),
    db: Session = Depends(get_db),
) -> dict:
    charts, missing_ids, chart_ids = _select_archive_chart_downloads(db, ids)
    store = get_object_store()
    if store.backend == "r2":
        files = _archive_r2_downloads(db, charts, missing_ids)
        return {
            "download_url": "",
            "file_name": "archive-charts.zip",
            "file_size": sum(item["file_size"] for item in files),
            "files": files,
        }
    prepared = _prepare_archive_zip(db, charts, missing_ids)
    query = urlencode({"ids": ",".join(str(item) for item in chart_ids)})
    return {
        "download_url": f"{get_settings().api_prefix}/guess-archive/charts/download.zip?{query}",
        "file_name": prepared.file_name,
        "file_size": prepared.file_size,
    }


@router.get("/charts/{chart_id}", response_model=ArchiveGuessChartRead)
def chart_detail(
    chart_id: int,
    response: Response,
    db: Session = Depends(get_db),
) -> dict:
    set_public_api_cache(response)
    chart = _archived_chart(db, chart_id)
    return _archive_payloads(db, [chart])[0]


@router.get("/charts/{chart_id}/cover")
def chart_cover(chart_id: int, db: Session = Depends(get_db)):
    chart = _archived_chart(db, chart_id)
    return FileResponse(_require_cover_file(chart), headers=COVER_CACHE_HEADERS)


@router.get("/charts/{chart_id}/cover-thumb")
def chart_cover_thumb(chart_id: int, db: Session = Depends(get_db)):
    chart = _archived_chart(db, chart_id)
    cover_file = _require_cover_file(chart)
    thumb = ensure_cover_thumbnail(cover_file)
    return FileResponse(thumb or cover_file, headers=COVER_CACHE_HEADERS)


@router.get("/charts/{chart_id}/download")
def download_chart(chart_id: int, db: Session = Depends(get_db)):
    chart = _archived_chart(db, chart_id)
    source = _resolve_original_archive(db, chart)
    if not source:
        raise HTTPException(status_code=404, detail="该谱面没有可下载的原始文件")
    location, file_name, _, _, remote = source
    download_name = _chart_download_name(chart, file_name)
    if remote:
        url = get_object_store().create_download_url(str(location), download_name)
        return RedirectResponse(url, status_code=307, headers={"Cache-Control": "private, no-store"})
    path = Path(location)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="投稿文件不存在")
    return file_download_response(path, download_name)


@router.get("/charts/{chart_id}/download-metadata", response_model=DownloadPreparation)
def download_chart_metadata(chart_id: int, db: Session = Depends(get_db)) -> dict:
    chart = _archived_chart(db, chart_id)
    source = _resolve_original_archive(db, chart)
    if not source:
        raise HTTPException(status_code=404, detail="该谱面没有可下载的原始文件")
    location, file_name, _, file_size, remote = source
    download_name = _chart_download_name(chart, file_name)
    return {
        "download_url": (
            get_object_store().create_download_url(str(location), download_name)
            if remote
            else f"{get_settings().api_prefix}/guess-archive/charts/{chart_id}/download"
        ),
        "file_name": download_name,
        "file_size": file_size,
    }


@router.get("/charts/{chart_id}/preview-manifest", response_model=PreviewManifestRead)
def chart_preview_manifest(
    chart_id: int,
    request: Request,
    response: Response,
    background_tasks: BackgroundTasks,
    _: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
) -> dict:
    response.headers["Cache-Control"] = "private, no-store"
    chart = _archived_chart(db, chart_id)
    if chart.source_submission_id is None:
        raise HTTPException(status_code=409, detail="该谱面没有可用的投稿源文件")
    if chart.source_submission_type == "admin":
        source_type = "admin_archive"
        source = db.get(AdminGuessArchive, chart.source_submission_id)
    else:
        source_type = "submission"
        source = db.get(Submission, chart.source_submission_id)
    if source is None or source.event_id != chart.event_id:
        raise HTTPException(status_code=404, detail="谱面不存在")
    try:
        slot = int(chart.source_level_slot)
    except (TypeError, ValueError):
        slot = None
    manifest = _prepare_manifest(
        db,
        background_tasks,
        event_id=chart.event_id,
        source_type=source_type,
        source_id=source.id,
        source_storage_path=source.storage_path,
        base_url=str(request.base_url).rstrip("/"),
        selected_level_slot=slot,
    )
    manifest["levels"] = [
        level for level in manifest["levels"]
        if slot is not None and level["slot"] == slot
    ]
    return manifest
