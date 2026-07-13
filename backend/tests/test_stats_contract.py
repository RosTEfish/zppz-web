import pytest

from app.db.bootstrap import seed_defaults
from app.db.session import Base, SessionLocal, engine
from app.models import Event, GuessAuthorGuess, GuessChart, Song, Submission, User
from app.modules.guess_game.stats import build_guess_stats


@pytest.fixture(autouse=True)
def reset_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed_defaults(db)


def test_chart_stats_preserve_per_owner_results_when_group_keys_collide():
    with SessionLocal() as db:
        event = db.query(Event).filter(Event.is_current.is_(True)).one()
        owner_a = User(
            user_code="owner-a",
            qq_id="owner-a",
            password_hash="unused",
            identity="participant",
            display_name="Owner A",
        )
        owner_b = User(
            user_code="owner-b",
            qq_id="owner-b",
            password_hash="unused",
            identity="participant",
            display_name="Owner B",
        )
        guesser = User(
            user_code="guesser",
            qq_id="guesser",
            password_hash="unused",
            identity="participant",
            display_name="Guesser",
        )
        db.add_all([owner_a, owner_b, guesser])
        db.flush()

        song_a = Song(
            event_id=event.id,
            submitted_by_id=owner_a.id,
            song_name="Collision A",
            artist="Artist",
            song_type="A",
        )
        song_b = Song(
            event_id=event.id,
            submitted_by_id=owner_b.id,
            song_name="Collision B",
            artist="Artist",
            song_type="A",
        )
        db.add_all([song_a, song_b])
        db.flush()

        submission_a = Submission(
            event_id=event.id,
            user_id=owner_a.id,
            source_song_id=song_a.id,
            source_kind="self",
            track="normal",
            file_name="a.zip",
            storage_path="uploads/a.zip",
            file_size=1,
        )
        submission_b = Submission(
            event_id=event.id,
            user_id=owner_b.id,
            source_song_id=song_b.id,
            source_kind="self",
            track="normal",
            file_name="b.zip",
            storage_path="uploads/b.zip",
            file_size=1,
        )
        db.add_all([submission_a, submission_b])
        db.flush()

        chart_a = GuessChart(
            event_id=event.id,
            title="Same Title",
            author="Same Artist",
            level="13",
            lane="normal",
            guess_group_key="same-title||same-artist",
            source_submission_type="normal",
            source_submission_id=submission_a.id,
            source_level_slot="4",
        )
        chart_b = GuessChart(
            event_id=event.id,
            title="Same Title",
            author="Same Artist",
            level="14",
            lane="normal",
            guess_group_key="same-title||same-artist",
            source_submission_type="normal",
            source_submission_id=submission_b.id,
            source_level_slot="5",
        )
        db.add_all([chart_a, chart_b])
        db.flush()

        db.add_all(
            [
                GuessAuthorGuess(
                    chart_id=chart_a.id,
                    user_id=guesser.id,
                    guessed_user_id=owner_a.id,
                ),
                GuessAuthorGuess(
                    chart_id=chart_a.id,
                    user_id=owner_a.id,
                    guessed_user_id=owner_b.id,
                ),
            ]
        )
        db.commit()

        stats = build_guess_stats(db, "all", include_details=False)

    rows = {row["chart_id"]: row for row in stats["chart_stats"]}
    assert rows[chart_a.id]["guess_count"] == 2
    assert rows[chart_a.id]["counted_guesses"] == 1
    assert rows[chart_a.id]["correct_guesses"] == 1
    assert rows[chart_a.id]["accuracy"] == 100.0
    assert rows[chart_b.id]["guess_count"] == 2
    assert rows[chart_b.id]["counted_guesses"] == 2
    assert rows[chart_b.id]["correct_guesses"] == 1
    assert rows[chart_b.id]["accuracy"] == 50.0
