"""manual true-love vote bucket override per chart

Revision ID: 0020_love_vote_bucket_override
Revises: 0019_submission_has_readme
Create Date: 2026-09-27
"""

from alembic import op
import sqlalchemy as sa


revision = "0020_love_vote_bucket_override"
down_revision = "0019_submission_has_readme"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("guess_charts")}
    if "love_vote_bucket_override" not in columns:
        op.add_column(
            "guess_charts",
            sa.Column("love_vote_bucket_override", sa.String(length=20), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("guess_charts")}
    if "love_vote_bucket_override" in columns:
        op.drop_column("guess_charts", "love_vote_bucket_override")
