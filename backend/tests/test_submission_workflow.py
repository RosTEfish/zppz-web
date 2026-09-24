import asyncio
from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path
import re
import shutil
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile

import pytest
from fastapi import BackgroundTasks
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select

from app.core.config import get_settings
from app.db.bootstrap import seed_defaults
from app.db.session import Base, SessionLocal, engine
from app.main import app
from app.models import DrawAssignment, Event, GuessChart, GuessComment, GuessVote, ImportIssue, PreviewBundle, Song, StorageDeletion, Submission, SubmissionProcessingJob, SubmissionUploadIntent, User
from app.modules.downloads import DownloadEntry, prepare_streaming_zip
from app.modules.submissions import service as submission_service
from app.modules.submissions import processing as submission_processing
from app.modules.submissions.processing import claim_next_job, process_job
from app.modules.submissions.router import _complete_intent


def png_cover_bytes() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (4, 4), "#2374d8").save(buffer, format="PNG")
    return buffer.getvalue()


PNG_COVER = png_cover_bytes()


@pytest.fixture(autouse=True)
def reset_db_and_files():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed_defaults(db)
    settings = get_settings()
    shutil.rmtree(settings.uploads_dir, ignore_errors=True)
    shutil.rmtree(settings.assets_dir / "guess-covers", ignore_errors=True)
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    (settings.assets_dir / "guess-covers").mkdir(parents=True, exist_ok=True)


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def archive_bytes(
    title: str = "Song",
    levels: str = "&lv_4=13\n&lv_5=14",
    *,
    video_name: str | None = None,
    background_name: str = "bg.png",
    background: bytes = PNG_COVER,
) -> bytes:
    playable = "\n".join(
        f"&inote_{slot}=(120){{1}},"
        for slot in re.findall(r"(?im)^\s*&lv_([1-7])\s*=", levels)
    )
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        archive.writestr("nested/maidata.txt", f"&title={title}\n&artist=Artist\n{levels}\n{playable}")
        archive.writestr(f"nested/{background_name}", background)
        archive.writestr("nested/track.mp3", (bytes.fromhex("FFFB9064") + bytes(413)) * 2)
        if video_name:
            archive.writestr(f"nested/{video_name}", b"video")
    return buffer.getvalue()


def test_streaming_zip_yields_before_the_source_is_fully_read(tmp_path: Path):
    source = tmp_path / "large-source.zip"
    source.write_bytes(b"x" * (2 * 1024 * 1024))
    prepared = prepare_streaming_zip(
        [DownloadEntry(path=source, archive_name="source.zip")],
        file_name="submissions.zip",
    )

    chunks = iter(prepared.stream)
    first_chunk = next(chunks)
    assert first_chunk.startswith(b"PK")
    assert len(first_chunk) < prepared.file_size

    payload = first_chunk + b"".join(chunks)
    assert len(payload) == prepared.file_size
    with ZipFile(BytesIO(payload)) as archive:
        assert archive.read("source.zip") == source.read_bytes()


def test_streaming_zip_keeps_sized_iterables_lazy():
    source = b"remote payload"
    started = False

    def chunks():
        nonlocal started
        started = True
        yield source

    prepared = prepare_streaming_zip(
        [DownloadEntry(path=None, archive_name="remote.zip", data=chunks(), data_size=len(source))],
        file_name="submissions.zip",
    )

    assert not started
    payload = b"".join(prepared.stream)
    assert started
    assert len(payload) == prepared.file_size
    with ZipFile(BytesIO(payload)) as archive:
        assert archive.read("remote.zip") == source


def register(client: TestClient, code: str, identity: str = "participant") -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={"user_code": code, "qq_id": code, "password": "secret123", "identity": identity},
    )
    assert response.status_code == 201, response.text


def login(client: TestClient, code: str, password: str = "secret123") -> None:
    response = client.post("/api/v1/auth/login", json={"user_code": code, "password": password})
    assert response.status_code == 200, response.text


def login_admin(client: TestClient) -> None:
    login(client, "admin", "change-me-please")


def set_manual_phase(phase: str | None) -> None:
    with SessionLocal() as db:
        event = db.scalar(select(Event).where(Event.is_current.is_(True)))
        event.settings.phase_mode = "manual" if phase else "auto"
        event.settings.manual_phase = phase
        db.commit()


def public_chart_for_submission(client: TestClient, submission_id: int) -> dict:
    with SessionLocal() as db:
        chart_id = db.scalar(select(GuessChart.id).where(GuessChart.source_submission_id == submission_id))
    return next(row for row in client.get("/api/v1/guess-game/charts").json() if row["id"] == chart_id)


def create_candidate_rows() -> tuple[int, int, int]:
    with SessionLocal() as db:
        event = db.scalar(select(Event).where(Event.is_current.is_(True)))
        player = db.scalar(select(User).where(User.user_code == "player"))
        owner = db.scalar(select(User).where(User.user_code == "owner"))
        own = Song(event_id=event.id, submitted_by_id=player.id, song_name="Own", artist="Artist", song_type="A")
        assigned = Song(event_id=event.id, submitted_by_id=owner.id, song_name="Assigned", artist="Artist", song_type="B")
        db.add_all([own, assigned])
        db.flush()
        db.add(DrawAssignment(event_id=event.id, assigned_to_id=player.id, song_id=assigned.id))
        db.commit()
        return event.id, own.id, assigned.id


def run_next_processing_job() -> str:
    with SessionLocal() as db:
        job_id = claim_next_job(db)
    assert job_id is not None
    process_job(job_id)
    return job_id


def test_worker_claim_is_exclusive_and_recovers_expired_lease(client: TestClient):
    register(client, "owner")
    with SessionLocal() as db:
        event = db.scalar(select(Event).where(Event.is_current.is_(True)))
        owner = db.scalar(select(User).where(User.user_code == "owner"))
        job = SubmissionProcessingJob(
            id="lease-job",
            event_id=event.id,
            user_id=owner.id,
            source_storage_path="pending/lease.zip",
            status="queued",
            stage="uploaded",
            next_attempt_at=datetime.utcnow(),
        )
        db.add(job)
        db.commit()

    with SessionLocal() as first:
        assert claim_next_job(first) == "lease-job"
    with SessionLocal() as second:
        assert claim_next_job(second) is None
        job = second.get(SubmissionProcessingJob, "lease-job")
        assert job is not None
        job.lease_until = datetime.utcnow() - timedelta(seconds=1)
        second.commit()
    with SessionLocal() as recovered:
        assert claim_next_job(recovered) == "lease-job"
        job = recovered.get(SubmissionProcessingJob, "lease-job")
        assert job is not None and job.attempts == 2


