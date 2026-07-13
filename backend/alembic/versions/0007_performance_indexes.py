"""add query-backed performance indexes

Revision ID: 0007_performance_indexes
Revises: 0006_event_phases_swaps
Create Date: 2026-07-13
"""

from alembic import op
import sqlalchemy as sa


revision = "0007_performance_indexes"
down_revision = "0006_event_phases_swaps"
branch_labels = None
depends_on = None


INDEXES: tuple[tuple[str, str, list[str]], ...] = (
    ("ix_guess_charts_event_source", "guess_charts", ["event_id", "source_submission_type", "source_submission_id"]),
    ("ix_draw_assignments_event_assignee_status", "draw_assignments", ["event_id", "assigned_to_id", "status"]),
    ("ix_guess_votes_user_type", "guess_votes", ["user_id", "vote_type"]),
    ("ix_guess_comments_chart_created", "guess_comments", ["chart_id", "created_at"]),
    ("ix_songs_event_submitter", "songs", ["event_id", "submitted_by_id"]),
    ("ix_submissions_event_user_track", "submissions", ["event_id", "user_id", "track"]),
    ("ix_user_sessions_expires_at", "user_sessions", ["expires_at"]),
)


def _create_index(name: str, table: str, columns: list[str]) -> None:
    bind = op.get_bind()
    existing = {index["name"] for index in sa.inspect(bind).get_indexes(table)}
    if name in existing:
        return
    if bind.dialect.name == "postgresql":
        # Avoid blocking writes while production-sized tables are indexed.
        with op.get_context().autocommit_block():
            op.create_index(name, table, columns, unique=False, postgresql_concurrently=True)
    else:
        op.create_index(name, table, columns, unique=False)


def _drop_index(name: str, table: str) -> None:
    bind = op.get_bind()
    existing = {index["name"] for index in sa.inspect(bind).get_indexes(table)}
    if name not in existing:
        return
    if bind.dialect.name == "postgresql":
        with op.get_context().autocommit_block():
            op.drop_index(name, table_name=table, postgresql_concurrently=True)
    else:
        op.drop_index(name, table_name=table)


def upgrade() -> None:
    for name, table, columns in INDEXES:
        _create_index(name, table, columns)


def downgrade() -> None:
    for name, table, _columns in reversed(INDEXES):
        _drop_index(name, table)
