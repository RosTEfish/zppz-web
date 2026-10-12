from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import zipfile

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError


CACHE_CONTROL = "public, max-age=31536000, immutable"
DOWNLOAD_ATTEMPTS = 4
DOWNLOAD_TIMEOUT_SECONDS = 300
DOWNLOAD_BACKOFF_SECONDS = (2, 5, 15)
INVENTORY_NAME = "object-inventory.json"
MARKER_RELATIVE_PATHS = (
    "sdk/index.mjs",
    "renderer/index.html",
    "renderer/miacode-preview.wasm",
    "miaview-build.json",
    INVENTORY_NAME,
)
PUBLISH_ROOTS = ("sdk", "renderer")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def download(url: str, target: Path, *, headers: dict[str, str] | None = None) -> None:
    """Download with retries; GitHub transfers can stall under load."""
    last_error: Exception | None = None
    request_headers = {"User-Agent": "zppz-preview-publisher/2", **(headers or {})}
    for attempt in range(1, DOWNLOAD_ATTEMPTS + 1):
        temporary = target.with_suffix(target.suffix + f".part{attempt}")
        try:
            request = Request(url, headers=request_headers)
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


def content_type_for(relative_path: str) -> str:
    name = Path(relative_path).name.lower()
    if name.endswith(".mjs") or name.endswith(".js"):
        return "application/javascript; charset=utf-8"
    if name.endswith(".wasm"):
        return "application/wasm"
    if name.endswith(".html"):
        return "text/html; charset=utf-8"
    if name.endswith(".css"):
        return "text/css; charset=utf-8"
    if name.endswith(".json"):
        return "application/json"
    if name.endswith(".wav"):
        return "audio/wav"
    if name.endswith(".md") or name == "license" or name.endswith(".txt"):
        return "text/plain; charset=utf-8"
    if name.endswith(".br") or name.endswith(".gz"):
        return "application/octet-stream"
    guessed, _ = mimetypes.guess_type(name)
    return guessed or "application/octet-stream"


def head_object(client, bucket: str, key: str) -> dict | None:
    try:
        return client.head_object(Bucket=bucket, Key=key)
    except ClientError as exc:
        if exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode") == 404:
            return None
        error = exc.response.get("Error", {})
        if error.get("Code") in {"404", "NoSuchKey", "NotFound"}:
            return None
        raise


def get_object_text(client, bucket: str, key: str) -> str | None:
    try:
        response = client.get_object(Bucket=bucket, Key=key)
    except ClientError as exc:
        error = exc.response.get("Error", {})
        if error.get("Code") in {"404", "NoSuchKey", "NotFound"}:
            return None
        if exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode") == 404:
            return None
        raise
    return response["Body"].read().decode("utf-8")


def all_objects_present(client, bucket: str, keys: list[str]) -> bool:
    for key in keys:
        if head_object(client, bucket, key) is None:
            return False
    return True


def iter_publish_files(artifact_root: Path) -> list[Path]:
    files: list[Path] = []
    for root_name in PUBLISH_ROOTS:
        root = artifact_root / root_name
        if not root.is_dir():
            raise RuntimeError(f"artifact is missing required directory: {root_name}/")
        for path in sorted(root.rglob("*")):
            if path.is_file():
                files.append(path)
    return files


def relative_publish_path(artifact_root: Path, path: Path) -> str:
    return path.relative_to(artifact_root).as_posix()


def required_object_keys(prefix: str, relative_paths: list[str]) -> list[str]:
    return [f"{prefix}/{path}" for path in relative_paths]


def marker_object_keys(prefix: str) -> list[str]:
    return [f"{prefix}/{path}" for path in MARKER_RELATIVE_PATHS]


