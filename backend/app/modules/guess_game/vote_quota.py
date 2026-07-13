from __future__ import annotations

import re
from typing import Literal
import unicodedata

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Event, GuessChart, GuessVote
from app.modules.events.service import get_current_event


LoveVoteBucket = Literal["below_14", "at_least_14"]
LOVE_VOTE_BUCKETS: tuple[LoveVoteBucket, ...] = ("below_14", "at_least_14")
_FIRST_NUMBER = re.compile(r"\d+(?:\.\d+)?")


def love_vote_bucket(level: str) -> LoveVoteBucket:
    normalized = unicodedata.normalize("NFKC", level or "")
    match = _FIRST_NUMBER.search(normalized)
    if match is None:
        return "at_least_14"
    try:
        return "below_14" if float(match.group(0)) < 14 else "at_least_14"
    except ValueError:
        return "at_least_14"


def love_vote_quota(db: Session, user_id: int, event: Event | None = None) -> dict[str, dict[str, int]]:
    event = event or get_current_event(db)
    used = {bucket: 0 for bucket in LOVE_VOTE_BUCKETS}
    levels = db.scalars(
        select(GuessChart.level)
        .join(GuessVote, GuessVote.chart_id == GuessChart.id)
        .where(
            GuessChart.event_id == event.id,
            GuessChart.source_submission_type != "exhibition",
            GuessVote.user_id == user_id,
            GuessVote.vote_type == "love",
        )
    ).all()
    for level in levels:
        used[love_vote_bucket(str(level))] += 1

    limits = {
        "below_14": event.settings.true_love_vote_limit_below_14,
        "at_least_14": event.settings.true_love_vote_limit_at_least_14,
    }
    return {
        bucket: {
            "used": used[bucket],
            "limit": limits[bucket],
            "remaining": max(limits[bucket] - used[bucket], 0),
        }
        for bucket in LOVE_VOTE_BUCKETS
    }
