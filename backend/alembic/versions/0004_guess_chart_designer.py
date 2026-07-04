"""add guess chart designer metadata

Revision ID: 0004_guess_chart_designer
Revises: 0003_schema_repair
Create Date: 2026-07-04
"""

from alembic import op
import sqlalchemy as sa


revision = "0004_guess_chart_designer"
down_revision = "0003_schema_repair"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    chart_columns = {column["name"] for column in inspector.get_columns("guess_charts")}
    if "designer" not in chart_columns:
        with op.batch_alter_table("guess_charts") as batch:
            batch.add_column(sa.Column("designer", sa.String(length=200), server_default="", nullable=False))

    setting_columns = {column["name"] for column in inspector.get_columns("event_settings")}
    if "guess_chart_metadata_version" not in setting_columns:
        with op.batch_alter_table("event_settings") as batch:
            batch.add_column(
                sa.Column("guess_chart_metadata_version", sa.Integer(), server_default="0", nullable=False)
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    setting_columns = {column["name"] for column in inspector.get_columns("event_settings")}
    if "guess_chart_metadata_version" in setting_columns:
        with op.batch_alter_table("event_settings") as batch:
            batch.drop_column("guess_chart_metadata_version")

    inspector = sa.inspect(bind)
    chart_columns = {column["name"] for column in inspector.get_columns("guess_charts")}
    if "designer" in chart_columns:
        with op.batch_alter_table("guess_charts") as batch:
            batch.drop_column("designer")
