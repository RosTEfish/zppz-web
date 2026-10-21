"""Best-effort auth attempt limiter.

Counts live in this process. Uvicorn runs one limiter per worker, so the
effective budget is the limit below multiplied by ``WEB_CONCURRENCY``.
"""

from collections import deque
from math import ceil
from threading import Lock
from time import monotonic


AUTH_WINDOW_SECONDS = 15 * 60
LOGIN_FAILURE_LIMIT = 8
LOGIN_IP_FAILURE_LIMIT = 40
LOGIN_FAILURE_WINDOW_SECONDS = AUTH_WINDOW_SECONDS
REGISTER_LIMIT = 30
PASSWORD_FAILURE_LIMIT = 8
PASSWORD_IP_FAILURE_LIMIT = 40
_MAX_TRACKED_KEYS = 10_000

_lock = Lock()
_hits: dict[tuple[str, ...], deque[float]] = {}


def reset_login_attempts() -> None:
    with _lock:
        _hits.clear()


def _account_key(user_code: str) -> str:
    return user_code.strip().casefold()[:128]


def _trim(hits: deque[float], now: float, window: float) -> None:
    while hits and now - hits[0] >= window:
        hits.popleft()


def _drop_expired(now: float) -> None:
    expired = [key for key, hits in _hits.items() if not hits or now - hits[-1] >= AUTH_WINDOW_SECONDS]
    for key in expired:
        del _hits[key]


def _retry_after(key: tuple[str, ...], limit: int, now: float) -> int | None:
    hits = _hits.get(key)
    if not hits:
        return None
    _trim(hits, now, AUTH_WINDOW_SECONDS)
    if len(hits) < limit:
        if not hits:
            _hits.pop(key, None)
        return None
    remaining = AUTH_WINDOW_SECONDS - (now - hits[0])
    return max(1, ceil(remaining))


def _record(key: tuple[str, ...], now: float) -> None:
    hits = _hits.get(key)
    if hits is None:
        _drop_expired(now)
        if len(_hits) >= _MAX_TRACKED_KEYS:
            oldest = min(_hits, key=lambda item: _hits[item][-1] if _hits[item] else -1.0)
            del _hits[oldest]
        hits = deque()
        _hits[key] = hits
    _trim(hits, now, AUTH_WINDOW_SECONDS)
    hits.append(now)


def _longest(waits: list[int | None]) -> int | None:
    present = [item for item in waits if item is not None]
    return max(present) if present else None


def login_retry_after(
    client_ip: str,
    user_code: str,
    now: float | None = None,
    *,
    enforce_ip_budget: bool = True,
) -> int | None:
    """Seconds until another attempt is allowed, or None when under the limit."""
    current = monotonic() if now is None else now
    account = (client_ip or "unknown", _account_key(user_code))
    with _lock:
        waits = [_retry_after(("login", *account), LOGIN_FAILURE_LIMIT, current)]
        if enforce_ip_budget:
            waits.append(_retry_after(("login-ip", client_ip or "unknown"), LOGIN_IP_FAILURE_LIMIT, current))
        return _longest(waits)


def record_login_failure(
    client_ip: str,
    user_code: str,
    now: float | None = None,
    *,
    enforce_ip_budget: bool = True,
) -> None:
    current = monotonic() if now is None else now
    account = (client_ip or "unknown", _account_key(user_code))
    with _lock:
        _record(("login", *account), current)
        if enforce_ip_budget:
            _record(("login-ip", client_ip or "unknown"), current)


def clear_login_failures(client_ip: str, user_code: str) -> None:
    account = (client_ip or "unknown", _account_key(user_code))
    with _lock:
        _hits.pop(("login", *account), None)


def registration_retry_after(client_ip: str, now: float | None = None) -> int | None:
    current = monotonic() if now is None else now
    with _lock:
        return _retry_after(("register", client_ip or "unknown"), REGISTER_LIMIT, current)


def record_registration(client_ip: str, now: float | None = None) -> None:
    current = monotonic() if now is None else now
    with _lock:
        _record(("register", client_ip or "unknown"), current)


def password_change_retry_after(
    client_ip: str,
    user_code: str,
    now: float | None = None,
    *,
    enforce_ip_budget: bool = True,
) -> int | None:
    current = monotonic() if now is None else now
    account = (client_ip or "unknown", _account_key(user_code))
    with _lock:
        waits = [_retry_after(("password", *account), PASSWORD_FAILURE_LIMIT, current)]
        if enforce_ip_budget:
            waits.append(_retry_after(("password-ip", client_ip or "unknown"), PASSWORD_IP_FAILURE_LIMIT, current))
        return _longest(waits)


def record_password_change_failure(
    client_ip: str,
    user_code: str,
    now: float | None = None,
    *,
    enforce_ip_budget: bool = True,
) -> None:
    current = monotonic() if now is None else now
    account = (client_ip or "unknown", _account_key(user_code))
    with _lock:
        _record(("password", *account), current)
        if enforce_ip_budget:
            _record(("password-ip", client_ip or "unknown"), current)


def clear_password_change_failures(client_ip: str, user_code: str) -> None:
    account = (client_ip or "unknown", _account_key(user_code))
    with _lock:
        _hits.pop(("password", *account), None)
