from datetime import datetime, timedelta
import json
from pathlib import Path
import shutil

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.security import hash_password
from app.db.bootstrap import seed_defaults
from app.db.session import Base, SessionLocal, engine
from app.main import app
from app.models import (
    DrawAssignment,
    Event,
    EventPhase,
    EventSetting,
    GuessAuthorCandidate,
    GuessAuthorGuess,
    GuessChart,
    GuessComment,
    GuessVote,
    ImportIssue,
    JTrackSubmission,
    Role,
    Song,
    Submission,
    SwapRequest,
    SwapRequestItem,
    SwapRound,
    User,
    UserSession,
)
from app.core.config import get_settings


@pytest.fixture(autouse=True)
def reset_db_and_files():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed_defaults(db)
    settings = get_settings()
    shutil.rmtree(settings.uploads_dir, ignore_errors=True)
    shutil.rmtree(settings.assets_dir / "guess-covers", ignore_errors=True)
    (settings.data_dir / "permissions.json").unlink(missing_ok=True)
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    (settings.assets_dir / "guess-covers").mkdir(parents=True, exist_ok=True)
    yield
    shutil.rmtree(settings.uploads_dir, ignore_errors=True)
    shutil.rmtree(settings.assets_dir / "guess-covers", ignore_errors=True)
    (settings.assets_dir / "rules" / "shared.pdf").unlink(missing_ok=True)
    (settings.data_dir / "permissions.json").unlink(missing_ok=True)


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def login_admin(client: TestClient) -> None:
    response = client.post("/api/v1/auth/login", json={"user_code": "admin", "password": "change-me-please"})
    assert response.status_code == 200, response.text


def create_reset_fixture() -> tuple[int, int, int, int]:
    with SessionLocal() as db:
        event = db.scalar(select(Event).where(Event.is_current.is_(True)))
        roles = {role.name: role for role in db.scalars(select(Role)).all()}
        assert event and event.settings
        event.name = "保留名称"
        event.slug = "keep-slug"
        event.settings.submissions_open = True
        event.settings.phase_mode = "auto"
        event.settings.manual_phase = None

        admin_two = User(
            user_code="admin-two",
            qq_id="admin-two",
            password_hash=hash_password("secret123"),
            identity="participant",
            display_name="Second admin",
            roles=[roles["admin"]],
        )
        player = User(
            user_code="player",
            qq_id="player",
            password_hash=hash_password("secret123"),
            identity="participant",
            display_name="Player",
            roles=[roles["participant"]],
        )
        editor = User(
            user_code="editor",
            qq_id="editor",
            password_hash=hash_password("secret123"),
            identity="audience",
            display_name="Editor",
            roles=[roles["pool_editor"]],
        )
        db.add_all([admin_two, player, editor])
        db.flush()

        original_song = Song(event_id=event.id, submitted_by_id=player.id, song_name="Original", artist="Artist", song_type="A")
        replacement_song = Song(event_id=event.id, submitted_by_id=player.id, song_name="Replacement", artist="Artist", song_type="A")
        db.add_all([original_song, replacement_song])
        db.flush()
        original_assignment = DrawAssignment(event_id=event.id, assigned_to_id=player.id, song_id=original_song.id)
        replacement_assignment = DrawAssignment(event_id=event.id, assigned_to_id=player.id, song_id=replacement_song.id)
        db.add_all([original_assignment, replacement_assignment])
        db.flush()

        swap_round = SwapRound(
            event_id=event.id,
            round_number=1,
            starts_at=datetime.utcnow(),
            ends_at=datetime.utcnow() + timedelta(hours=1),
            random_seed="seed",
        )
        db.add(swap_round)
        db.flush()
        swap_request = SwapRequest(round_id=swap_round.id, user_id=player.id, status="pending")
        db.add(swap_request)
        db.flush()
        db.add(
            SwapRequestItem(
                request_id=swap_request.id,
                original_assignment_id=original_assignment.id,
                replacement_assignment_id=replacement_assignment.id,
                position=0,
            )
        )

        submission = Submission(
            event_id=event.id,
            user_id=player.id,
            source_song_id=original_song.id,
            source_kind="self",
            track="normal",
            file_name="submission.zip",
            storage_path=f"events/{event.id}/submission.zip",
            public_storage_path=f"events/{event.id}/public.zip",
            file_size=10,
        )
        db.add(submission)
        db.add(JTrackSubmission(event_id=event.id, user_id=player.id, file_name="j.zip", storage_path=f"events/{event.id}/j.zip", file_size=10))
        db.flush()

        chart = GuessChart(
            event_id=event.id,
            title="Chart",
            author="Artist",
            designer="Designer",
            level="13",
            lane="normal",
            guess_group_key="group",
            source_submission_type="normal",
            source_submission_id=submission.id,
            source_level_slot="4",
            cover_path="/api/v1/assets/guess-covers/chart.png",
            storage_path=f"events/{event.id}/chart.zip",
        )
        db.add(chart)
        db.flush()
        db.add_all(
            [
                GuessVote(chart_id=chart.id, user_id=player.id, vote_type="love"),
                GuessComment(chart_id=chart.id, user_id=player.id, content="comment"),
                GuessAuthorCandidate(event_id=event.id, user_id=player.id, display_id="P01"),
                GuessAuthorGuess(chart_id=chart.id, user_id=player.id, guessed_user_id=admin_two.id),
                ImportIssue(event_id=event.id, source_type="submission", source_id=submission.id, file_name="submission.zip", issue_type="warning", message="issue"),
            ]
        )
        db.add(
            EventPhase(
                event_id=event.id,
                phase="guess",
                starts_at=datetime.utcnow(),
                ends_at=datetime.utcnow() + timedelta(hours=1),
            )
        )

        other_event = Event(name="Old", slug="old", is_current=False, settings=EventSetting())
        db.add(other_event)
        db.flush()
        db.add(UserSession(user_id=player.id, token_hash="player-session", expires_at=datetime.utcnow() + timedelta(hours=1)))
        db.commit()

        settings = get_settings()
        event_file_dir = settings.uploads_dir / "events" / str(event.id)
        event_file_dir.mkdir(parents=True, exist_ok=True)
        (event_file_dir / "submission.zip").write_bytes(b"submission")
        (settings.assets_dir / "guess-covers" / "chart.png").write_bytes(b"cover")
        (settings.assets_dir / "rules" / "shared.pdf").write_bytes(b"shared")
        (settings.data_dir / "permissions.json").write_text(
            json.dumps({"users": [{"user_code": "admin"}, {"user_code": "player"}]}, ensure_ascii=False),
            encoding="utf-8",
        )
        return event.id, event_file_dir, original_song.id, chart.id


