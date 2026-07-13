from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, inspect, select, text

from app.db.bootstrap import seed_defaults
from app.db.session import Base, SessionLocal, engine
from app.main import app
from app.models import Event, EventSetting, GuessChart, GuessVote, User
from app.modules.guess_game.vote_quota import love_vote_bucket


@pytest.fixture(autouse=True)
def reset_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed_defaults(db)


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def register(client: TestClient, code: str = "quota-viewer") -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "user_code": code,
            "qq_id": code,
            "password": "secret123",
            "identity": "audience",
        },
    )
    assert response.status_code == 201, response.text


def create_chart(
    *,
    event_id: int,
    title: str,
    level: str,
    submission_type: str = "normal",
) -> GuessChart:
    return GuessChart(
        event_id=event_id,
        title=title,
        author="Artist",
        designer="Designer",
        level=level,
        lane="j" if submission_type == "j" else submission_type,
        guess_group_key=title.lower(),
        source_submission_type=submission_type,
        source_submission_id=None,
        source_level_slot="4",
        cover_path="",
        storage_path="",
        is_self_selected=False,
    )


def configure_guess_phase(*, below_limit: int = 1, at_least_limit: int = 1) -> dict[str, int]:
    with SessionLocal() as db:
        event = db.scalar(select(Event).where(Event.is_current.is_(True)))
        assert event and event.settings
        event.settings.phase_mode = "manual"
        event.settings.manual_phase = "guess"
        event.settings.true_love_vote_limit_below_14 = below_limit
        event.settings.true_love_vote_limit_at_least_14 = at_least_limit
        charts = [
            create_chart(event_id=event.id, title="Below A", level="13+"),
            create_chart(event_id=event.id, title="Below J", level="12", submission_type="j"),
            create_chart(event_id=event.id, title="Upper A", level="14"),
            create_chart(event_id=event.id, title="Upper J", level="15", submission_type="j"),
            create_chart(event_id=event.id, title="Exhibition", level="13", submission_type="exhibition"),
        ]
        db.add_all(charts)
        db.commit()
        return {chart.title: chart.id for chart in charts}


@pytest.mark.parametrize(
    ("level", "expected"),
    [
        ("13", "below_14"),
        ("13+", "below_14"),
        ("13.999", "below_14"),
        ("[13+]", "below_14"),
        ("１３＋", "below_14"),
        ("14", "at_least_14"),
        ("14+", "at_least_14"),
        ("14.0", "at_least_14"),
        ("宴", "at_least_14"),
    ],
)
def test_love_vote_bucket_boundaries(level: str, expected: str):
    assert love_vote_bucket(level) == expected


def test_vote_buckets_are_independent_and_mutations_return_quota(client: TestClient):
    register(client)
    charts = configure_guess_phase()

    initial = client.get("/api/v1/guess-game/vote-quota")
    assert initial.status_code == 200, initial.text
    assert initial.json() == {
        "below_14": {"used": 0, "limit": 1, "remaining": 1},
        "at_least_14": {"used": 0, "limit": 1, "remaining": 1},
    }

    below_vote = client.post(
        "/api/v1/guess-game/vote",
        json={"chart_id": charts["Below A"], "vote_type": "love"},
    )
    assert below_vote.status_code == 200, below_vote.text
    assert set(below_vote.json()) == {"message", "vote_counts", "my_votes", "love_vote_quota"}
    assert below_vote.json()["vote_counts"] == {"love": 1, "funny": 0}
    assert below_vote.json()["my_votes"] == ["love"]
    assert below_vote.json()["love_vote_quota"] == {
        "below_14": {"used": 1, "limit": 1, "remaining": 0},
        "at_least_14": {"used": 0, "limit": 1, "remaining": 1},
    }

    duplicate = client.post(
        "/api/v1/guess-game/vote",
        json={"chart_id": charts["Below A"], "vote_type": "love"},
    )
    assert duplicate.status_code == 200, duplicate.text
    assert duplicate.json()["vote_counts"] == {"love": 1, "funny": 0}
    assert duplicate.json()["love_vote_quota"] == below_vote.json()["love_vote_quota"]

    below_over_limit = client.post(
        "/api/v1/guess-game/vote",
        json={"chart_id": charts["Below J"], "vote_type": "love"},
    )
    assert below_over_limit.status_code == 400

    upper_vote = client.post(
        "/api/v1/guess-game/vote",
        json={"chart_id": charts["Upper J"], "vote_type": "love"},
    )
    assert upper_vote.status_code == 200, upper_vote.text
    assert upper_vote.json()["love_vote_quota"] == {
        "below_14": {"used": 1, "limit": 1, "remaining": 0},
        "at_least_14": {"used": 1, "limit": 1, "remaining": 0},
    }
    assert client.post(
        "/api/v1/guess-game/vote",
        json={"chart_id": charts["Upper A"], "vote_type": "love"},
    ).status_code == 400

    unvoted = client.request(
        "DELETE",
        "/api/v1/guess-game/vote",
        json={"chart_id": charts["Below A"], "vote_type": "love"},
    )
    assert unvoted.status_code == 200, unvoted.text
    assert unvoted.json()["love_vote_quota"]["below_14"] == {
        "used": 0,
        "limit": 1,
        "remaining": 1,
    }
    assert client.post(
        "/api/v1/guess-game/vote",
        json={"chart_id": charts["Below J"], "vote_type": "love"},
    ).status_code == 200


