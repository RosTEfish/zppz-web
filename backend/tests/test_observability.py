import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from starlette.requests import Request

from app.db.bootstrap import seed_defaults
from app.db.session import Base, SessionLocal, engine
from app.main import app
from app.models import (
    Event,
    SubmissionProcessingJob,
    User,
    WebhookDelivery,
    WebhookEndpoint,
    WebhookEvent,
    WebhookIntegration,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def reset_observability_database(monkeypatch):
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    monkeypatch.delenv("SENTRY_ENVIRONMENT", raising=False)
    monkeypatch.delenv("SENTRY_RELEASE", raising=False)
    monkeypatch.delenv("METRICS_TOKEN", raising=False)
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed_defaults(db)
    try:
        from app.core.metrics import reset_http_response_counts
    except ImportError:
        yield
        return
    reset_http_response_counts()
    yield
    reset_http_response_counts()


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def _request(path: str, *, query: bytes = b"", cookie: str | None = None, route: str | None = None) -> Request:
    headers = []
    if cookie is not None:
        headers.append((b"cookie", f"zppz_session={cookie}".encode()))
    request = Request(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "query_string": query,
            "headers": headers,
            "client": ("127.0.0.1", 50000),
            "server": ("testserver", 80),
        }
    )
    if route is not None:
        request.scope["route"] = SimpleNamespace(path=route)
    return request


def _login(client: TestClient, user_code: str, password: str) -> None:
    response = client.post("/api/v1/auth/login", json={"user_code": user_code, "password": password})
    assert response.status_code == 200, response.text


def _set_stage(stage: str) -> int:
    with SessionLocal() as db:
        event = db.scalar(select(Event).where(Event.is_current.is_(True)))
        assert event is not None and event.settings is not None
        event.settings.phase_mode = "manual"
        event.settings.manual_phase = stage
        admin = db.scalar(select(User).where(User.user_code == "admin"))
        assert admin is not None
        db.commit()
        return admin.id


def _seed_queue_and_webhooks() -> None:
    with SessionLocal() as db:
        event = db.scalar(select(Event).where(Event.is_current.is_(True)))
        admin = db.scalar(select(User).where(User.user_code == "admin"))
        assert event is not None and admin is not None
        jobs = [
            ("queued", None),
            ("queued", None),
            ("processing", None),
            ("failed", None),
            ("failed", datetime.utcnow()),
            ("completed", None),
        ]
        for index, (status, superseded_at) in enumerate(jobs):
            db.add(
                SubmissionProcessingJob(
                    id=f"job-{index}",
                    event_id=event.id,
                    user_id=admin.id,
                    source_storage_path=f"pending/{index}.zip",
                    status=status,
                    stage="uploaded",
                    superseded_at=superseded_at,
                )
            )
        integration = WebhookIntegration(
            id=uuid4().hex,
            name="bot",
            token_hash="a" * 64,
            token_prefix="zppz_whk_test",
        )
        db.add(integration)
        db.flush()
        endpoint = WebhookEndpoint(id=uuid4().hex, integration_id=integration.id, status="failing")
        db.add(endpoint)
        db.flush()
        for index, status in enumerate(("pending", "pending", "retrying", "delivering", "failed", "delivered")):
            webhook_event = WebhookEvent(
                id=uuid4().hex,
                event_id=event.id,
                event_type="chart.published",
                source_type="normal",
                source_id=index + 1,
                revision=1,
                payload_json="{}",
            )
            db.add(webhook_event)
            db.flush()
            db.add(WebhookDelivery(webhook_event_id=webhook_event.id, endpoint_id=endpoint.id, status=status))
        db.commit()


def test_error_tracking_stays_quiet_without_dsn(monkeypatch):
    from app.core.observability import init_error_tracking, report_exception

    def forbidden(*_args, **_kwargs):
        raise AssertionError("Sentry was called without a DSN")

    monkeypatch.setattr("sentry_sdk.init", forbidden)
    monkeypatch.setattr("sentry_sdk.capture_exception", forbidden)
    assert init_error_tracking() is False
    report_exception(_request("/health"), RuntimeError("token=super-secret"))


