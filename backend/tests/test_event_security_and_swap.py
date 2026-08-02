from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
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
    GuessComment,
    GuessVote,
    Song,
    SwapRequest,
    User,
)
from app.modules.events.phase_policy import get_phase_status
from app.schemas import EventUpdate


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


def create_single_swap_case(client: TestClient, player_code: str) -> int:
    register(client, player_code)
    register(client, f"{player_code}-owner")
    with SessionLocal() as db:
        event = db.scalar(select(Event).where(Event.is_current.is_(True)))
        player = db.scalar(select(User).where(User.user_code == player_code))
        owner = db.scalar(select(User).where(User.user_code == f"{player_code}-owner"))
        assert event and player and owner and event.settings
        original = Song(event_id=event.id, submitted_by_id=owner.id, song_name="Original", artist="Artist", song_type="A")
        db.add(original)
        db.flush()
        assignment = DrawAssignment(event_id=event.id, assigned_to_id=player.id, song_id=original.id)
        db.add(assignment)
        now = datetime.utcnow()
        db.add(EventPhase(event_id=event.id, phase="submission_2", starts_at=now - timedelta(hours=1), ends_at=now + timedelta(hours=1)))
        event.settings.phase_mode = "manual"
        event.settings.manual_phase = "submission_2"
        db.commit()
        return assignment.id


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
        event.settings.manual_phase = "guess"
        overridden = get_phase_status(db, event, now=now)
        assert overridden.active_phase == "guess"
        assert overridden.capabilities.normal_submission_public is True
        assert overridden.capabilities.author_guess is True
        assert overridden.next_transition_at is None

        event.settings.phase_mode = "auto"
        event.settings.manual_phase = None
        gap = get_phase_status(db, event, now=now + timedelta(hours=1, minutes=30))
        assert gap.active_phase is None
        assert not any(gap.capabilities.as_dict().values())

        after_guess = get_phase_status(db, event, now=now + timedelta(hours=4))
        assert after_guess.active_phase is None
        assert after_guess.capabilities.normal_submission_public is True
        assert after_guess.capabilities.author_guess is False
        assert after_guess.capabilities.quality_vote is False


def test_phase_schedule_is_idempotent_and_restore_auto_is_always_available(client: TestClient):
    login(client, "admin", "change-me-please")
    now = datetime.now(timezone.utc).replace(microsecond=0)
    windows = [
        {
            "phase": "registration",
            "starts_at": (now - timedelta(hours=2)).isoformat(),
            "ends_at": (now - timedelta(hours=1)).isoformat(),
        },
        {
            "phase": "guess",
            "starts_at": (now + timedelta(hours=1)).isoformat(),
            "ends_at": (now + timedelta(hours=2)).isoformat(),
        },
    ]
    manual_payload = {
        "phase_mode": "manual",
        "manual_phase": "submission_1",
        "phases": windows,
    }

    first = client.put("/api/v1/admin/event/phases", json=manual_payload)
    assert first.status_code == 200, first.text
    first_ids = {row["phase"]: row["id"] for row in first.json()["phases"]}

    repeated = client.put("/api/v1/admin/event/phases", json=manual_payload)
    assert repeated.status_code == 200, repeated.text
    assert {row["phase"]: row["id"] for row in repeated.json()["phases"]} == first_ids

    restored = client.put(
        "/api/v1/admin/event/phases",
        json={"phase_mode": "auto", "manual_phase": None, "phases": windows},
    )
    assert restored.status_code == 200, restored.text
    assert restored.json()["phase_mode"] == "auto"
    assert restored.json()["manual_phase"] is None
    assert {row["phase"]: row["id"] for row in restored.json()["phases"]} == first_ids

    with SessionLocal() as db:
        event = db.scalar(select(Event).where(Event.is_current.is_(True)))
        assert event
        rows = list(db.scalars(select(EventPhase).where(EventPhase.event_id == event.id)))
        assert len(rows) == len(windows)


