import json
import shutil
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select

from app.core.config import get_settings
from app.db.bootstrap import seed_defaults
from app.db.session import Base, SessionLocal, engine
from app.main import app
from app.models import (
    Event,
    GuessChart,
    Role,
    Song,
    Submission,
    User,
    WebhookDelivery,
    WebhookEndpoint,
    WebhookEvent,
    WebhookIntegration,
    WebhookSystemState,
)
from app.modules.webhooks import service as webhook_service


@pytest.fixture(autouse=True)
def reset_webhook_data():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed_defaults(db)
        admin = db.scalar(select(User).where(User.user_code == "admin"))
        owner_role = db.scalar(select(Role).where(Role.name == "owner"))
        admin.roles.append(owner_role)
        db.commit()
    settings = get_settings()
    shutil.rmtree(settings.data_dir / "webhook-events", ignore_errors=True)
    shutil.rmtree(settings.assets_dir / "guess-covers", ignore_errors=True)
    (settings.assets_dir / "guess-covers").mkdir(parents=True, exist_ok=True)


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def login_owner(client: TestClient) -> None:
    response = client.post("/api/v1/auth/login", json={"user_code": "admin", "password": "change-me-please"})
    assert response.status_code == 200, response.text


def register_endpoint(client: TestClient, monkeypatch, name: str, url: str) -> tuple[str, str]:
    login_owner(client)
    credentials = client.post("/api/v1/admin/webhook-integrations", json={"name": name})
    assert credentials.status_code == 201, credentials.text
    token = credentials.json()["integration_token"]
    integration_id = credentials.json()["integration_id"]
    monkeypatch.setattr(webhook_service, "validate_callback_url", lambda value: value)
    monkeypatch.setattr(webhook_service, "verify_endpoint", lambda integration, callback_url: None)
    registered = client.put(
        "/api/v1/integrations/webhook-subscription",
        headers={"Authorization": f"Bearer {token}"},
        json={"callback_url": url, "events": ["chart.published", "chart.updated"], "schema_version": 1},
    )
    assert registered.status_code == 200, registered.text
    return integration_id, registered.json()["id"]


def create_chart(*, track: str = "j", title: str = "Webhook Song") -> tuple[int, int]:
    settings = get_settings()
    cover = settings.assets_dir / "guess-covers" / f"{track}-cover.png"
    Image.new("RGB", (96, 64), "#2374d8").save(cover)
    with SessionLocal() as db:
        event = db.scalar(select(Event).where(Event.is_current.is_(True)))
        event.settings.phase_mode = "manual"
        event.settings.manual_phase = "submission_1"
        user = db.scalar(select(User).where(User.user_code == "admin"))
        song = Song(event_id=event.id, submitted_by_id=user.id, song_name=title, artist="Artist", song_type="A")
        db.add(song)
        db.flush()
        submission = Submission(
            event_id=event.id,
            user_id=user.id,
            source_song_id=song.id,
            source_kind="self",
            track=track,
            file_name="chart.zip",
            storage_path=f"events/{event.id}/submissions/source-v1.zip",
            public_storage_path=f"events/{event.id}/submissions/public-v1.zip",
            public_package_status="ready",
            file_size=123,
        )
        db.add(submission)
        db.flush()
        chart = GuessChart(
            event_id=event.id,
            title=title,
            author="Artist",
            designer="Designer",
            level="13+",
            lane=track,
            guess_group_key="webhook-song",
            source_submission_type=track,
            source_submission_id=submission.id,
            source_level_slot="4",
            cover_path=f"/api/v1/assets/guess-covers/{cover.name}",
            storage_path=submission.storage_path,
            is_self_selected=True,
            plays=0,
        )
        db.add(chart)
        db.commit()
        return submission.id, chart.id


def test_owner_can_issue_credentials_and_bot_self_registers(client: TestClient, monkeypatch):
    integration_id, endpoint_id = register_endpoint(client, monkeypatch, "Main bot", "https://bot.example.com/webhooks/zppz")
    rows = client.get("/api/v1/admin/webhook-integrations")
    assert rows.status_code == 200
    row = next(item for item in rows.json() if item["id"] == integration_id)
    assert row["endpoint"]["id"] == endpoint_id
    assert row["endpoint"]["status"] == "active"
    assert row["endpoint"]["events"] == ["chart.published", "chart.updated"]
    assert "integration_token" not in row
    assert "webhook_secret" not in row


