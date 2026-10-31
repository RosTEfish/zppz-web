from __future__ import annotations

import json
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = REPOSITORY_ROOT / "preview-player" / "miaview-build.json"


def test_miaview_build_manifest_pins_repository_and_artifact() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    assert manifest["repository"] == "Team-MiaCode/MiaView_Web"
    assert manifest["artifact_name"] == "miaview-preview"
    assert manifest["workflow_name"] == "Web preview"
    assert len(manifest["commit"]) == 40
    assert manifest["version"].startswith("miaview-")
    assert manifest["commit"].startswith(manifest["version"].removeprefix("miaview-"))
