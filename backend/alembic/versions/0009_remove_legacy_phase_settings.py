"""remove legacy phase settings

Revision ID: 0009_remove_legacy_phase_settings
Revises: 0008_split_love_vote_quota
Create Date: 2026-07-13
"""

from alembic import op
from datetime import datetime, timezone
import sqlalchemy as sa


revision = "0009_remove_legacy_phase_settings"
down_revision = "0008_split_love_vote_quota"
branch_labels = None
depends_on = None


LEGACY_COLUMNS = (
    "registration_deadline",
    "submission_deadline",
    "guess_game_open_at",
    "submissions_open",
    "guess_game_visible",
)
VALID_PHASES = (
    "registration",
    "draw",
    "submission_1",
    "swap",
    "submission_2",
    "guess",
    "reveal",
    "closed",
)


def upgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("event_settings")}

    # Preserve the observable state of legacy automatic events that have no
    # schedule. Existing schedules and valid manual overrides stay untouched.
    if {"submissions_open", "guess_game_open_at"}.issubset(columns):
        settings = sa.table(
            "event_settings",
            sa.column("event_id", sa.Integer()),
            sa.column("phase_mode", sa.String()),
            sa.column("manual_phase", sa.String()),
            sa.column("submissions_open", sa.Boolean()),
            sa.column("guess_game_open_at", sa.DateTime()),
        )
        phases = sa.table("event_phases", sa.column("event_id", sa.Integer()))
        no_schedule = ~sa.exists(sa.select(1).where(phases.c.event_id == settings.c.event_id))
        now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
        migrated_phase = sa.case(
            (settings.c.submissions_open.is_(True), "submission_1"),
            (
                sa.and_(
                    settings.c.guess_game_open_at.is_not(None),
                    settings.c.guess_game_open_at <= now_utc,
                ),
                "guess",
            ),
            else_="registration",
        )
        valid_manual = sa.and_(
            settings.c.phase_mode == "manual",
            settings.c.manual_phase.in_(VALID_PHASES),
        )
        bind.execute(
            sa.update(settings)
            .where(no_schedule, ~valid_manual)
            .values(phase_mode="manual", manual_phase=migrated_phase)
        )

    with op.batch_alter_table("event_settings") as batch_op:
        for column in LEGACY_COLUMNS:
            if column in columns:
                batch_op.drop_column(column)


def downgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("event_settings")}
    with op.batch_alter_table("event_settings") as batch_op:
        if "registration_deadline" not in columns:
            batch_op.add_column(sa.Column("registration_deadline", sa.DateTime(), nullable=True))
        if "submission_deadline" not in columns:
            batch_op.add_column(sa.Column("submission_deadline", sa.DateTime(), nullable=True))
        if "guess_game_open_at" not in columns:
            batch_op.add_column(sa.Column("guess_game_open_at", sa.DateTime(), nullable=True))
        if "submissions_open" not in columns:
            batch_op.add_column(
                sa.Column("submissions_open", sa.Boolean(), nullable=False, server_default=sa.false())
            )
        if "guess_game_visible" not in columns:
            batch_op.add_column(
                sa.Column("guess_game_visible", sa.Boolean(), nullable=False, server_default=sa.true())
            )
