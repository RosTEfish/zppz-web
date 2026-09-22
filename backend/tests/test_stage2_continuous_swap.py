from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from alembic import command
from alembic.config import Config
import pytest
from fastapi.testclient import TestClient
import sqlalchemy as sa
from sqlalchemy import select

from app.db.bootstrap import seed_defaults
from app.db.session import Base, SessionLocal, engine
from app.main import app
from app.models import DrawAssignment, Event, EventPhase, EventSetting, Song, Submission, SwapExcludedSong, SwapRequest, SwapRound, User


@pytest.fixture(autouse=True)
def reset_db() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed_defaults(db)
        event = db.scalar(select(Event).where(Event.is_current.is_(True)))
        assert event and event.settings
        event.settings.participant_song_limit = 0
        event.settings.audience_song_limit = 0
        db.commit()


@pytest.fixture
def client() -> TestClient:
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


def set_phase(phase: str) -> None:
    with SessionLocal() as db:
        event = db.scalar(select(Event).where(Event.is_current.is_(True)))
        assert event and event.settings
        event.settings.phase_mode = "manual"
        event.settings.manual_phase = phase
        if phase in {"submission_2", "submission_buffer"}:
            now = datetime.utcnow()
            existing = {row.phase for row in event.phases}
            if "submission_2" not in existing:
                db.add(
                    EventPhase(
                        event_id=event.id,
                        phase="submission_2",
                        starts_at=now - timedelta(hours=2),
                        ends_at=now - timedelta(hours=1) if phase == "submission_buffer" else now + timedelta(hours=1),
                    )
                )
            if phase == "submission_buffer" and "submission_buffer" not in existing:
                db.add(
                    EventPhase(
                        event_id=event.id,
                        phase="submission_buffer",
                        starts_at=now - timedelta(hours=1),
                        ends_at=now + timedelta(hours=1),
                    )
                )
        db.commit()


def add_song(db, event_id: int, user_id: int, name: str) -> Song:
    song = Song(event_id=event_id, submitted_by_id=user_id, song_name=name, artist="Artist", song_type="A", remark="")
    db.add(song)
    db.flush()
    return song


def create_complete_allocation(*, per_user: int = 1, free_songs: int = 0) -> dict[str, list[int] | int]:
    with SessionLocal() as db:
        event = db.scalar(select(Event).where(Event.is_current.is_(True)))
        admin = db.scalar(select(User).where(User.user_code == "admin"))
        player = db.scalar(select(User).where(User.user_code == "player"))
        other = db.scalar(select(User).where(User.user_code == "other"))
        assert event and admin and player and other and event.settings
        event.settings.draw_songs_per_participant = per_user
        users = [admin, player, other]
        songs = [add_song(db, event.id, users[index % len(users)].id, f"Song {index + 1}") for index in range(per_user * len(users) + free_songs)]
        assignments: dict[str, list[int]] = {user.user_code: [] for user in users}
        cursor = 0
        for user in users:
            for _ in range(per_user):
                assignment = DrawAssignment(event_id=event.id, assigned_to_id=user.id, song_id=songs[cursor].id)
                db.add(assignment)
                db.flush()
                assignments[user.user_code].append(assignment.id)
                cursor += 1
        db.commit()
        return {**assignments, "free_song_ids": [song.id for song in songs[cursor:]]}


def create_song_pool() -> None:
    with SessionLocal() as db:
        event = db.scalar(select(Event).where(Event.is_current.is_(True)))
        users = [
            db.scalar(select(User).where(User.user_code == code))
            for code in ("admin", "player", "other")
        ]
        assert event and all(users)
        for user in users:
            for suffix in ("A", "B"):
                add_song(db, event.id, user.id, f"{user.user_code}-{suffix}")
        db.commit()


def test_auto_global_draw_is_idempotent_and_admin_can_redraw_before_submission(client: TestClient) -> None:
    register(client, "player")
    register(client, "other")
    create_song_pool()
    set_phase("submission_1")

    login(client, "player")
    first = client.get("/api/v1/draw/results")
    second = client.get("/api/v1/draw/results")
    assert first.status_code == second.status_code == 200
    assert [row["id"] for row in first.json()] == [row["id"] for row in second.json()]

    login(client, "admin", "change-me-please")
    redraw = client.post("/api/v1/admin/draw")
    assert redraw.status_code == 200, redraw.text
    with SessionLocal() as db:
        event = db.scalar(select(Event).where(Event.is_current.is_(True)))
        assert event
        all_rows = list(db.scalars(select(DrawAssignment).where(DrawAssignment.event_id == event.id)).all())
        assert len(all_rows) == 6
        assert sum(row.status == "active" for row in all_rows) == 3
        assert sum(row.status == "returned" for row in all_rows) == 3


