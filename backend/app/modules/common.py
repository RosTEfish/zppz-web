from collections.abc import Sequence
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import user_payload
from app.models import GuessChart, GuessVote, Song, Submission
from app.modules.guess_game.vote_quota import love_vote_bucket


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
        "track_duration_seconds": item.track_duration_seconds,
        "is_long_track": bool(item.track_duration_seconds is not None and item.track_duration_seconds > 240),
        "public_package_ready": bool(item.public_storage_path),
        "validation": {
            "maidata": True,
            "track": True,
            "background": True,
            "duration": bool(item.track_duration_seconds and item.track_duration_seconds > 0),
        },
        "source_song": serialize_song(item.source_song) if item.source_song else None,
        "user": user_payload(item.user) if item.user else None,
        "created_at": item.created_at,
    }


def _chart_payload(
    chart: GuessChart,
    love_votes: int = 0,
    funny_votes: int = 0,
    my_votes: list[str] | None = None,
    *,
    track_duration_seconds: float | None = None,
    include_private: bool = False,
    include_designer: bool = False,
) -> dict:
    payload = {
        "id": chart.id,
        "title": chart.title,
        "author": chart.author,
        "level": chart.level,
        "lane": chart.lane,
        "guess_group_key": chart.guess_group_key,
        "source_submission_type": chart.source_submission_type,
        "source_level_slot": chart.source_level_slot,
        "cover_path": (
            f"/api/v1/guess-game/charts/{chart.id}/cover?v={Path(chart.cover_path).stem}"
            if chart.cover_path
            else ""
        ),
        "is_self_selected": chart.is_self_selected,
        "track_duration_seconds": track_duration_seconds,
        "is_long_track": bool(track_duration_seconds is not None and track_duration_seconds > 240),
        "plays": chart.plays,
        "created_at": chart.created_at,
        "love_votes": love_votes,
        "funny_votes": funny_votes,
        "my_votes": my_votes or [],
        "love_vote_bucket": love_vote_bucket(chart.level),
    }
    if include_designer or include_private:
        payload["designer"] = chart.designer
    if include_private:
        payload.update({
            "source_submission_id": chart.source_submission_id,
            "storage_path": chart.storage_path,
            "cover_path": chart.cover_path,
        })
    return payload


def serialize_chart(
    db: Session,
    chart: GuessChart,
    current_user_id: int | None = None,
    *,
    include_private: bool = False,
    include_designer: bool = False,
) -> dict:
    return serialize_charts(
        db,
        [chart],
        current_user_id,
        include_private=include_private,
        include_designer=include_designer,
    )[0]


def serialize_charts(
    db: Session,
    charts: Sequence[GuessChart],
    current_user_id: int | None = None,
    *,
    include_private: bool = False,
    include_designer: bool = False,
) -> list[dict]:
    if not charts:
        return []

    chart_ids = [chart.id for chart in charts]
    submission_ids = {
        int(chart.source_submission_id)
        for chart in charts
        if chart.source_submission_id is not None and chart.source_submission_type in {"normal", "j", "exhibition"}
    }
    duration_by_submission = dict(
        db.execute(
            select(Submission.id, Submission.track_duration_seconds).where(Submission.id.in_(submission_ids))
        ).all()
    ) if submission_ids else {}
    votable_chart_ids = [
        chart.id for chart in charts if chart.source_submission_type != "exhibition"
    ]
    vote_counts: dict[int, dict[str, int]] = {chart_id: {"love": 0, "funny": 0} for chart_id in chart_ids}
    if votable_chart_ids:
        for chart_id, vote_type, count in db.execute(
            select(GuessVote.chart_id, GuessVote.vote_type, func.count())
            .where(GuessVote.chart_id.in_(votable_chart_ids))
            .group_by(GuessVote.chart_id, GuessVote.vote_type)
        ):
            vote_counts.setdefault(chart_id, {})[vote_type] = int(count)

    my_votes_by_chart: dict[int, list[str]] = {chart_id: [] for chart_id in chart_ids}
    if current_user_id and votable_chart_ids:
        for chart_id, vote_type in db.execute(
            select(GuessVote.chart_id, GuessVote.vote_type).where(
                GuessVote.chart_id.in_(votable_chart_ids),
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
            track_duration_seconds=duration_by_submission.get(chart.source_submission_id),
            include_private=include_private,
            include_designer=include_designer,
        )
        for chart in charts
    ]
