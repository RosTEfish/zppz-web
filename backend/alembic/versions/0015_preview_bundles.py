"""add versioned browser preview bundles

Revision ID: 0015_preview_bundles
Revises: 0014_stage2_continuous_swap
Create Date: 2026-07-25
"""

from alembic import op
import sqlalchemy as sa


revision = "0015_preview_bundles"
down_revision = "0014_stage2_continuous_swap"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "preview_bundles" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "preview_bundles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_id", sa.Integer(), sa.ForeignKey("events.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_type", sa.String(length=24), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("source_storage_path", sa.String(length=500), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("maidata_key", sa.String(length=500), nullable=True),
        sa.Column("track_key", sa.String(length=500), nullable=True),
        sa.Column("background_key", sa.String(length=500), nullable=True),
        sa.Column("video_key", sa.String(length=500), nullable=True),
        sa.Column("maidata_mime", sa.String(length=100), nullable=True),
        sa.Column("track_mime", sa.String(length=100), nullable=True),
        sa.Column("background_mime", sa.String(length=100), nullable=True),
        sa.Column("video_mime", sa.String(length=100), nullable=True),
        sa.Column("error_code", sa.String(length=64), server_default="", nullable=False),
        sa.Column("error_message", sa.String(length=500), server_default="", nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("source_type IN ('submission', 'admin_archive')", name="ck_preview_bundle_source_type"),
        sa.CheckConstraint(
            "status IN ('processing', 'ready', 'unsupported', 'failed')",
            name="ck_preview_bundle_status",
        ),
        sa.UniqueConstraint("event_id", "source_type", "source_id", name="uq_preview_bundle_source"),
    )
    op.create_index("ix_preview_bundles_event_id", "preview_bundles", ["event_id"], unique=False)
    op.create_index("ix_preview_bundles_event_status", "preview_bundles", ["event_id", "status"], unique=False)


def downgrade() -> None:
    if "preview_bundles" not in sa.inspect(op.get_bind()).get_table_names():
        return
    op.drop_index("ix_preview_bundles_event_status", table_name="preview_bundles")
    op.drop_index("ix_preview_bundles_event_id", table_name="preview_bundles")
    op.drop_table("preview_bundles")