def find_successful_run_id(repository: str, commit: str, workflow_name: str, token: str) -> int:
    url = (
        f"https://api.github.com/repos/{repository}/actions/runs"
        f"?head_sha={commit}&status=completed&per_page=20"
    )
    request = Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "zppz-preview-publisher/2",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urlopen(request, timeout=60) as response:
        payload = json.loads(response.read().decode("utf-8"))
    for run in payload.get("workflow_runs", []):
        if run.get("conclusion") != "success":
            continue
        if workflow_name and run.get("name") != workflow_name:
            continue
        return int(run["id"])
    raise RuntimeError(
        f"no successful GitHub Actions run named {workflow_name!r} for {repository}@{commit}"
    )


def find_artifact_id(repository: str, run_id: int, artifact_name: str, token: str) -> int:
    url = f"https://api.github.com/repos/{repository}/actions/runs/{run_id}/artifacts"
    request = Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "zppz-preview-publisher/2",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urlopen(request, timeout=60) as response:
        payload = json.loads(response.read().decode("utf-8"))
    for artifact in payload.get("artifacts", []):
        if artifact.get("name") == artifact_name and not artifact.get("expired"):
            return int(artifact["id"])
    raise RuntimeError(
        f"artifact {artifact_name!r} not found (or expired) on run {run_id} for {repository}"
    )


def download_artifact_zip(
    repository: str,
    *,
    commit: str,
    workflow_name: str,
    artifact_name: str,
    target: Path,
) -> None:
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        raise RuntimeError("GITHUB_TOKEN (or GH_TOKEN) is required to download MiaView CI artifacts")

    # Prefer gh when available: handles redirects and auth cleanly.
    if shutil.which("gh"):
        with tempfile.TemporaryDirectory(prefix="zppz-gh-artifact-") as temp:
            staging = Path(temp)
            command = [
                "gh",
                "run",
                "download",
                "--repo",
                repository,
                "--name",
                artifact_name,
                "--dir",
                str(staging),
                str(find_successful_run_id(repository, commit, workflow_name, token)),
            ]
            print(" ".join(command))
            subprocess.run(command, check=True)
            # Package the extracted tree back into a zip so callers share one extract path.
            with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for path in sorted(staging.rglob("*")):
                    if path.is_file():
                        archive.write(path, path.relative_to(staging).as_posix())
        return

    run_id = find_successful_run_id(repository, commit, workflow_name, token)
    artifact_id = find_artifact_id(repository, run_id, artifact_name, token)
    url = f"https://api.github.com/repos/{repository}/actions/artifacts/{artifact_id}/zip"
    download(
        url,
        target,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )


def extract_artifact(zip_path: Path, destination: Path) -> Path:
    with zipfile.ZipFile(zip_path) as archive:
        archive.extractall(destination)
    # Artifacts may nest under a single top-level directory.
    if (destination / "sdk").is_dir() and (destination / "renderer").is_dir():
        return destination
    children = [path for path in destination.iterdir() if path.is_dir()]
    for child in children:
        if (child / "sdk").is_dir() and (child / "renderer").is_dir():
            return child
    raise RuntimeError("extracted artifact does not contain sdk/ and renderer/")


def verify_origin(origin: str, prefix: str) -> None:
    checks = (
        ("sdk/index.mjs", "javascript"),
        ("renderer/index.html", "text/html"),
        ("renderer/miacode-preview.wasm", "application/wasm"),
    )
    for name, expected in checks:
        url = f"{origin}/{prefix}/{name}"
        request = Request(url, method="HEAD", headers={"User-Agent": "zppz-preview-publisher/2"})
        with urlopen(request, timeout=30) as response:
            received = response.headers.get("Content-Type", "")
            if expected not in received:
                raise RuntimeError(f"unexpected Content-Type for {url}: {received}")
            if name == "renderer/index.html":
                csp = response.headers.get("Content-Security-Policy", "")
                if "frame-ancestors https://www.przppz.club" not in csp:
                    raise RuntimeError(
                        "renderer response is missing Content-Security-Policy: "
                        "frame-ancestors https://www.przppz.club"
                    )


def write_outputs(player_url: str, version: str) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        return
    with open(output_path, "a", encoding="utf-8") as output:
        output.write(f"player_url={player_url}\n")
        output.write(f"player_version={version}\n")


