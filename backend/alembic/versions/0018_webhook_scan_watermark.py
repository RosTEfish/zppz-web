"""webhook publication scan watermark

Revision ID: 0018_webhook_scan_watermark
Revises: 0017_webhook_integrations
Create Date: 2026-08-31
"""

from alembic import op
import sqlalchemy as sa


revision = "0018_webhook_scan_watermark"
down_revision = "0017_webhook_integrations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("webhook_system_states")}
    if "last_publication_scan_at" not in columns:
        op.add_column("webhook_system_states", sa.Column("last_publication_scan_at", sa.DateTime(), nullable=True))
    if "last_visibility_key" not in columns:
        op.add_column("webhook_system_states", sa.Column("last_visibility_key", sa.String(length=64), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("webhook_system_states")}
    if "last_visibility_key" in columns:
        op.drop_column("webhook_system_states", "last_visibility_key")
    if "last_publication_scan_at" in columns:
        op.drop_column("webhook_system_states", "last_publication_scan_at")
