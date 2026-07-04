import csv
import io

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.core.security import get_current_user, require_role
from app.db.session import get_db
from app.models import Song, Submission, User
from app.modules.common import serialize_song
from app.modules.events.service import assert_song_limit, get_current_event
from app.schemas import BatchDeleteRequest, BatchDeleteResponse, SongCreate, SongRead


router = APIRouter(prefix="/song-pool", tags=["song-pool"])
admin_router = APIRouter(prefix="/admin/song-pool", tags=["admin-song-pool"])


@router.get("/me", response_model=list[SongRead])
def my_songs(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[dict]:
    event = get_current_event(db)
    songs = db.scalars(
        select(Song)
        .options(selectinload(Song.submitter).selectinload(User.roles))
        .where(Song.event_id == event.id, Song.submitted_by_id == user.id)
        .order_by(Song.created_at.desc())
    ).all()
    return [serialize_song(song) for song in songs]


@router.post("/me", response_model=SongRead)
def create_song(payload: SongCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    event = get_current_event(db)
    assert_song_limit(db, user.id, user.identity)
    song = Song(event_id=event.id, submitted_by_id=user.id, **payload.model_dump())
    db.add(song)
    db.commit()
    db.refresh(song)
    song.submitter = user
    return serialize_song(song)


@router.put("/me/{song_id}", response_model=SongRead)
def update_my_song(song_id: int, payload: SongCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    event = get_current_event(db)
    song = db.scalar(select(Song).where(Song.id == song_id, Song.event_id == event.id, Song.submitted_by_id == user.id))
    if not song:
        raise HTTPException(status_code=404, detail="曲目不存在")
    for key, value in payload.model_dump().items():
        setattr(song, key, value)
    db.commit()
    db.refresh(song)
    song.submitter = user
    return serialize_song(song)


@router.delete("/me/{song_id}")
def delete_my_song(song_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    event = get_current_event(db)
    song = db.scalar(select(Song).where(Song.id == song_id, Song.event_id == event.id, Song.submitted_by_id == user.id))
    if not song:
        raise HTTPException(status_code=404, detail="曲目不存在")
    if db.scalar(select(Submission.id).where(Submission.source_song_id == song.id).limit(1)):
        raise HTTPException(status_code=409, detail="该曲目已有投稿，不能删除")
    db.delete(song)
    db.commit()
    return {"message": "曲目已删除"}


@admin_router.get("", response_model=list[SongRead])
def admin_list_songs(_: User = Depends(require_role("admin", "pool_editor")), db: Session = Depends(get_db)) -> list[dict]:
    event = get_current_event(db)
    songs = db.scalars(
        select(Song)
        .options(selectinload(Song.submitter).selectinload(User.roles))
        .where(Song.event_id == event.id)
        .order_by(Song.created_at.desc())
    ).all()
    return [serialize_song(song) for song in songs]


@admin_router.post("/batch-delete", response_model=BatchDeleteResponse)
def admin_batch_delete_songs(
    payload: BatchDeleteRequest,
    _: User = Depends(require_role("admin", "pool_editor")),
    db: Session = Depends(get_db),
) -> dict:
    event = get_current_event(db)
    song_ids = list(dict.fromkeys(payload.ids))
    songs = list(
        db.scalars(
            select(Song)
            .where(Song.event_id == event.id, Song.id.in_(song_ids))
            .order_by(Song.id.asc())
        ).all()
    )
    found_ids = {song.id for song in songs}
    missing_ids = [song_id for song_id in song_ids if song_id not in found_ids]
    if missing_ids:
        raise HTTPException(status_code=404, detail=f"曲目不存在：{', '.join(map(str, missing_ids))}")
    linked_ids = set(
        db.scalars(
            select(Submission.source_song_id).where(Submission.source_song_id.in_(song_ids))
        ).all()
    )
    if linked_ids:
        blocked = [f"{song.song_name}（ID {song.id}）" for song in songs if song.id in linked_ids]
        raise HTTPException(status_code=409, detail=f"以下曲目已有投稿，整批未删除：{'、'.join(blocked)}")
    try:
        for song in songs:
            db.delete(song)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {"deleted": len(songs), "message": f"已删除 {len(songs)} 首曲目"}


@admin_router.put("/{song_id}", response_model=SongRead)
def admin_update_song(song_id: int, payload: SongCreate, _: User = Depends(require_role("admin", "pool_editor")), db: Session = Depends(get_db)) -> dict:
    event = get_current_event(db)
    song = db.scalar(select(Song).where(Song.id == song_id, Song.event_id == event.id))
    if not song:
        raise HTTPException(status_code=404, detail="曲目不存在")
    for key, value in payload.model_dump().items():
        setattr(song, key, value)
    db.commit()
    db.refresh(song)
    return serialize_song(song)


@admin_router.delete("/{song_id}")
def admin_delete_song(song_id: int, _: User = Depends(require_role("admin", "pool_editor")), db: Session = Depends(get_db)) -> dict:
    event = get_current_event(db)
    song = db.scalar(select(Song).where(Song.id == song_id, Song.event_id == event.id))
    if not song:
        raise HTTPException(status_code=404, detail="曲目不存在")
    if db.scalar(select(Submission.id).where(Submission.source_song_id == song.id).limit(1)):
        raise HTTPException(status_code=409, detail="该曲目已有投稿，不能删除")
    db.delete(song)
    db.commit()
    return {"message": "曲目已删除"}


@admin_router.get("/export.csv")
def export_songs(_: User = Depends(require_role("admin", "pool_editor")), db: Session = Depends(get_db)):
    event = get_current_event(db)
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["曲目ID", "曲名", "曲师", "备注", "分类(A=Pop+术力口,B=通常意义音游核,C=小众宝藏乐曲)"])
    songs = db.scalars(
        select(Song).options(joinedload(Song.submitter)).where(Song.event_id == event.id).order_by(Song.id.asc())
    ).all()
    for song in songs:
        writer.writerow([song.id, song.song_name, song.artist, song.remark, song.song_type])
    payload = output.getvalue().encode("utf-8-sig")
    return StreamingResponse(
        iter([payload]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=song-pool.csv"},
    )


@admin_router.post("/import.csv")
async def import_songs(
    file: UploadFile = File(...),
    _: User = Depends(require_role("admin", "pool_editor")),
    db: Session = Depends(get_db),
) -> dict:
    raw = await file.read()
    text = _decode_csv(raw)
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise HTTPException(status_code=400, detail="CSV 缺少表头")
    event = get_current_event(db)
    rows = list(reader)
    if not rows:
        raise HTTPException(status_code=400, detail="CSV 中没有曲目数据")

    id_header = _find_header(reader.fieldnames, ("曲目ID", "id", "ID"))
    name_header = _find_header(reader.fieldnames, ("曲名", "song_name", "songName"))
    artist_header = _find_header(reader.fieldnames, ("曲师", "artist"))
    remark_header = _find_header(reader.fieldnames, ("备注", "remark"), required=False)
    type_header = _find_header(
        reader.fieldnames,
        (
            "分类(A=Pop+术力口,B=通常意义音游核,C=小众宝藏乐曲)",
            "分类",
            "song_type",
            "songType",
            "type",
        ),
        required=False,
    )

    parsed: list[tuple[int, str, str, str, str | None]] = []
    seen_ids: set[int] = set()
    for line_number, row in enumerate(rows, start=2):
        try:
            song_id = int((row.get(id_header) or "").strip())
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"第 {line_number} 行曲目ID无效") from exc
        if song_id in seen_ids:
            raise HTTPException(status_code=400, detail=f"第 {line_number} 行曲目ID重复：{song_id}")
        seen_ids.add(song_id)
        name = (row.get(name_header) or "").strip()
        artist = (row.get(artist_header) or "").strip()
        if not name or not artist:
            raise HTTPException(status_code=400, detail=f"第 {line_number} 行曲名和曲师不能为空")
        remark = (row.get(remark_header) or "").strip() if remark_header else ""
        song_type = (row.get(type_header) or "").strip().upper() if type_header else None
        if song_type is not None and song_type not in {"A", "B", "C"}:
            raise HTTPException(status_code=400, detail=f"第 {line_number} 行分类必须为 A、B 或 C")
        parsed.append((song_id, name, artist, remark, song_type))

    songs = {
        song.id: song
        for song in db.scalars(select(Song).where(Song.event_id == event.id, Song.id.in_(seen_ids))).all()
    }
    missing_ids = sorted(seen_ids - songs.keys())
    if missing_ids:
        preview = "、".join(str(item) for item in missing_ids[:10])
        raise HTTPException(status_code=400, detail=f"当前曲池不存在以下曲目ID：{preview}")

    for song_id, name, artist, remark, song_type in parsed:
        song = songs[song_id]
        song.song_name = name
        song.artist = artist
        song.remark = remark
        if song_type is not None:
            song.song_type = song_type
    db.commit()
    return {"message": f"已更新 {len(parsed)} 首曲目", "updated": len(parsed)}


def _decode_csv(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gbk", "shift_jis"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise HTTPException(status_code=400, detail="CSV 编码无法识别，请使用 UTF-8、GBK 或 Shift-JIS")


def _find_header(fieldnames: list[str], aliases: tuple[str, ...], *, required: bool = True) -> str | None:
    normalized = {name.strip(): name for name in fieldnames if name}
    for alias in aliases:
        if alias in normalized:
            return normalized[alias]
    if required:
        raise HTTPException(status_code=400, detail=f"CSV 缺少字段：{aliases[0]}")
    return None
