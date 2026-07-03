from __future__ import annotations

from collections import Counter, defaultdict

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models import (
    GuessAuthorCandidate,
    GuessAuthorGuess,
    GuessChart,
    GuessVote,
    JTrackSubmission,
    Submission,
    User,
)
from app.modules.events.service import get_current_event


def build_guess_stats(db: Session, scope: str) -> dict:
    if scope not in {"all", "j"}:
        raise HTTPException(status_code=400, detail="scope 只能是 all 或 j")
    event = get_current_event(db)
    stmt = select(GuessChart).where(GuessChart.event_id == event.id).order_by(GuessChart.id.asc())
    if scope == "j":
        stmt = stmt.where(GuessChart.lane == "j")
    charts = list(db.scalars(stmt).all())
    chart_ids = [chart.id for chart in charts]
    chart_by_id = {chart.id: chart for chart in charts}
    group_chart_ids: dict[str, list[int]] = defaultdict(list)
    for chart in charts:
        group_chart_ids[_group_key(chart)].append(chart.id)
    group_by_chart_id = {
        chart_id: group_key for group_key, ids in group_chart_ids.items() for chart_id in ids
    }

    vote_counts: dict[int, Counter[str]] = defaultdict(Counter)
    if chart_ids:
        for chart_id, vote_type, count in db.execute(
            select(GuessVote.chart_id, GuessVote.vote_type, func.count(GuessVote.id))
            .where(GuessVote.chart_id.in_(chart_ids))
            .group_by(GuessVote.chart_id, GuessVote.vote_type)
        ):
            vote_counts[int(chart_id)][str(vote_type)] = int(count)

    guesses = []
    if chart_ids:
        guesses = list(
            db.scalars(
                select(GuessAuthorGuess).where(GuessAuthorGuess.chart_id.in_(chart_ids)).order_by(GuessAuthorGuess.id.asc())
            ).all()
        )

    users = {user.id: user for user in db.scalars(select(User)).all()}
    owner_by_chart = _owner_by_chart(db, charts)
    candidate_rows = list(
        db.scalars(
            select(GuessAuthorCandidate).where(GuessAuthorCandidate.event_id == event.id)
        ).all()
    )
    candidate_display = {
        row.user_id: (row.display_id.strip() or users.get(row.user_id).user_code if users.get(row.user_id) else str(row.user_id))
        for row in candidate_rows
    }

    guesses_by_group: dict[str, list[GuessAuthorGuess]] = defaultdict(list)
    user_aggregate: dict[int, dict[str, int]] = defaultdict(lambda: {"guesses": 0, "counted": 0, "correct": 0})
    candidate_counts: Counter[int] = Counter()
    details: list[dict] = []
    counted_guesses = 0
    correct_guesses = 0

    for guess in guesses:
        group_key = group_by_chart_id.get(guess.chart_id)
        if not group_key:
            continue
        guesses_by_group[group_key].append(guess)
        anchor_chart = chart_by_id[guess.chart_id]
        owner_id = owner_by_chart.get(guess.chart_id)
        is_own = owner_id is not None and owner_id == guess.user_id
        is_counted = owner_id is not None and not is_own
        is_correct = bool(is_counted and guess.guessed_user_id == owner_id)
        user_aggregate[guess.user_id]["guesses"] += 1
        candidate_counts[guess.guessed_user_id] += 1
        if is_counted:
            counted_guesses += 1
            user_aggregate[guess.user_id]["counted"] += 1
            if is_correct:
                correct_guesses += 1
                user_aggregate[guess.user_id]["correct"] += 1
        details.append(
            {
                "chart_id": anchor_chart.id,
                "title": anchor_chart.title,
                "level": anchor_chart.level,
                "lane": anchor_chart.lane,
                "guesser": _user_summary(users.get(guess.user_id)),
                "guessed_user": _user_summary(users.get(guess.guessed_user_id)),
                "guessed_display_id": candidate_display.get(
                    guess.guessed_user_id,
                    users.get(guess.guessed_user_id).user_code if users.get(guess.guessed_user_id) else str(guess.guessed_user_id),
                ),
                "actual_author": _user_summary(users.get(owner_id)) if owner_id else None,
                "is_own_chart": is_own,
                "is_counted": is_counted,
                "is_correct": is_correct,
                "updated_at": guess.updated_at,
            }
        )

    chart_stats: list[dict] = []
    for chart in charts:
        group_guesses = guesses_by_group.get(_group_key(chart), [])
        owner_id = owner_by_chart.get(chart.id)
        counted = [guess for guess in group_guesses if owner_id is not None and guess.user_id != owner_id]
        correct = [guess for guess in counted if guess.guessed_user_id == owner_id]
        chart_stats.append(
            {
                "chart_id": chart.id,
                "title": chart.title,
                "author": chart.author,
                "level": chart.level,
                "lane": chart.lane,
                "views": chart.plays,
                "love_votes": vote_counts[chart.id]["love"],
                "funny_votes": vote_counts[chart.id]["funny"],
                "total_votes": vote_counts[chart.id]["love"] + vote_counts[chart.id]["funny"],
                "guess_count": len(group_guesses),
                "counted_guesses": len(counted),
                "correct_guesses": len(correct),
                "accuracy": _accuracy(len(correct), len(counted)),
                "actual_author": _user_summary(users.get(owner_id)) if owner_id else None,
            }
        )

    user_stats = []
    for user_id, values in user_aggregate.items():
        user_stats.append(
            {
                "user": _user_summary(users.get(user_id)),
                **values,
                "accuracy": _accuracy(values["correct"], values["counted"]),
            }
        )
    user_stats.sort(key=lambda row: (-row["correct"], -row["counted"], row["user"]["user_code"] if row["user"] else ""))

    candidate_stats = [
        {
            "user": _user_summary(users.get(user_id)),
            "display_id": candidate_display.get(
                user_id,
                users.get(user_id).user_code if users.get(user_id) else str(user_id),
            ),
            "selected_count": count,
        }
        for user_id, count in candidate_counts.most_common()
    ]

    return {
        "scope": scope,
        "overview": {
            "charts": len(charts),
            "views": sum(chart.plays for chart in charts),
            "love_votes": sum(counts["love"] for counts in vote_counts.values()),
            "funny_votes": sum(counts["funny"] for counts in vote_counts.values()),
            "guess_records": len(guesses),
            "counted_guesses": counted_guesses,
            "correct_guesses": correct_guesses,
            "accuracy": _accuracy(correct_guesses, counted_guesses),
            "users_guessing": len(user_aggregate),
            "users_guessed": len(candidate_counts),
        },
        "chart_stats": chart_stats,
        "user_stats": user_stats,
        "candidate_stats": candidate_stats,
        "guess_details": details,
    }