@pytest.mark.parametrize("removed_phase", ["reveal", "closed", "draw", "swap"])
def test_phase_schedule_rejects_removed_phase_names(client: TestClient, removed_phase: str):
    login(client, "admin", "change-me-please")
    now = datetime.now(timezone.utc)
    response = client.put(
        "/api/v1/admin/event/phases",
        json={
            "phase_mode": "manual",
            "manual_phase": removed_phase,
            "phases": [
                {
                    "phase": removed_phase,
                    "starts_at": now.isoformat(),
                    "ends_at": (now + timedelta(hours=1)).isoformat(),
                }
            ],
        },
    )
    assert response.status_code == 422


def test_phase_policy_auto_without_schedule_defaults_to_registration():
    with SessionLocal() as db:
        event = db.scalar(select(Event).where(Event.is_current.is_(True)))
        event.phases.clear()
        event.settings.phase_mode = "auto"
        event.settings.manual_phase = None
        status = get_phase_status(db, event)
        assert status.active_phase == "registration"
        assert status.capabilities.song_pool_edit is True
        assert status.capabilities.submission is False


def test_event_update_rejects_removed_legacy_phase_fields():
    payload = {
        "name": "Event",
        "participant_song_limit": 5,
        "audience_song_limit": 3,
        "draw_songs_per_participant": 1,
        "true_love_vote_limit_below_14": 3,
        "true_love_vote_limit_at_least_14": 3,
        "funny_vote_limit": 3,
        "announcement_text": "",
        "submissions_open": True,
    }
    with pytest.raises(ValidationError, match="extra_forbidden"):
        EventUpdate.model_validate(payload)


def test_hidden_normal_chart_cannot_be_enumerated_or_accessed_anonymously(client: TestClient):
    normal_id, j_id = create_chart_pair()
    set_manual_phase("registration")

    listed = client.get("/api/v1/guess-game/charts")
    assert listed.status_code == 200
    assert [row["id"] for row in listed.json()] == [j_id]
    assert client.get(f"/api/v1/guess-game/charts/{normal_id}").status_code == 404
    assert client.get(f"/api/v1/guess-game/charts/{normal_id}/download-metadata").status_code == 404
    assert client.get(f"/api/v1/guess-game/charts/{normal_id}/comments").status_code == 404

    public_j = client.get(f"/api/v1/guess-game/charts/{j_id}")
    assert public_j.status_code == 200
    assert {
        "source_submission_id",
        "storage_path",
    }.isdisjoint(public_j.json())
    assert public_j.json()["designer"] == "J designer"


def test_logged_in_user_can_comment_on_any_public_chart_before_guess_phase(client: TestClient):
    register(client, "public-commenter", identity="audience")
    normal_id, j_id = create_chart_pair()
    set_manual_phase("registration")
    login(client, "public-commenter")

    listed = client.get("/api/v1/guess-game/charts")
    assert listed.status_code == 200
    assert listed.json()[0]["id"] == j_id
    assert listed.json()[0]["can_comment"] is True

    created = client.post(
        f"/api/v1/guess-game/charts/{j_id}/comments",
        json={"content": "公开后就可以评论"},
    )
    assert created.status_code == 200, created.text
    comments = client.get(f"/api/v1/guess-game/charts/{j_id}/comments")
    assert comments.status_code == 200
    assert [row["content"] for row in comments.json()] == ["公开后就可以评论"]

    assert client.post(
        f"/api/v1/guess-game/charts/{normal_id}/comments",
        json={"content": "尚未公开"},
    ).status_code == 404


def test_exhibition_chart_cannot_receive_quality_votes(client: TestClient):
    register(client, "viewer")
    with SessionLocal() as db:
        event = db.scalar(select(Event).where(Event.is_current.is_(True)))
        viewer = db.scalar(select(User).where(User.user_code == "viewer"))
        assert event and viewer
        chart = GuessChart(
            event_id=event.id,
            title="Exhibition",
            author="Artist",
            designer="Exhibition designer",
            level="13",
            lane="exhibition",
            guess_group_key="exhibition",
            source_submission_type="exhibition",
            source_submission_id=103,
            source_level_slot="4",
            cover_path="",
            storage_path="uploads/private/exhibition.zip",
            is_self_selected=False,
        )
        db.add(chart)
        db.commit()
        chart_id = chart.id
        db.add(GuessVote(chart_id=chart_id, user_id=viewer.id, vote_type="love"))
        db.commit()
    set_manual_phase("guess")
    login(client, "viewer")

    listed = client.get("/api/v1/guess-game/charts")
    assert listed.status_code == 200, listed.text
    exhibition = next(row for row in listed.json() if row["id"] == chart_id)
    assert exhibition["designer"] == "Exhibition designer"
    assert exhibition["can_vote"] is False
    assert exhibition["love_votes"] == 0
    assert exhibition["my_votes"] == []
    payload = {"chart_id": chart_id, "vote_type": "love"}
    assert client.post("/api/v1/guess-game/vote", json=payload).status_code == 403
    assert client.request("DELETE", "/api/v1/guess-game/vote", json=payload).status_code == 403


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