def upload_file(client, bucket: str, key: str, path: Path, mime: str) -> None:
    digest = sha256(path)
    existing = head_object(client, bucket, key)
    if existing:
        if existing.get("Metadata", {}).get("sha256") != digest:
            raise RuntimeError(f"immutable object already exists with a different hash: {key}")
        print(f"skip {key}")
        return
    client.upload_file(
        str(path),
        bucket,
        key,
        ExtraArgs={
            "ContentType": mime,
            "CacheControl": CACHE_CONTROL,
            "Metadata": {"sha256": digest},
        },
    )
    print(f"uploaded {key}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default="preview-player/miaview-build.json")
    parser.add_argument("--verify-origin", required=True)
    args = parser.parse_args()

    manifest_path = Path(args.manifest)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    version = manifest["version"]
    repository = manifest["repository"]
    commit = manifest["commit"]
    artifact_name = manifest.get("artifact_name", "miaview-preview")
    workflow_name = manifest.get("workflow_name", "Web preview")
    prefix = f"miaview/{version}"
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
    player_url = f"{origin}/{prefix}/sdk/index.mjs"

    inventory_key = f"{prefix}/{INVENTORY_NAME}"
    remote_inventory_text = get_object_text(client, bucket, inventory_key)
    if remote_inventory_text is not None:
        inventory = json.loads(remote_inventory_text)
        relative_paths = list(inventory.get("files", []))
        keys = required_object_keys(prefix, relative_paths)
        if relative_paths and all_objects_present(client, bucket, keys):
            local_digest = sha256(manifest_path)
            remote_manifest = head_object(client, bucket, f"{prefix}/miaview-build.json") or {}
            remote_digest = remote_manifest.get("Metadata", {}).get("sha256")
            if remote_digest != local_digest:
                raise RuntimeError(
                    f"miaview-build.json changed but player version {version!r} is already published. "
                    "Bump miaview-build.json version so a new immutable prefix is uploaded."
                )
            print(f"pinned player {version} already published; skipping artifact download")
            for key in keys:
                print(f"skip {key}")
            verify_origin(origin, prefix)
            write_outputs(player_url, version)
            print(player_url)
            return

    if all_objects_present(client, bucket, marker_object_keys(prefix)):
        # Incomplete prior publish without inventory: force a fresh inventory rebuild.
        print(f"marker objects exist for {version} but inventory is missing; rebuilding from artifact")

    with tempfile.TemporaryDirectory(prefix="zppz-miaview-publish-") as temp:
        root = Path(temp)
        zip_path = root / "miaview-preview.zip"
        extract_root = root / "extracted"
        extract_root.mkdir()
        download_artifact_zip(
            repository,
            commit=commit,
            workflow_name=workflow_name,
            artifact_name=artifact_name,
            target=zip_path,
        )
        artifact_root = extract_artifact(zip_path, extract_root)
        files = iter_publish_files(artifact_root)
        relative_paths = [relative_publish_path(artifact_root, path) for path in files]
        relative_paths.extend(["miaview-build.json", INVENTORY_NAME])

        inventory_path = root / INVENTORY_NAME
        inventory_path.write_text(
            json.dumps(
                {
                    "version": version,
                    "commit": commit,
                    "repository": repository,
                    "files": relative_paths,
                },
                indent=2,
                ensure_ascii=True,
            )
            + "\n",
            encoding="utf-8",
        )

        for path, relative in zip(files, relative_paths[:-2], strict=True):
            upload_file(client, bucket, f"{prefix}/{relative}", path, content_type_for(relative))

        upload_file(
            client,
            bucket,
            f"{prefix}/miaview-build.json",
            manifest_path,
            "application/json",
        )
        upload_file(
            client,
            bucket,
            inventory_key,
            inventory_path,
            "application/json",
        )

    verify_origin(origin, prefix)
    write_outputs(player_url, version)
    print(player_url)


if __name__ == "__main__":
    main()
