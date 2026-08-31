import logging
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.db.bootstrap import seed_defaults
from app.db.session import Base, SessionLocal, engine
from app.main import app


@pytest.fixture(autouse=True)
def reset_runtime_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed_defaults(db)


def test_slow_request_log_uses_normalized_route_and_omits_query(caplog):
    settings = get_settings()
    original_threshold = settings.slow_request_ms
    settings.slow_request_ms = 0
    try:
        with caplog.at_level(logging.WARNING, logger="app.requests"):
            with TestClient(app) as client:
                response = client.get("/health?token=must-not-be-logged")
        assert response.status_code == 200
        messages = [record.getMessage() for record in caplog.records if record.name == "app.requests"]
        assert any("route=/health" in message for message in messages)
        assert all("must-not-be-logged" not in message for message in messages)
    finally:
        settings.slow_request_ms = original_threshold


def test_frontend_routes_and_public_cache_headers():
    with TestClient(app) as client:
        index = client.get("/")
        assert index.status_code == 200
        assert index.headers["cache-control"] == "public, max-age=0, s-maxage=60, stale-while-revalidate=300"

        robots = client.get("/robots.txt")
        assert robots.status_code == 200
        assert robots.headers["content-type"].startswith("text/plain")
        assert "<!doctype" not in robots.text.lower()

        llms = client.get("/llms.txt")
        assert llms.status_code == 200
        assert llms.headers["content-type"].startswith("text/plain")
        assert llms.text.startswith("# ")
        assert "<!doctype" not in llms.text.lower()

        unknown_route = client.get("/client-side-route")
        assert unknown_route.status_code == 200
        assert "<!doctype" in unknown_route.text.lower()

        phases = client.get("/api/v1/event/phases")
        availability = client.get("/api/v1/guess-game/availability")
        current_event = client.get("/api/v1/events/current")
        expected = "public, max-age=30, s-maxage=30, stale-while-revalidate=60"
        assert current_event.headers["cache-control"] == expected
        assert phases.headers["cache-control"] == expected
        assert availability.headers["cache-control"] == expected


def test_bootstrap_includes_phases_and_availability():
    with TestClient(app) as client:
        response = client.get("/api/v1/bootstrap")
        assert response.status_code == 200
        payload = response.json()
        assert "phases" in payload
        assert "guess_availability" in payload
        assert "capabilities" in payload["phases"]
        assert "available" in payload["guess_availability"]


def test_bootstrap_cache_policy_varies_with_session():
    with TestClient(app) as client:
        anonymous = client.get("/api/v1/bootstrap")
        assert anonymous.headers["cache-control"] == "public, max-age=0, s-maxage=30, stale-while-revalidate=60"
        assert "Cookie" in anonymous.headers["vary"].split(", ")

        registration = client.post(
            "/api/v1/auth/register",
            json={
                "user_code": f"cache-{uuid4().hex[:10]}",
                "qq_id": uuid4().hex[:8],
                "password": "cache-password",
                "identity": "audience",
            },
        )
        assert registration.status_code == 201

        authenticated = client.get("/api/v1/bootstrap")
        assert authenticated.headers["cache-control"] == "private, no-store"
        assert "Cookie" in authenticated.headers["vary"].split(", ")