def test_guess_history_stays_visible_and_comments_stay_open_after_guess_deadline(client: TestClient):
    register(client, "candidate-history")
    register(client, "viewer-history", identity="audience")
    normal_id, _ = create_chart_pair()
    with SessionLocal() as db:
        event = db.scalar(select(Event).where(Event.is_current.is_(True)))
        candidate = db.scalar(select(User).where(User.user_code == "candidate-history"))
        viewer = db.scalar(select(User).where(User.user_code == "viewer-history"))
        assert event and event.settings and candidate and viewer
        db.add(GuessAuthorCandidate(event_id=event.id, user_id=candidate.id, display_id="P99"))
        db.add(GuessVote(chart_id=normal_id, user_id=viewer.id, vote_type="love"))
        db.add(GuessComment(chart_id=normal_id, user_id=viewer.id, content="kept comment"))
        db.add(
            GuessAuthorGuess(
                chart_id=normal_id,
                user_id=viewer.id,
                guessed_user_id=candidate.id,
            )
        )
        now = datetime.utcnow()
        db.add(
            EventPhase(
                event_id=event.id,
                phase="guess",
                starts_at=now - timedelta(hours=2),
                ends_at=now - timedelta(hours=1),
            )
        )
        event.settings.phase_mode = "auto"
        event.settings.manual_phase = None
        db.commit()
        candidate_id = candidate.id

    login(client, "viewer-history")
    phases = client.get("/api/v1/event/phases")
    assert phases.status_code == 200
    assert phases.json()["active_phase"] is None
    assert phases.json()["capabilities"]["normal_submission_public"] is True
    assert phases.json()["capabilities"]["quality_vote"] is False

    charts = client.get("/api/v1/guess-game/charts")
    assert charts.status_code == 200
    normal = next(row for row in charts.json() if row["id"] == normal_id)
    assert normal["love_votes"] == 1
    assert normal["my_votes"] == ["love"]
    assert normal["can_vote"] is False
    assert normal["can_comment"] is True
    assert normal["can_author_guess"] is False

    comments = client.get(f"/api/v1/guess-game/charts/{normal_id}/comments")
    assert comments.status_code == 200
    assert [row["content"] for row in comments.json()] == ["kept comment"]
    guesses = client.get("/api/v1/guess-game/designer-guesses")
    assert guesses.status_code == 200
    assert guesses.json()["can_guess"] is False
    assert guesses.json()["candidates"] == [{"user_id": candidate_id, "display_id": "P99"}]
    state = next(row for row in guesses.json()["states"] if row["chart_id"] == normal_id)
    assert state["guessed_user_id"] == candidate_id

    vote_payload = {"chart_id": normal_id, "vote_type": "love"}
    assert client.post("/api/v1/guess-game/vote", json=vote_payload).status_code == 409
    assert client.request("DELETE", "/api/v1/guess-game/vote", json=vote_payload).status_code == 409
    created_comment = client.post(
        f"/api/v1/guess-game/charts/{normal_id}/comments",
        json={"content": "new comment"},
    )
    assert created_comment.status_code == 200, created_comment.text
    guess_payload = {"guessed_user_id": candidate_id}
    assert client.put(
        f"/api/v1/guess-game/charts/{normal_id}/designer-guess",
        json=guess_payload,
    ).status_code == 409
    assert client.delete(
        f"/api/v1/guess-game/charts/{normal_id}/designer-guess"
    ).status_code == 409


