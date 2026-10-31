import json
import os

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["ADMIN_SEED_PASSWORD"] = "change-me-please"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.time import utc_now_naive
from app.db.bootstrap import seed_defaults
from app.db.session import Base, SessionLocal, engine
from app.main import app
from app.models import (
    DomainEvent,
    DrawAssignment,
    Event,
    GuessChart,
    Role,
    Song,
    SubmissionProcessingJob,
    SwapRound,
    User,
)
from app.modules.realtime.outbox import prune_domain_events
from app.modules.realtime.stream import event_visible, iter_event_stream, resolve_cursor


@pytest.fixture(autouse=True)
def sse_test_limits():
    keys = ("SSE_POLL_SECONDS", "SSE_KEEPALIVE_EVERY", "SSE_MAX_POLLS")
    previous = {key: os.environ.get(key) for key in keys}
    os.environ["SSE_POLL_SECONDS"] = "0.01"
    os.environ["SSE_KEEPALIVE_EVERY"] = "1"
    os.environ["SSE_MAX_POLLS"] = "1"
    yield
    for key, value in previous.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


@pytest.fixture(autouse=True)
def reset_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed_defaults(db)
        event = db.scalar(select(Event).where(Event.is_current.is_(True)))
        event.settings.participant_song_limit = 0
        event.settings.audience_song_limit = 0
        db.commit()


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def _user(user_code: str) -> User:
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.user_code == user_code))
        assert user is not None
        db.expunge(user)
        return user


def _event_id() -> int:
    with SessionLocal() as db:
        event = db.scalar(select(Event).where(Event.is_current.is_(True)))
        assert event is not None
        return event.id


def _add_job(user: User, job_id: str, *, status: str = "processing", stage: str = "validating") -> None:
    with SessionLocal() as db:
        db.add(
            SubmissionProcessingJob(
                id=job_id,
                event_id=_event_id(),
                user_id=user.id,
                source_storage_path=f"pending/{job_id}.zip",
                status=status,
                stage=stage,
            )
        )
        db.commit()


def _topics() -> list[str]:
    with SessionLocal() as db:
        return list(db.scalars(select(DomainEvent.topic).order_by(DomainEvent.id.asc())).all())


def register_user(client: TestClient, user_code: str) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={"user_code": user_code, "qq_id": user_code, "password": "secret123", "identity": "participant"},
    )
    assert response.status_code == 201, response.text


def login_user(client: TestClient, user_code: str) -> None:
    password = "change-me-please" if user_code == "admin" else "secret123"
    response = client.post("/api/v1/auth/login", json={"user_code": user_code, "password": password})
    assert response.status_code == 200, response.text


def read_sse(client: TestClient, *, params: dict | None = None, limit: int = 20) -> tuple[int, dict, list[dict]]:
    response = client.get("/api/v1/events", params=params)
    headers = {key.lower(): value for key, value in response.headers.items()}
    events: list[dict] = []
    if response.status_code != 200:
        return response.status_code, headers, events
    for line in response.text.splitlines():
        if line.startswith("data:"):
            events.append(json.loads(line.removeprefix("data:").strip()))
            if len(events) >= limit:
                break
    return response.status_code, headers, events


def test_invalid_session_cookie_is_rejected(client: TestClient):
    response = client.get("/api/v1/events", cookies={"zppz_session": "not-a-session"})
    assert response.status_code == 401


def test_invalid_bearer_token_is_rejected(client: TestClient):
    response = client.get("/api/v1/events", headers={"Authorization": "Bearer not-a-session"})
    assert response.status_code == 401


def test_anonymous_stream_receives_public_events_only(client: TestClient):
    _add_job(_user("admin"), "job-private")
    status, headers, events = read_sse(client, params={"after": 0}, limit=50)
    assert status == 200
    assert headers["content-type"].startswith("text/event-stream")
    assert headers["x-accel-buffering"] == "no"
    assert headers["cache-control"] == "no-cache"
    topics = {event["topic"] for event in events}
    assert "contest.updated" in topics
    assert "submission.job" not in topics
    assert all(event["scope"] == "public" for event in events)


def test_owner_receives_job_events_and_other_participants_do_not(client: TestClient):
    register_user(client, "alice")
    login_user(client, "alice")
    alice = _user("alice")
    _add_job(alice, "job-alice", status="completed", stage="complete")

    with TestClient(app) as bob:
        register_user(bob, "bob")
        login_user(bob, "bob")
        _status, _headers, bob_events = read_sse(bob, params={"after": 0}, limit=50)
    job_events = [event for event in bob_events if event["topic"] == "submission.job"]
    assert job_events == []

    status, _headers, alice_events = read_sse(client, params={"after": 0}, limit=50)
    assert status == 200
    matching = [event for event in alice_events if event["topic"] == "submission.job"]
    assert len(matching) == 1
    assert matching[0]["subject_user_id"] == alice.id
    assert matching[0]["resources"] == ["submissions"]
    assert matching[0]["payload"]["jobs"] == [{"id": "job-alice", "status": "completed", "stage": "complete"}]


