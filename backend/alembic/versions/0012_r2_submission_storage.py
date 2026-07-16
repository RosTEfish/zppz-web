"""add R2 submission upload intents and deletion queue

Revision ID: 0012_r2_submission_storage
Revises: 0011_banlist
Create Date: 2026-07-17
"""

from alembic import op
import sqlalchemy as sa


revision = "0012_r2_submission_storage"
down_revision = "0011_banlist"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("submissions")}
    if "public_file_size" not in columns:
        op.add_column("submissions", sa.Column("public_file_size", sa.Integer(), nullable=True))

    tables = set(inspector.get_table_names())
    if "submission_upload_intents" not in tables:
        op.create_table(
            "submission_upload_intents",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column("event_id", sa.Integer(), sa.ForeignKey("events.id", ondelete="CASCADE"), nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("source_song_id", sa.Integer(), sa.ForeignKey("songs.id", ondelete="CASCADE"), nullable=True),
            sa.Column("replace_submission_id", sa.Integer(), sa.ForeignKey("submissions.id", ondelete="CASCADE"), nullable=True),
            sa.Column("result_submission_id", sa.Integer(), sa.ForeignKey("submissions.id", ondelete="SET NULL"), nullable=True),
            sa.Column("track", sa.String(length=20), nullable=False),
            sa.Column("file_name", sa.String(length=255), nullable=False),
            sa.Column("file_size", sa.Integer(), nullable=False),
            sa.Column("content_type", sa.String(length=100), nullable=False),
            sa.Column("object_key", sa.String(length=500), nullable=False, unique=True),
            sa.Column("acknowledge_ban_warning", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
            sa.Column("error_message", sa.String(length=500), nullable=False, server_default=""),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_submission_upload_intents_event_id", "submission_upload_intents", ["event_id"])
        op.create_index("ix_submission_upload_intents_user_id", "submission_upload_intents", ["user_id"])
        op.create_index("ix_submission_upload_intents_status", "submission_upload_intents", ["status"])
        op.create_index("ix_submission_upload_intents_expires_at", "submission_upload_intents", ["expires_at"])

    if "storage_deletions" not in tables:
        op.create_table(
            "storage_deletions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("object_key", sa.String(length=500), nullable=False, unique=True),
            sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("last_error", sa.String(length=500), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )


def downgrade() -> None:
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    if "storage_deletions" in tables:
        op.drop_table("storage_deletions")
    if "submission_upload_intents" in tables:
        op.drop_index("ix_submission_upload_intents_expires_at", table_name="submission_upload_intents")
        op.drop_index("ix_submission_upload_intents_status", table_name="submission_upload_intents")
        op.drop_index("ix_submission_upload_intents_user_id", table_name="submission_upload_intents")
        op.drop_index("ix_submission_upload_intents_event_id", table_name="submission_upload_intents")
        op.drop_table("submission_upload_intents")
    columns = {column["name"] for column in sa.inspect(bind).get_columns("submissions")}
    if "public_file_size" in columns:
        op.drop_column("submissions", "public_file_size")