def test_error_tracking_init_is_env_gated_and_scrubs(monkeypatch, tmp_path):
    from sentry_sdk.integrations.excepthook import ExcepthookIntegration
    from sentry_sdk.integrations.logging import LoggingIntegration

    from app.core.observability import init_error_tracking, scrub_sentry_event

    revision = tmp_path / "REVISION"
    revision.write_text("abc123def456\n", encoding="utf-8")
    monkeypatch.setattr("app.core.observability._revision_file", lambda: revision)
    monkeypatch.setenv("SENTRY_DSN", "https://public@example.ingest.sentry.io/1")
    monkeypatch.setenv("SENTRY_ENVIRONMENT", "production")
    monkeypatch.delenv("SENTRY_RELEASE", raising=False)
    recorded = {}

    def fake_init(**kwargs):
        recorded.update(kwargs)

    monkeypatch.setattr("sentry_sdk.init", fake_init)
    assert init_error_tracking(capture_logged_errors=True) is True
    assert recorded["dsn"] == "https://public@example.ingest.sentry.io/1"
    assert recorded["environment"] == "production"
    assert recorded["release"] == "abc123def456"
    assert recorded["send_default_pii"] is False
    assert recorded["include_local_variables"] is False
    assert recorded["max_request_body_size"] == "never"
    assert recorded["traces_sample_rate"] == 0.0
    assert recorded["default_integrations"] is False
    assert recorded["before_send"] is scrub_sentry_event
    assert any(isinstance(item, ExcepthookIntegration) for item in recorded["integrations"])
    logging_integration = next(item for item in recorded["integrations"] if isinstance(item, LoggingIntegration))
    assert logging_integration._handler is not None
    assert logging_integration._sentry_logs_handler is None

    monkeypatch.setenv("SENTRY_RELEASE", "release-from-env")
    recorded.clear()
    assert init_error_tracking() is True
    assert recorded["release"] == "release-from-env"
    logging_integration = next(item for item in recorded["integrations"] if isinstance(item, LoggingIntegration))
    assert logging_integration._handler is None
    assert not any(isinstance(item, ExcepthookIntegration) for item in recorded["integrations"])

    def exploding_init(**_kwargs):
        raise RuntimeError("dsn=super-secret could not start")

    monkeypatch.setattr("sentry_sdk.init", exploding_init)
    assert init_error_tracking() is False


def test_sentry_event_scrubber_drops_secrets_and_keeps_ids():
    from app.core.observability import scrub_sentry_event

    event = {
        "request": {
            "url": "https://www.przppz.club/api/v1/submissions/1?token=super-secret",
            "query_string": "token=super-secret",
            "headers": {
                "Authorization": "Bearer super-secret",
                "Cookie": "zppz_session=super-secret",
                "User-Agent": "pytest",
            },
            "cookies": {"zppz_session": "super-secret"},
            "data": {"password": "super-secret"},
        },
        "user": {"id": "7", "email": "admin@example.com", "ip_address": "203.0.113.8", "username": "admin"},
        "extra": {"dsn": "https://super-secret@sentry.example/1", "route": "/api/v1/submissions/{submission_id}"},
        "exception": {"values": [{"type": "RuntimeError", "value": "failed token=super-secret"}]},
        "tags": {"stage": "guess", "route": "/api/v1/submissions/{submission_id}"},
    }
    scrubbed = scrub_sentry_event(event, {})
    assert scrubbed is not None
    blob = json.dumps(scrubbed)
    assert "super-secret" not in blob
    assert "admin@example.com" not in blob
    assert "203.0.113.8" not in blob
    assert scrubbed["user"] == {"id": "7"}
    assert scrubbed["tags"]["stage"] == "guess"
    assert scrubbed["request"]["url"] == "https://www.przppz.club/api/v1/submissions/1"
    assert scrubbed["extra"]["route"] == "/api/v1/submissions/{submission_id}"
    assert "cookies" not in scrubbed["request"]
    assert "data" not in scrubbed["request"]


