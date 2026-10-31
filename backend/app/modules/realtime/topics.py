"""Event names the SSE stream and the SWR client share.

``resources`` are stable invalidation groups. The frontend maps each name onto
SWR keys; the backend does not embed key arrays.
"""

from __future__ import annotations

TOPIC_SCOPE = {
    "submission.job": "user",
    "contest.updated": "public",
    "draw.reveal": "authenticated",
    "guess.state": "public",
    "swap.updated": "authenticated",
}

TOPIC_RESOURCES: dict[str, tuple[str, ...]] = {
    "submission.job": ("submissions",),
    "contest.updated": ("contest", "guess", "draws", "swap", "submissions", "admin"),
    "draw.reveal": ("draws", "swap", "admin"),
    "guess.state": ("guess", "contest", "admin"),
    "swap.updated": ("swap", "draws"),
}

RETENTION_ROWS = 2000
REPLAY_SECONDS = 20