def test_global_redraw_is_locked_once_any_submission_exists(client: TestClient) -> None:
    register(client, "player")
    register(client, "other")
    allocation = create_complete_allocation()
    set_phase("submission_1")
    login(client, "player")
    assert client.get("/api/v1/draw/results").status_code == 200

    with SessionLocal() as db:
        event = db.scalar(select(Event).where(Event.is_current.is_(True)))
        player = db.scalar(select(User).where(User.user_code == "player"))
        assert event and player
        db.add(
            Submission(
                event_id=event.id,
                user_id=player.id,
                source_song_id=allocation["player"][0],
                source_kind="assigned",
                track="normal",
                file_name="chart.zip",
                storage_path="uploads/chart.zip",
                file_size=1,
            )
        )
        db.commit()

    login(client, "admin", "change-me-please")
    blocked = client.post("/api/v1/admin/draw")
    assert blocked.status_code == 409
    with SessionLocal() as db:
        event = db.scalar(select(Event).where(Event.is_current.is_(True)))
        assert event
        assert len(list(db.scalars(select(DrawAssignment).where(DrawAssignment.event_id == event.id)).all())) == 3


def test_auto_global_draw_repairs_partial_legacy_allocation_without_deleting_history(client: TestClient) -> None:
    register(client, "player")
    register(client, "other")
    allocation = create_complete_allocation()
    with SessionLocal() as db:
        partial = db.get(DrawAssignment, allocation["player"][0])
        assert partial is not None
        partial.status = "returned"
        db.commit()
    set_phase("submission_1")
    login(client, "player")

    response = client.get("/api/v1/draw/results")
    assert response.status_code == 200, response.text
    with SessionLocal() as db:
        event = db.scalar(select(Event).where(Event.is_current.is_(True)))
        assert event
        rows = list(db.scalars(select(DrawAssignment).where(DrawAssignment.event_id == event.id)).all())
        assert len(rows) == 6
        assert sum(row.status == "active" for row in rows) == 3


def test_legacy_personal_draw_endpoint_is_read_only_compatibility(client: TestClient) -> None:
    register(client, "viewer", identity="audience")
    set_phase("submission_1")
    login(client, "viewer")
    response = client.post("/api/v1/draw/me")
    assert response.status_code == 410


