from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import shutil
import tempfile
from typing import Iterator

import boto3
from botocore.config import Config

from app.core.config import get_settings


@dataclass(frozen=True)
class ObjectInfo:
    size: int
    content_type: str


class ObjectChunks:
    def __init__(self, iterator, size: int):
        self.iterator = iterator
        self.size = size

    def __len__(self) -> int:
        return self.size

    def __iter__(self):
        return iter(self.iterator)


class LocalObjectStore:
    backend = "local"

    def _path(self, key: str) -> Path:
        root = get_settings().data_dir.resolve()
        path = (root / key).resolve()
        path.relative_to(root)
        return path

    def head(self, key: str) -> ObjectInfo:
        path = self._path(key)
        if not path.is_file():
            raise FileNotFoundError(key)
        return ObjectInfo(path.stat().st_size, "application/octet-stream")

    def put_file(self, key: str, path: Path, *, content_type: str, content_disposition: str | None = None) -> None:
        del content_type, content_disposition
        target = self._path(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)

    def copy(self, source_key: str, target_key: str, *, content_type: str, content_disposition: str | None = None) -> None:
        self.put_file(target_key, self._path(source_key), content_type=content_type, content_disposition=content_disposition)

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    def download_to(self, key: str, target: Path) -> None:
        shutil.copyfile(self._path(key), target)

    def chunks(self, key: str, size: int, chunk_size: int = 1024 * 1024) -> ObjectChunks:
        def generate():
            with self._path(key).open("rb") as source:
                while chunk := source.read(chunk_size):
                    yield chunk
        return ObjectChunks(generate(), size)

    def create_upload_url(self, intent_id: str, content_type: str, object_key: str | None = None) -> str:
        del content_type, object_key
        return f"{get_settings().api_prefix}/submissions/upload-intents/{intent_id}/content"

    def writable_path(self, key: str) -> Path:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def create_download_url(self, key: str, file_name: str) -> str | None:
        del key, file_name
        return None

    def create_inline_url(self, key: str, content_type: str, expires_in: int) -> str | None:
        del key, content_type, expires_in
        return None

    def check(self) -> None:
        get_settings().data_dir.mkdir(parents=True, exist_ok=True)


class R2ObjectStore:
    backend = "r2"

    def __init__(self):
        settings = get_settings()
        settings.validate_object_storage()
        self.bucket = settings.r2_bucket_name
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.r2_endpoint,
            aws_access_key_id=settings.r2_access_key_id,
            aws_secret_access_key=settings.r2_secret_access_key,
            region_name="auto",
            config=Config(signature_version="s3v4"),
        )

    def head(self, key: str) -> ObjectInfo:
        response = self.client.head_object(Bucket=self.bucket, Key=key)
        return ObjectInfo(int(response["ContentLength"]), response.get("ContentType") or "application/octet-stream")

    def put_file(self, key: str, path: Path, *, content_type: str, content_disposition: str | None = None) -> None:
        extra = {"ContentType": content_type}
        if content_disposition:
            extra["ContentDisposition"] = content_disposition
        self.client.upload_file(str(path), self.bucket, key, ExtraArgs=extra)

    def copy(self, source_key: str, target_key: str, *, content_type: str, content_disposition: str | None = None) -> None:
        args = {
            "Bucket": self.bucket,
            "Key": target_key,
            "CopySource": {"Bucket": self.bucket, "Key": source_key},
            "MetadataDirective": "REPLACE",
            "ContentType": content_type,
        }
        if content_disposition:
            args["ContentDisposition"] = content_disposition
        self.client.copy_object(**args)

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)

    def download_to(self, key: str, target: Path) -> None:
        self.client.download_file(self.bucket, key, str(target))

    def chunks(self, key: str, size: int, chunk_size: int = 1024 * 1024) -> ObjectChunks:
        def generate():
            response = self.client.get_object(Bucket=self.bucket, Key=key)
            body = response["Body"]
            try:
                while chunk := body.read(chunk_size):
                    yield chunk
            finally:
                body.close()
        return ObjectChunks(generate(), size)

    def create_upload_url(self, intent_id: str, content_type: str, object_key: str | None = None) -> str:
        del intent_id
        if object_key is None:
            raise ValueError("object_key is required for R2 uploads")
        return self.client.generate_presigned_url(
            "put_object",
            Params={"Bucket": self.bucket, "Key": object_key, "ContentType": content_type},
            ExpiresIn=get_settings().r2_upload_url_ttl_seconds,
        )

    def create_download_url(self, key: str, file_name: str) -> str:
        from app.modules.downloads import content_disposition

        return self.client.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": self.bucket,
                "Key": key,
                "ResponseContentDisposition": content_disposition(file_name),
            },
            ExpiresIn=get_settings().r2_download_url_ttl_seconds,
        )

    def create_inline_url(self, key: str, content_type: str, expires_in: int) -> str:
        return self.client.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": self.bucket,
                "Key": key,
                "ResponseContentType": content_type,
                "ResponseContentDisposition": "inline",
            },
            ExpiresIn=expires_in,
        )

    def check(self) -> None:
        from uuid import uuid4

        key = f"healthchecks/{uuid4().hex}"
        self.client.head_bucket(Bucket=self.bucket)
        self.client.put_object(Bucket=self.bucket, Key=key, Body=b"ok", ContentType="text/plain")
        try:
            info = self.head(key)
            if info.size != 2:
                raise RuntimeError("R2 storage check returned an unexpected object size")
        finally:
            self.delete(key)


@lru_cache
def get_object_store():
    settings = get_settings()
    settings.validate_object_storage()
    return R2ObjectStore() if settings.object_storage_backend == "r2" else LocalObjectStore()


@contextmanager
def materialized_object(key: str, suffix: str = "") -> Iterator[Path]:
    store = get_object_store()
    if store.backend == "local":
        yield store._path(key)
        return
    with tempfile.TemporaryDirectory(prefix="zppz-object-") as directory:
        path = Path(directory) / f"object{suffix}"
        store.download_to(key, path)
        yield path