@pytest.mark.skip(reason="replaced by continuous Stage2 roll coverage")
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
        db.add(EventPhase(event_id=event.id, phase="submission_2", starts_at=now - timedelta(hours=1), ends_at=now + timedelta(hours=1)))
        event.settings.phase_mode = "manual"
        event.settings.manual_phase = "submission_2"
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


@pytest.mark.skip(reason="legacy cancel endpoint is covered as 410 compatibility")
def test_participant_can_cancel_swap_request_and_finish_empty_round(client: TestClient):
    assignment_id = create_single_swap_case(client, "cancel-player")
    login(client, "cancel-player")
    saved = client.put("/api/v1/swap/me", json={"assignment_ids": [assignment_id]})
    assert saved.status_code == 200, saved.text

    cancelled = client.delete("/api/v1/swap/me")
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["request"]["status"] == "cancelled"
    assert cancelled.json()["request"]["assignment_ids"] == []

    login(client, "admin", "change-me-please")
    validation = client.post("/api/v1/admin/swap/validate")
    assert validation.status_code == 200
    assert validation.json()["valid"] is True
    finalized = client.post("/api/v1/admin/swap/finalize")
    assert finalized.status_code == 200, finalized.text
    assert finalized.json()["round"]["status"] == "finalized"


@pytest.mark.skip(reason="legacy admin mutation endpoints are covered as 410 compatibility")
def test_admin_can_reject_blocking_swap_request_and_finalize_round(client: TestClient):
    assignment_id = create_single_swap_case(client, "reject-player")
    login(client, "reject-player")
    saved = client.put("/api/v1/swap/me", json={"assignment_ids": [assignment_id]})
    assert saved.status_code == 200, saved.text
    request_id = saved.json()["request"]["id"]

    login(client, "admin", "change-me-please")
    validation = client.post("/api/v1/admin/swap/validate")
    assert validation.status_code == 200
    assert validation.json()["valid"] is False

    rejected = client.post(f"/api/v1/admin/swap/requests/{request_id}/reject")
    assert rejected.status_code == 200, rejected.text
    row = next(item for item in rejected.json()["requests"] if item["id"] == request_id)
    assert row["status"] == "rejected"
    assert row["error_message"] == "管理员驳回申请"

    validation_after_reject = client.post("/api/v1/admin/swap/validate")
    assert validation_after_reject.status_code == 200
    assert validation_after_reject.json()["valid"] is True
    finalized = client.post("/api/v1/admin/swap/finalize")
    assert finalized.status_code == 200, finalized.text
    assert finalized.json()["round"]["status"] == "finalized"

    with SessionLocal() as db:
        request = db.scalar(select(SwapRequest).where(SwapRequest.id == request_id))
        assert request and request.status == "rejected"


@pytest.mark.skip(reason="legacy rejection flow is replaced by continuous Stage2 rolls")
def test_rejected_swap_request_does_not_block_redraw_or_login(client: TestClient):
    assignment_id = create_single_swap_case(client, "redraw-player")
    login(client, "redraw-player")
    saved = client.put("/api/v1/swap/me", json={"assignment_ids": [assignment_id]})
    assert saved.status_code == 200, saved.text
    request_id = saved.json()["request"]["id"]

    login(client, "admin", "change-me-please")
    rejected = client.post(f"/api/v1/admin/swap/requests/{request_id}/reject")
    assert rejected.status_code == 200, rejected.text
    finalized = client.post("/api/v1/admin/swap/finalize")
    assert finalized.status_code == 200, finalized.text

    with SessionLocal() as db:
        event = db.scalar(select(Event).where(Event.is_current.is_(True)))
        assert event and event.settings
        event.settings.participant_song_limit = 0
        event.settings.audience_song_limit = 0
        db.commit()
    set_manual_phase("draw")

    login(client, "redraw-player")
    drawn = client.post("/api/v1/draw/me")
    assert drawn.status_code == 200, drawn.text
    assert len(drawn.json()) == 1

    login(client, "redraw-player")
    with SessionLocal() as db:
        old_assignment = db.get(DrawAssignment, assignment_id)
        assert old_assignment and old_assignment.status == "returned"
