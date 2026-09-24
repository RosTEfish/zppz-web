"""submission has_readme flag

Revision ID: 0019_submission_has_readme
Revises: 0018_webhook_scan_watermark
Create Date: 2026-09-25
"""

from alembic import op
import sqlalchemy as sa


revision = "0019_submission_has_readme"
down_revision = "0018_webhook_scan_watermark"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("submissions")}
    if "has_readme" not in columns:
        op.add_column("submissions", sa.Column("has_readme", sa.Boolean(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("submissions")}
    if "has_readme" in columns:
        op.drop_column("submissions", "has_readme")
