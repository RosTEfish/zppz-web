from __future__ import annotations

from pathlib import Path
import sys
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import publish_preview_player as publisher  # noqa: E402


def test_required_object_keys_prefix_relative_paths():
    keys = publisher.required_object_keys(
        "miaview/v1",
        ["sdk/index.mjs", "renderer/index.html", "miaview-build.json"],
    )
    assert keys == [
        "miaview/v1/sdk/index.mjs",
        "miaview/v1/renderer/index.html",
        "miaview/v1/miaview-build.json",
    ]


def test_marker_object_keys_cover_sdk_renderer_and_inventory():
    keys = publisher.marker_object_keys("miaview/v1")
    assert "miaview/v1/sdk/index.mjs" in keys
    assert "miaview/v1/renderer/index.html" in keys
    assert "miaview/v1/renderer/miacode-preview.wasm" in keys
    assert "miaview/v1/miaview-build.json" in keys
    assert "miaview/v1/object-inventory.json" in keys


def test_content_type_for_common_miaview_assets():
    assert "javascript" in publisher.content_type_for("sdk/index.mjs")
    assert publisher.content_type_for("renderer/miacode-preview.wasm") == "application/wasm"
    assert "html" in publisher.content_type_for("renderer/index.html")
    assert publisher.content_type_for("renderer/sfx/tap.wav") == "audio/wav"


def test_all_objects_present_requires_every_key():
    client = MagicMock()
    with patch.object(publisher, "head_object", side_effect=[object(), None]):
        assert publisher.all_objects_present(client, "bucket", ["a", "b"]) is False
    with patch.object(publisher, "head_object", side_effect=[object(), object()]):
        assert publisher.all_objects_present(client, "bucket", ["a", "b"]) is True


def test_iter_publish_files_requires_sdk_and_renderer(tmp_path: Path):
    with pytest.raises(RuntimeError, match="sdk/"):
        publisher.iter_publish_files(tmp_path)

    (tmp_path / "sdk").mkdir()
    (tmp_path / "sdk" / "index.mjs").write_text("export {}\n", encoding="utf-8")
    (tmp_path / "renderer").mkdir()
    (tmp_path / "renderer" / "index.html").write_text("<html></html>\n", encoding="utf-8")
    (tmp_path / "backend").mkdir()
    (tmp_path / "backend" / "log.mjs").write_text("export {}\n", encoding="utf-8")

    files = publisher.iter_publish_files(tmp_path)
    relatives = [publisher.relative_publish_path(tmp_path, path) for path in files]
    assert relatives == ["sdk/index.mjs", "renderer/index.html"]


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