def test_exception_report_includes_route_user_and_stage(monkeypatch, client, caplog):
    from app.core.observability import error_context, report_exception

    admin_id = _set_stage("guess")
    _login(client, "admin", "change-me-please")
    cookie = client.cookies.get("zppz_session")
    assert cookie
    request = _request(
        "/api/v1/submissions/1",
        query=b"token=super-secret",
        cookie=cookie,
        route="/api/v1/submissions/{submission_id}",
    )
    context = error_context(request)
    assert context == {
        "route": "/api/v1/submissions/{submission_id}",
        "user_id": admin_id,
        "stage": "guess",
    }
    assert "super-secret" not in json.dumps(context)

    captured = {}

    class Scope:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def set_tag(self, key, value):
            captured.setdefault("tags", {})[key] = value

        def set_user(self, user):
            captured["user"] = dict(user)

    monkeypatch.setenv("SENTRY_DSN", "https://public@example.ingest.sentry.io/1")
    monkeypatch.setattr("sentry_sdk.new_scope", lambda: Scope())
    monkeypatch.setattr("sentry_sdk.capture_exception", lambda exc: captured.setdefault("exception", exc))
    with caplog.at_level(logging.WARNING):
        report_exception(request, RuntimeError("token=super-secret"))
    assert captured["tags"] == {"route": "/api/v1/submissions/{submission_id}", "stage": "guess"}
    assert captured["user"] == {"id": str(admin_id)}
    assert isinstance(captured["exception"], RuntimeError)
    assert "super-secret" not in json.dumps({"tags": captured["tags"], "user": captured["user"]})
    assert "super-secret" not in caplog.text


def test_middleware_counts_contest_5xx():
    from app.core.metrics import http_response_counts
    from app.core.observability import observe_server_errors

    async def explode(_request):
        raise RuntimeError("boom")

    vote = _request("/api/v1/guess-game/vote", query=b"token=super-secret")
    with pytest.raises(RuntimeError):
        asyncio.run(observe_server_errors(vote, explode))

    class Response:
        status_code = 500

    async def http_500(_request):
        return Response()

    submission = _request("/api/v1/submissions/9")
    asyncio.run(observe_server_errors(submission, http_500))

    async def ok(_request):
        return SimpleNamespace(status_code=200)

    asyncio.run(observe_server_errors(_request("/api/v1/guess-game/vote"), ok))
    asyncio.run(observe_server_errors(_request("/health"), ok))
    counts = http_response_counts()
    assert counts[("vote", "5xx")] == 1
    assert counts[("vote", "other")] == 1
    assert counts[("submission", "5xx")] == 1
    assert counts[("submission", "other")] == 0


def test_middleware_report_hooks_see_route_context(monkeypatch):
    from app.core.observability import observe_server_errors

    seen = []
    monkeypatch.setattr(
        "app.core.observability.report_exception",
        lambda request, exc: seen.append(("exception", request.url.path, type(exc).__name__)),
    )
    monkeypatch.setattr(
        "app.core.observability.report_http_status",
        lambda request, status_code: seen.append(("status", request.url.path, status_code)),
    )

    async def explode(_request):
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        asyncio.run(observe_server_errors(_request("/api/v1/submissions/1", query=b"token=super-secret"), explode))

    async def http_500(_request):
        return SimpleNamespace(status_code=500)

    asyncio.run(observe_server_errors(_request("/api/v1/guess-game/vote"), http_500))
    async def ok(_request):
        return SimpleNamespace(status_code=201)

    asyncio.run(observe_server_errors(_request("/api/v1/submissions"), ok))
    assert seen == [
        ("exception", "/api/v1/submissions/1", "RuntimeError"),
        ("status", "/api/v1/guess-game/vote", 500),
    ]
    assert all("super-secret" not in json.dumps(item) for item in seen)


def test_startup_initializes_error_tracking(monkeypatch):
    seen = []
    monkeypatch.setattr("app.main.init_error_tracking", lambda **kwargs: seen.append(kwargs) or False)
    with TestClient(app):
        pass
    assert seen == [{}]


