from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import user_payload
from app.models import GuessChart, GuessVote, Song, Submission


def serialize_song(song: Song) -> dict:
    return {
        "id": song.id,
        "song_name": song.song_name,
        "artist": song.artist,
        "song_type": song.song_type,
        "remark": song.remark,
        "submitter": user_payload(song.submitter) if song.submitter else None,
        "created_at": song.created_at,
    }


def serialize_submission(item: Submission) -> dict:
    return {
        "id": item.id,
        "file_name": item.file_name,
        "file_size": item.file_size,
        "review_status": item.review_status,
        "review_note": item.review_note,
        "user": user_payload(item.user) if item.user else None,
        "created_at": item.created_at,
    }


def serialize_chart(db: Session, chart: GuessChart, current_user_id: int | None = None) -> dict:
    love_votes = db.scalar(select(func.count()).select_from(GuessVote).where(GuessVote.chart_id == chart.id, GuessVote.vote_type == "love")) or 0
    funny_votes = db.scalar(select(func.count()).select_from(GuessVote).where(GuessVote.chart_id == chart.id, GuessVote.vote_type == "funny")) or 0
    my_votes: list[str] = []
    if current_user_id:
        my_votes = list(db.scalars(select(GuessVote.vote_type).where(GuessVote.chart_id == chart.id, GuessVote.user_id == current_user_id)).all())
    return {
        "id": chart.id,
        "title": chart.title,
        "author": chart.author,
        "level": chart.level,
        "lane": chart.lane,
        "guess_group_key": chart.guess_group_key,
        "source_submission_type": chart.source_submission_type,
        "source_submission_id": chart.source_submission_id,
        "source_level_slot": chart.source_level_slot,
        "cover_path": chart.cover_path,
        "storage_path": chart.storage_path,
        "is_self_selected": chart.is_self_selected,
        "plays": chart.plays,
        "created_at": chart.created_at,
        "love_votes": love_votes,
        "funny_votes": funny_votes,
        "my_votes": my_votes,
    }

