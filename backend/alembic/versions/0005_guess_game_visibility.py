"""add guess game entry visibility

Revision ID: 0005_guess_game_visibility
Revises: 0004_guess_chart_designer
Create Date: 2026-07-04
"""

from alembic import op
import sqlalchemy as sa


revision = "0005_guess_game_visibility"
down_revision = "0004_guess_chart_designer"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("event_settings")}
    if "guess_game_visible" not in columns:
        with op.batch_alter_table("event_settings") as batch:
            batch.add_column(sa.Column("guess_game_visible", sa.Boolean(), server_default=sa.true(), nullable=False))


def downgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("event_settings")}
    if "guess_game_visible" in columns:
        with op.batch_alter_table("event_settings") as batch:
            batch.drop_column("guess_game_visible")
