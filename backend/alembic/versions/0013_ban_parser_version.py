"""track the Ban workbook parser version

Revision ID: 0013_ban_parser_version
Revises: 0012_r2_submission_storage
Create Date: 2026-07-17
"""

from alembic import op
import sqlalchemy as sa


revision = "0013_ban_parser_version"
down_revision = "0012_r2_submission_storage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("ban_imports")}
    if "parser_version" not in columns:
        op.add_column(
            "ban_imports",
            sa.Column("parser_version", sa.Integer(), nullable=False, server_default="1"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("ban_imports")}
    if "parser_version" in columns:
        op.drop_column("ban_imports", "parser_version")
