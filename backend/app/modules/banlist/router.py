from __future__ import annotations

import time
from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import get_current_user, require_role
from app.db.session import get_db
from app.models import BanEntry, BanImport, User
from app.modules.banlist.service import (
    MAX_BAN_FILE_BYTES,
    check_song,
    create_ban_import,
    enforce_query_rate_limit,
    get_import_entries,
    publish_ban_import,
    search_ban_entries,
    serialize_import,
    serialize_preview,
)
from app.schemas import BanAliasCreate, BanCheckRequest, BanCheckResponse, BanImportPreview, BanImportRead, BanSearchResponse


router = APIRouter(prefix="/banlist", tags=["banlist"])
admin_router = APIRouter(prefix="/admin/banlist", tags=["admin-banlist"])


@router.post("/check", response_model=BanCheckResponse)
def check_ban(payload: BanCheckRequest, response: Response, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    enforce_query_rate_limit(user.id, time.monotonic())
    response.headers["Cache-Control"] = "private, max-age=15"
    return check_song(db, payload.title, payload.artist)


@router.get("/search", response_model=BanSearchResponse)
def search_ban(
    response: Response,
    title: str = Query(default="", max_length=200),
    artist: str = Query(default="", max_length=200),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    if len(title.strip()) + len(artist.strip()) < 2:
        raise HTTPException(status_code=422, detail="至少输入两个字符后再搜索")
    enforce_query_rate_limit(user.id, time.monotonic())
    response.headers["Cache-Control"] = "private, max-age=15"
    return search_ban_entries(db, title=title, artist=artist)


@admin_router.get("", response_model=list[BanImportRead])
def list_ban_imports(_: User = Depends(require_role("admin")), db: Session = Depends(get_db)) -> list[dict]:
    records = db.scalars(select(BanImport).order_by(BanImport.created_at.desc(), BanImport.id.desc())).all()
    return [serialize_import(record) for record in records]


@admin_router.post("/import", response_model=BanImportPreview)
def import_banlist(
    file: UploadFile = File(...),
    user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> dict:
    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=422, detail="请上传 .xlsx 格式的 Ban 曲文件")
    raw = file.file.read()
    if len(raw) > MAX_BAN_FILE_BYTES:
        raise HTTPException(status_code=413, detail="Ban 曲 Excel 文件不能超过 10 MB")
    try:
        record = create_ban_import(db, file.filename, raw, user.id)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return serialize_preview(record, get_import_entries(db, record.id))


@admin_router.get("/{import_id}/preview", response_model=BanImportPreview)
def preview_banlist(import_id: int, _: User = Depends(require_role("admin")), db: Session = Depends(get_db)) -> dict:
    record = db.get(BanImport, import_id)
    if not record:
        raise HTTPException(status_code=404, detail="Ban 曲导入版本不存在")
    return serialize_preview(record, get_import_entries(db, record.id))


@admin_router.post("/{import_id}/publish", response_model=BanImportRead)
def publish_banlist(import_id: int, _: User = Depends(require_role("admin")), db: Session = Depends(get_db)) -> dict:
    return serialize_import(publish_ban_import(db, import_id))


@admin_router.post("/aliases", response_model=dict)
def add_ban_alias(payload: BanAliasCreate, user: User = Depends(require_role("admin")), db: Session = Depends(get_db)) -> dict:
    from app.models import BanAlias
    from app.modules.banlist.service import normalize_text

    entry = db.get(BanEntry, payload.entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Ban 曲记录不存在")
    alias = db.scalar(
        select(BanAlias).where(
            BanAlias.entry_id == entry.id,
            BanAlias.normalized_song_name == normalize_text(payload.title),
            BanAlias.normalized_artist == normalize_text(payload.artist),
        )
    )
    if not alias:
        alias = BanAlias(
            entry_id=entry.id,
            song_name=payload.title.strip(),
            artist=payload.artist.strip(),
            normalized_song_name=normalize_text(payload.title),
            normalized_artist=normalize_text(payload.artist),
        )
        db.add(alias)
    alias.confirmed_by_id = user.id
    alias.confirmed_at = datetime.utcnow()
    alias.source = "admin"
    db.commit()
    return {"message": "Ban 曲别名已确认", "entry_id": entry.id}
