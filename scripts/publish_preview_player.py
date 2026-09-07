from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import tempfile
from urllib.request import Request, urlopen

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError


CACHE_CONTROL = "public, max-age=31536000, immutable"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def download(url: str, target: Path) -> None:
    request = Request(url, headers={"User-Agent": "zppz-preview-publisher/1"})
    with urlopen(request, timeout=120) as response, target.open("wb") as output:
        while chunk := response.read(1024 * 1024):
            output.write(chunk)


def resolve_asset(url: str, name: str, player_dir: Path, temp_root: Path) -> Path:
    """Fetch a Build/license/source asset from HTTPS or local://preview-player/... paths."""
    target = temp_root / name
    if url.startswith("local://"):
        relative = url.removeprefix("local://")
        local_path = Path(relative)
        if not local_path.is_absolute():
            local_path = Path.cwd() / local_path
        if local_path.is_dir():
            local_path = local_path / name
        if not local_path.is_file():
            # Allow shorthand local://preview-player/Build → player_dir/Build/name
            fallback = player_dir / Path(relative).name / name
            if fallback.is_file():
                local_path = fallback
            else:
                raise RuntimeError(f"local asset missing for {name}: {url}")
        target.write_bytes(local_path.read_bytes())
        return target
    download(url, target)
    return target


def gzip_file(source: Path, target: Path) -> None:
    with source.open("rb") as input_file, target.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0, compresslevel=9) as output:
            while chunk := input_file.read(1024 * 1024):
                output.write(chunk)


def content_type(name: str) -> str:
    return {
        "player.html": "text/html; charset=utf-8",
        "player-bridge.js": "application/javascript",
        "LICENSE": "text/plain; charset=utf-8",
        "THIRD_PARTY_NOTICES.txt": "text/plain; charset=utf-8",
        "corresponding-source.zip": "application/zip",
    }[name]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default="preview-player/majdata-build.json")
    parser.add_argument("--player-dir", default="preview-player")
    parser.add_argument("--verify-origin", required=True)
    args = parser.parse_args()

    manifest_path = Path(args.manifest)
    player_dir = Path(args.player_dir)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    version = manifest["version"]
    prefix = f"majdata/{version}"
    required_env = (
        "R2_ACCOUNT_ID",
        "PREVIEW_PUBLIC_BUCKET_NAME",
        "PREVIEW_PUBLIC_ACCESS_KEY_ID",
        "PREVIEW_PUBLIC_SECRET_ACCESS_KEY",
    )
    missing = [name for name in required_env if not os.environ.get(name)]
    if missing:
        raise RuntimeError(f"missing environment variables: {', '.join(missing)}")

    client = boto3.client(
        "s3",
        endpoint_url=f"https://{os.environ['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["PREVIEW_PUBLIC_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["PREVIEW_PUBLIC_SECRET_ACCESS_KEY"],
        region_name="auto",
        config=Config(signature_version="s3v4"),
    )
    bucket = os.environ["PREVIEW_PUBLIC_BUCKET_NAME"]

    with tempfile.TemporaryDirectory(prefix="zppz-player-publish-") as temp:
        root = Path(temp)
        prepared: dict[str, tuple[Path, str, str | None]] = {}
        build_base = manifest["build_base_url"].rstrip("/")
        for name, item in manifest["files"].items():
            source = resolve_asset(f"{build_base}/{name}", name, player_dir, root)
            actual = sha256(source)
            if actual != item["sha256"]:
                raise RuntimeError(
                    f"SHA-256 mismatch for {name}: expected {item['sha256']}, "
                    f"got {actual} ({source.stat().st_size} bytes) from {build_base}/{name}"
                )
            upload_path = source
            encoding = None
            if item.get("compress"):
                upload_path = root / f"{name}.gz"
                gzip_file(source, upload_path)
                encoding = "gzip"
            prepared[name] = (upload_path, item["content_type"], encoding)

        license_path = resolve_asset(manifest["license_url"], "LICENSE", player_dir, root)
        local_source = player_dir / "corresponding-source.zip"
        if str(manifest.get("source_archive_url", "")).startswith("local://") or local_source.is_file():
            source_url = (
                manifest["source_archive_url"]
                if str(manifest.get("source_archive_url", "")).startswith("local://")
                else f"local://{local_source.as_posix()}"
            )
            source_path = resolve_asset(source_url, "corresponding-source.zip", player_dir, root)
        else:
            source_path = resolve_asset(
                manifest["source_archive_url"],
                "corresponding-source.zip",
                player_dir,
                root,
            )
        for name in ("player.html", "player-bridge.js", "THIRD_PARTY_NOTICES.txt"):
            prepared[name] = (player_dir / name, content_type(name), None)
        prepared["LICENSE"] = (license_path, content_type("LICENSE"), None)
        prepared["corresponding-source.zip"] = (
            source_path,
            content_type("corresponding-source.zip"),
            None,
        )
        prepared["majdata-build.json"] = (
            manifest_path,
            "application/json",
            None,
        )

        for name, (path, mime, encoding) in prepared.items():
            key = f"{prefix}/{name}"
            digest = sha256(path)
            try:
                existing = client.head_object(Bucket=bucket, Key=key)
            except ClientError as exc:
                if exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode") != 404:
                    raise
                existing = None
            if existing:
                if existing.get("Metadata", {}).get("sha256") != digest:
                    raise RuntimeError(f"immutable object already exists with a different hash: {key}")
                print(f"skip {key}")
                continue
            extra = {
                "ContentType": mime,
                "CacheControl": CACHE_CONTROL,
                "Metadata": {"sha256": digest},
            }
            if encoding:
                extra["ContentEncoding"] = encoding
            client.upload_file(str(path), bucket, key, ExtraArgs=extra)
            print(f"uploaded {key}")

    origin = args.verify_origin.rstrip("/")
    for name, expected in (
        ("player.html", "text/html"),
        ("Build.wasm", "application/wasm"),
        ("Build.data", "application/octet-stream"),
    ):
        url = f"{origin}/{prefix}/{name}"
        request = Request(url, method="HEAD", headers={"User-Agent": "zppz-preview-publisher/1"})
        with urlopen(request, timeout=30) as response:
            received = response.headers.get("Content-Type", "")
            if expected not in received:
                raise RuntimeError(f"unexpected Content-Type for {url}: {received}")
            if name == "player.html":
                csp = response.headers.get("Content-Security-Policy", "")
                if "frame-ancestors https://przppz.club" not in csp:
                    raise RuntimeError(
                        "player response is missing Content-Security-Policy: "
                        "frame-ancestors https://przppz.club"
                    )

    player_url = f"{origin}/{prefix}/player.html"
    output_path = os.environ.get("GITHUB_OUTPUT")
    if output_path:
        with open(output_path, "a", encoding="utf-8") as output:
            output.write(f"player_url={player_url}\n")
            output.write(f"player_version={version}\n")
    print(player_url)


if __name__ == "__main__":
    main()