def _owner_by_chart(db: Session, charts: list[GuessChart]) -> dict[int, int]:
    submission_ids = {
        int(chart.source_submission_id)
        for chart in charts
        if chart.source_submission_type in {"normal", "j"} and chart.source_submission_id is not None
    }
    submissions = {
        row.id: row.user_id
        for row in db.scalars(select(Submission).where(Submission.id.in_(submission_ids))).all()
    }
    legacy_j = {
        row.id: row.user_id
        for row in db.scalars(select(JTrackSubmission).where(JTrackSubmission.id.in_(submission_ids))).all()
    }
    result: dict[int, int] = {}
    for chart in charts:
        if chart.source_submission_id is None:
            continue
        owner_id = submissions.get(chart.source_submission_id)
        if owner_id is None and chart.source_submission_type == "j":
            owner_id = legacy_j.get(chart.source_submission_id)
        if owner_id is not None:
            result[chart.id] = owner_id
    return result


def _group_key(chart: GuessChart) -> str:
    return chart.guess_group_key or f"chart:{chart.id}"


def _accuracy(correct: int, counted: int) -> float | None:
    return round(correct / counted * 100, 2) if counted else None


def _user_summary(user: User | None) -> dict | None:
    if not user:
        return None
    return {
        "id": user.id,
        "user_code": user.user_code,
        "display_name": user.display_name,
        "identity": user.identity,
    }
