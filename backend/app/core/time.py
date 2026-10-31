"""Timezone-aware UTC clock and the naive-UTC database boundary.

Naive UTC timestamps cannot be compared with aware datetimes (``TypeError``).
This module is the single clock:

* ``utc_now()`` is timezone-aware UTC.
* Columns stay ``TIMESTAMP WITHOUT TIME ZONE`` / SQLite ``DateTime`` and keep
  storing UTC wall time without an offset. ``UtcDateTime`` converts aware
  values to that shape on the way in, so PostgreSQL does not shift them into
  the session time zone and existing rows stay readable.
* Loaded values stay naive. API fields that already omit an offset
  (``created_at`` and the other stored timestamps) therefore keep the same
  JSON. Clients parse those strings as local time; adding ``+00:00`` would
  move displayed clocks. Fields that already advertise an offset
  (phase schedule, ``server_time``) go through ``as_utc()`` before serialization.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime
from sqlalchemy.types import TypeDecorator


def utc_now() -> datetime:
    """Current time as a timezone-aware UTC datetime."""
    return datetime.now(UTC)


def as_utc(value: datetime) -> datetime:
    """Interpret a naive value as UTC and convert an aware value to UTC."""
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def as_naive_utc(value: datetime) -> datetime:
    """UTC wall time without tzinfo, matching the timestamp columns."""
    return as_utc(value).replace(tzinfo=None)


def utc_now_naive() -> datetime:
    """Naive UTC stamp for values kept on ORM instances or in offset-free JSON."""
    return as_naive_utc(utc_now())


def utc_from_timestamp(seconds: float) -> datetime:
    """Timezone-aware UTC datetime from a POSIX timestamp."""
    return datetime.fromtimestamp(seconds, UTC)


def utc_iso(value: datetime) -> str:
    """UTC instant rendered with a ``Z`` suffix (webhook payloads)."""
    return as_utc(value).isoformat().replace("+00:00", "Z")


class UtcDateTime(TypeDecorator):
    """DateTime column that stores naive UTC and accepts aware inputs.

    Result values stay naive so existing API JSON does not grow a ``+00:00``
    suffix. Compare them with ``as_utc()`` against ``utc_now()``.
    """

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None or not isinstance(value, datetime):
            return value
        return as_naive_utc(value)

    def process_result_value(self, value, dialect):
        if value is None or not isinstance(value, datetime):
            return value
        return as_naive_utc(value)
