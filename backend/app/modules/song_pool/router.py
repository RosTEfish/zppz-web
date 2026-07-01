import csv
import io

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.core.security import get_current_user, require_role
from app.db.session import get_db
from app.models import Song, User
from app.modules.common import serialize_song
from app.modules.events.service import assert_song_limit, get_current_event
from app.schemas import SongCreate, SongRead


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


@admin_router.put("/{song_id}", response_model=SongRead)
def admin_update_song(song_id: int, payload: SongCreate, _: User = Depends(require_role("admin", "pool_editor")), db: Session = Depends(get_db)) -> dict:
    song = db.get(Song, song_id)
    if not song:
        raise HTTPException(status_code=404, detail="曲目不存在")
    for key, value in payload.model_dump().items():
        setattr(song, key, value)
    db.commit()
    db.refresh(song)
    return serialize_song(song)


@admin_router.delete("/{song_id}")
def admin_delete_song(song_id: int, _: User = Depends(require_role("admin", "pool_editor")), db: Session = Depends(get_db)) -> dict:
    song = db.get(Song, song_id)
    if not song:
        raise HTTPException(status_code=404, detail="曲目不存在")
    db.delete(song)
    db.commit()
    return {"message": "曲目已删除"}


@admin_router.get("/export.csv")
def export_songs(_: User = Depends(require_role("admin", "pool_editor")), db: Session = Depends(get_db)):
    event = get_current_event(db)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "submitter", "identity", "song_name", "artist", "song_type", "remark"])
    songs = db.scalars(select(Song).options(joinedload(Song.submitter)).where(Song.event_id == event.id)).all()
    for song in songs:
        writer.writerow([song.id, song.submitter.user_code, song.submitter.identity, song.song_name, song.artist, song.song_type, song.remark])
    output.seek(0)
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=song-pool.csv"})


@admin_router.post("/import.csv")
async def import_songs(file: UploadFile, _: User = Depends(require_role("admin", "pool_editor")), db: Session = Depends(get_db)) -> dict:
    raw = (await file.read()).decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(raw))
    event = get_current_event(db)
    created = 0
    first_user = db.scalar(select(User).order_by(User.id))
    if not first_user:
        raise HTTPException(status_code=400, detail="需要至少一个用户才能导入曲池")
    for row in reader:
        db.add(
            Song(
                event_id=event.id,
                submitted_by_id=first_user.id,
                song_name=row.get("song_name") or row.get("曲名") or "",
                artist=row.get("artist") or row.get("曲师") or "",
                song_type=(row.get("song_type") or "A")[:1],
                remark=row.get("remark") or "",
            )
        )
        created += 1
    db.commit()
    return {"message": f"已导入 {created} 首曲目", "created": created}
