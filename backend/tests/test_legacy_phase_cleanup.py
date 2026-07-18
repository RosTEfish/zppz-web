from __future__ import annotations

from datetime import datetime, timedelta, timezone
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
from app.models import Event


LEGACY_PHASE_FIELDS = {
    "registration_deadline",
    "submission_deadline",
    "guess_game_open_at",
    "submissions_open",
    "guess_game_visible",
}
PHASES = (
    "registration",
    "submission_1",
    "submission_2",
    "guess",
)


@pytest.fixture(autouse=True)
def reset_db() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed_defaults(db)


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def _login_admin(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"user_code": "admin", "password": "change-me-please"},
    )
    assert response.status_code == 200, response.text


def _event_update_payload(event: dict) -> dict:
    settings = event["settings"]
    return {
        "name": event["name"],
        "participant_song_limit": settings["participant_song_limit"],
        "audience_song_limit": settings["audience_song_limit"],
        "draw_songs_per_participant": settings["draw_songs_per_participant"],
        "true_love_vote_limit_below_14": settings["true_love_vote_limit_below_14"],
        "true_love_vote_limit_at_least_14": settings["true_love_vote_limit_at_least_14"],
        "funny_vote_limit": settings["funny_vote_limit"],
        "announcement_text": settings["announcement_text"],
    }


def test_event_contract_omits_all_legacy_phase_fields(client: TestClient) -> None:
    current = client.get("/api/v1/events/current")
    bootstrap = client.get("/api/v1/bootstrap")

    assert current.status_code == 200
    assert bootstrap.status_code == 200
    assert LEGACY_PHASE_FIELDS.isdisjoint(current.json()["settings"])
    assert LEGACY_PHASE_FIELDS.isdisjoint(bootstrap.json()["event"]["settings"])


def test_auto_event_without_schedule_is_reported_as_registration(client: TestClient) -> None:
    with SessionLocal() as db:
        event = db.scalar(select(Event).where(Event.is_current.is_(True)))
        assert event is not None and event.settings is not None
        event.phases.clear()
        event.settings.phase_mode = "auto"
        event.settings.manual_phase = None
        db.commit()

    response = client.get("/api/v1/event/phases")

    assert response.status_code == 200
    assert response.json()["active_phase"] == "registration"
    assert response.json()["capabilities"]["submission"] is False
    assert response.json()["capabilities"]["author_guess"] is False


@pytest.mark.parametrize("legacy_field", sorted(LEGACY_PHASE_FIELDS))
def test_admin_event_update_rejects_each_legacy_field(
    client: TestClient,
    legacy_field: str,
) -> None:
    _login_admin(client)
    event = client.get("/api/v1/events/current").json()
    payload = _event_update_payload(event)
    payload[legacy_field] = True

    response = client.put("/api/v1/admin/events/current", json=payload)

    assert response.status_code == 422
    assert any(
        error["loc"][-1] == legacy_field and error["type"] == "extra_forbidden"
        for error in response.json()["detail"]
    )


@pytest.mark.parametrize("phase", PHASES)
def test_registration_remains_open_in_every_manual_phase(
    client: TestClient,
    phase: str,
) -> None:
    with SessionLocal() as db:
        event = db.scalar(select(Event).where(Event.is_current.is_(True)))
        assert event is not None and event.settings is not None
        event.settings.phase_mode = "manual"
        event.settings.manual_phase = phase
        db.commit()

    response = client.post(
        "/api/v1/auth/register",
        json={
            "user_code": f"new-{phase}",
            "qq_id": f"qq-{phase}",
            "password": "secret123",
            "identity": "audience",
        },
    )

    assert response.status_code == 201, response.text


def _migration_config(backend_root: Path) -> Config:
    config = Config(str(backend_root / "alembic.ini"))
    config.set_main_option("script_location", str(backend_root / "alembic"))
    config.set_main_option("prepend_sys_path", str(backend_root))
    return config


