"""split true-love vote quota by chart level

Revision ID: 0008_split_love_vote_quota
Revises: 0007_performance_indexes
Create Date: 2026-07-13
"""

from alembic import op
import sqlalchemy as sa


revision = "0008_split_love_vote_quota"
down_revision = "0007_performance_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Product policy intentionally resets both new buckets to 3 instead of
    # copying the former shared quota.
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("event_settings")}
    with op.batch_alter_table("event_settings") as batch_op:
        if "true_love_vote_limit_below_14" not in columns:
            batch_op.add_column(
                sa.Column(
                    "true_love_vote_limit_below_14",
                    sa.Integer(),
                    nullable=False,
                    server_default=sa.text("3"),
                )
            )
        if "true_love_vote_limit_at_least_14" not in columns:
            batch_op.add_column(
                sa.Column(
                    "true_love_vote_limit_at_least_14",
                    sa.Integer(),
                    nullable=False,
                    server_default=sa.text("3"),
                )
            )
        if "true_love_vote_limit" in columns:
            batch_op.drop_column("true_love_vote_limit")


def downgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("event_settings")}
    with op.batch_alter_table("event_settings") as batch_op:
        if "true_love_vote_limit" not in columns:
            batch_op.add_column(
                sa.Column(
                    "true_love_vote_limit",
                    sa.Integer(),
                    nullable=False,
                    server_default=sa.text("3"),
                )
            )
        if "true_love_vote_limit_at_least_14" in columns:
            batch_op.drop_column("true_love_vote_limit_at_least_14")
        if "true_love_vote_limit_below_14" in columns:
            batch_op.drop_column("true_love_vote_limit_below_14")
