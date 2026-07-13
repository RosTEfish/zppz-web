from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.bootstrap import seed_defaults
from app.db.session import Base, SessionLocal, engine
from app.main import app
from app.models import (
    DrawAssignment,
    Event,
    EventPhase,
    GuessAuthorCandidate,
    GuessAuthorGuess,
    GuessChart,
    Song,
    User,
)
from app.modules.events.phase_policy import get_phase_status


@pytest.fixture(autouse=True)
def reset_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed_defaults(db)


@pytest.fixture
def client():
    with TestClient(app) as value:
        yield value


def register(client: TestClient, code: str, identity: str = "participant") -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={"user_code": code, "qq_id": code, "password": "secret123", "identity": identity},
    )
    assert response.status_code == 201, response.text


def login(client: TestClient, code: str, password: str = "secret123") -> None:
    response = client.post("/api/v1/auth/login", json={"user_code": code, "password": password})
    assert response.status_code == 200, response.text


def set_manual_phase(phase: str) -> None:
    with SessionLocal() as db:
        event = db.scalar(select(Event).where(Event.is_current.is_(True)))
        assert event and event.settings
        event.settings.phase_mode = "manual"
        event.settings.manual_phase = phase
        db.commit()


def create_chart_pair() -> tuple[int, int]:
    with SessionLocal() as db:
        event = db.scalar(select(Event).where(Event.is_current.is_(True)))
        assert event
        normal = GuessChart(
            event_id=event.id,
            title="Hidden normal",
            author="Artist",
            designer="Secret designer",
            level="13",
            lane="normal",
            guess_group_key="normal",
            source_submission_type="normal",
            source_submission_id=101,
            source_level_slot="4",
            cover_path="/api/v1/assets/guess-covers/normal.png",
            storage_path="uploads/private/original.zip",
            is_self_selected=False,
        )
        j_chart = GuessChart(
            event_id=event.id,
            title="Public J",
            author="Artist",
            designer="J designer",
            level="14",
            lane="j",
            guess_group_key="j",
            source_submission_type="j",
            source_submission_id=102,
            source_level_slot="5",
            cover_path="/api/v1/assets/guess-covers/j.png",
            storage_path="uploads/private/j-original.zip",
            is_self_selected=True,
        )
        db.add_all([normal, j_chart])
        db.commit()
        return normal.id, j_chart.id


def test_phase_policy_auto_boundaries_and_manual_override():
    now = datetime(2026, 7, 13, 4, tzinfo=timezone.utc)
    with SessionLocal() as db:
        event = db.scalar(select(Event).where(Event.is_current.is_(True)))
        assert event and event.settings
        event.phases.extend(
            [
                EventPhase(event_id=event.id, phase="submission_1", starts_at=now - timedelta(hours=1), ends_at=now + timedelta(hours=1)),
                EventPhase(event_id=event.id, phase="guess", starts_at=now + timedelta(hours=2), ends_at=now + timedelta(hours=3)),
            ]
        )
        db.flush()

        automatic = get_phase_status(db, event, now=now)
        assert automatic.active_phase == "submission_1"
        assert automatic.capabilities.submission is True
        assert automatic.capabilities.normal_submission_public is False
        assert automatic.next_transition_at == now + timedelta(hours=1)

        event.settings.phase_mode = "manual"
        event.settings.manual_phase = "reveal"
        overridden = get_phase_status(db, event, now=now)
        assert overridden.active_phase == "reveal"
        assert overridden.capabilities.answers_visible is True
        assert overridden.next_transition_at is None


def test_hidden_normal_chart_cannot_be_enumerated_or_accessed_anonymously(client: TestClient):
    normal_id, j_id = create_chart_pair()
    set_manual_phase("registration")

    listed = client.get("/api/v1/guess-game/charts")
    assert listed.status_code == 200
    assert [row["id"] for row in listed.json()] == [j_id]
    assert client.get(f"/api/v1/guess-game/charts/{normal_id}").status_code == 404
    assert client.get(f"/api/v1/guess-game/charts/{normal_id}/download-metadata").status_code == 404
    assert client.get(f"/api/v1/guess-game/charts/{normal_id}/comments").status_code == 409

    public_j = client.get(f"/api/v1/guess-game/charts/{j_id}")
    assert public_j.status_code == 200
    assert {
        "designer",
        "source_submission_id",
        "storage_path",
    }.isdisjoint(public_j.json())


