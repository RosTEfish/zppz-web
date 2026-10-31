"""Write domain events in the same transaction as the change that caused them.

Any process that imports ``app.db.session`` registers these hooks, so the API,
the submission worker, and the webhook worker publish through the shared
database. A rollback drops the event with the change.
"""

from __future__ import annotations

import json
import logging
import time

from sqlalchemy import delete, event, func, inspect, select
from sqlalchemy.orm import Session

from app.modules.realtime.topics import RETENTION_ROWS, TOPIC_SCOPE

logger = logging.getLogger(__name__)
_INSTALLED = False
_READY: dict[int, bool] = {}
_WATCH: dict[type, str] | None = None
_last_prune = 0.0


def install_domain_event_hooks() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    event.listen(Session, "before_flush", _before_flush)
    _INSTALLED = True


def _watch_map() -> dict[type, str]:
    global _WATCH
    if _WATCH is not None:
        return _WATCH
    from app import models

    _WATCH = {
        models.SubmissionProcessingJob: "submission.job",
        models.Event: "contest.updated",
        models.EventPhase: "contest.updated",
        models.EventSetting: "contest.updated",
        models.DrawAssignment: "draw.reveal",
        models.GuessChart: "guess.state",
        models.GuessVote: "guess.state",
        models.GuessComment: "guess.state",
        models.GuessAuthorGuess: "guess.state",
        models.GuessAuthorCandidate: "guess.state",
        models.SwapRound: "swap.updated",
        models.SwapRequest: "swap.updated",
        models.SwapRequestItem: "swap.updated",
        models.SwapExcludedSong: "swap.updated",
    }
    return _WATCH


def _outbox_ready(session: Session) -> bool:
    bind = session.get_bind()
    key = id(bind)
    ready = _READY.get(key)
    if ready is not None:
        return ready
    try:
        ready = "domain_events" in inspect(session.connection()).get_table_names()
    except Exception:
        logger.exception("domain event outbox availability check failed")
        return False
    _READY[key] = ready
    return ready


def _collect(session: Session) -> list[dict]:
    watch = _watch_map()
    drafts: dict[tuple[str, int | None], dict] = {}
    seen: set[int] = set()
    changed = list(session.new) + list(session.deleted) + list(session.dirty)
    for obj in changed:
        marker = id(obj)
        if marker in seen:
            continue
        seen.add(marker)
        topic = watch.get(type(obj))
        if topic is None:
            continue
        if obj in session.dirty and obj not in session.new and obj not in session.deleted:
            if not session.is_modified(obj, include_collections=False):
                continue
        subject = obj.user_id if topic == "submission.job" else None
        key = (topic, subject)
        draft = drafts.get(key)
        if draft is None:
            draft = {
                "topic": topic,
                "scope": TOPIC_SCOPE[topic],
                "subject_user_id": subject,
                "payload": {},
            }
            drafts[key] = draft
        if topic == "submission.job":
            jobs = draft["payload"].setdefault("jobs", [])
            jobs.append({"id": obj.id, "status": obj.status, "stage": obj.stage})
        else:
            sources = draft["payload"].setdefault("sources", [])
            name = type(obj).__name__
            if name not in sources:
                sources.append(name)
    return list(drafts.values())


def _before_flush(session: Session, _flush_context, _instances) -> None:
    # Objects added here are included in the flush that is about to run.
    # A nested flush is rejected while the session is already flushing.
    if session.info.get("_domain_event_emit"):
        return
    if not _outbox_ready(session):
        return
    drafts = _collect(session)
    if not drafts:
        return
    from app.models import DomainEvent

    session.info["_domain_event_emit"] = True
    try:
        for draft in drafts:
            session.add(
                DomainEvent(
                    topic=draft["topic"],
                    scope=draft["scope"],
                    subject_user_id=draft["subject_user_id"],
                    payload_json=json.dumps(
                        draft["payload"], ensure_ascii=False, separators=(",", ":"), sort_keys=True
                    ),
                )
            )
    finally:
        session.info["_domain_event_emit"] = False


def prune_domain_events(keep: int = RETENTION_ROWS) -> int:
    """Drop oldest rows, keeping the newest ``keep`` ids."""
    from app.db.session import SessionLocal
    from app.models import DomainEvent

    if keep < 1:
        return 0
    with SessionLocal() as db:
        newest = db.scalar(select(func.max(DomainEvent.id)))
        if newest is None:
            return 0
        cutoff = int(newest) - keep
        if cutoff <= 0:
            return 0
        result = db.execute(delete(DomainEvent).where(DomainEvent.id <= cutoff))
        db.commit()
        deleted = int(result.rowcount or 0)
    return deleted


def prune_domain_events_if_due(interval_seconds: float = 60.0) -> None:
    global _last_prune
    now = time.monotonic()
    if now - _last_prune < interval_seconds:
        return
    _last_prune = now
    try:
        prune_domain_events()
    except Exception:
        logger.exception("domain event prune failed")
