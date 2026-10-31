"""durable domain events for SSE fan-out

Revision ID: 0021_domain_events
Revises: 0020_love_vote_bucket_override
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0021_domain_events"
down_revision = "0020_love_vote_bucket_override"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "domain_events" in inspector.get_table_names():
        return
    op.create_table(
        "domain_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("topic", sa.String(length=64), nullable=False),
        sa.Column("scope", sa.String(length=20), nullable=False),
        sa.Column("subject_user_id", sa.Integer(), nullable=True),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_domain_events_created_at", "domain_events", ["created_at"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "domain_events" not in inspector.get_table_names():
        return
    op.drop_index("ix_domain_events_created_at", table_name="domain_events")
    op.drop_table("domain_events")
