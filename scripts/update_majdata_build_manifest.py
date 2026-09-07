#!/usr/bin/env python3
"""Refresh preview-player/majdata-build.json after a local WebGL build."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


FILES = {
    "Build.loader.js": {"content_type": "application/javascript", "compress": False},
    "Build.framework.js": {"content_type": "application/javascript", "compress": True},
    "Build.data": {"content_type": "application/octet-stream", "compress": True},
    "Build.wasm": {"content_type": "application/wasm", "compress": True},
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--build-dir", default="preview-player/Build")
    parser.add_argument("--manifest", default="preview-player/majdata-build.json")
    parser.add_argument(
        "--version",
        default="",
        help="Immutable player version directory name (required for a new pin)",
    )
    parser.add_argument(
        "--source-commit",
        default="",
        help="Fork commit that produced this WebGL build",
    )
    parser.add_argument(
        "--source-archive-url",
        default="",
        help="HTTPS URL of corresponding-source.zip (or leave empty to keep local publish)",
    )
    parser.add_argument(
        "--license-url",
        default="https://raw.githubusercontent.com/TeamMajdata/MajdataView/"
        "ad734f1272159a52cbd948c27c68cfa7cf1dc536/LICENSE",
    )
    parser.add_argument(
        "--build-base-url",
        default="",
        help="HTTPS directory containing the four Build.* files; "
        "leave empty when publishing from local preview-player/Build",
    )
    args = parser.parse_args()

    build_dir = Path(args.build_dir)
    manifest_path = Path(args.manifest)
    if not args.version:
        raise SystemExit("--version is required, e.g. majdataview-zppz-record1-webgl")

    files: dict[str, dict] = {}
    for name, meta in FILES.items():
        path = build_dir / name
        if not path.is_file():
            raise SystemExit(f"missing WebGL artifact: {path}")
        files[name] = {
            "sha256": sha256(path),
            "content_type": meta["content_type"],
            "compress": meta["compress"],
        }
        print(f"{name} {files[name]['sha256']}")

    payload = {
        "version": args.version,
        "distribution_commit": args.source_commit or "local-record-mode",
        "source_commit": args.source_commit or "local-record-mode",
        "source_archive_url": args.source_archive_url
        or "local://preview-player/corresponding-source.zip",
        "license_url": args.license_url,
        "build_base_url": args.build_base_url or "local://preview-player/Build",
        "files": files,
    }
    manifest_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"updated {manifest_path}")


if __name__ == "__main__":
    main()