def test_two_phase_submission_upload_is_idempotent_and_promotes_pending_object(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
):
    prepare_calls = 0
    original_prepare = submission_processing.prepare_archive

    def counted_prepare(*args, **kwargs):
        nonlocal prepare_calls
        prepare_calls += 1
        return original_prepare(*args, **kwargs)

    monkeypatch.setattr(submission_processing, "prepare_archive", counted_prepare)
    register(client, "owner")
    register(client, "player")
    _, own_id, _ = create_candidate_rows()
    set_manual_phase("submission_1")
    payload = archive_bytes(
        "Direct R2 Flow",
        background_name="bg.jpg",
        background=PNG_COVER,
    )

    created = client.post(
        "/api/v1/submissions/upload-intents",
        json={
            "song_id": own_id,
            "track": "normal",
            "file_name": "direct.zip",
            "file_size": len(payload),
            "content_type": "application/zip",
        },
    )
    assert created.status_code == 200, created.text
    intent = created.json()
    assert intent["method"] == "PUT"
    assert intent["headers"] == {"Content-Type": "application/zip"}

    uploaded = client.put(intent["upload_url"], content=payload, headers=intent["headers"])
    assert uploaded.status_code == 204, uploaded.text
    started = client.post(f"/api/v1/submissions/upload-intents/{intent['id']}/complete")
    assert started.status_code == 200, started.text
    assert started.json()["status"] == "queued"
    repeated = client.post(f"/api/v1/submissions/upload-intents/{intent['id']}/complete")
    assert repeated.status_code == 200
    assert repeated.json()["id"] == started.json()["id"]
    with SessionLocal() as db:
        assert len(list(db.scalars(select(SubmissionProcessingJob)).all())) == 1
    assert prepare_calls == 0

    run_next_processing_job()
    assert prepare_calls == 1
    completed = client.get(f"/api/v1/submissions/upload-intents/{intent['id']}/status")
    assert completed.status_code == 200, completed.text
    assert completed.json()["status"] == "completed"
    submission = completed.json()["submission"]
    assert submission is not None
    completed_again = client.post(f"/api/v1/submissions/upload-intents/{intent['id']}/complete")
    assert completed_again.status_code == 200
    assert completed_again.json()["status"] == "completed"
    assert completed_again.json()["submission"]["id"] == submission["id"]

    with SessionLocal() as db:
        row = db.get(Submission, submission["id"])
        upload_intent = db.get(SubmissionUploadIntent, intent["id"])
        assert row is not None and upload_intent is not None
        assert row.storage_path.startswith(f"events/{row.event_id}/submissions/{row.id}/source/")
        assert row.public_storage_path.startswith(f"events/{row.event_id}/submissions/{row.id}/public/")
        assert row.public_file_size and row.public_file_size > 0
        assert upload_intent.status == "completed"
        chart = db.scalar(select(GuessChart).where(GuessChart.source_submission_id == row.id))
        preview = db.scalar(select(PreviewBundle).where(PreviewBundle.source_id == row.id))
        issue = db.scalar(select(ImportIssue).where(ImportIssue.source_id == row.id))
        assert chart is not None and chart.cover_path.endswith(".png")
        assert preview is not None and preview.background_mime == "image/png"
        assert preview.background_key and preview.background_key.endswith("/bg.png")
        assert issue is not None and issue.issue_type == "cover_format_normalized"
        assert not (get_settings().data_dir / upload_intent.object_key).exists()
        assert (get_settings().data_dir / row.storage_path).read_bytes() == payload
        with ZipFile(get_settings().data_dir / row.public_storage_path) as public:
            compression = {info.filename: info.compress_type for info in public.infolist()}
        assert compression["maidata.txt"] == ZIP_DEFLATED
        assert compression["track.mp3"] == ZIP_STORED
        assert compression["bg.png"] == ZIP_STORED


def test_video_failure_keeps_static_preview_and_completed_submission(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
):
    register(client, "owner")
    register(client, "player")
    _, own_id, _ = create_candidate_rows()
    set_manual_phase("submission_1")
    payload = archive_bytes("Video Fallback", video_name="pv.mp4")

    def fail_video(*_args, **_kwargs):
        raise OSError("simulated video upload failure")

    monkeypatch.setattr(submission_processing, "attach_preview_video_from_files", fail_video)
    created = client.post(
        "/api/v1/submissions/upload-intents",
        json={
            "song_id": own_id,
            "track": "normal",
            "file_name": "video.zip",
            "file_size": len(payload),
            "content_type": "application/zip",
        },
    ).json()
    assert client.put(created["upload_url"], content=payload, headers=created["headers"]).status_code == 204
    queued = client.post(f"/api/v1/submissions/upload-intents/{created['id']}/complete")
    assert queued.status_code == 200
    run_next_processing_job()

    result = client.get(f"/api/v1/submissions/upload-intents/{created['id']}/status").json()
    assert result["status"] == "completed"
    assert result["submission"]["preview_status"] == "ready"
    assert result["submission"]["video_status"] == "failed"
    with SessionLocal() as db:
        bundle = db.scalar(
            select(PreviewBundle).where(
                PreviewBundle.source_id == result["submission"]["id"],
                PreviewBundle.source_type == "submission",
            )
        )
        assert bundle is not None
        assert bundle.status == "ready"
        assert bundle.video_status == "failed"
        row = db.get(Submission, result["submission"]["id"])
        assert row is not None and row.public_storage_path
        with ZipFile(get_settings().data_dir / row.public_storage_path) as public:
            assert public.getinfo("pv.mp4").compress_type == ZIP_STORED


def test_upload_intent_rejects_mime_and_size_mismatches(client: TestClient):
    register(client, "owner")
    register(client, "player")
    _, own_id, _ = create_candidate_rows()
    set_manual_phase("submission_1")
    payload = archive_bytes()

    wrong_mime = client.post(
        "/api/v1/submissions/upload-intents",
        json={
            "song_id": own_id,
            "track": "normal",
            "file_name": "source.zip",
            "file_size": len(payload),
            "content_type": "application/octet-stream",
        },
    )
    assert wrong_mime.status_code == 422

    created = client.post(
        "/api/v1/submissions/upload-intents",
        json={
            "song_id": own_id,
            "track": "normal",
            "file_name": "source.zip",
            "file_size": len(payload) + 1,
            "content_type": "application/zip",
        },
    )
    assert created.status_code == 200
    intent = created.json()
    mismatch = client.put(intent["upload_url"], content=payload, headers=intent["headers"])
    assert mismatch.status_code == 422


