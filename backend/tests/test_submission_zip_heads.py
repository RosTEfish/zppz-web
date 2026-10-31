"""Batch submission zip heads stay ordered while overlapping under a small cap."""

from __future__ import annotations

import threading
import time
from io import BytesIO
from types import SimpleNamespace
from zipfile import ZipFile

import pytest
from fastapi import HTTPException

from app.modules.object_storage import ObjectInfo
from app.modules.submissions import batch_zip

GIB = 1024 * 1024 * 1024


def _row(storage_path: str, *, submission_id: int, file_name: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        id=submission_id,
        track="normal",
        file_name=file_name or f"file-{submission_id}.zip",
        storage_path=storage_path,
        user_id=7,
        user=SimpleNamespace(user_code="P01"),
        source_song=SimpleNamespace(song_name="Song"),
    )


def _install_store(monkeypatch, store) -> None:
    monkeypatch.setattr(batch_zip, "get_object_store", lambda: store)


def test_zip_head_concurrency_default_is_small():
    assert getattr(batch_zip, "ZIP_HEAD_CONCURRENCY", None) == 8


def test_zip_object_heads_overlap_and_stay_within_the_limit(monkeypatch):
    monkeypatch.setattr(batch_zip, "ZIP_HEAD_CONCURRENCY", 3, raising=False)
    in_flight = 0
    max_in_flight = 0
    lock = threading.Lock()

    class Store:
        backend = "r2"

        def head(self, key: str) -> ObjectInfo:
            nonlocal in_flight, max_in_flight
            with lock:
                in_flight += 1
                max_in_flight = max(max_in_flight, in_flight)
            time.sleep(0.05)
            with lock:
                in_flight -= 1
            return ObjectInfo(size=4, content_type="application/zip")

        def chunks(self, key: str, size: int):
            return iter([b"abcd"])

    rows = [_row(f"obj/{index}.zip", submission_id=index) for index in range(1, 7)]
    _install_store(monkeypatch, Store())
    prepared = batch_zip._prepare_submission_zip(rows, "submissions.zip")
    assert prepared.file_name == "submissions.zip"
    assert max_in_flight == 3


def test_zip_heads_keep_input_order_when_calls_finish_out_of_order(monkeypatch):
    delays = {"slow": 0.08, "missing": 0.0, "fast": 0.02}
    sizes = {"slow": 5, "fast": 7}

    class Store:
        backend = "r2"

        def head(self, key: str) -> ObjectInfo:
            time.sleep(delays[key])
            if key == "missing":
                raise FileNotFoundError(key)
            return ObjectInfo(size=sizes[key], content_type="application/zip")

        def chunks(self, key: str, size: int):
            return iter([b"x" * size])

    rows = [
        _row("slow", submission_id=1, file_name="slow.zip"),
        _row("missing", submission_id=2, file_name="gone.zip"),
        _row("fast", submission_id=3, file_name="fast.zip"),
    ]
    _install_store(monkeypatch, Store())
    prepared = batch_zip._prepare_submission_zip(rows, "submissions.zip")
    with ZipFile(BytesIO(b"".join(prepared.stream))) as archive:
        names = archive.namelist()
        report = archive.read("_下载报告.txt").decode()
    assert [name for name in names if name.endswith(".zip")] == [
        "normal_P01_Song_1_slow.zip",
        "normal_P01_Song_3_fast.zip",
    ]
    assert report.splitlines() == ["以下投稿文件不存在：", "- ID 2: gone.zip"]


def test_zip_heads_treat_errors_as_missing_and_keep_status_codes(monkeypatch):
    class Store:
        backend = "r2"

        def head(self, key: str) -> ObjectInfo:
            if key == "missing":
                raise RuntimeError("gone")
            if key == "huge":
                return ObjectInfo(size=6 * GIB, content_type="application/zip")
            return ObjectInfo(size=1, content_type="application/zip")

        def chunks(self, key: str, size: int):
            return iter([b"x" * size])

    _install_store(monkeypatch, Store())
    with pytest.raises(HTTPException) as no_rows:
        batch_zip._prepare_submission_zip([], "submissions.zip")
    assert no_rows.value.status_code == 404
    assert no_rows.value.detail == "所选投稿文件均不存在"

    with pytest.raises(HTTPException) as empty:
        batch_zip._prepare_submission_zip(
            [_row("missing", submission_id=1), _row("missing", submission_id=2)],
            "submissions.zip",
        )
    assert empty.value.status_code == 404
    assert empty.value.detail == "所选投稿文件均不存在"

    with pytest.raises(HTTPException) as too_big:
        batch_zip._prepare_submission_zip(
            [_row("huge", submission_id=1), _row("huge", submission_id=2)],
            "submissions.zip",
        )
    assert too_big.value.status_code == 413
    assert too_big.value.detail == "所选投稿原文件总量不能超过 10 GiB"


def test_zip_size_limit_follows_input_order_not_completion_order(monkeypatch):
    """A later small object must not hide an earlier object that already overflows."""

    class Store:
        backend = "r2"

        def head(self, key: str) -> ObjectInfo:
            if key == "late-small":
                time.sleep(0.05)
                return ObjectInfo(size=1, content_type="application/zip")
            return ObjectInfo(size=11 * GIB, content_type="application/zip")

        def chunks(self, key: str, size: int):
            raise AssertionError("size limit should raise before streaming objects")

    _install_store(monkeypatch, Store())
    with pytest.raises(HTTPException) as exc:
        batch_zip._prepare_submission_zip(
            [_row("early-huge", submission_id=1), _row("late-small", submission_id=2)],
            "submissions.zip",
        )
    assert exc.value.status_code == 413