def _create_0008_legacy_schema(database_url: str) -> None:
    legacy_engine = sa.create_engine(database_url)
    metadata = sa.MetaData()
    sa.Table("events", metadata, sa.Column("id", sa.Integer(), primary_key=True))
    sa.Table(
        "event_settings",
        metadata,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("phase_mode", sa.String(10), nullable=False, server_default="auto"),
        sa.Column("manual_phase", sa.String(30)),
        sa.Column("registration_deadline", sa.DateTime()),
        sa.Column("submission_deadline", sa.DateTime()),
        sa.Column("guess_game_open_at", sa.DateTime()),
        sa.Column("submissions_open", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("guess_game_visible", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    sa.Table(
        "event_phases",
        metadata,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("phase", sa.String(30), nullable=False),
        sa.Column("starts_at", sa.DateTime(), nullable=False),
        sa.Column("ends_at", sa.DateTime(), nullable=False),
    )
    sa.Table(
        "alembic_version",
        metadata,
        sa.Column("version_num", sa.String(32), primary_key=True),
    )
    metadata.create_all(legacy_engine)
    with legacy_engine.begin() as connection:
        connection.execute(
            sa.text("INSERT INTO alembic_version (version_num) VALUES (:revision)"),
            {"revision": "0008_split_love_vote_quota"},
        )
    legacy_engine.dispose()


def _create_0009_phase_schema(database_url: str) -> None:
    legacy_engine = sa.create_engine(database_url)
    metadata = sa.MetaData()
    sa.Table("events", metadata, sa.Column("id", sa.Integer(), primary_key=True))
    sa.Table(
        "event_settings",
        metadata,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("phase_mode", sa.String(10), nullable=False, server_default="auto"),
        sa.Column("manual_phase", sa.String(30)),
    )
    sa.Table(
        "event_phases",
        metadata,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("phase", sa.String(30), nullable=False),
        sa.Column("starts_at", sa.DateTime(), nullable=False),
        sa.Column("ends_at", sa.DateTime(), nullable=False),
    )
    sa.Table(
        "alembic_version",
        metadata,
        sa.Column("version_num", sa.String(32), primary_key=True),
    )
    metadata.create_all(legacy_engine)
    with legacy_engine.begin() as connection:
        connection.execute(
            sa.text("INSERT INTO alembic_version (version_num) VALUES (:revision)"),
            {"revision": "0009_remove_legacy_phase_settings"},
        )
    legacy_engine.dispose()


def test_0009_sqlite_upgrade_maps_legacy_state_and_preserves_phase_managed_events(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = f"sqlite:///{(tmp_path / 'legacy.db').as_posix()}"
    _create_0008_legacy_schema(database_url)
    legacy_engine = sa.create_engine(database_url)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    rows = [
        # Legacy submission-open takes precedence over an elapsed guess timestamp.
        (1, "auto", None, True, now - timedelta(days=1)),
        (2, "auto", None, False, now - timedelta(days=1)),
        (3, "auto", None, False, now + timedelta(days=1)),
        (4, "manual", "reveal", False, None),
        (5, "auto", None, True, None),
    ]
    with legacy_engine.begin() as connection:
        for event_id, mode, manual_phase, is_open, guess_at in rows:
            connection.execute(sa.text("INSERT INTO events (id) VALUES (:id)"), {"id": event_id})
            connection.execute(
                sa.text(
                    """
                    INSERT INTO event_settings
                        (id, event_id, phase_mode, manual_phase, submissions_open,
                         guess_game_open_at, guess_game_visible)
                    VALUES
                        (:id, :event_id, :mode, :manual_phase, :is_open,
                         :guess_at, 1)
                    """
                ),
                {
                    "id": event_id,
                    "event_id": event_id,
                    "mode": mode,
                    "manual_phase": manual_phase,
                    "is_open": is_open,
                    "guess_at": guess_at,
                },
            )
        connection.execute(
            sa.text(
                """
                INSERT INTO event_phases (id, event_id, phase, starts_at, ends_at)
                VALUES (1, 5, 'submission_2', :starts_at, :ends_at)
                """
            ),
            {"starts_at": now - timedelta(hours=1), "ends_at": now + timedelta(hours=1)},
        )
    legacy_engine.dispose()

    backend_root = Path(__file__).resolve().parents[1]
    monkeypatch.setenv("DATABASE_URL", database_url)
    config = _migration_config(backend_root)
    command.upgrade(config, "0009_remove_legacy_phase_settings")

    migrated_engine = sa.create_engine(database_url)
    with migrated_engine.connect() as connection:
        settings = {
            row.event_id: (row.phase_mode, row.manual_phase)
            for row in connection.execute(
                sa.text(
                    "SELECT event_id, phase_mode, manual_phase FROM event_settings ORDER BY event_id"
                )
            )
        }
        columns = {
            column["name"] for column in sa.inspect(connection).get_columns("event_settings")
        }
    assert settings == {
        1: ("manual", "submission_1"),
        2: ("manual", "guess"),
        3: ("manual", "registration"),
        4: ("manual", "reveal"),
        5: ("auto", None),
    }
    assert LEGACY_PHASE_FIELDS.isdisjoint(columns)

    command.downgrade(config, "0008_split_love_vote_quota")
    with migrated_engine.connect() as connection:
        restored_columns = {
            column["name"]: column
            for column in sa.inspect(connection).get_columns("event_settings")
        }
        restored_defaults = connection.execute(
            sa.text(
                "SELECT submissions_open, guess_game_visible FROM event_settings WHERE event_id = 1"
            )
        ).one()
    assert LEGACY_PHASE_FIELDS.issubset(restored_columns)
    assert restored_defaults == (False, True)
    migrated_engine.dispose()


def test_0010_sqlite_upgrade_removes_retired_phases_and_releases_manual_override(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = f"sqlite:///{(tmp_path / 'retired-phases.db').as_posix()}"
    _create_0009_phase_schema(database_url)
    legacy_engine = sa.create_engine(database_url)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    with legacy_engine.begin() as connection:
        for event_id, mode, manual_phase in (
            (1, "manual", "reveal"),
            (2, "manual", "closed"),
            (3, "manual", "guess"),
            (4, "auto", None),
        ):
            connection.execute(sa.text("INSERT INTO events (id) VALUES (:id)"), {"id": event_id})
            connection.execute(
                sa.text(
                    """
                    INSERT INTO event_settings (id, event_id, phase_mode, manual_phase)
                    VALUES (:id, :id, :mode, :manual_phase)
                    """
                ),
                {"id": event_id, "mode": mode, "manual_phase": manual_phase},
            )
        for row_id, event_id, phase in (
            (1, 1, "reveal"),
            (2, 1, "guess"),
            (3, 2, "closed"),
            (4, 3, "submission_2"),
        ):
            connection.execute(
                sa.text(
                    """
                    INSERT INTO event_phases (id, event_id, phase, starts_at, ends_at)
                    VALUES (:id, :event_id, :phase, :starts_at, :ends_at)
                    """
                ),
                {
                    "id": row_id,
                    "event_id": event_id,
                    "phase": phase,
                    "starts_at": now - timedelta(hours=1),
                    "ends_at": now + timedelta(hours=1),
                },
            )
    legacy_engine.dispose()

    backend_root = Path(__file__).resolve().parents[1]
    monkeypatch.setenv("DATABASE_URL", database_url)
    config = _migration_config(backend_root)
    command.upgrade(config, "0010_remove_reveal_closed_phases")

    migrated_engine = sa.create_engine(database_url)
    with migrated_engine.connect() as connection:
        settings = {
            row.event_id: (row.phase_mode, row.manual_phase)
            for row in connection.execute(
                sa.text(
                    "SELECT event_id, phase_mode, manual_phase FROM event_settings ORDER BY event_id"
                )
            )
        }
        phase_rows = list(
            connection.execute(
                sa.text("SELECT event_id, phase FROM event_phases ORDER BY id")
            )
        )
    assert settings == {
        1: ("auto", None),
        2: ("auto", None),
        3: ("manual", "guess"),
        4: ("auto", None),
    }
    assert phase_rows == [(1, "guess"), (3, "submission_2")]

    command.downgrade(config, "0009_remove_legacy_phase_settings")
    with migrated_engine.connect() as connection:
        assert list(
            connection.execute(
                sa.text("SELECT event_id, phase FROM event_phases ORDER BY id")
            )
        ) == [(1, "guess"), (3, "submission_2")]
    migrated_engine.dispose()
