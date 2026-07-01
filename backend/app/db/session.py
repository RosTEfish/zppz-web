from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


settings = get_settings()
engine_kwargs = {"pool_pre_ping": True}
if settings.database_url.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}
    if settings.database_url.endswith(":memory:"):
        engine_kwargs["poolclass"] = StaticPool

engine = create_engine(settings.database_url, **engine_kwargs)

if settings.database_url.startswith("sqlite"):

    @event.listens_for(engine, "connect")
    def set_sqlite_pragmas(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
        if not settings.database_url.endswith(":memory:"):
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