def test_background_upload_reports_parse_failure_without_creating_submission(client: TestClient):
    register(client, "owner")
    register(client, "player")
    _, own_id, _ = create_candidate_rows()
    set_manual_phase("submission_1")
    payload = archive_bytes(title="")

    created = client.post(
        "/api/v1/submissions/upload-intents",
        json={
            "song_id": own_id,
            "track": "normal",
            "file_name": "invalid.zip",
            "file_size": len(payload),
            "content_type": "application/zip",
        },
    )
    intent = created.json()
    assert client.put(
        intent["upload_url"],
        content=payload,
        headers=intent["headers"],
    ).status_code == 204

    started = client.post(f"/api/v1/submissions/upload-intents/{intent['id']}/complete")
    assert started.status_code == 200
    assert started.json()["status"] == "queued"
    run_next_processing_job()
    result = client.get(f"/api/v1/submissions/upload-intents/{intent['id']}/status")
    assert result.status_code == 200
    assert result.json()["status"] == "failed"
    assert result.json()["submission"] is None
    with SessionLocal() as db:
        assert db.scalar(select(Submission.id).where(Submission.source_song_id == own_id)) is None


def test_processing_intent_blocks_a_new_upload_for_the_same_song(client: TestClient):
    register(client, "owner")
    register(client, "player")
    _, own_id, _ = create_candidate_rows()
    set_manual_phase("submission_1")
    payload = archive_bytes()
    metadata = {
        "song_id": own_id,
        "track": "normal",
        "file_name": "first.zip",
        "file_size": len(payload),
        "content_type": "application/zip",
    }
    created = client.post("/api/v1/submissions/upload-intents", json=metadata)
    assert created.status_code == 200
    with SessionLocal() as db:
        intent = db.get(SubmissionUploadIntent, created.json()["id"])
        assert intent is not None
        intent.status = "processing"
        db.commit()

    blocked = client.post(
        "/api/v1/submissions/upload-intents",
        json={**metadata, "file_name": "second.zip"},
    )
    assert blocked.status_code == 409
    assert "上一份投稿仍在服务器处理中" in blocked.json()["detail"]


def test_pending_intent_blocks_a_second_upload_for_the_same_song(client: TestClient):
    register(client, "owner")
    register(client, "player")
    _, own_id, _ = create_candidate_rows()
    set_manual_phase("submission_1")
    payload = archive_bytes()
    metadata = {
        "song_id": own_id,
        "track": "normal",
        "file_name": "first.zip",
        "file_size": len(payload),
        "content_type": "application/zip",
    }
    created = client.post("/api/v1/submissions/upload-intents", json=metadata)
    assert created.status_code == 200
    blocked = client.post(
        "/api/v1/submissions/upload-intents",
        json={**metadata, "file_name": "second.zip"},
    )
    assert blocked.status_code == 409
    assert "上一份投稿仍在服务器处理中" in blocked.json()["detail"]


