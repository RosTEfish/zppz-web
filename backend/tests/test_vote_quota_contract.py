import pytest
from sqlalchemy import select

from app.db.bootstrap import seed_defaults
from app.db.session import Base, SessionLocal, engine
from app.models import Event, GuessChart, GuessVote, User
from app.modules.guess_game.vote_quota import love_vote_quota


@pytest.fixture(autouse=True)
def reset_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed_defaults(db)


def test_legacy_exhibition_votes_do_not_consume_love_vote_quota():
    with SessionLocal() as db:
        event = db.scalar(select(Event).where(Event.is_current.is_(True)))
        voter = User(
            user_code="quota-voter",
            qq_id="quota-voter",
            password_hash="unused",
            identity="audience",
            display_name="Quota voter",
        )
        db.add(voter)
        db.flush()
        exhibition = GuessChart(
            event_id=event.id,
            title="Legacy exhibition",
            author="Artist",
            level="13+",
            lane="exhibition",
            guess_group_key="legacy-exhibition",
            source_submission_type="exhibition",
        )
        db.add(exhibition)
        db.flush()
        db.add(GuessVote(chart_id=exhibition.id, user_id=voter.id, vote_type="love"))
        db.commit()

        quota = love_vote_quota(db, voter.id, event)

    assert quota["below_14"] == {"used": 0, "limit": 3, "remaining": 3}
    assert quota["at_least_14"] == {"used": 0, "limit": 3, "remaining": 3}
