"""add durable multi-recipient chart webhooks

Revision ID: 0017_webhook_integrations
Revises: 0016_submission_processing_jobs
"""

from alembic import op
import sqlalchemy as sa


revision = "0017_webhook_integrations"
down_revision = "0016_submission_processing_jobs"
branch_labels = None
depends_on = None


WEBHOOK_TABLES = {
    "webhook_integrations",
    "webhook_system_states",
    "webhook_endpoints",
    "chart_publication_states",
    "webhook_events",
    "webhook_event_assets",
    "webhook_deliveries",
}


def upgrade() -> None:
    # Revision 0001 intentionally builds current metadata for a brand-new database.
    # In that path these tables already exist, while an upgraded production database
    # reaches this revision without any of them.
    existing = set(sa.inspect(op.get_bind()).get_table_names())
    if WEBHOOK_TABLES.issubset(existing):
        return
    partial = WEBHOOK_TABLES.intersection(existing)
    if partial:
        raise RuntimeError(f"partially-created webhook schema requires repair: {sorted(partial)}")

    op.create_table(
        "webhook_integrations",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column("token_prefix", sa.String(length=24), nullable=False),
        sa.Column("secret_generation", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("last_test_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_webhook_integrations_token_hash", "webhook_integrations", ["token_hash"], unique=True)
    op.create_index("ix_webhook_integrations_is_active", "webhook_integrations", ["is_active"])

    op.create_table(
        "webhook_system_states",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("baseline_completed_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "webhook_endpoints",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("integration_id", sa.String(length=32), sa.ForeignKey("webhook_integrations.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("callback_url", sa.String(length=1000), nullable=False, server_default=""),
        sa.Column("subscribed_events_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("schema_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("activated_at", sa.DateTime(), nullable=True),
        sa.Column("verified_at", sa.DateTime(), nullable=True),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_success_at", sa.DateTime(), nullable=True),
        sa.Column("last_failure_at", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.String(length=500), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_webhook_endpoints_integration_id", "webhook_endpoints", ["integration_id"], unique=True)
    op.create_index("ix_webhook_endpoints_status", "webhook_endpoints", ["status"])

    op.create_table(
        "chart_publication_states",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_id", sa.Integer(), sa.ForeignKey("events.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_type", sa.String(length=20), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("source_version", sa.String(length=500), nullable=False, server_default=""),
        sa.Column("snapshot_json", sa.Text(), nullable=False),
        sa.Column("first_published_at", sa.DateTime(), nullable=False),
        sa.Column("last_published_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("event_id", "source_type", "source_id", name="uq_chart_publication_source"),
    )
    op.create_index("ix_chart_publication_states_event_id", "chart_publication_states", ["event_id"])

    op.create_table(
        "webhook_events",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("event_id", sa.Integer(), sa.ForeignKey("events.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("source_type", sa.String(length=20), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("event_id", "source_type", "source_id", "revision", name="uq_webhook_event_revision"),
    )
    op.create_index("ix_webhook_events_event_created", "webhook_events", ["event_id", "created_at"])

    op.create_table(
        "webhook_event_assets",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("webhook_event_id", sa.String(length=32), sa.ForeignKey("webhook_events.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("object_key", sa.String(length=500), nullable=False, unique=True),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_webhook_event_assets_webhook_event_id", "webhook_event_assets", ["webhook_event_id"], unique=True)

    op.create_table(
        "webhook_deliveries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("webhook_event_id", sa.String(length=32), sa.ForeignKey("webhook_events.id", ondelete="CASCADE"), nullable=False),
        sa.Column("endpoint_id", sa.String(length=32), sa.ForeignKey("webhook_endpoints.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime(), nullable=True),
        sa.Column("lease_until", sa.DateTime(), nullable=True),
        sa.Column("response_status", sa.Integer(), nullable=True),
        sa.Column("last_error", sa.String(length=500), nullable=False, server_default=""),
        sa.Column("delivered_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("webhook_event_id", "endpoint_id", name="uq_webhook_delivery_event_endpoint"),
    )
    op.create_index("ix_webhook_deliveries_status", "webhook_deliveries", ["status"])
    op.create_index("ix_webhook_deliveries_status_schedule", "webhook_deliveries", ["status", "next_attempt_at"])
    op.create_index("ix_webhook_deliveries_endpoint_created", "webhook_deliveries", ["endpoint_id", "created_at"])


def downgrade() -> None:
    op.drop_table("webhook_deliveries")
    op.drop_table("webhook_event_assets")
    op.drop_table("webhook_events")
    op.drop_table("chart_publication_states")
    op.drop_table("webhook_endpoints")
    op.drop_table("webhook_system_states")
    op.drop_table("webhook_integrations")