def test_user_can_cancel_stuck_validating_job_and_reupload(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    register(client, "owner")
    register(client, "player")
    _, own_id, _ = create_candidate_rows()
    set_manual_phase("submission_1")
    payload = archive_bytes("Cancel Me")

    def hang_forever(*_args, **_kwargs):
        raise submission_processing.ArchiveParseError("谱面校验超时（超过 1 秒），请检查压缩包后重新上传")

    monkeypatch.setattr(submission_processing, "_prepare_archive_with_timeout", hang_forever)

    created = client.post(
        "/api/v1/submissions/upload-intents",
        json={
            "song_id": own_id,
            "track": "normal",
            "file_name": "cancel-me.zip",
            "file_size": len(payload),
            "content_type": "application/zip",
        },
    )
    intent = created.json()
    assert client.put(intent["upload_url"], content=payload, headers=intent["headers"]).status_code == 204
    started = client.post(f"/api/v1/submissions/upload-intents/{intent['id']}/complete")
    assert started.status_code == 200
    job_id = started.json()["id"]

    # Simulate a job stuck in validating before the worker finishes failing it.
    with SessionLocal() as db:
        job = db.get(SubmissionProcessingJob, job_id)
        assert job is not None
        job.status = "processing"
        job.stage = "validating"
        job.lease_until = datetime.utcnow() + timedelta(minutes=20)
        db.commit()

    cancelled = client.post(f"/api/v1/submissions/processing-jobs/{job_id}/cancel")
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "cancelled"

    jobs = client.get("/api/v1/submissions/processing-jobs")
    assert jobs.status_code == 200
    assert all(item["id"] != job_id for item in jobs.json())

    retry = client.post(
        "/api/v1/submissions/upload-intents",
        json={
            "song_id": own_id,
            "track": "normal",
            "file_name": "retry.zip",
            "file_size": len(payload),
            "content_type": "application/zip",
        },
    )
    assert retry.status_code == 200, retry.text


def test_validation_timeout_marks_job_failed(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    register(client, "owner")
    register(client, "player")
    _, own_id, _ = create_candidate_rows()
    set_manual_phase("submission_1")
    payload = archive_bytes("Timeout Chart")

    def slow_prepare(*_args, **_kwargs):
        import time

        time.sleep(0.2)
        return submission_processing.prepare_archive(*_args, **_kwargs)

    monkeypatch.setattr(submission_processing, "_download_and_prepare_archive", slow_prepare)
    monkeypatch.setattr(submission_processing, "VALIDATION_TIMEOUT_SECONDS", 0.01)

    created = client.post(
        "/api/v1/submissions/upload-intents",
        json={
            "song_id": own_id,
            "track": "normal",
            "file_name": "timeout.zip",
            "file_size": len(payload),
            "content_type": "application/zip",
        },
    )
    intent = created.json()
    assert client.put(intent["upload_url"], content=payload, headers=intent["headers"]).status_code == 204
    started = client.post(f"/api/v1/submissions/upload-intents/{intent['id']}/complete")
    assert started.status_code == 200
    run_next_processing_job()
    result = client.get(f"/api/v1/submissions/upload-intents/{intent['id']}/status")
    assert result.status_code == 200
    assert result.json()["status"] == "failed"
    assert "校验超时" in result.json()["message"]


def test_background_storage_cleanup_keeps_failures_and_retries(monkeypatch: pytest.MonkeyPatch):
    class FakeStore:
        def __init__(self):
            self.fail = True
            self.deleted: list[str] = []

        def delete(self, object_key: str) -> None:
            if self.fail:
                raise OSError("temporary R2 failure")
            self.deleted.append(object_key)

    store = FakeStore()
    monkeypatch.setattr(submission_service, "get_object_store", lambda: store)
    with SessionLocal() as db:
        db.add_all([StorageDeletion(object_key="old/source.zip"), StorageDeletion(object_key="old/public.zip")])
        db.commit()

    assert submission_service.drain_storage_deletions_in_background() == 0
    with SessionLocal() as db:
        rows = list(db.scalars(select(StorageDeletion).order_by(StorageDeletion.id)).all())
        assert [row.attempts for row in rows] == [1, 1]
        assert all("temporary R2 failure" in row.last_error for row in rows)

    store.fail = False
    assert submission_service.drain_storage_deletions_in_background() == 2
    assert store.deleted == ["old/source.zip", "old/public.zip"]
    with SessionLocal() as db:
        assert db.scalar(select(StorageDeletion.id).limit(1)) is None


def test_replacement_defers_pending_and_old_object_deletion_to_background(client: TestClient):
    register(client, "owner")
    register(client, "player")
    _, own_id, _ = create_candidate_rows()
    set_manual_phase("submission_1")
    first = client.post(
        "/api/v1/submissions",
        data={"song_id": own_id, "track": "normal"},
        files={"file": ("first.zip", archive_bytes("First"), "application/zip")},
    )
    assert first.status_code == 200, first.text
    submission_id = first.json()["id"]
    replacement = archive_bytes("Replacement")
    created = client.post(
        "/api/v1/submissions/upload-intents",
        json={
            "submission_id": submission_id,
            "track": "normal",
            "file_name": "replacement.zip",
            "file_size": len(replacement),
            "content_type": "application/zip",
        },
    )
    assert created.status_code == 200, created.text
    intent_payload = created.json()
    assert client.put(
        intent_payload["upload_url"],
        content=replacement,
        headers=intent_payload["headers"],
    ).status_code == 204

    background_tasks = BackgroundTasks()
    with SessionLocal() as db:
        intent = db.get(SubmissionUploadIntent, intent_payload["id"])
        user = db.scalar(select(User).where(User.user_code == "player"))
        old_submission = db.get(Submission, submission_id)
        assert intent and user and old_submission and old_submission.public_storage_path
        old_keys = {old_submission.storage_path, old_submission.public_storage_path}
        pending_key = intent.object_key
        completed = _complete_intent(intent, user, db, background_tasks)
        assert completed.id == submission_id
        queued_keys = set(db.scalars(select(StorageDeletion.object_key)).all())
        assert queued_keys == old_keys | {pending_key}
        assert all((get_settings().data_dir / key).is_file() for key in queued_keys)
        assert len(background_tasks.tasks) == 1

    asyncio.run(background_tasks())
    assert all(not (get_settings().data_dir / key).exists() for key in old_keys | {pending_key})
    with SessionLocal() as db:
        assert db.scalar(select(StorageDeletion.id).limit(1)) is None


def test_async_replacement_validation_failure_keeps_old_submission(client: TestClient):
    register(client, "owner")
    register(client, "player")
    _, own_id, _ = create_candidate_rows()
    set_manual_phase("submission_1")
    first = client.post(
        "/api/v1/submissions",
        data={"song_id": own_id, "track": "normal"},
        files={"file": ("first.zip", archive_bytes("First"), "application/zip")},
    )
    assert first.status_code == 200
    submission_id = first.json()["id"]
    old_storage = first.json()["file_name"], first.json()["file_size"]
    with SessionLocal() as db:
        old_path = db.get(Submission, submission_id).storage_path

    invalid = archive_bytes(title="")
    created = client.post(
        "/api/v1/submissions/upload-intents",
        json={
            "submission_id": submission_id,
            "track": "normal",
            "file_name": "invalid-replacement.zip",
            "file_size": len(invalid),
            "content_type": "application/zip",
        },
    ).json()
    assert client.put(created["upload_url"], content=invalid, headers=created["headers"]).status_code == 204
    queued = client.post(f"/api/v1/submissions/upload-intents/{created['id']}/complete")
    assert queued.status_code == 200
    with SessionLocal() as db:
        assert db.get(Submission, submission_id).storage_path == old_path

    run_next_processing_job()
    failed = client.get(f"/api/v1/submissions/upload-intents/{created['id']}/status").json()
    assert failed["status"] == "failed"
    with SessionLocal() as db:
        retained = db.get(Submission, submission_id)
        assert retained is not None
        assert retained.storage_path == old_path
        assert (retained.file_name, retained.file_size) == old_storage
        intent = db.get(SubmissionUploadIntent, created["id"])
        assert intent is not None
        assert not (get_settings().data_dir / intent.object_key).exists()


def test_targets_phase_gate_and_j_limit(client: TestClient):
    register(client, "owner")
    register(client, "player")
    _, own_id, assigned_id = create_candidate_rows()

    targets = client.get("/api/v1/submissions/targets")
    assert targets.status_code == 200
    assert {(row["song"]["id"], row["source_kind"]) for row in targets.json()["targets"]} == {
        (own_id, "self"),
        (assigned_id, "assigned"),
    }
    closed = client.post(
        "/api/v1/submissions",
        data={"song_id": own_id, "track": "normal"},
        files={"file": ("closed.zip", archive_bytes(), "application/zip")},
    )
    assert closed.status_code == 409

    with SessionLocal() as db:
        event = db.scalar(select(Event).where(Event.is_current.is_(True)))
        event.settings.phase_mode = "manual"
        event.settings.manual_phase = "submission_1"
        db.commit()
    first = client.post(
        "/api/v1/submissions",
        data={"song_id": assigned_id, "track": "j"},
        files={"file": ("j.zip", archive_bytes("J Song", "&lv_6=15"), "application/zip")},
    )
    assert first.status_code == 200, first.text
    set_manual_phase("guess")
    first_chart = public_chart_for_submission(client, first.json()["id"])
    voted = client.post("/api/v1/guess-game/vote", json={"chart_id": first_chart["id"], "vote_type": "love"})
    assert voted.status_code == 200
    assert voted.json()["vote_counts"] == {"love": 1, "funny": 0}
    assert voted.json()["my_votes"] == ["love"]
    detail = client.get(f"/api/v1/guess-game/charts/{first_chart['id']}")
    assert detail.status_code == 200
    assert detail.json()["plays"] == first_chart["plays"] + 1
    assert client.post(
        f"/api/v1/guess-game/charts/{first_chart['id']}/comments",
        json={"content": "保留这条评论"},
    ).status_code == 200
    set_manual_phase("submission_1")

    invalid = client.post(
        "/api/v1/submissions",
        data={"song_id": own_id, "track": "j"},
        files={"file": ("invalid.zip", b"not-a-zip", "application/zip")},
    )
    assert invalid.status_code == 422
    assert client.get("/api/v1/submissions/j-track").json()["submission"]["id"] == first.json()["id"]

    second = client.post(
        "/api/v1/submissions",
        data={"song_id": own_id, "track": "j"},
        files={"file": ("j2.zip", archive_bytes("Other J", "&lv_4=13"), "application/zip")},
    )
    assert second.status_code == 409
    assert "J" in second.json()["detail"]

    targets_after = client.get("/api/v1/submissions/targets").json()["targets"]
    tracks = {
        row["song"]["id"]: row["submission"]["track"] if row["submission"] else None
        for row in targets_after
    }
    assert tracks == {assigned_id: "j", own_id: None}
    set_manual_phase("guess")
    old_chart = next(row for row in client.get("/api/v1/guess-game/charts").json() if row["id"] == first_chart["id"])
    assert old_chart["lane"] == "j"
    assert old_chart["source_submission_type"] == "j"
    assert old_chart["love_votes"] == 1
    comments = client.get(f"/api/v1/guess-game/charts/{first_chart['id']}/comments").json()
    assert [row["content"] for row in comments] == ["保留这条评论"]


def test_track_switch_without_upload_and_j_replace_does_not_duplicate_charts(client: TestClient):
    register(client, "owner")
    register(client, "player")
    _, own_id, assigned_id = create_candidate_rows()
    with SessionLocal() as db:
        event = db.scalar(select(Event).where(Event.is_current.is_(True)))
        event.settings.phase_mode = "manual"
        event.settings.manual_phase = "submission_1"
        db.commit()

    own = client.post(
        "/api/v1/submissions",
        data={"song_id": own_id, "track": "normal"},
        files={"file": ("test1.zip", archive_bytes("test1", "&lv_4=13"), "application/zip")},
    )
    assigned = client.post(
        "/api/v1/submissions",
        data={"song_id": assigned_id, "track": "normal"},
        files={"file": ("test2.zip", archive_bytes("test2", "&lv_5=14"), "application/zip")},
    )
    assert own.status_code == assigned.status_code == 200
    own_id_submission = own.json()["id"]
    assigned_id_submission = assigned.json()["id"]
    set_manual_phase("guess")
    charts = client.get("/api/v1/guess-game/charts").json()
    assert len(charts) == 2
    own_chart = public_chart_for_submission(client, own_id_submission)
    assert client.post(
        "/api/v1/guess-game/vote",
        json={"chart_id": own_chart["id"], "vote_type": "love"},
    ).status_code == 200
    set_manual_phase("submission_1")
    with SessionLocal() as db:
        original_storage = db.get(Submission, own_id_submission).storage_path

    switched = client.patch(f"/api/v1/submissions/{own_id_submission}/track", json={"track": "j"})
    assert switched.status_code == 200, switched.text
    with SessionLocal() as db:
        assert db.get(Submission, own_id_submission).storage_path == original_storage
    targets = client.get("/api/v1/submissions/targets").json()["targets"]
    assert {row["song"]["id"]: row["submission"]["track"] for row in targets} == {
        own_id: "j",
        assigned_id: "normal",
    }
    set_manual_phase("guess")
    switched_charts = client.get("/api/v1/guess-game/charts").json()
    assert len(switched_charts) == 2
    assert next(row for row in switched_charts if row["id"] == own_chart["id"])["lane"] == "j"

    set_manual_phase("submission_1")
    assert client.patch(f"/api/v1/submissions/{own_id_submission}/track", json={"track": "normal"}).status_code == 200
    assert client.patch(f"/api/v1/submissions/{assigned_id_submission}/track", json={"track": "j"}).status_code == 200
    replaced = client.post(
        f"/api/v1/submissions/{own_id_submission}/replace",
        data={"track": "normal"},
        files={"file": ("test1-new.zip", archive_bytes("test1-new", "&lv_4=13+"), "application/zip")},
    )
    assert replaced.status_code == 200, replaced.text
    set_manual_phase("guess")
    final_charts = client.get("/api/v1/guess-game/charts").json()
    assert len(final_charts) == 2
    with SessionLocal() as db:
        own_chart_ids = set(db.scalars(select(GuessChart.id).where(GuessChart.source_submission_id == own_id_submission)).all())
        assigned_chart_ids = set(db.scalars(select(GuessChart.id).where(GuessChart.source_submission_id == assigned_id_submission)).all())
    final_own = [row for row in final_charts if row["id"] in own_chart_ids]
    final_assigned = [row for row in final_charts if row["id"] in assigned_chart_ids]
    assert len(final_own) == len(final_assigned) == 1
    assert final_own[0]["id"] == own_chart["id"]
    assert final_own[0]["title"] == "test1-new"
    assert final_own[0]["lane"] == "normal"
    assert final_own[0]["love_votes"] == 1
    assert final_assigned[0]["lane"] == "j"


def test_admin_open_validation_and_draw_lock(client: TestClient):
    register(client, "owner")
    register(client, "player")
    event_id, _, assigned_id = create_candidate_rows()
    with SessionLocal() as db:
        assignment = db.scalar(select(DrawAssignment).where(DrawAssignment.event_id == event_id))
        db.delete(assignment)
        current = db.get(Event, event_id)
        current.settings.phase_mode = "manual"
        current.settings.manual_phase = "submission_1"
        db.commit()
    login_admin(client)
    event = client.get("/api/v1/events/current").json()
    payload = {"name": event["name"], **event["settings"], "participant_song_limit": 0, "audience_song_limit": 0}
    payload.pop("phase_mode")
    payload.pop("manual_phase")
    rejected = client.put("/api/v1/admin/events/current", json=payload)
    assert rejected.status_code == 400
    with SessionLocal() as db:
        player = db.scalar(select(User).where(User.user_code == "player"))
        db.add(DrawAssignment(event_id=event_id, assigned_to_id=player.id, song_id=assigned_id))
        owner = db.scalar(select(User).where(User.user_code == "owner"))
        owner_song = Song(event_id=event_id, submitted_by_id=player.id, song_name="For Owner", artist="Artist", song_type="C")
        db.add(owner_song)
        db.flush()
        db.add(DrawAssignment(event_id=event_id, assigned_to_id=owner.id, song_id=owner_song.id))
        db.commit()
    opened = client.put("/api/v1/admin/events/current", json=payload)
    assert opened.status_code == 200, opened.text
    redrawn = client.post("/api/v1/admin/draw")
    assert redrawn.status_code == 200, redrawn.text


def test_chart_batch_download_deduplicates_source(client: TestClient):
    register(client, "player")
    with SessionLocal() as db:
        event = db.scalar(select(Event).where(Event.is_current.is_(True)))
        player = db.scalar(select(User).where(User.user_code == "player"))
        song = Song(event_id=event.id, submitted_by_id=player.id, song_name="Own", artist="Artist", song_type="A")
        db.add(song)
        event.settings.phase_mode = "manual"
        event.settings.manual_phase = "submission_1"
        db.commit()
        song_id = song.id
    uploaded = client.post(
        "/api/v1/submissions",
        data={"song_id": song_id, "track": "normal"},
        files={"file": ("source.zip", archive_bytes(), "application/zip")},
    )
    assert uploaded.status_code == 200
    set_manual_phase("guess")
    chart_ids = [row["id"] for row in client.get("/api/v1/guess-game/charts").json()]
    single_chart_metadata = client.get(f"/api/v1/guess-game/charts/{chart_ids[0]}/download-metadata")
    assert single_chart_metadata.status_code == 200
    assert "自选" in single_chart_metadata.json()["file_name"]
    assert "source.zip" not in single_chart_metadata.json()["file_name"]
    single_chart_download = client.get(single_chart_metadata.json()["download_url"])
    assert single_chart_download.status_code == 200
    assert "%E8%87%AA%E9%80%89" in single_chart_download.headers["content-disposition"]

    metadata = client.get(f"/api/v1/guess-game/charts/download-metadata?ids={','.join(map(str, chart_ids))}")
    assert metadata.status_code == 200, metadata.text
    assert metadata.json()["download_url"].endswith(f"ids={'%2C'.join(map(str, chart_ids))}")
    assert metadata.json()["file_size"] > 0
    download_token = "0123456789abcdef0123456789abcdef"
    response = client.get(
        f"/api/v1/guess-game/charts/download.zip?ids={','.join(map(str, chart_ids))}"
        f"&download_token={download_token}"
    )
    assert response.status_code == 200
    assert response.headers["content-encoding"] == "identity"
    assert response.headers["x-accel-buffering"] == "no"
    assert f"zppz_download_{download_token}=1" in response.headers["set-cookie"]
    assert "Max-Age=300" in response.headers["set-cookie"]
    assert "HttpOnly" not in response.headers["set-cookie"]
    assert int(response.headers["content-length"]) == len(response.content)
    with ZipFile(BytesIO(response.content)) as archive:
        archive_names = archive.namelist()
        assert len([name for name in archive_names if name.endswith(".zip")]) == 1
        assert any("自选" in name for name in archive_names if name.endswith(".zip"))
        assert all("source.zip" not in name for name in archive_names)
    assert "_下载报告.txt" in archive_names
    invalid_token = client.get(
        f"/api/v1/guess-game/charts/download.zip?ids={chart_ids[0]}&download_token=invalid"
    )
    assert invalid_token.status_code == 422

    with SessionLocal() as db:
        chart = db.get(GuessChart, chart_ids[0])
        chart.is_self_selected = False
        db.commit()
    non_self_metadata = client.get(f"/api/v1/guess-game/charts/{chart_ids[0]}/download-metadata")
    assert non_self_metadata.status_code == 200
    assert "非自选" in non_self_metadata.json()["file_name"]

    login_admin(client)
    submission_id = uploaded.json()["id"]
    single_metadata = client.get(f"/api/v1/admin/submissions/{submission_id}/download-metadata")
    assert single_metadata.status_code == 200
    assert single_metadata.json()["file_size"] == uploaded.json()["file_size"]
    batch_metadata = client.get(f"/api/v1/admin/submissions/download-metadata?ids={submission_id}")
    assert batch_metadata.status_code == 200
    admin_token = "fedcba9876543210fedcba9876543210"
    admin_download = client.get(f"{batch_metadata.json()['download_url']}&download_token={admin_token}")
    assert admin_download.status_code == 200
    assert admin_download.headers["content-encoding"] == "identity"
    assert f"zppz_download_{admin_token}=1" in admin_download.headers["set-cookie"]
    assert int(admin_download.headers["content-length"]) == len(admin_download.content)


def test_admin_song_batch_delete_is_atomic(client: TestClient):
    register(client, "player")
    with SessionLocal() as db:
        event = db.scalar(select(Event).where(Event.is_current.is_(True)))
        player = db.scalar(select(User).where(User.user_code == "player"))
        free_song = Song(event_id=event.id, submitted_by_id=player.id, song_name="Free", artist="Artist", song_type="A")
        linked_song = Song(event_id=event.id, submitted_by_id=player.id, song_name="Linked", artist="Artist", song_type="B")
        db.add_all([free_song, linked_song])
        db.flush()
        db.add(Submission(event_id=event.id, user_id=player.id, source_song_id=linked_song.id, source_kind="self", track="normal", file_name="linked.zip", storage_path="uploads/linked.zip", file_size=1))
        db.commit()
        free_id, linked_id = free_song.id, linked_song.id

    login_admin(client)
    blocked = client.post("/api/v1/admin/song-pool/batch-delete", json={"ids": [free_id, linked_id]})
    assert blocked.status_code == 409
    with SessionLocal() as db:
        assert db.get(Song, free_id) is not None
        assert db.get(Song, linked_id) is not None

    missing = client.post("/api/v1/admin/song-pool/batch-delete", json={"ids": [free_id, 99999]})
    assert missing.status_code == 404
    with SessionLocal() as db:
        assert db.get(Song, free_id) is not None

    deleted = client.post("/api/v1/admin/song-pool/batch-delete", json={"ids": [free_id, free_id]})
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["deleted"] == 1
    with SessionLocal() as db:
        assert db.get(Song, free_id) is None
        assert db.get(Song, linked_id) is not None


def test_admin_submission_batch_delete_cleans_all_linked_resources(client: TestClient):
    register(client, "owner")
    register(client, "player")
    _, own_id, assigned_id = create_candidate_rows()
    with SessionLocal() as db:
        event = db.scalar(select(Event).where(Event.is_current.is_(True)))
        event.settings.phase_mode = "manual"
        event.settings.manual_phase = "submission_1"
        db.commit()
    first = client.post(
        "/api/v1/submissions",
        data={"song_id": own_id, "track": "normal"},
        files={"file": ("first.zip", archive_bytes("First", "&lv_4=13"), "application/zip")},
    )
    second = client.post(
        "/api/v1/submissions",
        data={"song_id": assigned_id, "track": "j"},
        files={"file": ("second.zip", archive_bytes("Second", "&lv_5=14"), "application/zip")},
    )
    assert first.status_code == second.status_code == 200
    submission_ids = [first.json()["id"], second.json()["id"]]
    set_manual_phase("guess")
    charts = client.get("/api/v1/guess-game/charts").json()
    assert client.post("/api/v1/guess-game/vote", json={"chart_id": charts[0]["id"], "vote_type": "love"}).status_code == 200
    assert client.post(f"/api/v1/guess-game/charts/{charts[0]['id']}/comments", json={"content": "cleanup"}).status_code == 200
    with SessionLocal() as db:
        rows = [db.get(Submission, item) for item in submission_ids]
        storage_files = [get_settings().data_dir / row.storage_path for row in rows]
        cover_files = [get_settings().assets_dir / "guess-covers" / Path(chart["cover_path"]).name for chart in charts]
    assert all(path.is_file() for path in storage_files)

    login_admin(client)
    missing = client.post("/api/v1/admin/submissions/batch-delete", json={"ids": [submission_ids[0], 99999]})
    assert missing.status_code == 404
    with SessionLocal() as db:
        assert db.get(Submission, submission_ids[0]) is not None

    deleted = client.post("/api/v1/admin/submissions/batch-delete", json={"ids": submission_ids})
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["deleted"] == 2
    with SessionLocal() as db:
        assert not list(db.scalars(select(Submission).where(Submission.id.in_(submission_ids))).all())
        assert not list(db.scalars(select(GuessChart).where(GuessChart.source_submission_id.in_(submission_ids))).all())
        assert db.scalar(select(GuessVote.id).limit(1)) is None
        assert db.scalar(select(GuessComment.id).limit(1)) is None
    assert all(not path.exists() for path in storage_files)
    assert all(not path.exists() for path in cover_files)


def test_admin_chart_batch_delete_is_atomic_and_preserves_submission_archive(client: TestClient):
    settings = get_settings()
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    retained_file = settings.uploads_dir / "retained-source.zip"
    retained_file.write_bytes(b"source")
    with SessionLocal() as db:
        event = db.scalar(select(Event).where(Event.is_current.is_(True)))
        admin = db.scalar(select(User).where(User.user_code == "admin"))
        song = Song(event_id=event.id, submitted_by_id=admin.id, song_name="Retained", artist="Artist", song_type="A")
        db.add(song)
        db.flush()
        storage_path = str(retained_file.relative_to(settings.data_dir)).replace("\\", "/")
        submission = Submission(event_id=event.id, user_id=admin.id, source_song_id=song.id, source_kind="self", track="normal", file_name="retained-source.zip", storage_path=storage_path, file_size=retained_file.stat().st_size)
        db.add(submission)
        db.flush()
        chart = GuessChart(event_id=event.id, title="Retained", author="Artist", designer="Designer", level="13", lane="normal", guess_group_key="retained", source_submission_type="normal", source_submission_id=submission.id, source_level_slot="4", cover_path="", storage_path=storage_path, is_self_selected=True, plays=0)
        db.add(chart)
        db.commit()
        submission_id, retained_chart_id = submission.id, chart.id

    login_admin(client)
    retained_delete = client.post("/api/v1/admin/guess-game/charts/batch-delete", json={"ids": [retained_chart_id]})
    assert retained_delete.status_code == 200, retained_delete.text
    assert retained_file.is_file()
    with SessionLocal() as db:
        assert db.get(Submission, submission_id) is not None

    imported = client.post(
        "/api/v1/admin/guess-game/charts/import",
        files={"file": ("manual.zip", archive_bytes("Manual"), "application/zip")},
    )
    assert imported.status_code == 200, imported.text
    chart_ids = [chart["id"] for chart in imported.json()["charts"]]
    archive_path = settings.data_dir / imported.json()["charts"][0]["storage_path"]
    cover_path = settings.assets_dir / "guess-covers" / Path(imported.json()["charts"][0]["cover_path"]).name

    missing = client.post("/api/v1/admin/guess-game/charts/batch-delete", json={"ids": [chart_ids[0], 99999]})
    assert missing.status_code == 404
    with SessionLocal() as db:
        assert db.get(GuessChart, chart_ids[0]) is not None
    assert archive_path.is_file()

    deleted = client.post("/api/v1/admin/guess-game/charts/batch-delete", json={"ids": chart_ids})
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["deleted"] == len(chart_ids)
    assert not archive_path.exists()
    assert not cover_path.exists()


def test_song_pool_csv_updates_in_place_and_rolls_back(client: TestClient):
    register(client, "player")
    with SessionLocal() as db:
        event = db.scalar(select(Event).where(Event.is_current.is_(True)))
        player = db.scalar(select(User).where(User.user_code == "player"))
        song = Song(event_id=event.id, submitted_by_id=player.id, song_name="Before", artist="Old", song_type="A")
        db.add(song)
        db.commit()
        song_id = song.id
    login_admin(client)
    exported = client.get("/api/v1/admin/song-pool/export.csv")
    assert exported.status_code == 200
    assert exported.content.startswith(b"\xef\xbb\xbf")
    csv_body = f"曲目ID,曲名,曲师,备注,分类\n{song_id},After,New,Updated,C\n".encode("gbk")
    imported = client.post("/api/v1/admin/song-pool/import.csv", files={"file": ("songs.csv", csv_body, "text/csv")})
    assert imported.status_code == 200, imported.text
    bad_body = f"曲目ID,曲名,曲师,分类\n{song_id},Broken,Nope,A\n99999,Missing,Nope,B\n".encode()
    rejected = client.post("/api/v1/admin/song-pool/import.csv", files={"file": ("bad.csv", bad_body, "text/csv")})
    assert rejected.status_code == 400
    with SessionLocal() as db:
        song = db.get(Song, song_id)
        assert (song.song_name, song.artist, song.remark, song.song_type) == ("After", "New", "Updated", "C")


def test_admin_archive_import_and_grouped_author_stats(client: TestClient):
    register(client, "owner")
    register(client, "guesser")
    register(client, "viewer", "audience")
    register(client, "disabled")
    with SessionLocal() as db:
        event = db.scalar(select(Event).where(Event.is_current.is_(True)))
        owner = db.scalar(select(User).where(User.user_code == "owner"))
        guesser = db.scalar(select(User).where(User.user_code == "guesser"))
        disabled = db.scalar(select(User).where(User.user_code == "disabled"))
        disabled.is_active = False
        owner_song = Song(event_id=event.id, submitted_by_id=owner.id, song_name="Owner Song", artist="Artist", song_type="A")
        guesser_song = Song(event_id=event.id, submitted_by_id=guesser.id, song_name="Guesser Song", artist="Artist", song_type="B")
        db.add_all([owner_song, guesser_song])
        event.settings.phase_mode = "manual"
        event.settings.manual_phase = "submission_1"
        db.commit()
        owner_song_id = owner_song.id
        owner_user_id = owner.id

    login(client, "owner")
    uploaded = client.post(
        "/api/v1/submissions",
        data={"song_id": owner_song_id, "track": "normal"},
        files={"file": ("owner.zip", archive_bytes("Owner Work"), "application/zip")},
    )
    assert uploaded.status_code == 200, uploaded.text
    set_manual_phase("guess")
    chart_ids = [row["id"] for row in client.get("/api/v1/guess-game/charts").json()]

    assert client.post("/api/v1/auth/logout").status_code == 200
    public_overview = client.get("/api/v1/guess-game/designer-guesses").json()
    assert public_overview["can_guess"] is False
    assert public_overview["candidates"] == []

    login_admin(client)
    admin_candidates = client.get("/api/v1/admin/guess-game/author-candidates")
    assert admin_candidates.status_code == 200, admin_candidates.text
    candidates_by_code = {row["user"]["user_code"]: row for row in admin_candidates.json()}
    assert set(candidates_by_code) == {"admin", "owner", "guesser"}
    assert all("selected" in row for row in candidates_by_code.values())
    configured = client.put(
        "/api/v1/admin/guess-game/author-candidates",
        json={"rows": [{"user_id": owner_user_id, "display_id": "P01"}]},
    )
    assert configured.status_code == 200, configured.text

    login(client, "guesser")
    overview = client.get("/api/v1/guess-game/designer-guesses")
    assert overview.status_code == 200, overview.text
    assert overview.json()["can_guess"] is True
    display_ids = {item["display_id"] for item in overview.json()["candidates"]}
    assert display_ids == {"P01"}
    assert {item["chart_id"] for item in overview.json()["states"]} == set(chart_ids)
    assert {item["guessed_user_id"] for item in overview.json()["states"]} == {None}
    owner_id = next(item["user_id"] for item in overview.json()["candidates"] if item["display_id"] == "P01")
    saved = client.put(f"/api/v1/guess-game/charts/{chart_ids[0]}/designer-guess", json={"guessed_user_id": owner_id})
    assert saved.status_code == 200
    grouped = client.get("/api/v1/guess-game/designer-guesses").json()
    assert {item["guessed_user_id"] for item in grouped["states"] if item["chart_id"] in chart_ids} == {owner_id}
    sibling_state = client.get(f"/api/v1/guess-game/charts/{chart_ids[1]}/author-guess").json()
    assert sibling_state["my_guess_user_id"] == owner_id
    assert client.delete(f"/api/v1/guess-game/charts/{chart_ids[0]}/designer-guess").status_code == 200
    cleared = client.get("/api/v1/guess-game/designer-guesses").json()
    assert {item["guessed_user_id"] for item in cleared["states"] if item["chart_id"] in chart_ids} == {None}
    assert client.put(f"/api/v1/guess-game/charts/{chart_ids[0]}/author-guess", json={"guessed_user_id": owner_id}).status_code == 200

    login_admin(client)
    stats = client.get("/api/v1/admin/guess-game/stats?scope=all&include_details=true")
    assert stats.status_code == 200, stats.text
    assert stats.json()["overview"]["counted_guesses"] == 1
    assert stats.json()["overview"]["correct_guesses"] == 1
    owner_stats = next(row for row in stats.json()["author_stats"] if row["user"]["user_code"] == "owner")
    assert owner_stats["received_guesses"] == 1
    assert owner_stats["received_correct"] == 1
    assert owner_stats["being_guessed_probability"] == 100.0

    summary = client.get("/api/v1/admin/guess-game/stats?scope=all&include_details=false")
    assert summary.status_code == 200, summary.text
    assert "guess_details" not in summary.json()
    assert summary.json()["overview"] == stats.json()["overview"]
    details = client.get("/api/v1/admin/guess-game/stats/details?scope=all&limit=1&offset=0")
    assert details.status_code == 200, details.text
    assert details.json()["total"] == 1
    assert details.json()["limit"] == 1
    assert details.json()["offset"] == 0
    assert details.json()["items"] == stats.json()["guess_details"]
    assert client.get("/api/v1/admin/guess-game/stats/details?limit=101").status_code == 422

    imported = client.post(
        "/api/v1/admin/guess-game/charts/import",
        files={"file": ("manual.zip", archive_bytes("Manual"), "application/zip")},
    )
    assert imported.status_code == 200, imported.text
    assert len(imported.json()["charts"]) == 2
    first_manual = imported.json()["charts"][0]
    second_manual = imported.json()["charts"][1]
    storage_path = first_manual["storage_path"]
    assert (get_settings().data_dir / storage_path).is_file()
    assert client.delete(f"/api/v1/admin/guess-game/charts/{first_manual['id']}").status_code == 200
    assert (get_settings().data_dir / storage_path).is_file()
    assert client.delete(f"/api/v1/admin/guess-game/charts/{second_manual['id']}").status_code == 200
    assert not (get_settings().data_dir / storage_path).exists()


def test_admin_list_and_download_can_exclude_tracks_and_mark_readme(client: TestClient):
    login_admin(client)
    settings = get_settings()
    with SessionLocal() as db:
        event = db.scalar(select(Event).where(Event.is_current.is_(True)))
        admin = db.scalar(select(User).where(User.user_code == "admin"))
        song_ids: dict[str, int] = {}
        for track in ("normal", "j", "exhibition"):
            song = Song(event_id=event.id, submitted_by_id=admin.id, song_name=track, artist="Artist", song_type="A")
            db.add(song)
            db.flush()
            song_ids[track] = song.id
        ids: dict[str, int] = {}
        for track, include_readme in (("normal", True), ("j", False), ("exhibition", False)):
            payload = archive_bytes(track)
            if include_readme:
                buffer = BytesIO(payload)
                with ZipFile(buffer, "a") as archive:
                    archive.writestr("nested/README.md", "notes")
                payload = buffer.getvalue()
            relative = f"uploads/admin-{track}.zip"
            target = settings.data_dir / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
            row = Submission(
                event_id=event.id,
                user_id=admin.id,
                source_song_id=song_ids[track],
                source_kind="self",
                track=track,
                file_name=f"{track}.zip",
                storage_path=relative,
                file_size=len(payload),
            )
            db.add(row)
            db.flush()
            ids[track] = row.id
        db.commit()

    listed = client.get("/api/v1/admin/submissions?tracks=normal,j")
    assert listed.status_code == 200, listed.text
    by_track = {item["track"]: item for item in listed.json()["items"]}
    assert set(by_track) == {"normal", "j"}
    assert by_track["normal"]["has_readme"] is True
    assert by_track["j"]["has_readme"] is False
    assert client.get("/api/v1/admin/submissions?tracks=side").status_code == 422

    downloaded = client.get(
        f"/api/v1/admin/submissions/download.zip?ids={ids['normal']},{ids['exhibition']}&tracks=normal,j"
    )
    assert downloaded.status_code == 200, downloaded.text
    with ZipFile(BytesIO(downloaded.content)) as archive:
        names = archive.namelist()
    assert len(names) == 1
    assert names[0].startswith("normal_")
