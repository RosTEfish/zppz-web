from __future__ import annotations

import copy
import logging
from pathlib import Path
import re

from starlette.requests import Request

from app.core.config import get_settings
from app.core.metrics import record_http_response
from app.core.security import get_optional_user
from app.db.session import SessionLocal
from app.modules.events.phase_policy import get_phase_status


logger = logging.getLogger("app.observability")
_SENSITIVE_KEY = re.compile(
    r"password|secret|token|dsn|authorization|cookie|api_key|access_key|session",
    re.IGNORECASE,
)
_SECRET_ASSIGNMENT = re.compile(
    r"(?i)(token|password|secret|dsn|authorization|api_key|access_key|session)=([^&\s]+)"
)
_REVISION_SHA = re.compile(r"[0-9a-fA-F]{7,64}")


def _revision_file() -> Path:
    return Path(__file__).resolve().parents[3] / "REVISION"


def _release_name() -> str:
    configured = get_settings().sentry_release
    if configured:
        return configured
    try:
        text = _revision_file().read_text(encoding="utf-8").strip()
    except OSError:
        return ""
    return text if _REVISION_SHA.fullmatch(text) else ""


def _redact_text(value: str) -> str:
    return _SECRET_ASSIGNMENT.sub(r"\1=[redacted]", value)


def _scrub_tree(value):
    if isinstance(value, dict):
        for key in list(value.keys()):
            if key == "id":
                continue
            if isinstance(key, str) and _SENSITIVE_KEY.search(key):
                value[key] = "[redacted]"
            else:
                value[key] = _scrub_tree(value[key])
        return value
    if isinstance(value, list):
        return [_scrub_tree(item) for item in value]
    if isinstance(value, str):
        return _redact_text(value)
    return value


def _scrub_headers(headers):
    if isinstance(headers, dict):
        cleaned = {}
        for key, value in headers.items():
            if isinstance(key, str) and _SENSITIVE_KEY.search(key):
                cleaned[key] = "[redacted]"
            else:
                cleaned[key] = _redact_text(value) if isinstance(value, str) else value
        return cleaned
    if isinstance(headers, list):
        scrubbed = []
        for item in headers:
            sensitive = (
                isinstance(item, (list, tuple))
                and len(item) == 2
                and isinstance(item[0], str)
                and _SENSITIVE_KEY.search(item[0])
            )
            if sensitive:
                scrubbed.append([item[0], "[redacted]"])
            else:
                scrubbed.append(_scrub_tree(copy.deepcopy(item)))
        return scrubbed
    return headers


def scrub_sentry_event(event, _hint):
    """Drop cookies, credentials, and query strings before an event leaves the process."""
    try:
        if not isinstance(event, dict):
            return None
        cleaned = copy.deepcopy(event)
        request = cleaned.get("request")
        if isinstance(request, dict):
            url = request.get("url")
            if isinstance(url, str):
                request["url"] = url.split("?", 1)[0]
            request["query_string"] = ""
            if "headers" in request:
                request["headers"] = _scrub_headers(request.get("headers"))
            request.pop("cookies", None)
            request.pop("data", None)
            request.pop("env", None)
        user = cleaned.get("user")
        if isinstance(user, dict):
            user_id = user.get("id")
            cleaned["user"] = {"id": user_id} if user_id is not None else {}
        return _scrub_tree(cleaned)
    except Exception:
        logger.warning("Sentry event scrubber failed; the event was dropped")
        return None


def _integrations(capture_logged_errors: bool):
    from sentry_sdk.integrations.logging import LoggingIntegration

    integrations = [
        LoggingIntegration(
            level=logging.WARNING,
            event_level=logging.ERROR if capture_logged_errors else None,
            sentry_logs_level=None,
        )
    ]
    if capture_logged_errors:
        from sentry_sdk.integrations.excepthook import ExcepthookIntegration

        integrations.append(ExcepthookIntegration())
    return integrations


def init_error_tracking(*, capture_logged_errors: bool = False) -> bool:
    """Enable Sentry when SENTRY_DSN is set. An empty DSN keeps local and CI silent."""
    dsn = get_settings().sentry_dsn
    if not dsn:
        return False
    try:
        import sentry_sdk

        options = {
            "dsn": dsn,
            "send_default_pii": False,
            "include_local_variables": False,
            "max_request_body_size": "never",
            "traces_sample_rate": 0.0,
            "default_integrations": False,
            "before_send": scrub_sentry_event,
            "integrations": _integrations(capture_logged_errors),
        }
        environment = get_settings().sentry_environment
        if environment:
            options["environment"] = environment
        release = _release_name()
        if release:
            options["release"] = release
        sentry_sdk.init(**options)
    except Exception:
        logger.warning("Sentry initialization failed; error tracking stays disabled")
        return False
    return True


def error_context(request: Request) -> dict:
    route = request.scope.get("route")
    route_path = getattr(route, "path", None) or request.url.path
    user_id = None
    stage = "unknown"
    try:
        with SessionLocal() as db:
            user = get_optional_user(request, db)
            if user is not None:
                user_id = user.id
            phase = get_phase_status(db)
            stage = phase.active_phase or "none"
    except Exception:
        logger.warning("error tracking context lookup failed")
    return {"route": route_path, "user_id": user_id, "stage": stage}


def _capture(context: dict, *, exc: BaseException | None = None, message: str | None = None) -> None:
    if not get_settings().sentry_dsn:
        return
    import sentry_sdk

    with sentry_sdk.new_scope() as scope:
        scope.set_tag("route", context["route"])
        scope.set_tag("stage", context["stage"])
        if context["user_id"] is not None:
            scope.set_user({"id": str(context["user_id"])})
        if exc is not None:
            sentry_sdk.capture_exception(exc)
        elif message:
            sentry_sdk.capture_message(message, level="error")


def report_exception(request: Request, exc: BaseException) -> None:
    if not get_settings().sentry_dsn:
        return
    _capture(error_context(request), exc=exc)


def report_http_status(request: Request, status_code: int) -> None:
    if not get_settings().sentry_dsn:
        return
    context = error_context(request)
    _capture(context, message=f"HTTP {status_code} {context['route']}")


async def observe_server_errors(request: Request, call_next):
    try:
        response = await call_next(request)
    except Exception as exc:
        record_http_response(request.url.path, 500)
        report_exception(request, exc)
        raise
    record_http_response(request.url.path, response.status_code)
    if response.status_code >= 500:
        report_http_status(request, response.status_code)
    return response
