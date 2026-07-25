from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import get_current_user, get_optional_user, is_owner, require_role
from app.db.session import get_db
from app.models import AdminGuessArchive, GuessChart, PreviewBundle, Submission, User
from app.modules.events.phase_policy import get_phase_status
from app.modules.events.service import get_current_event
from app.modules.object_storage import get_object_store
from app.modules.preview.service import (
    create_processing_bundle,
    manifest_payload,
    parse_local_asset_token,
    rebuild_preview_in_background,
)
from app.schemas import PreviewManifestRead


router = APIRouter(tags=["preview"])


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "private, no-store"


def _can_manage(user: User) -> bool:
    return is_owner(user) or user.has_role("admin") or user.has_role("pool_editor")


def _prepare_manifest(
    db: Session,
    background_tasks: BackgroundTasks,
    *,
    event_id: int,
    source_type: str,
    source_id: int,
    source_storage_path: str,
    base_url: str,
    selected_level_slot: int | None = None,
    force: bool = False,
) -> dict:
    try:
        bundle, should_build = create_processing_bundle(
            db,
            event_id=event_id,
            source_type=source_type,
            source_id=source_id,
            source_storage_path=source_storage_path,
            force=force,
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        bundle = db.scalar(
            select(PreviewBundle).where(
                PreviewBundle.event_id == event_id,
                PreviewBundle.source_type == source_type,
                PreviewBundle.source_id == source_id,
            )
        )
        should_build = False
        if bundle is None:
            raise
    if should_build:
        background_tasks.add_task(
            rebuild_preview_in_background,
            event_id,
            source_type,
            source_id,
            source_storage_path,
        )
    return manifest_payload(
        db,
        bundle,
        base_url=base_url,
        selected_level_slot=selected_level_slot,
    )


@router.get("/submissions/{submission_id}/preview-manifest", response_model=PreviewManifestRead)
def submission_preview_manifest(
    submission_id: int,
    request: Request,
    response: Response,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    _no_store(response)
    event = get_current_event(db)
    submission = db.scalar(
        select(Submission).where(Submission.id == submission_id, Submission.event_id == event.id)
    )
    if not submission or (submission.user_id != user.id and not _can_manage(user)):
        raise HTTPException(status_code=404, detail="投稿不存在")
    manifest = _prepare_manifest(
        db,
        background_tasks,
        event_id=event.id,
        source_type="submission",
        source_id=submission.id,
        source_storage_path=submission.storage_path,
        base_url=str(request.base_url).rstrip("/"),
    )
    return manifest


@router.get("/guess-game/charts/{chart_id}/preview-manifest", response_model=PreviewManifestRead)
def guess_chart_preview_manifest(
    chart_id: int,
    request: Request,
    response: Response,
    background_tasks: BackgroundTasks,
    _: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
) -> dict:
    _no_store(response)
    event = get_current_event(db)
    chart = db.scalar(
        select(GuessChart).where(GuessChart.id == chart_id, GuessChart.event_id == event.id)
    )
    phase = get_phase_status(db, event)
    if not chart or (
        chart.source_submission_type not in {"j", "exhibition"}
        and not phase.can("normal_submission_public")
    ):
        raise HTTPException(status_code=404, detail="谱面不存在")
    if chart.source_submission_id is None:
        raise HTTPException(status_code=409, detail="该谱面没有可用的投稿源文件")

    if chart.source_submission_type == "admin":
        source_type = "admin_archive"
        source = db.get(AdminGuessArchive, chart.source_submission_id)
    else:
        source_type = "submission"
        source = db.get(Submission, chart.source_submission_id)
    if source is None or source.event_id != event.id:
        raise HTTPException(status_code=404, detail="谱面不存在")
    try:
        slot = int(chart.source_level_slot)
    except (TypeError, ValueError):
        slot = None
    manifest = _prepare_manifest(
        db,
        background_tasks,
        event_id=event.id,
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


@router.post("/admin/submissions/{submission_id}/preview/rebuild", response_model=PreviewManifestRead)
def rebuild_submission_preview(
    submission_id: int,
    request: Request,
    response: Response,
    background_tasks: BackgroundTasks,
    _: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> dict:
    _no_store(response)
    event = get_current_event(db)
    submission = db.scalar(
        select(Submission).where(Submission.id == submission_id, Submission.event_id == event.id)
    )
    if not submission:
        raise HTTPException(status_code=404, detail="投稿不存在")
    return _prepare_manifest(
        db,
        background_tasks,
        event_id=event.id,
        source_type="submission",
        source_id=submission.id,
        source_storage_path=submission.storage_path,
        base_url=str(request.base_url).rstrip("/"),
        force=True,
    )


@router.get("/preview-assets/{signed_token}")
def local_preview_asset(signed_token: str) -> FileResponse:
    store = get_object_store()
    if store.backend != "local":
        raise HTTPException(status_code=404, detail="资源不存在")
    try:
        key, mime = parse_local_asset_token(signed_token)
    except TimeoutError as exc:
        raise HTTPException(status_code=410, detail="预览地址已过期") from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="资源不存在") from exc
    try:
        path = store._path(key)
        if not path.is_file():
            raise FileNotFoundError
    except (FileNotFoundError, ValueError):
        raise HTTPException(status_code=404, detail="资源不存在")
    return FileResponse(
        path,
        media_type=mime,
        headers={"Cache-Control": "private, max-age=60", "Accept-Ranges": "bytes"},
    )
