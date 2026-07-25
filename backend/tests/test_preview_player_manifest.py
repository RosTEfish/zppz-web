from __future__ import annotations

import json
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = REPOSITORY_ROOT / "preview-player" / "majdata-build.json"


def test_framework_digest_matches_raw_github_bytes() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    assert manifest["build_base_url"] == (
        "https://raw.githubusercontent.com/TeamMajdata/MajdataNet/"
        f"{manifest['distribution_commit']}/public/WebGLBuild"
    )
    assert manifest["files"]["Build.framework.js"]["sha256"] == (
        "3270d993549f8b577760731a51b00a1481a883bf2935f20e1ee8c84694a119ec"
    )
