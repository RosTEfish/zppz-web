from __future__ import annotations

from pathlib import Path

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
from app.modules.downloads import file_download_response, safe_download_name
from app.modules.guess_game.importer import ensure_cover_thumbnail
from app.modules.object_storage import get_object_store
from app.modules.preview.router import _prepare_manifest
from app.modules.submissions.service import absolute_storage_path
from app.schemas import ArchiveEditionRead, ArchiveGuessChartRead, DownloadPreparation, PreviewManifestRead


router = APIRouter(prefix="/guess-archive", tags=["guess-archive"])

COVER_CACHE_HEADERS = {"Cache-Control": "public, max-age=31536000, immutable", "Content-Encoding": "identity"}


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
) -> tuple[Path | str, str, int, bool] | None:
    """Resolve downloadable original package for an archived chart."""
    source_id = chart.source_submission_id
    store = get_object_store()
    if source_id is not None and chart.source_submission_type in {"normal", "j", "exhibition"}:
        submission = db.get(Submission, source_id)
        if not submission or submission.event_id != chart.event_id or not submission.storage_path:
            return None
        file_name = Path(submission.file_name or "chart.zip").name or "chart.zip"
        if store.backend == "r2":
            try:
                size = submission.file_size or store.head(submission.storage_path).size
            except Exception:
                return None
            return submission.storage_path, file_name, size, True
        path = absolute_storage_path(submission.storage_path)
        if not path.is_file():
            return None
        return path, file_name, path.stat().st_size, False
    if source_id is not None and chart.source_submission_type == "admin":
        archive = db.get(AdminGuessArchive, source_id)
        if not archive or archive.event_id != chart.event_id:
            return None
        path = absolute_storage_path(archive.storage_path)
        if not path.is_file():
            return None
        return path, archive.file_name, archive.file_size, False
    if chart.storage_path:
        path = absolute_storage_path(chart.storage_path)
        if not path.is_file():
            return None
        return path, Path(chart.storage_path).name, path.stat().st_size if path.is_file() else 0, False
    return None


def _chart_download_name(chart: GuessChart, file_name: str) -> str:
    source_label = "自选" if chart.is_self_selected else "非自选"
    return safe_download_name(
        f"{chart.title}_{chart.level}_{source_label}_{file_name}",
        f"chart_{chart.id}_{source_label}{Path(file_name).suffix}",
    )


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
    location, file_name, _, remote = source
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
    location, file_name, file_size, remote = source
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
