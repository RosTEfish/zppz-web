"""add durable submission processing jobs

Revision ID: 0016_submission_processing_jobs
Revises: 0015_preview_bundles
"""

from __future__ import annotations

from datetime import datetime

from alembic import op
import sqlalchemy as sa


revision = "0016_submission_processing_jobs"
down_revision = "0015_preview_bundles"
branch_labels = None
depends_on = None


def _columns(table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())

    submission_columns = _columns("submissions")
    with op.batch_alter_table("submissions") as batch:
        if "public_package_status" not in submission_columns:
            batch.add_column(
                sa.Column("public_package_status", sa.String(length=20), nullable=False, server_default="processing")
            )
        if "public_package_message" not in submission_columns:
            batch.add_column(
                sa.Column("public_package_message", sa.String(length=500), nullable=False, server_default="")
            )
    op.execute(
        sa.text(
            "UPDATE submissions SET public_package_status = "
            "CASE WHEN public_storage_path IS NOT NULL THEN 'ready' ELSE 'failed' END"
        )
    )

    preview_columns = _columns("preview_bundles")
    with op.batch_alter_table("preview_bundles") as batch:
        if "video_status" not in preview_columns:
            batch.add_column(sa.Column("video_status", sa.String(length=20), nullable=False, server_default="none"))
        if "video_error_message" not in preview_columns:
            batch.add_column(
                sa.Column("video_error_message", sa.String(length=500), nullable=False, server_default="")
            )
    op.execute(
        sa.text(
            "UPDATE preview_bundles SET video_status = "
            "CASE WHEN video_key IS NOT NULL THEN 'ready' ELSE 'none' END"
        )
    )

    if "submission_processing_jobs" not in tables:
        op.create_table(
            "submission_processing_jobs",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column(
                "upload_intent_id",
                sa.String(length=32),
                sa.ForeignKey("submission_upload_intents.id", ondelete="CASCADE"),
                nullable=True,
                unique=True,
            ),
            sa.Column("event_id", sa.Integer(), sa.ForeignKey("events.id", ondelete="CASCADE"), nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("job_type", sa.String(length=24), nullable=False, server_default="upload"),
            sa.Column("source_song_id", sa.Integer(), sa.ForeignKey("songs.id", ondelete="CASCADE"), nullable=True),
            sa.Column(
                "replace_submission_id",
                sa.Integer(),
                sa.ForeignKey("submissions.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "result_submission_id",
                sa.Integer(),
                sa.ForeignKey("submissions.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("source_storage_path", sa.String(length=500), nullable=False),
            sa.Column("source_version", sa.String(length=64), nullable=False, server_default=""),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="queued"),
            sa.Column("stage", sa.String(length=24), nullable=False, server_default="uploaded"),
            sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("next_attempt_at", sa.DateTime(), nullable=True),
            sa.Column("lease_until", sa.DateTime(), nullable=True),
            sa.Column("accepted_at", sa.DateTime(), nullable=True),
            sa.Column("finished_at", sa.DateTime(), nullable=True),
            sa.Column("superseded_at", sa.DateTime(), nullable=True),
            sa.Column("error_code", sa.String(length=64), nullable=False, server_default=""),
            sa.Column("error_message", sa.String(length=500), nullable=False, server_default=""),
            sa.Column("stage_timings_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime(), nullable=False, default=datetime.utcnow),
            sa.Column("updated_at", sa.DateTime(), nullable=False, default=datetime.utcnow),
            sa.CheckConstraint("job_type IN ('upload', 'resources_rebuild')", name="ck_submission_job_type"),
            sa.CheckConstraint(
                "status IN ('queued', 'processing', 'completed', 'failed', 'cancelled')",
                name="ck_submission_job_status",
            ),
            sa.CheckConstraint(
                "stage IN ('uploaded', 'validating', 'accepted', 'preview_core', "
                "'public_package', 'video', 'cleanup', 'complete')",
                name="ck_submission_job_stage",
            ),
        )
        op.create_index(
            "ix_submission_jobs_status_schedule",
            "submission_processing_jobs",
            ["status", "next_attempt_at"],
        )
        op.create_index(
            "ix_submission_jobs_event_user",
            "submission_processing_jobs",
            ["event_id", "user_id"],
        )
        active_song = sa.text(
            "status IN ('queued', 'processing') "
            "AND source_song_id IS NOT NULL AND replace_submission_id IS NULL"
        )
        op.create_index(
            "uq_submission_jobs_active_song_target",
            "submission_processing_jobs",
            ["event_id", "user_id", "source_song_id"],
            unique=True,
            sqlite_where=active_song,
            postgresql_where=active_song,
        )
        active_replacement = sa.text(
            "status IN ('queued', 'processing') AND replace_submission_id IS NOT NULL"
        )
        op.create_index(
            "uq_submission_jobs_active_replacement",
            "submission_processing_jobs",
            ["replace_submission_id"],
            unique=True,
            sqlite_where=active_replacement,
            postgresql_where=active_replacement,
        )

    # Older releases marked in-flight work as "processing" inside the web
    # process. Requeue it so the durable worker can safely resume it.
    op.execute(
        sa.text(
            "INSERT INTO submission_processing_jobs "
            "(id, upload_intent_id, event_id, user_id, job_type, source_song_id, "
            "replace_submission_id, result_submission_id, source_storage_path, "
            "source_version, status, stage, attempts, error_code, error_message, "
            "stage_timings_json, created_at, updated_at) "
            "SELECT id, id, event_id, user_id, 'upload', source_song_id, "
            "replace_submission_id, result_submission_id, object_key, '', 'queued', "
            "'uploaded', 0, '', '', '{}', created_at, updated_at "
            "FROM submission_upload_intents "
            "WHERE status = 'processing' AND result_submission_id IS NULL "
            "AND NOT EXISTS (SELECT 1 FROM submission_processing_jobs jobs "
            "WHERE jobs.upload_intent_id = submission_upload_intents.id)"
        )
    )
    op.execute(
        sa.text(
            "INSERT INTO submission_processing_jobs "
            "(id, upload_intent_id, event_id, user_id, job_type, source_song_id, "
            "replace_submission_id, result_submission_id, source_storage_path, "
            "source_version, status, stage, attempts, error_code, error_message, "
            "stage_timings_json, created_at, updated_at) "
            "SELECT intents.id, intents.id, intents.event_id, intents.user_id, "
            "'resources_rebuild', intents.source_song_id, submissions.id, submissions.id, "
            "submissions.storage_path, '', 'queued', 'accepted', 0, '', '', '{}', "
            "intents.created_at, intents.updated_at "
            "FROM submission_upload_intents intents "
            "JOIN submissions ON submissions.id = intents.result_submission_id "
            "WHERE intents.status = 'processing' AND intents.result_submission_id IS NOT NULL "
            "AND NOT EXISTS (SELECT 1 FROM submission_processing_jobs jobs "
            "WHERE jobs.upload_intent_id = intents.id)"
        )
    )
    op.execute(
        sa.text(
            "UPDATE submission_upload_intents SET status = 'uploaded' "
            "WHERE status = 'processing'"
        )
    )


def downgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "submission_processing_jobs" in tables:
        op.drop_index("uq_submission_jobs_active_replacement", table_name="submission_processing_jobs")
        op.drop_index("uq_submission_jobs_active_song_target", table_name="submission_processing_jobs")
        op.drop_index("ix_submission_jobs_event_user", table_name="submission_processing_jobs")
        op.drop_index("ix_submission_jobs_status_schedule", table_name="submission_processing_jobs")
        op.drop_table("submission_processing_jobs")

    preview_columns = _columns("preview_bundles")
    with op.batch_alter_table("preview_bundles") as batch:
        if "video_error_message" in preview_columns:
            batch.drop_column("video_error_message")
        if "video_status" in preview_columns:
            batch.drop_column("video_status")

    submission_columns = _columns("submissions")
    with op.batch_alter_table("submissions") as batch:
        if "public_package_message" in submission_columns:
            batch.drop_column("public_package_message")
        if "public_package_status" in submission_columns:
            batch.drop_column("public_package_status")