def test_reset_requires_exact_confirmation_without_mutating_data(client: TestClient):
    event_id, _, song_id, _ = create_reset_fixture()
    login_admin(client)

    response = client.post("/api/v1/admin/reset", json={"confirmation": "清除当前赛事"})

    assert response.status_code == 400
    with SessionLocal() as db:
        assert db.get(Song, song_id) is not None
        assert db.get(Event, event_id) is not None


def test_pool_editor_cannot_reset(client: TestClient):
    with SessionLocal() as db:
        roles = {role.name: role for role in db.scalars(select(Role)).all()}
        editor = User(
            user_code="editor-only",
            qq_id="editor-only",
            password_hash=hash_password("secret123"),
            identity="audience",
            display_name="Editor",
            roles=[roles["pool_editor"]],
        )
        db.add(editor)
        db.commit()

    response = client.post("/api/v1/auth/login", json={"user_code": "editor-only", "password": "secret123"})
    assert response.status_code == 200
    response = client.post("/api/v1/admin/reset", json={"confirmation": "清除全部数据"})

    assert response.status_code == 403


def test_reset_clears_business_data_preserves_admin_and_shared_resources(client: TestClient):
    event_id, _, _, _ = create_reset_fixture()
    login_admin(client)

    response = client.post("/api/v1/admin/reset", json={"confirmation": "清除全部数据"})

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["event_id"] == event_id
    assert payload["event_name"] == "保留名称"
    assert payload["event_slug"] == "keep-slug"
    with SessionLocal() as db:
        current = db.scalar(select(Event).where(Event.is_current.is_(True)))
        assert current and current.id == event_id
        assert current.name == "保留名称"
        assert current.slug == "keep-slug"
        assert current.settings.phase_mode == "manual"
        assert current.settings.manual_phase == "registration"
        assert current.settings.submissions_open is False
        assert current.phases == []
        assert db.scalar(select(func.count()).select_from(Event)) == 1
        assert db.scalar(select(func.count()).select_from(Song)) == 0
        assert db.scalar(select(func.count()).select_from(DrawAssignment)) == 0
        assert db.scalar(select(func.count()).select_from(SwapRound)) == 0
        assert db.scalar(select(func.count()).select_from(SwapRequest)) == 0
        assert db.scalar(select(func.count()).select_from(SwapRequestItem)) == 0
        assert db.scalar(select(func.count()).select_from(Submission)) == 0
        assert db.scalar(select(func.count()).select_from(JTrackSubmission)) == 0
        assert db.scalar(select(func.count()).select_from(GuessChart)) == 0
        assert db.scalar(select(func.count()).select_from(GuessVote)) == 0
        assert db.scalar(select(func.count()).select_from(GuessComment)) == 0
        assert db.scalar(select(func.count()).select_from(GuessAuthorCandidate)) == 0
        assert db.scalar(select(func.count()).select_from(GuessAuthorGuess)) == 0
        assert db.scalar(select(func.count()).select_from(ImportIssue)) == 0
        assert db.scalar(select(func.count()).select_from(UserSession)) == 0
        users = list(db.scalars(select(User).order_by(User.user_code)).all())
        assert {user.user_code for user in users} == {"admin", "admin-two"}
        assert all(user.has_role("admin") for user in users)

    settings = get_settings()
    events_dir = settings.uploads_dir / "events"
    assert events_dir.exists()
    assert not list(events_dir.rglob("*"))
    assert not list((settings.assets_dir / "guess-covers").iterdir())
    assert (settings.assets_dir / "rules" / "shared.pdf").read_bytes() == b"shared"
    permissions = json.loads((settings.data_dir / "permissions.json").read_text(encoding="utf-8"))
    assert permissions["users"] == [{"user_code": "admin"}]


def test_reset_is_idempotent_after_admin_logs_in_again(client: TestClient):
    create_reset_fixture()
    login_admin(client)
    first = client.post("/api/v1/admin/reset", json={"confirmation": "清除全部数据"})
    assert first.status_code == 200, first.text

    login_admin(client)
    second = client.post("/api/v1/admin/reset", json={"confirmation": "清除全部数据"})

    assert second.status_code == 200, second.text