def test_metrics_require_admin_or_bearer_token(monkeypatch, client):
    anonymous = client.get("/api/v1/admin/metrics")
    assert anonymous.status_code == 401

    registered = client.post(
        "/api/v1/auth/register",
        json={"user_code": "player-obs", "qq_id": "10001", "password": "secret123", "identity": "participant"},
    )
    assert registered.status_code == 201, registered.text
    forbidden = client.get("/api/v1/admin/metrics")
    assert forbidden.status_code == 403

    logged_out = client.post("/api/v1/auth/logout")
    assert logged_out.status_code == 200
    monkeypatch.setenv("METRICS_TOKEN", "metrics-token-value")
    query = client.get("/api/v1/admin/metrics?access_token=metrics-token-value")
    assert query.status_code == 401
    wrong = client.get("/api/v1/admin/metrics", headers={"Authorization": "Bearer wrong"})
    assert wrong.status_code == 401
    allowed = client.get("/api/v1/admin/metrics", headers={"Authorization": "Bearer metrics-token-value"})
    assert allowed.status_code == 200, allowed.text
    assert "metrics-token-value" not in allowed.text
    assert allowed.headers["cache-control"] == "no-store"
    assert "version=0.0.4" in allowed.headers["content-type"]
    assert 'zppz_submission_jobs{status="queued"} 0' in allowed.text
    assert 'zppz_webhook_deliveries{status="failed"} 0' in allowed.text


def test_metrics_expose_queue_depth_webhook_failures_and_http_counters(client):
    from app.core.metrics import record_http_response

    _set_stage("guess")
    _seed_queue_and_webhooks()
    record_http_response("/api/v1/submissions/1", 500)
    record_http_response("/api/v1/admin/submissions/1", 200)
    record_http_response("/api/v1/guess-game/vote", 503)
    record_http_response("/api/v1/guess-game/vote-quota", 500)
    _login(client, "admin", "change-me-please")
    response = client.get("/api/v1/admin/metrics")
    assert response.status_code == 200, response.text
    body = response.text
    assert 'zppz_submission_jobs{status="queued"} 2' in body
    assert 'zppz_submission_jobs{status="processing"} 1' in body
    assert 'zppz_submission_jobs{status="failed"} 1' in body
    assert 'status="completed"' not in body
    assert 'zppz_webhook_deliveries{status="pending"} 2' in body
    assert 'zppz_webhook_deliveries{status="retrying"} 1' in body
    assert 'zppz_webhook_deliveries{status="delivering"} 1' in body
    assert 'zppz_webhook_deliveries{status="failed"} 1' in body
    assert 'status="delivered"' not in body
    assert 'zppz_webhook_endpoints{status="failing"} 1' in body
    assert 'zppz_contest_stage{stage="guess"} 1' in body
    assert 'zppz_http_responses_total{area="submission",status_class="5xx"} 1' in body
    assert 'zppz_http_responses_total{area="submission",status_class="other"} 1' in body
    assert 'zppz_http_responses_total{area="vote",status_class="5xx"} 1' in body
    assert 'zppz_http_responses_total{area="vote",status_class="other"} 0' in body
    assert "# TYPE zppz_submission_jobs gauge" in body
    assert "# TYPE zppz_http_responses_total counter" in body