def test_audience_can_guess_normal_but_not_j_and_anonymous_cannot_write(client: TestClient):
    register(client, "candidate")
    register(client, "viewer", identity="audience")
    normal_id, j_id = create_chart_pair()
    with SessionLocal() as db:
        event = db.scalar(select(Event).where(Event.is_current.is_(True)))
        candidate = db.scalar(select(User).where(User.user_code == "candidate"))
        assert event and candidate
        db.add(GuessAuthorCandidate(event_id=event.id, user_id=candidate.id, display_id="P01"))
        db.commit()
        candidate_id = candidate.id
    set_manual_phase("guess")

    assert client.post("/api/v1/auth/logout").status_code == 200
    anonymous = client.put(
        f"/api/v1/guess-game/charts/{normal_id}/designer-guess",
        json={"guessed_user_id": candidate_id},
    )
    assert anonymous.status_code == 401

    login(client, "viewer")
    overview = client.get("/api/v1/guess-game/designer-guesses")
    assert overview.status_code == 200
    assert overview.json()["can_guess"] is True
    assert overview.json()["candidates"] == [{"user_id": candidate_id, "display_id": "P01"}]
    saved = client.put(
        f"/api/v1/guess-game/charts/{normal_id}/designer-guess",
        json={"guessed_user_id": candidate_id},
    )
    assert saved.status_code == 200, saved.text
    with SessionLocal() as db:
        guess = db.scalar(select(GuessAuthorGuess).where(GuessAuthorGuess.user_id != candidate_id))
        assert guess and guess.guessed_user_id == candidate_id

    rejected = client.put(
        f"/api/v1/guess-game/charts/{j_id}/designer-guess",
        json={"guessed_user_id": candidate_id},
    )
    assert rejected.status_code == 403


def test_swap_finalize_is_idempotent_and_never_returns_same_or_self_submitted_song(client: TestClient):
    register(client, "player")
    register(client, "owner")
    register(client, "other")
    with SessionLocal() as db:
        event = db.scalar(select(Event).where(Event.is_current.is_(True)))
        player = db.scalar(select(User).where(User.user_code == "player"))
        owner = db.scalar(select(User).where(User.user_code == "owner"))
        other = db.scalar(select(User).where(User.user_code == "other"))
        assert event and player and owner and other and event.settings
        original = Song(event_id=event.id, submitted_by_id=owner.id, song_name="Original A", artist="A", song_type="A")
        original_b = Song(event_id=event.id, submitted_by_id=owner.id, song_name="Original B", artist="A", song_type="A")
        own = Song(event_id=event.id, submitted_by_id=player.id, song_name="Own", artist="A", song_type="A")
        eligible = Song(event_id=event.id, submitted_by_id=other.id, song_name="Eligible A", artist="A", song_type="A")
        eligible_b = Song(event_id=event.id, submitted_by_id=other.id, song_name="Eligible B", artist="A", song_type="A")
        db.add_all([original, original_b, own, eligible, eligible_b])
        db.flush()
        assignment = DrawAssignment(event_id=event.id, assigned_to_id=player.id, song_id=original.id)
        assignment_b = DrawAssignment(event_id=event.id, assigned_to_id=player.id, song_id=original_b.id)
        db.add_all([assignment, assignment_b])
        now = datetime.utcnow()
        db.add(EventPhase(event_id=event.id, phase="swap", starts_at=now - timedelta(hours=1), ends_at=now + timedelta(hours=1)))
        event.settings.phase_mode = "manual"
        event.settings.manual_phase = "swap"
        db.commit()
        assignment_ids = [assignment.id, assignment_b.id]
        returned_song_ids = {original.id, original_b.id}
        own_id = own.id
        eligible_ids = {eligible.id, eligible_b.id}

    login(client, "player")
    saved = client.put("/api/v1/swap/me", json={"assignment_ids": assignment_ids})
    assert saved.status_code == 200, saved.text
    login(client, "admin", "change-me-please")
    assert client.post("/api/v1/admin/swap/validate").json()["valid"] is True
    first = client.post("/api/v1/admin/swap/finalize")
    second = client.post("/api/v1/admin/swap/finalize")
    assert first.status_code == second.status_code == 200

    with SessionLocal() as db:
        old_assignments = [db.get(DrawAssignment, assignment_id) for assignment_id in assignment_ids]
        replacements = list(
            db.scalars(select(DrawAssignment).where(DrawAssignment.replaces_assignment_id.in_(assignment_ids)))
        )
        assert all(old and old.status == "returned" for old in old_assignments)
        assert len(replacements) == 2
        replacement_song_ids = {row.song_id for row in replacements}
        assert replacement_song_ids.isdisjoint(returned_song_ids | {own_id})
        assert replacement_song_ids == eligible_ids