def test_quota_lowering_keeps_votes_and_allows_unvote(client: TestClient):
    register(client)
    charts = configure_guess_phase(below_limit=2)
    payload = {"chart_id": charts["Below A"], "vote_type": "love"}
    assert client.post("/api/v1/guess-game/vote", json=payload).status_code == 200

    with SessionLocal() as db:
        event = db.scalar(select(Event).where(Event.is_current.is_(True)))
        assert event and event.settings
        event.settings.true_love_vote_limit_below_14 = 0
        db.commit()

    quota = client.get("/api/v1/guess-game/vote-quota")
    assert quota.status_code == 200
    assert quota.json()["below_14"] == {"used": 1, "limit": 0, "remaining": 0}
    assert client.post(
        "/api/v1/guess-game/vote",
        json={"chart_id": charts["Below J"], "vote_type": "love"},
    ).status_code == 400

    removed = client.request("DELETE", "/api/v1/guess-game/vote", json=payload)
    assert removed.status_code == 200, removed.text
    assert removed.json()["love_vote_quota"]["below_14"] == {
        "used": 0,
        "limit": 0,
        "remaining": 0,
    }


def test_quota_uses_current_event_only_and_tracks_current_chart_level(client: TestClient):
    register(client)
    charts = configure_guess_phase(below_limit=2, at_least_limit=2)
    current_payload = {"chart_id": charts["Below A"], "vote_type": "love"}
    assert client.post("/api/v1/guess-game/vote", json=current_payload).status_code == 200

    with SessionLocal() as db:
        viewer = db.scalar(select(User).where(User.user_code == "quota-viewer"))
        current_chart = db.get(GuessChart, charts["Below A"])
        assert viewer and current_chart
        other_event = Event(name="Other", slug="other", is_current=False, settings=EventSetting())
        db.add(other_event)
        db.flush()
        other_chart = create_chart(event_id=other_event.id, title="Other Below", level="12")
        db.add(other_chart)
        db.flush()
        db.add(GuessVote(chart_id=other_chart.id, user_id=viewer.id, vote_type="love"))
        current_chart.level = "14"
        db.commit()

    quota = client.get("/api/v1/guess-game/vote-quota")
    assert quota.status_code == 200, quota.text
    assert quota.json() == {
        "below_14": {"used": 0, "limit": 2, "remaining": 2},
        "at_least_14": {"used": 1, "limit": 2, "remaining": 1},
    }


def test_j_is_votable_exhibition_is_not_and_chart_contract_has_bucket(client: TestClient):
    register(client)
    charts = configure_guess_phase(below_limit=2, at_least_limit=2)

    listed = client.get("/api/v1/guess-game/charts")
    assert listed.status_code == 200, listed.text
    buckets = {row["title"]: row["love_vote_bucket"] for row in listed.json()}
    assert buckets["Below A"] == "below_14"
    assert buckets["Upper J"] == "at_least_14"
    assert buckets["Exhibition"] == "below_14"

    assert client.post(
        "/api/v1/guess-game/vote",
        json={"chart_id": charts["Upper J"], "vote_type": "love"},
    ).status_code == 200
    exhibition = client.post(
        "/api/v1/guess-game/vote",
        json={"chart_id": charts["Exhibition"], "vote_type": "love"},
    )
    assert exhibition.status_code == 403

    settings = client.get("/api/v1/events/current")
    assert settings.status_code == 200
    settings_payload = settings.json()["settings"]
    assert settings_payload["true_love_vote_limit_below_14"] == 2
    assert settings_payload["true_love_vote_limit_at_least_14"] == 2
    assert "true_love_vote_limit" not in settings_payload


def _load_quota_migration():
    path = Path(__file__).parents[1] / "alembic" / "versions" / "0008_split_love_vote_quota.py"
    spec = spec_from_file_location("test_migration_0008_split_love_vote_quota", path)
    assert spec and spec.loader
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_sqlite_migration_resets_new_buckets_and_removes_legacy_column(tmp_path: Path):
    migration_engine = create_engine(f"sqlite:///{tmp_path / 'quota-migration.db'}")
    migration = _load_quota_migration()

    with migration_engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE event_settings ("
                "id INTEGER PRIMARY KEY, "
                "event_id INTEGER NOT NULL UNIQUE, "
                "true_love_vote_limit INTEGER NOT NULL"
                ")"
            )
        )
        connection.execute(
            text(
                "INSERT INTO event_settings (id, event_id, true_love_vote_limit) "
                "VALUES (1, 1, 17)"
            )
        )
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()

        upgraded_columns = {column["name"] for column in inspect(connection).get_columns("event_settings")}
        assert "true_love_vote_limit" not in upgraded_columns
        assert {
            "true_love_vote_limit_below_14",
            "true_love_vote_limit_at_least_14",
        }.issubset(upgraded_columns)
        assert connection.execute(
            text(
                "SELECT true_love_vote_limit_below_14, "
                "true_love_vote_limit_at_least_14 FROM event_settings"
            )
        ).one() == (3, 3)

        migration.downgrade()
        downgraded_columns = {column["name"] for column in inspect(connection).get_columns("event_settings")}
        assert "true_love_vote_limit" in downgraded_columns
        assert "true_love_vote_limit_below_14" not in downgraded_columns
        assert "true_love_vote_limit_at_least_14" not in downgraded_columns
        assert connection.execute(text("SELECT true_love_vote_limit FROM event_settings")).scalar_one() == 3

    migration_engine.dispose()