def test_admin_receives_participant_job_events(client: TestClient):
    register_user(client, "alice")
    alice = _user("alice")
    _add_job(alice, "job-alice")
    login_user(client, "admin")
    _status, _headers, events = read_sse(client, params={"after": 0}, limit=50)
    matching = [event for event in events if event["topic"] == "submission.job"]
    assert len(matching) == 1
    assert matching[0]["payload"]["jobs"][0]["id"] == "job-alice"


def test_after_cursor_skips_already_seen_events(client: TestClient):
    register_user(client, "alice")
    login_user(client, "alice")
    alice = _user("alice")
    _add_job(alice, "job-old", status="queued", stage="uploaded")
    with SessionLocal() as db:
        first_id = db.scalar(select(func.max(DomainEvent.id)))
    _add_job(alice, "job-new", status="completed", stage="complete")
    _status, _headers, events = read_sse(client, params={"after": first_id}, limit=20)
    job_ids = [
        job["id"]
        for event in events
        if event["topic"] == "submission.job"
        for job in event["payload"]["jobs"]
    ]
    assert job_ids == ["job-new"]


def test_phase_draw_guess_and_swap_commits_publish_domain_events():
    with SessionLocal() as db:
        event = db.scalar(select(Event).where(Event.is_current.is_(True)))
        user = db.scalar(select(User).where(User.user_code == "admin"))
        assert event is not None and user is not None
        event.settings.phase_mode = "manual"
        event.settings.manual_phase = "guess"
        song = Song(
            event_id=event.id,
            submitted_by_id=user.id,
            song_name="song",
            artist="artist",
            song_type="A",
            remark="",
        )
        db.add(song)
        db.flush()
        db.add(
            DrawAssignment(
                event_id=event.id,
                assigned_to_id=user.id,
                song_id=song.id,
                status="active",
                draw_kind="initial",
            )
        )
        db.add(
            GuessChart(
                event_id=event.id,
                title="chart",
                author="author",
                level="13",
            )
        )
        db.add(
            SwapRound(
                event_id=event.id,
                round_number=1,
                starts_at=utc_now_naive(),
                ends_at=utc_now_naive(),
                random_seed="seed",
            )
        )
        db.commit()
    assert "contest.updated" in _topics()
    assert "draw.reveal" in _topics()
    assert "guess.state" in _topics()
    assert "swap.updated" in _topics()


def test_rolled_back_job_is_not_published():
    user = _user("admin")
    with SessionLocal() as db:
        db.add(
            SubmissionProcessingJob(
                id="job-rollback",
                event_id=_event_id(),
                user_id=user.id,
                source_storage_path="pending/rollback.zip",
                status="queued",
                stage="uploaded",
            )
        )
        db.flush()
        db.rollback()
    assert "submission.job" not in _topics()


def test_visibility_hides_user_events_from_anonymous_and_other_users():
    user_event = DomainEvent(
        id=1,
        topic="submission.job",
        scope="user",
        subject_user_id=4,
        payload_json="{}",
        created_at=utc_now_naive(),
    )
    public_event = DomainEvent(
        id=2,
        topic="guess.state",
        scope="public",
        subject_user_id=None,
        payload_json="{}",
        created_at=utc_now_naive(),
    )
    owner = User(id=4, user_code="owner", qq_id="1", password_hash="x", identity="participant")
    other = User(id=5, user_code="other", qq_id="2", password_hash="x", identity="participant")
    admin = User(id=9, user_code="root", qq_id="9", password_hash="x", identity="participant")
    admin.roles = [Role(name="admin", label="管理员")]
    authenticated = DomainEvent(
        id=3,
        topic="draw.reveal",
        scope="authenticated",
        subject_user_id=None,
        payload_json="{}",
        created_at=utc_now_naive(),
    )
    assert event_visible(public_event, None) is True
    assert event_visible(user_event, None) is False
    assert event_visible(user_event, owner) is True
    assert event_visible(user_event, other) is False
    assert event_visible(user_event, admin) is True
    assert event_visible(authenticated, None) is False
    assert event_visible(authenticated, other) is True


def test_resolve_cursor_prefers_after_then_last_event_id():
    assert resolve_cursor(4, "9") == 4
    assert resolve_cursor(None, "9") == 9
    assert resolve_cursor(None, "nope") >= 0


def test_idle_stream_emits_retry_and_keepalive():
    import asyncio

    async def collect() -> str:
        chunks: list[str] = []
        async for chunk in iter_event_stream(
            None,
            cursor=10**12,
            user_id=None,
            is_admin=False,
            credentials_presented=False,
            max_polls=1,
        ):
            chunks.append(chunk)
        return "".join(chunks)

    text = asyncio.run(collect())
    assert text.startswith("retry: 5000")
    assert ": keepalive" in text


def test_prune_keeps_the_newest_rows():
    user = _user("admin")
    for index in range(5):
        _add_job(user, f"job-{index}", status="queued", stage="uploaded")
    removed = prune_domain_events(keep=2)
    assert removed >= 1
    with SessionLocal() as db:
        remaining = list(db.scalars(select(DomainEvent.id).order_by(DomainEvent.id.asc())).all())
    assert len(remaining) == 2
    assert remaining == sorted(remaining)
