"""Tail ``domain_events`` and render Server-Sent Events."""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import AsyncIterator
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from starlette.requests import Request

from app.core.security import get_optional_user, has_admin_access
from app.core.time import utc_iso, utc_now_naive
from app.db.session import SessionLocal
from app.models import DomainEvent, User
from app.modules.realtime.outbox import prune_domain_events_if_due
from app.modules.realtime.topics import REPLAY_SECONDS, TOPIC_RESOURCES

FETCH_LIMIT = 100


def poll_seconds() -> float:
    try:
        value = float(os.getenv("SSE_POLL_SECONDS", "0.5"))
    except ValueError:
        return 0.5
    return value if value >= 0 else 0.5


def sse_max_polls() -> int | None:
    """Optional cap so tests can finish a stream. Unset in production."""
    raw = os.getenv("SSE_MAX_POLLS", "").strip()
    if not raw:
        return None
    try:
        value = int(raw)
    except ValueError:
        return None
    return value if value >= 1 else None


def keepalive_every() -> int:
    try:
        value = int(os.getenv("SSE_KEEPALIVE_EVERY", "30"))
    except ValueError:
        return 30
    return value if value >= 1 else 30


def presented_credentials(request: Request) -> bool:
    from app.core.config import get_settings

    settings = get_settings()
    if request.cookies.get(settings.session_cookie_name):
        return True
    authorization = request.headers.get("authorization", "")
    return authorization.lower().startswith("bearer ")


def _viewer_is_admin(viewer: User) -> bool:
    roles = viewer.__dict__.get("roles")
    if not roles:
        return False
    return has_admin_access(viewer)


def event_visible(event: DomainEvent, viewer: User | None) -> bool:
    """Return whether ``viewer`` may receive ``event``. Anonymous viewers only see public rows."""
    user_id = None if viewer is None else viewer.id
    is_admin = False if viewer is None else _viewer_is_admin(viewer)
    return principal_visible(event, user_id=user_id, is_admin=is_admin)


def principal_visible(event: DomainEvent, *, user_id: int | None, is_admin: bool) -> bool:
    if event.scope == "public":
        return True
    if user_id is None:
        return False
    if event.scope == "authenticated":
        return True
    if event.scope == "user":
        return user_id == event.subject_user_id or is_admin
    return False


def snapshot_viewer(request: Request) -> tuple[bool, int | None, bool]:
    """Return ``(credentials_were_sent, user_id, is_admin)``."""
    presented = presented_credentials(request)
    with SessionLocal() as db:
        user = get_optional_user(request, db)
        if user is None:
            return presented, None, False
        return presented, user.id, has_admin_access(user)


def resolve_cursor(after: int | None, last_event_id: str | None, db: Session | None = None) -> int:
    if after is not None:
        return after
    if last_event_id:
        try:
            parsed = int(last_event_id)
        except ValueError:
            parsed = -1
        if parsed >= 0:
            return parsed
    return live_cursor(db)


def live_cursor(db: Session | None = None) -> int:
    """Resume just before events from the last few seconds, or at the current tip."""
    owns_session = db is None
    session = db or SessionLocal()
    try:
        cutoff = utc_now_naive() - timedelta(seconds=REPLAY_SECONDS)
        oldest = session.scalar(select(func.min(DomainEvent.id)).where(DomainEvent.created_at >= cutoff))
        if oldest:
            return int(oldest) - 1
        newest = session.scalar(select(func.max(DomainEvent.id)))
        return int(newest or 0)
    finally:
        if owns_session:
            session.close()


def fetch_events(after_id: int, *, limit: int = FETCH_LIMIT) -> list[DomainEvent]:
    with SessionLocal() as db:
        rows = list(
            db.scalars(
                select(DomainEvent)
                .where(DomainEvent.id > after_id)
                .order_by(DomainEvent.id.asc())
                .limit(limit)
            ).all()
        )
        for row in rows:
            db.expunge(row)
        return rows


def format_sse(event: DomainEvent) -> str:
    try:
        payload = json.loads(event.payload_json or "{}")
    except json.JSONDecodeError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    body = {
        "id": event.id,
        "topic": event.topic,
        "scope": event.scope,
        "subject_user_id": event.subject_user_id,
        "resources": list(TOPIC_RESOURCES.get(event.topic, ())),
        "payload": payload,
        "created_at": utc_iso(event.created_at),
    }
    data = json.dumps(body, ensure_ascii=False, separators=(",", ":"))
    return f"id: {event.id}\nevent: {event.topic}\ndata: {data}\n\n"


async def iter_event_stream(
    request: Request | None,
    cursor: int,
    *,
    user_id: int | None,
    is_admin: bool,
    credentials_presented: bool,
    max_polls: int | None = None,
) -> AsyncIterator[str]:
    yield "retry: 5000\n\n"
    polls = 0
    limit = sse_max_polls() if max_polls is None else max_polls
    while limit is None or polls < limit:
        # Starlette's TestClient receive() waits until the response completes, so
        # asking for disconnect from inside the stream deadlocks that client.
        # Production servers return http.disconnect when the browser goes away.
        if request is not None and limit is None and await request.is_disconnected():
            return
        if (
            credentials_presented
            and request is not None
            and polls > 0
            and polls % keepalive_every() == 0
        ):
            # Short indexed reads stay on the event loop. asyncio.to_thread deadlocks
            # under Starlette's TestClient portal, and these queries are one primary-key
            # range on a small outbox.
            presented, refreshed_id, refreshed_admin = snapshot_viewer(request)
            if presented and refreshed_id is None:
                return
            user_id = refreshed_id
            is_admin = refreshed_admin
        rows = fetch_events(cursor)
        if rows:
            for row in rows:
                cursor = row.id
                if principal_visible(row, user_id=user_id, is_admin=is_admin):
                    yield format_sse(row)
            if len(rows) >= FETCH_LIMIT:
                continue
        polls += 1
        if polls % keepalive_every() == 0:
            yield ": keepalive\n\n"
            prune_domain_events_if_due()
        if limit is not None and polls >= limit:
            return
        await asyncio.sleep(poll_seconds())
