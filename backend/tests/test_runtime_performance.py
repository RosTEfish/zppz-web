import logging

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app


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
