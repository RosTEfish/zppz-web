from datetime import UTC, datetime, timedelta, timezone

from sqlalchemy import Column, Integer, MetaData, Table, create_engine, select

from app.core.time import (
    UtcDateTime,
    as_naive_utc,
    as_utc,
    utc_from_timestamp,
    utc_iso,
    utc_now,
    utc_now_naive,
)


def test_as_utc_treats_naive_values_as_utc_and_converts_offsets():
    naive = datetime(2026, 1, 2, 3, 4, 5)
    aware = as_utc(naive)
    assert aware.tzinfo is UTC
    assert aware.replace(tzinfo=None) == naive

    shanghai = timezone(timedelta(hours=8))
    converted = as_utc(datetime(2026, 1, 2, 8, 0, tzinfo=shanghai))
    assert converted == datetime(2026, 1, 2, 0, 0, tzinfo=UTC)
    assert as_naive_utc(converted) == datetime(2026, 1, 2, 0, 0)
    assert as_naive_utc(naive) == naive


def test_utc_iso_and_timestamp_round_trip():
    instant = datetime(2026, 1, 1, tzinfo=UTC)
    stamp = utc_from_timestamp(instant.timestamp())
    assert stamp == instant
    assert utc_iso(stamp) == "2026-01-01T00:00:00Z"
    assert utc_iso(datetime(2026, 1, 1)) == "2026-01-01T00:00:00Z"
    assert abs(as_utc(utc_now_naive()).timestamp() - utc_now().timestamp()) < 1


def test_utc_datetime_column_stores_naive_utc_wall_time():
    engine = create_engine("sqlite://")
    ticks = Table(
        "ticks",
        MetaData(),
        Column("id", Integer, primary_key=True),
        Column("at", UtcDateTime()),
    )
    ticks.create(engine)
    shanghai = timezone(timedelta(hours=8))
    with engine.begin() as conn:
        conn.execute(ticks.insert().values(id=1, at=datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)))
        conn.execute(ticks.insert().values(id=2, at=datetime(2026, 1, 2, 8, 0, tzinfo=shanghai)))
        conn.execute(ticks.insert().values(id=3, at=datetime(2020, 1, 1)))

    with engine.connect() as conn:
        loaded = dict(conn.execute(select(ticks.c.id, ticks.c.at)).all())

    assert loaded[1] == datetime(2026, 1, 2, 3, 4, 5)
    assert loaded[1].tzinfo is None
    assert loaded[1].isoformat() == "2026-01-02T03:04:05"
    assert loaded[2] == datetime(2026, 1, 2, 0, 0)
    assert loaded[3] == datetime(2020, 1, 1)
    assert as_utc(loaded[3]) < utc_now()

    with engine.connect() as conn:
        matched = conn.execute(select(ticks.c.id).where(ticks.c.at < utc_now()).order_by(ticks.c.id)).scalars().all()
    assert matched == [1, 2, 3]
