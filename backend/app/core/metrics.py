from __future__ import annotations

import hmac
import json
import logging
from dataclasses import dataclass
from threading import Lock

from fastapi import HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import get_optional_user, has_admin_access
from app.db.session import SessionLocal
from app.models import SubmissionProcessingJob, WebhookDelivery, WebhookEndpoint
from app.modules.events.phase_policy import get_phase_status


logger = logging.getLogger("app.observability")

JOB_STATUSES = ("queued", "processing", "failed")
DELIVERY_STATUSES = ("pending", "retrying", "delivering", "failed")
_HTTP_AREAS = ("submission", "vote")
_HTTP_CLASSES = ("5xx", "other")
_lock = Lock()
_counts = {(area, status_class): 0 for area in _HTTP_AREAS for status_class in _HTTP_CLASSES}


@dataclass(frozen=True)
class ContestSignals:
    stage: str
    submission_jobs: dict[str, int]
    webhook_deliveries: dict[str, int]
    webhook_endpoints_failing: int


def reset_http_response_counts() -> None:
    with _lock:
        for key in _counts:
            _counts[key] = 0


def http_response_counts() -> dict[tuple[str, str], int]:
    with _lock:
        return dict(_counts)


def _http_area(path: str) -> str | None:
    if path.startswith("/api/v1/submissions") or path.startswith("/api/v1/admin/submissions"):
        return "submission"
    if path == "/api/v1/guess-game/vote" or path.startswith("/api/v1/guess-game/vote/"):
        return "vote"
    return None


def record_http_response(path: str, status_code: int) -> None:
    area = _http_area(path)
    if area is None:
        return
    status_class = "5xx" if status_code >= 500 else "other"
    with _lock:
        _counts[(area, status_class)] += 1


def _grouped_counts(db: Session, column, statuses: tuple[str, ...], *filters) -> dict[str, int]:
    found = {status: 0 for status in statuses}
    rows = db.execute(select(column, func.count()).where(column.in_(statuses), *filters).group_by(column)).all()
    for status, count in rows:
        if status in found:
            found[str(status)] = int(count)
    return found


def collect_contest_signals(db: Session) -> ContestSignals:
    stage = "unknown"
    try:
        phase = get_phase_status(db)
        stage = phase.active_phase or "none"
    except Exception:
        logger.warning("contest stage lookup failed")
    failing = db.scalar(select(func.count()).select_from(WebhookEndpoint).where(WebhookEndpoint.status == "failing"))
    return ContestSignals(
        stage=stage,
        submission_jobs=_grouped_counts(
            db,
            SubmissionProcessingJob.status,
            JOB_STATUSES,
            SubmissionProcessingJob.superseded_at.is_(None),
        ),
        webhook_deliveries=_grouped_counts(db, WebhookDelivery.status, DELIVERY_STATUSES),
        webhook_endpoints_failing=int(failing or 0),
    )


def _label(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def _line(name: str, labels: dict[str, str], value: int) -> str:
    rendered = ",".join(f'{key}="{_label(label)}"' for key, label in labels.items())
    return f"{name}{{{rendered}}} {value}"


def render_prometheus(snapshot: ContestSignals) -> str:
    counts = http_response_counts()
    lines = [
        (
            "# HELP zppz_submission_jobs Submission processing jobs still needing attention. "
            "queued is waiting and processing is claimed by a worker."
        ),
        "# TYPE zppz_submission_jobs gauge",
    ]
    lines.extend(
        _line("zppz_submission_jobs", {"status": status}, snapshot.submission_jobs[status]) for status in JOB_STATUSES
    )
    lines.extend(
        [
            (
                "# HELP zppz_webhook_deliveries Webhook delivery backlog and terminal failures. "
                "delivering is claimed by the webhook worker."
            ),
            "# TYPE zppz_webhook_deliveries gauge",
        ]
    )
    lines.extend(
        _line("zppz_webhook_deliveries", {"status": status}, snapshot.webhook_deliveries[status])
        for status in DELIVERY_STATUSES
    )
    lines.extend(
        [
            "# HELP zppz_webhook_endpoints Webhook endpoints currently marked failing.",
            "# TYPE zppz_webhook_endpoints gauge",
            _line("zppz_webhook_endpoints", {"status": "failing"}, snapshot.webhook_endpoints_failing),
            "# HELP zppz_contest_stage Active contest phase. The sample for the current phase is 1.",
            "# TYPE zppz_contest_stage gauge",
            _line("zppz_contest_stage", {"stage": snapshot.stage}, 1),
            (
                "# HELP zppz_http_responses_total Contest path responses since this process started. "
                "status_class is 5xx or other."
            ),
            "# TYPE zppz_http_responses_total counter",
        ]
    )
    for area in _HTTP_AREAS:
        for status_class in _HTTP_CLASSES:
            lines.append(
                _line(
                    "zppz_http_responses_total",
                    {"area": area, "status_class": status_class},
                    counts[(area, status_class)],
                )
            )
    return "\n".join(lines) + "\n"


def emit_contest_signals() -> ContestSignals:
    with SessionLocal() as db:
        snapshot = collect_contest_signals(db)
    payload = {
        "event": "contest_signals",
        "stage": snapshot.stage,
        "submission_jobs": snapshot.submission_jobs,
        "webhook_deliveries": snapshot.webhook_deliveries,
        "webhook_endpoints_failing": snapshot.webhook_endpoints_failing,
    }
    alert = (
        payload["submission_jobs"]["failed"] > 0
        or payload["webhook_deliveries"]["failed"] > 0
        or payload["webhook_endpoints_failing"] > 0
    )
    logger.log(
        logging.WARNING if alert else logging.INFO,
        "contest_signals %s",
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
    )
    return snapshot


def _bearer_token(request: Request) -> str:
    scheme, _, rest = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer":
        return ""
    return rest.strip()


def require_metrics_access(request: Request, db: Session) -> None:
    """Allow a configured bearer token or an admin session. Query tokens are ignored."""
    token = get_settings().metrics_token
    presented = _bearer_token(request)
    if token and presented and hmac.compare_digest(presented, token):
        return
    user = get_optional_user(request, db)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="请先登录")
    if not has_admin_access(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="没有权限执行此操作")
