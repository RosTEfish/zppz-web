"""Create, replace, track-change, and delete routes."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.session import get_db
from app.models import (
    Submission,
    User,
)
from app.modules.banlist.service import enforce_song_allowed
from app.modules.common import serialize_submissions
from app.modules.events.service import get_current_event
from app.modules.submissions.support import (
    _create_upload_intent,
    _delete_submission,
    _demote_existing_j_track,
    _eligible_song,
    _legacy_upload_metadata,
    _move_submission_track,
    _normalize_track,
    _put_legacy_upload,
    _require_participant,
    _require_submission_phase,
    _submission_options,
)
from app.modules.submissions.upload import _complete_intent
from app.schemas import (
    StoredFileRead,
    SubmissionTrackUpdate,
)


def upload_submission(
    background_tasks: BackgroundTasks,
    song_id: int | None = Form(None),
    track: str = Form("normal"),
    file: UploadFile = File(...),
    acknowledge_ban_warning: bool = Form(False),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    _require_participant(user)
    event = get_current_event(db)
    _require_submission_phase(db, event)
    normalized_track = _normalize_track(track)
    if normalized_track == "exhibition":
        song = None if song_id is None else _eligible_song(db, event.id, user, song_id)[0]
    else:
        if song_id is None:
            raise HTTPException(status_code=422, detail="普通和 J 投稿必须关联候选曲目")
        song, _ = _eligible_song(db, event.id, user, song_id)
    file_name, file_size, content_type = _legacy_upload_metadata(file)
    intent = _create_upload_intent(
        db,
        event_id=event.id,
        user=user,
        song_id=song.id if song else None,
        submission_id=None,
        track=normalized_track,
        file_name=file_name,
        file_size=file_size,
        content_type=content_type,
        acknowledge_ban_warning=acknowledge_ban_warning,
        is_admin=False,
    )
    _put_legacy_upload(intent, file, db)
    return serialize_submissions(db, [_complete_intent(intent, user, db, background_tasks)])[0]


def replace_submission(
    submission_id: int,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    track: str | None = Form(None),
    acknowledge_ban_warning: bool = Form(False),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    _require_participant(user)
    event = get_current_event(db)
    _require_submission_phase(db, event)
    row = db.scalar(select(Submission).options(*_submission_options()).where(Submission.id == submission_id))
    if not row or row.user_id != user.id or row.event_id != event.id:
        raise HTTPException(status_code=404, detail="投稿不存在")
    if row.source_song_id is None:
        if row.track != "exhibition":
            raise HTTPException(status_code=409, detail="非场外投稿缺少关联曲目")
        if track is not None and _normalize_track(track) != "exhibition":
            raise HTTPException(status_code=422, detail="独立场外投稿不能改为普通或 J 投稿")
        song = None
    else:
        song, _ = _eligible_song(db, event.id, user, row.source_song_id)
    if song is not None:
        enforce_song_allowed(db, song.song_name, song.artist, acknowledge_ban_warning)
    file_name, file_size, content_type = _legacy_upload_metadata(file)
    intent = _create_upload_intent(
        db,
        event_id=event.id,
        user=user,
        song_id=song.id if song else None,
        submission_id=row.id,
        track=_normalize_track(track, row.track),
        file_name=file_name,
        file_size=file_size,
        content_type=content_type,
        acknowledge_ban_warning=acknowledge_ban_warning,
        is_admin=False,
    )
    _put_legacy_upload(intent, file, db)
    return serialize_submissions(db, [_complete_intent(intent, user, db, background_tasks)])[0]


def update_submission_track(
    submission_id: int,
    payload: SubmissionTrackUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    _require_participant(user)
    event = get_current_event(db)
    _require_submission_phase(db, event)
    row = db.scalar(
        select(Submission)
        .options(*_submission_options())
        .where(Submission.id == submission_id)
    )
    if not row or row.user_id != user.id or row.event_id != event.id or row.source_song_id is None:
        raise HTTPException(status_code=404, detail="投稿不存在")
    song, source_kind = _eligible_song(db, event.id, user, row.source_song_id)
    next_track = _normalize_track(payload.track)
    if next_track != "exhibition" and row.source_song_id is None:
        raise HTTPException(status_code=422, detail="普通和 J 投稿必须关联候选曲目")
    try:
        if next_track == "j":
            _demote_existing_j_track(db, event.id, user.id, row.id)
        _move_submission_track(db, row, next_track)
        row.source_kind = source_kind
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="J 赛道切换冲突，请刷新页面后重试") from exc
    except Exception:
        db.rollback()
        raise
    row = db.scalar(
        select(Submission)
        .options(*_submission_options())
        .where(Submission.id == submission_id)
    )
    assert row is not None
    row.user = user
    row.source_song = song
    return serialize_submissions(db, [row])[0]


# Compatibility endpoints for clients that previously treated J submissions separately.
def my_j_track(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    _require_participant(user)
    event = get_current_event(db)
    row = db.scalar(
        select(Submission)
        .options(*_submission_options())
        .where(Submission.event_id == event.id, Submission.user_id == user.id, Submission.track == "j")
    )
    return {"submission": serialize_submissions(db, [row])[0] if row else None}


def delete_j_track(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    _require_participant(user)
    event = get_current_event(db)
    _require_submission_phase(db, event)
    row = db.scalar(
        select(Submission).where(
            Submission.event_id == event.id,
            Submission.user_id == user.id,
            Submission.track == "j",
        )
    )
    if not row:
        raise HTTPException(status_code=404, detail="J 赛道投稿不存在")
    _delete_submission(db, row)
    return {"message": "J 赛道投稿已删除"}


def delete_submission(submission_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    _require_participant(user)
    event = get_current_event(db)
    _require_submission_phase(db, event)
    row = db.get(Submission, submission_id)
    if not row or row.user_id != user.id or row.event_id != event.id:
        raise HTTPException(status_code=404, detail="投稿不存在")
    _delete_submission(db, row)
    return {"message": "投稿已删除"}


def register_submit_routes(router: APIRouter) -> None:
    router.post("", response_model=StoredFileRead, deprecated=True)(upload_submission)
    router.post("/{submission_id}/replace", response_model=StoredFileRead, deprecated=True)(replace_submission)
    router.patch("/{submission_id}/track", response_model=StoredFileRead)(update_submission_track)
    router.get("/j-track")(my_j_track)
    router.delete("/j-track")(delete_j_track)
    router.delete("/{submission_id}")(delete_submission)
