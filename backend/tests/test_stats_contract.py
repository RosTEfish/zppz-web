import pytest

from app.db.bootstrap import seed_defaults
from app.db.session import Base, SessionLocal, engine
from app.models import Event, GuessAuthorGuess, GuessChart, GuessVote, Song, Submission, User
from app.modules.guess_game.stats import build_guess_stats


@pytest.fixture(autouse=True)
def reset_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed_defaults(db)


def _seed_two_owned_charts(db):
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
    return event, owner_a, owner_b, guesser, chart_a, chart_b


def test_chart_stats_keep_same_title_submissions_independent_when_group_keys_collide():
    with SessionLocal() as db:
        _event, owner_a, owner_b, guesser, chart_a, chart_b = _seed_two_owned_charts(db)

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
        chart_a_id, chart_b_id = chart_a.id, chart_b.id

    rows = {row["chart_id"]: row for row in stats["chart_stats"]}
    assert rows[chart_a_id]["guess_count"] == 2
    assert rows[chart_a_id]["counted_guesses"] == 1
    assert rows[chart_a_id]["correct_guesses"] == 1
    assert rows[chart_a_id]["accuracy"] == 100.0
    # Different submission packages must not inherit each other's designer guesses,
    # even when title/author (guess_group_key) collide.
    assert rows[chart_b_id]["guess_count"] == 0
    assert rows[chart_b_id]["counted_guesses"] == 0
    assert rows[chart_b_id]["correct_guesses"] == 0
    assert rows[chart_b_id]["accuracy"] is None


def test_chart_stats_exclude_owner_votes_on_own_charts():
    with SessionLocal() as db:
        _event, owner_a, owner_b, guesser, chart_a, chart_b = _seed_two_owned_charts(db)

        db.add_all(
            [
                # Owner self-votes must not count.
                GuessVote(chart_id=chart_a.id, user_id=owner_a.id, vote_type="love"),
                GuessVote(chart_id=chart_a.id, user_id=owner_a.id, vote_type="funny"),
                # Other users' votes still count.
                GuessVote(chart_id=chart_a.id, user_id=guesser.id, vote_type="love"),
                GuessVote(chart_id=chart_a.id, user_id=owner_b.id, vote_type="funny"),
                # Owner voting on someone else's chart still counts.
                GuessVote(chart_id=chart_b.id, user_id=owner_a.id, vote_type="love"),
            ]
        )
        db.commit()

        stats = build_guess_stats(db, "all", include_details=False)
        chart_a_id, chart_b_id = chart_a.id, chart_b.id

    rows = {row["chart_id"]: row for row in stats["chart_stats"]}
    assert rows[chart_a_id]["love_votes"] == 1
    assert rows[chart_a_id]["funny_votes"] == 1
    assert rows[chart_a_id]["total_votes"] == 2
    assert rows[chart_b_id]["love_votes"] == 1
    assert rows[chart_b_id]["funny_votes"] == 0
    assert stats["overview"]["love_votes"] == 2
    assert stats["overview"]["funny_votes"] == 1