def test_contest_signal_log_warns_when_failures_exist(caplog):
    from app.core.metrics import emit_contest_signals

    _set_stage("submission_1")
    with caplog.at_level(logging.INFO, logger="app.observability"):
        emit_contest_signals()
    quiet = [record for record in caplog.records if record.name == "app.observability"]
    assert len(quiet) == 1
    assert quiet[0].levelno == logging.INFO
    payload = json.loads(quiet[0].getMessage().split(" ", 1)[1])
    assert payload["event"] == "contest_signals"
    assert payload["stage"] == "submission_1"
    assert payload["submission_jobs"] == {"queued": 0, "processing": 0, "failed": 0}
    assert payload["webhook_deliveries"]["failed"] == 0
    assert payload["webhook_endpoints_failing"] == 0

    caplog.clear()
    _seed_queue_and_webhooks()
    with caplog.at_level(logging.INFO, logger="app.observability"):
        emit_contest_signals()
    alert = [record for record in caplog.records if record.name == "app.observability"]
    assert len(alert) == 1
    assert alert[0].levelno == logging.WARNING
    alert_payload = json.loads(alert[0].getMessage().split(" ", 1)[1])
    assert alert_payload["submission_jobs"]["queued"] == 2
    assert alert_payload["submission_jobs"]["processing"] == 1
    assert alert_payload["submission_jobs"]["failed"] == 1
    assert alert_payload["webhook_deliveries"]["pending"] == 2
    assert alert_payload["webhook_deliveries"]["failed"] == 1
    assert alert_payload["webhook_endpoints_failing"] == 1
    assert "token" not in alert[0].getMessage()


def test_workers_opt_into_error_tracking_and_signal_logs(monkeypatch):
    import app.webhook_worker as webhook_worker
    import app.worker as worker

    monkeypatch.setattr(worker.signal, "signal", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(webhook_worker.signal, "signal", lambda *_args, **_kwargs: None)
    worker_seen = []
    signal_calls = []

    def worker_init(**kwargs):
        worker_seen.append(kwargs)
        return False

    def emit():
        signal_calls.append("emit")

    def stop_sleep(_seconds):
        worker._stopping = True

    monkeypatch.setattr(worker, "init_error_tracking", worker_init)
    monkeypatch.setattr(worker, "emit_contest_signals", emit)
    monkeypatch.setattr(worker, "cleanup_expired_upload_intents", lambda: 0)
    monkeypatch.setattr(worker, "process_next_job", lambda: False)
    monkeypatch.setattr(worker.time, "sleep", stop_sleep)
    worker._stopping = False
    try:
        assert worker.main() == 0
    finally:
        worker._stopping = False
    assert worker_seen == [{"capture_logged_errors": True}]
    assert signal_calls == ["emit"]

    signal_calls.clear()
    worker_seen.clear()

    def failing_emit():
        signal_calls.append("emit")
        raise RuntimeError("snapshot failed")

    monkeypatch.setattr(worker, "emit_contest_signals", failing_emit)
    worker._stopping = False
    try:
        assert worker.main() == 0
    finally:
        worker._stopping = False
    assert signal_calls == ["emit"]

    webhook_seen = []

    def webhook_init(**kwargs):
        webhook_seen.append(kwargs)
        return False

    def stop_webhook_sleep(_seconds):
        webhook_worker._stopping = True

    monkeypatch.setattr(webhook_worker, "init_error_tracking", webhook_init)
    monkeypatch.setattr(webhook_worker, "materialize_publication_events", lambda: None)
    monkeypatch.setattr(webhook_worker, "cleanup_expired_assets", lambda: 0)
    monkeypatch.setattr(webhook_worker, "process_next_delivery", lambda: False)
    monkeypatch.setattr(webhook_worker.time, "sleep", stop_webhook_sleep)
    webhook_worker._stopping = False
    try:
        assert webhook_worker.main() == 0
    finally:
        webhook_worker._stopping = False
    assert webhook_seen == [{"capture_logged_errors": True}]


def test_ops_notes_and_deploy_script_document_optional_observability():
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    example = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    deploy = (REPO_ROOT / "scripts" / "deploy_remote.sh").read_text(encoding="utf-8")
    assert "SENTRY_DSN" in readme
    assert "METRICS_TOKEN" in readme
    assert "/api/v1/admin/metrics" in readme
    assert "contest_signals" in readme
    assert "/opt/zppz/.env" in readme or "$DEPLOY_PATH/.env" in readme
    assert "SENTRY_DSN=" in example
    assert "METRICS_TOKEN=" in example
    assert "grep -q '^SENTRY_DSN='" in deploy
    assert "grep -q '^METRICS_TOKEN='" in deploy
    assert "SENTRY_DSN|" not in deploy