def test_multiple_endpoints_receive_publication_update_and_cover(client: TestClient, monkeypatch):
    _, first_endpoint = register_endpoint(client, monkeypatch, "Bot one", "https://one.example.com/webhooks/zppz")
    _, second_endpoint = register_endpoint(client, monkeypatch, "Bot two", "https://two.example.com/webhooks/zppz")
    submission_id, chart_id = create_chart()

    assert webhook_service.materialize_publication_events() == 1
    with SessionLocal() as db:
        published = db.scalars(select(WebhookEvent).order_by(WebhookEvent.created_at)).all()
        assert len(published) == 1
        assert published[0].event_type == "chart.published"
        deliveries = db.scalars(select(WebhookDelivery)).all()
        assert {row.endpoint_id for row in deliveries} == {first_endpoint, second_endpoint}
        endpoint = db.get(WebhookEndpoint, first_endpoint)
        payload = webhook_service._delivery_payload(db, published[0], endpoint)
        cover = payload["chart_set"]["cover"]
        assert (cover["width"], cover["height"]) == (96, 64)
        assert cover["content_type"] == "image/png"
        cover_url = cover["url"].replace(get_settings().public_base_url, "")

    downloaded = client.get(cover_url)
    assert downloaded.status_code == 200
    assert downloaded.headers["content-type"].startswith("image/png")
    assert len(downloaded.content) == cover["size_bytes"]
    tampered = cover_url[:-1] + ("0" if cover_url[-1] != "0" else "1")
    assert client.get(tampered).status_code == 403

    with SessionLocal() as db:
        chart = db.get(GuessChart, chart_id)
        chart.level = "14"
        db.commit()
    assert webhook_service.materialize_publication_events() == 1
    with SessionLocal() as db:
        events = db.scalars(select(WebhookEvent).order_by(WebhookEvent.created_at)).all()
        assert [row.event_type for row in events] == ["chart.published", "chart.updated"]
        update_payload = json.loads(events[-1].payload_json)
        assert update_payload["source"]["revision"] == 2
        assert update_payload["changes"]["levels_changed"][0]["before"]["level"] == "13+"

        submission = db.get(Submission, submission_id)
        submission.storage_path = "events/1/submissions/source-v2.zip"
        db.commit()
    assert webhook_service.materialize_publication_events() == 1
    assert webhook_service.materialize_publication_events() == 0


def test_normal_chart_waits_until_public_phase():
    create_chart(track="normal")
    assert webhook_service.materialize_publication_events() == 0
    with SessionLocal() as db:
        event = db.scalar(select(Event).where(Event.is_current.is_(True)))
        event.settings.manual_phase = "guess"
        db.commit()
    assert webhook_service.materialize_publication_events() == 1


def test_prepare_baseline_runs_only_once_and_does_not_swallow_future_publications():
    with SessionLocal() as db:
        assert webhook_service.seed_publication_baseline(db) == 0
        assert db.get(WebhookSystemState, 1) is not None
    create_chart()
    with SessionLocal() as db:
        assert webhook_service.seed_publication_baseline(db) == 0
    assert webhook_service.materialize_publication_events() == 1


def test_delivery_signs_raw_body_and_retries_server_errors(client: TestClient, monkeypatch):
    integration_id, endpoint_id = register_endpoint(
        client, monkeypatch, "Delivery bot", "https://delivery.example.com/webhooks/zppz"
    )
    create_chart()
    assert webhook_service.materialize_publication_events() == 1
    with SessionLocal() as db:
        delivery = db.scalar(select(WebhookDelivery).where(WebhookDelivery.endpoint_id == endpoint_id))
        delivery.status = "delivering"
        delivery.attempts = 1
        delivery.lease_until = datetime.utcnow() + timedelta(seconds=60)
        delivery_id = delivery.id
        db.commit()

    calls: list[tuple[bytes, dict[str, str]]] = []

    class FakeResponse:
        status_code = 500

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def post(self, _url, *, content, headers):
            calls.append((content, headers))
            return FakeResponse()

    monkeypatch.setattr(webhook_service, "validate_callback_url", lambda value: value)
    monkeypatch.setattr(webhook_service.httpx, "Client", FakeClient)
    webhook_service.process_delivery(delivery_id)

    with SessionLocal() as db:
        delivery = db.get(WebhookDelivery, delivery_id)
        integration = db.get(WebhookIntegration, integration_id)
        assert delivery.status == "retrying"
        assert delivery.response_status == 500
        assert delivery.next_attempt_at > datetime.utcnow()
        body, headers = calls[0]
        timestamp = int(headers["X-ZPPZ-Timestamp"])
        expected = webhook_service.sign_payload(webhook_service.derive_webhook_secret(integration), timestamp, body)
        assert headers["X-ZPPZ-Signature"] == f"sha256={expected}"
        assert json.loads(body)["event_type"] == "chart.published"


def test_callback_validation_rejects_private_and_non_https(monkeypatch):
    monkeypatch.setattr(webhook_service.socket, "getaddrinfo", lambda *args, **kwargs: [(None, None, None, None, ("127.0.0.1", 443))])
    with pytest.raises(Exception):
        webhook_service.validate_callback_url("https://bot.example.com/webhooks")
    with pytest.raises(Exception):
        webhook_service.validate_callback_url("http://bot.example.com/webhooks")
