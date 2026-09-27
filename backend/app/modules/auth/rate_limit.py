"""Best-effort login failure limiter.

Counts live in this process. Uvicorn runs one limiter per worker, so the
effective budget is the limit below multiplied by ``WEB_CONCURRENCY``.
"""

from collections import deque
from math import ceil
from threading import Lock
from time import monotonic


LOGIN_FAILURE_LIMIT = 8
LOGIN_FAILURE_WINDOW_SECONDS = 15 * 60
_MAX_TRACKED_KEYS = 10_000

_lock = Lock()
_failures: dict[tuple[str, str], deque[float]] = {}


def reset_login_attempts() -> None:
    with _lock:
        _failures.clear()


def _account_key(user_code: str) -> str:
    return user_code.strip().casefold()[:128]


def _bucket(client_ip: str, user_code: str) -> tuple[str, str]:
    return (client_ip or "unknown", _account_key(user_code))


def _trim(hits: deque[float], now: float) -> None:
    while hits and now - hits[0] >= LOGIN_FAILURE_WINDOW_SECONDS:
        hits.popleft()


def _drop_expired(now: float) -> None:
    expired = [key for key, hits in _failures.items() if not hits or now - hits[-1] >= LOGIN_FAILURE_WINDOW_SECONDS]
    for key in expired:
        del _failures[key]


def login_retry_after(client_ip: str, user_code: str, now: float | None = None) -> int | None:
    """Seconds until another attempt is allowed, or None when under the limit."""
    current = monotonic() if now is None else now
    with _lock:
        hits = _failures.get(_bucket(client_ip, user_code))
        if not hits:
            return None
        _trim(hits, current)
        if len(hits) < LOGIN_FAILURE_LIMIT:
            if not hits:
                _failures.pop(_bucket(client_ip, user_code), None)
            return None
        remaining = LOGIN_FAILURE_WINDOW_SECONDS - (current - hits[0])
        return max(1, ceil(remaining))


def record_login_failure(client_ip: str, user_code: str, now: float | None = None) -> None:
    current = monotonic() if now is None else now
    key = _bucket(client_ip, user_code)
    with _lock:
        hits = _failures.get(key)
        if hits is None:
            _drop_expired(current)
            if len(_failures) >= _MAX_TRACKED_KEYS:
                oldest = min(_failures, key=lambda item: _failures[item][-1] if _failures[item] else -1.0)
                del _failures[oldest]
            hits = deque()
            _failures[key] = hits
        _trim(hits, current)
        hits.append(current)


def clear_login_failures(client_ip: str, user_code: str) -> None:
    with _lock:
        _failures.pop(_bucket(client_ip, user_code), None)
