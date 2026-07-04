from collections.abc import Sequence

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
        "source_kind": item.source_kind,
        "track": item.track,
        "source_song": serialize_song(item.source_song) if item.source_song else None,
        "user": user_payload(item.user) if item.user else None,
        "created_at": item.created_at,
    }


def _chart_payload(chart: GuessChart, love_votes: int = 0, funny_votes: int = 0, my_votes: list[str] | None = None) -> dict:
    return {
        "id": chart.id,
        "title": chart.title,
        "author": chart.author,
        "designer": chart.designer,
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
        "my_votes": my_votes or [],
    }


def serialize_chart(db: Session, chart: GuessChart, current_user_id: int | None = None) -> dict:
    return serialize_charts(db, [chart], current_user_id)[0]


def serialize_charts(db: Session, charts: Sequence[GuessChart], current_user_id: int | None = None) -> list[dict]:
    if not charts:
        return []

    chart_ids = [chart.id for chart in charts]
    vote_counts: dict[int, dict[str, int]] = {chart_id: {"love": 0, "funny": 0} for chart_id in chart_ids}
    for chart_id, vote_type, count in db.execute(
        select(GuessVote.chart_id, GuessVote.vote_type, func.count())
        .where(GuessVote.chart_id.in_(chart_ids))
        .group_by(GuessVote.chart_id, GuessVote.vote_type)
    ):
        vote_counts.setdefault(chart_id, {})[vote_type] = int(count)

    my_votes_by_chart: dict[int, list[str]] = {chart_id: [] for chart_id in chart_ids}
    if current_user_id:
        for chart_id, vote_type in db.execute(
            select(GuessVote.chart_id, GuessVote.vote_type).where(
                GuessVote.chart_id.in_(chart_ids),
                GuessVote.user_id == current_user_id,
            )
        ):
            my_votes_by_chart.setdefault(chart_id, []).append(vote_type)

    return [
        _chart_payload(
            chart,
            love_votes=vote_counts.get(chart.id, {}).get("love", 0),
            funny_votes=vote_counts.get(chart.id, {}).get("funny", 0),
            my_votes=my_votes_by_chart.get(chart.id, []),
        )
        for chart in charts
    ]
