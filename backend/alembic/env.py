from logging.config import fileConfig
import os

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.db.session import Base
from app import models  # noqa: F401


config = context.config
if config.config_file_name is not None:
    # Migration checks can run in the application process (notably tests and
    # deployment preparation); do not disable already configured app loggers.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata
database_url = os.getenv("DATABASE_URL")
if database_url:
    config.set_main_option("sqlalchemy.url", database_url)


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


def _widen_version_table(connectable) -> None:
    """Alembic's default alembic_version.version_num column is varchar(32), but
    this project has a revision id longer than 32 characters
    (0009_remove_legacy_phase_settings), which fails on PostgreSQL with a
    StringDataRightTruncation error (SQLite ignores the declared length, which is
    why production never noticed). Pre-create / widen the column so the full
    migration chain also runs on PostgreSQL (e.g. the Docker Compose stack).

    This runs on its own committed Engine transaction BEFORE the Alembic
    migration connection is opened; executing DDL on the migration connection
    itself would open a transaction that turns Alembic's migration into a nested
    savepoint and rolls everything back when the connection closes."""
    url = config.get_main_option("sqlalchemy.url")
    if not (url or "").startswith("postgres"):
        return
    from sqlalchemy import text

    with connectable.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE IF NOT EXISTS alembic_version ("
                "version_num VARCHAR(128) NOT NULL, PRIMARY KEY (version_num))"
            )
        )
        connection.execute(
            text("ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(128)")
        )


def run_migrations_online() -> None:
    connectable = engine_from_config(config.get_section(config.config_ini_section, {}), prefix="sqlalchemy.", poolclass=pool.NullPool)
    _widen_version_table(connectable)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