def test_stage2_supports_return_only_without_drawing_replacement(client: TestClient) -> None:
    register(client, "player")
    register(client, "other")
    allocation = create_complete_allocation(per_user=4, free_songs=0)
    set_phase("submission_2")
    login(client, "player")

    before = client.get("/api/v1/swap/me")
    assert before.status_code == 200, before.text
    assert len(before.json()["assignments"]) == 4

    response = client.post(
        "/api/v1/swap/me/roll",
        json={"assignment_ids": allocation["player"][:2], "mode": "return_only"},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert len(payload["assignments"]) == 2
    assert len(payload["last_roll"]["items"]) == 2
    assert all(item["replacement"] is None for item in payload["last_roll"]["items"])

    with SessionLocal() as db:
        event = db.scalar(select(Event).where(Event.is_current.is_(True)))
        player = db.scalar(select(User).where(User.user_code == "player"))
        assert event and player
        active_count = len(
            list(
                db.scalars(
                    select(DrawAssignment).where(
                        DrawAssignment.event_id == event.id,
                        DrawAssignment.assigned_to_id == player.id,
                        DrawAssignment.status == "active",
                    )
                ).all()
            )
        )
        assert active_count == 2
        excluded_count = len(
            list(db.scalars(select(SwapExcludedSong).where(SwapExcludedSong.user_id == player.id)).all())
        )
        assert excluded_count == 2


def test_stage2_return_only_does_not_require_pool_candidates(client: TestClient) -> None:
    register(client, "player")
    register(client, "other")
    allocation = create_complete_allocation(per_user=1, free_songs=0)
    set_phase("submission_2")
    login(client, "player")

    response = client.post(
        "/api/v1/swap/me/roll",
        json={"assignment_ids": allocation["player"], "mode": "return_only"},
    )
    assert response.status_code == 200, response.text
    assert len(response.json()["assignments"]) == 0


def test_stage2_supports_arbitrary_and_repeated_rolls(client: TestClient) -> None:
    register(client, "player")
    register(client, "other")
    allocation = create_complete_allocation(per_user=4, free_songs=12)
    set_phase("submission_2")
    login(client, "player")

    first = client.post("/api/v1/swap/me/roll", json={"assignment_ids": allocation["player"]})
    assert first.status_code == 200, first.text
    assert len(first.json()["last_roll"]["items"]) == 4
    replacement_ids = [row["id"] for row in first.json()["assignments"]]

    second = client.post("/api/v1/swap/me/roll", json={"assignment_ids": replacement_ids})
    assert second.status_code == 200, second.text
    assert len(second.json()["last_roll"]["items"]) == 4
    with SessionLocal() as db:
        event = db.scalar(select(Event).where(Event.is_current.is_(True)))
        player = db.scalar(select(User).where(User.user_code == "player"))
        assert event and player
        assert db.scalar(select(SwapRequest.id).where(SwapRequest.user_id == player.id).order_by(SwapRequest.id.desc())) is not None
        assert len(list(db.scalars(select(SwapExcludedSong).where(SwapExcludedSong.user_id == player.id)).all())) == 8


def test_stage2_rejects_submitted_song_and_legacy_write_endpoints(client: TestClient) -> None:
    register(client, "player")
    register(client, "other")
    allocation = create_complete_allocation()
    set_phase("submission_2")
    login(client, "player")

    with SessionLocal() as db:
        event = db.scalar(select(Event).where(Event.is_current.is_(True)))
        player = db.scalar(select(User).where(User.user_code == "player"))
        assert event and player
        db.add(
            Submission(
                event_id=event.id,
                user_id=player.id,
                source_song_id=allocation["player"][0],
                source_kind="assigned",
                track="normal",
                file_name="chart.zip",
                storage_path="uploads/chart.zip",
                file_size=1,
            )
        )
        db.commit()

    blocked = client.post("/api/v1/swap/me/roll", json={"assignment_ids": allocation["player"]})
    assert blocked.status_code == 409
    assert client.put("/api/v1/swap/me", json={"assignment_ids": allocation["player"]}).status_code == 410
    assert client.delete("/api/v1/swap/me").status_code == 410

    login(client, "admin", "change-me-please")
    assert client.post("/api/v1/admin/swap/validate").status_code == 410
    assert client.post("/api/v1/admin/swap/finalize").status_code == 410
    assert client.post("/api/v1/admin/swap/requests/1/reject").status_code == 410


def test_stage2_roll_can_reuse_another_participants_returned_song(client: TestClient) -> None:
    register(client, "player")
    register(client, "other")
    allocation = create_complete_allocation(per_user=1, free_songs=1)
    set_phase("submission_2")
    login(client, "player")
    first = client.post("/api/v1/swap/me/roll", json={"assignment_ids": allocation["player"]})
    assert first.status_code == 200, first.text
    player_replacement = first.json()["assignments"][0]["song"]["id"]

    login(client, "other")
    second = client.post("/api/v1/swap/me/roll", json={"assignment_ids": allocation["other"]})
    assert second.status_code == 200, second.text
    assert second.json()["assignments"][0]["song"]["id"] != player_replacement


def test_stage2_roll_is_rejected_after_deadline(client: TestClient) -> None:
    register(client, "player")
    register(client, "other")
    allocation = create_complete_allocation()
    with SessionLocal() as db:
        event = db.scalar(select(Event).where(Event.is_current.is_(True)))
        assert event
        now = datetime.utcnow()
        db.add(EventPhase(event_id=event.id, phase="submission_2", starts_at=now - timedelta(hours=2), ends_at=now - timedelta(hours=1)))
        event.settings.phase_mode = "auto"
        event.settings.manual_phase = None
        db.commit()

    login(client, "player")
    response = client.post("/api/v1/swap/me/roll", json={"assignment_ids": allocation["player"]})
    assert response.status_code == 409


def test_submission_buffer_extends_continuous_swap_deadline(client: TestClient) -> None:
    register(client, "player")
    register(client, "other")
    allocation = create_complete_allocation(free_songs=1)
    now = datetime.utcnow().replace(microsecond=0)
    buffer_end = now + timedelta(hours=2)
    with SessionLocal() as db:
        event = db.scalar(select(Event).where(Event.is_current.is_(True)))
        assert event and event.settings
        db.add(
            EventPhase(
                event_id=event.id,
                phase="submission_2",
                starts_at=now - timedelta(hours=3),
                ends_at=now - timedelta(hours=1),
            )
        )
        db.add(
            EventPhase(
                event_id=event.id,
                phase="submission_buffer",
                starts_at=now - timedelta(minutes=30),
                ends_at=buffer_end,
            )
        )
        event.settings.phase_mode = "manual"
        event.settings.manual_phase = "submission_buffer"
        db.commit()

    login(client, "player")
    response = client.post("/api/v1/swap/me/roll", json={"assignment_ids": allocation["player"]})
    assert response.status_code == 200, response.text

    with SessionLocal() as db:
        event = db.scalar(select(Event).where(Event.is_current.is_(True)))
        assert event
        round_row = db.scalar(
            select(SwapRound).where(
                SwapRound.event_id == event.id,
                SwapRound.round_kind == "continuous",
                SwapRound.status == "open",
            )
        )
        assert round_row is not None
        assert round_row.roll_ends_at == buffer_end


def test_0014_preserves_legacy_windows_and_merges_stage2(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    database_url = f"sqlite:///{(tmp_path / 'stage2-migration.db').as_posix()}"
    legacy_engine = sa.create_engine(database_url)
    Base.metadata.create_all(bind=legacy_engine)
    now = datetime.utcnow().replace(microsecond=0)
    with SessionLocal(bind=legacy_engine) as db:
        event = Event(name="Migration event", slug="migration-event", is_current=True)
        event.settings = EventSetting(
            participant_song_limit=0,
            audience_song_limit=0,
            draw_songs_per_participant=1,
            phase_mode="manual",
            manual_phase="swap",
        )
        event.phases = [
            EventPhase(event=event, phase="draw", starts_at=now - timedelta(days=3), ends_at=now - timedelta(days=2)),
            EventPhase(event=event, phase="swap", starts_at=now - timedelta(hours=3), ends_at=now + timedelta(hours=2)),
            EventPhase(event=event, phase="submission_2", starts_at=now - timedelta(hours=1), ends_at=now + timedelta(hours=1)),
        ]
        event.swap_rounds = []
        db.add(event)
        db.flush()
        db.add(
            SwapRound(
                event_id=event.id,
                round_number=1,
                starts_at=now - timedelta(hours=3),
                ends_at=now - timedelta(hours=2),
                random_seed="legacy-seed",
                round_kind="continuous",
            )
        )
        db.commit()
    with legacy_engine.begin() as connection:
        connection.execute(sa.text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)"))
        connection.execute(sa.text("INSERT INTO alembic_version (version_num) VALUES ('0013_ban_parser_version')"))

    monkeypatch.setenv("DATABASE_URL", database_url)
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "alembic"))
    config.set_main_option("prepend_sys_path", str(Path(__file__).resolve().parents[1]))
    command.upgrade(config, "head")

    with legacy_engine.connect() as connection:
        phases = list(connection.execute(sa.text("SELECT phase, starts_at, ends_at FROM event_phases ORDER BY phase")))
        snapshots = list(connection.execute(sa.text("SELECT original_phase, starts_at, ends_at FROM event_phase_snapshots ORDER BY source_id")))
        round_row = connection.execute(sa.text("SELECT round_kind, roll_ends_at FROM swap_rounds")).one()
        setting = connection.execute(sa.text("SELECT manual_phase FROM event_settings")).scalar_one()
    assert [row[0] for row in phases] == ["submission_2"]
    assert datetime.fromisoformat(str(phases[0][1])) == now - timedelta(hours=3)
    assert datetime.fromisoformat(str(phases[0][2])) == now + timedelta(hours=1)
    assert [row[0] for row in snapshots] == ["draw", "swap", "submission_2"]
    assert round_row[0] == "legacy"
    assert setting == "submission_2"
    legacy_engine.dispose()
