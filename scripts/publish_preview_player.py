from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError


CACHE_CONTROL = "public, max-age=31536000, immutable"
DOWNLOAD_ATTEMPTS = 4
DOWNLOAD_TIMEOUT_SECONDS = 300
DOWNLOAD_BACKOFF_SECONDS = (2, 5, 15)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def download(url: str, target: Path) -> None:
    """Download with retries; GitHub archive/raw transfers can stall under load."""
    last_error: Exception | None = None
    for attempt in range(1, DOWNLOAD_ATTEMPTS + 1):
        temporary = target.with_suffix(target.suffix + f".part{attempt}")
        try:
            request = Request(url, headers={"User-Agent": "zppz-preview-publisher/1"})
            with urlopen(request, timeout=DOWNLOAD_TIMEOUT_SECONDS) as response, temporary.open("wb") as output:
                while chunk := response.read(1024 * 1024):
                    output.write(chunk)
            temporary.replace(target)
            return
        except (TimeoutError, HTTPError, URLError, OSError) as exc:
            last_error = exc
            temporary.unlink(missing_ok=True)
            if attempt >= DOWNLOAD_ATTEMPTS:
                break
            delay = DOWNLOAD_BACKOFF_SECONDS[min(attempt - 1, len(DOWNLOAD_BACKOFF_SECONDS) - 1)]
            print(f"download retry {attempt}/{DOWNLOAD_ATTEMPTS} for {url}: {exc}; sleeping {delay}s")
            time.sleep(delay)
    raise RuntimeError(f"failed to download {url} after {DOWNLOAD_ATTEMPTS} attempts: {last_error}")


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


def head_object(client, bucket: str, key: str) -> dict | None:
    try:
        return client.head_object(Bucket=bucket, Key=key)
    except ClientError as exc:
        if exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode") == 404:
            return None
        # botocore may surface NoSuchKey / 404 as error code instead of status.
        error = exc.response.get("Error", {})
        if error.get("Code") in {"404", "NoSuchKey", "NotFound"}:
            return None
        raise


def required_object_keys(prefix: str, manifest: dict) -> list[str]:
    names = list(manifest["files"])
    names.extend(
        (
            "player.html",
            "player-bridge.js",
            "THIRD_PARTY_NOTICES.txt",
            "LICENSE",
            "corresponding-source.zip",
            "majdata-build.json",
        )
    )
    return [f"{prefix}/{name}" for name in names]


def all_objects_present(client, bucket: str, keys: list[str]) -> bool:
    for key in keys:
        if head_object(client, bucket, key) is None:
            return False
    return True


def verify_origin(origin: str, prefix: str) -> None:
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


def write_outputs(player_url: str, version: str) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        return
    with open(output_path, "a", encoding="utf-8") as output:
        output.write(f"player_url={player_url}\n")
        output.write(f"player_version={version}\n")


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
    origin = args.verify_origin.rstrip("/")
    player_url = f"{origin}/{prefix}/player.html"

    keys = required_object_keys(prefix, manifest)
    if all_objects_present(client, bucket, keys):
        print(f"pinned player {version} already published; skipping source downloads")
        for key in keys:
            print(f"skip {key}")
        verify_origin(origin, prefix)
        write_outputs(player_url, version)
        print(player_url)
        return

    with tempfile.TemporaryDirectory(prefix="zppz-player-publish-") as temp:
        root = Path(temp)
        prepared: dict[str, tuple[Path, str, str | None]] = {}
        for name, item in manifest["files"].items():
            key = f"{prefix}/{name}"
            if head_object(client, bucket, key) is not None:
                print(f"skip download for existing {key}")
                continue
            source = root / name
            source_url = f"{manifest['build_base_url']}/{name}"
            download(source_url, source)
            actual = sha256(source)
            if actual != item["sha256"]:
                raise RuntimeError(
                    f"SHA-256 mismatch for {name}: expected {item['sha256']}, "
                    f"downloaded {actual} ({source.stat().st_size} bytes) from {source_url}"
                )
            upload_path = source
            encoding = None
            if item.get("compress"):
                upload_path = root / f"{name}.gz"
                gzip_file(source, upload_path)
                encoding = "gzip"
            prepared[name] = (upload_path, item["content_type"], encoding)

        for name in ("player.html", "player-bridge.js", "THIRD_PARTY_NOTICES.txt"):
            prepared[name] = (player_dir / name, content_type(name), None)

        license_key = f"{prefix}/LICENSE"
        source_key = f"{prefix}/corresponding-source.zip"
        if head_object(client, bucket, license_key) is None:
            license_path = root / "LICENSE"
            download(manifest["license_url"], license_path)
            prepared["LICENSE"] = (license_path, content_type("LICENSE"), None)
        else:
            print(f"skip download for existing {license_key}")

        if head_object(client, bucket, source_key) is None:
            source_path = root / "corresponding-source.zip"
            download(manifest["source_archive_url"], source_path)
            prepared["corresponding-source.zip"] = (
                source_path,
                content_type("corresponding-source.zip"),
                None,
            )
        else:
            print(f"skip download for existing {source_key}")

        prepared["majdata-build.json"] = (
            manifest_path,
            "application/json",
            None,
        )

        for name, (path, mime, encoding) in prepared.items():
            key = f"{prefix}/{name}"
            digest = sha256(path)
            existing = head_object(client, bucket, key)
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

    verify_origin(origin, prefix)
    write_outputs(player_url, version)
    print(player_url)


if __name__ == "__main__":
    main()
