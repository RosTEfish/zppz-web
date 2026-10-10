from __future__ import annotations

from pathlib import Path
import sys
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import publish_preview_player as publisher  # noqa: E402


def test_required_object_keys_cover_gpl_and_player_files():
    keys = publisher.required_object_keys(
        "majdata/v1",
        {"files": {"Build.wasm": {}, "Build.data": {}}},
    )
    assert keys == [
        "majdata/v1/Build.wasm",
        "majdata/v1/Build.data",
        "majdata/v1/player.html",
        "majdata/v1/player-bridge.js",
        "majdata/v1/THIRD_PARTY_NOTICES.txt",
        "majdata/v1/LICENSE",
        "majdata/v1/corresponding-source.zip",
        "majdata/v1/majdata-build.json",
    ]


def test_all_objects_present_requires_every_key():
    client = MagicMock()
    with patch.object(publisher, "head_object", side_effect=[object(), None]):
        assert publisher.all_objects_present(client, "bucket", ["a", "b"]) is False
    with patch.object(publisher, "head_object", side_effect=[object(), object()]):
        assert publisher.all_objects_present(client, "bucket", ["a", "b"]) is True


def test_download_retries_transient_timeouts(tmp_path: Path):
    target = tmp_path / "artifact.bin"
    payload = b"player-bytes"
    responses = [
        TimeoutError("slow"),
        TimeoutError("still slow"),
        _FakeResponse(payload),
    ]

    def fake_urlopen(request, timeout=0):
        del request, timeout
        result = responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    with (
        patch.object(publisher, "DOWNLOAD_BACKOFF_SECONDS", (0, 0, 0)),
        patch.object(publisher, "urlopen", side_effect=fake_urlopen),
    ):
        publisher.download("https://example.test/file.bin", target)

    assert target.read_bytes() == payload


def test_download_gives_up_after_retries(tmp_path: Path):
    target = tmp_path / "artifact.bin"
    with (
        patch.object(publisher, "DOWNLOAD_ATTEMPTS", 2),
        patch.object(publisher, "DOWNLOAD_BACKOFF_SECONDS", (0,)),
        patch.object(publisher, "urlopen", side_effect=TimeoutError("nope")),
    ):
        with pytest.raises(RuntimeError, match="failed to download"):
            publisher.download("https://example.test/file.bin", target)
    assert not target.exists()


class _FakeResponse:
    def __init__(self, payload: bytes):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        del exc_type, exc, tb
        return False

    def read(self, size: int = -1) -> bytes:
        del size
        data = self._payload
        self._payload = b""
        return data
