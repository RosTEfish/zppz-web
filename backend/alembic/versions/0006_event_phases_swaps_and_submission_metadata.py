"""add event phases, swaps, and submission publication metadata

Revision ID: 0006_event_phases_swaps
Revises: 0005_guess_game_visibility
Create Date: 2026-07-13
"""

from alembic import op
import sqlalchemy as sa


revision = "0006_event_phases_swaps"
down_revision = "0005_guess_game_visibility"
branch_labels = None
depends_on = None


def _timestamps() -> tuple[sa.Column, sa.Column]:
    return (
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    setting_columns = {column["name"] for column in inspector.get_columns("event_settings")}
    with op.batch_alter_table("event_settings") as batch:
        if "phase_mode" not in setting_columns:
            batch.add_column(sa.Column("phase_mode", sa.String(length=10), server_default="auto", nullable=False))
        if "manual_phase" not in setting_columns:
            batch.add_column(sa.Column("manual_phase", sa.String(length=30), nullable=True))

    if "event_phases" not in inspector.get_table_names():
        op.create_table(
            "event_phases",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("event_id", sa.Integer(), sa.ForeignKey("events.id", ondelete="CASCADE"), nullable=False),
            sa.Column("phase", sa.String(length=30), nullable=False),
            sa.Column("starts_at", sa.DateTime(), nullable=False),
            sa.Column("ends_at", sa.DateTime(), nullable=False),
            *_timestamps(),
            sa.UniqueConstraint("event_id", "phase", name="uq_event_phase_name"),
        )
        op.create_index("ix_event_phases_event_id", "event_phases", ["event_id"], unique=False)

    draw_columns = {column["name"] for column in inspector.get_columns("draw_assignments")}
    draw_uniques = {item.get("name") for item in inspector.get_unique_constraints("draw_assignments")}
    draw_foreign_keys = inspector.get_foreign_keys("draw_assignments")
    has_replaces_fk = any(item.get("constrained_columns") == ["replaces_assignment_id"] for item in draw_foreign_keys)
    with op.batch_alter_table("draw_assignments") as batch:
        if "status" not in draw_columns:
            batch.add_column(sa.Column("status", sa.String(length=20), server_default="active", nullable=False))
        if "draw_kind" not in draw_columns:
            batch.add_column(sa.Column("draw_kind", sa.String(length=20), server_default="initial", nullable=False))
        if "replaces_assignment_id" not in draw_columns:
            batch.add_column(sa.Column("replaces_assignment_id", sa.Integer(), nullable=True))
        if not has_replaces_fk:
            batch.create_foreign_key(
                "fk_draw_assignments_replaces_assignment_id",
                "draw_assignments",
                ["replaces_assignment_id"],
                ["id"],
                ondelete="SET NULL",
            )
        if "uq_draw_event_song" in draw_uniques:
            batch.drop_constraint("uq_draw_event_song", type_="unique")

    inspector = sa.inspect(bind)
    draw_indexes = {item.get("name") for item in inspector.get_indexes("draw_assignments")}
    if "ix_draw_assignments_replaces_assignment_id" not in draw_indexes:
        op.create_index(
            "ix_draw_assignments_replaces_assignment_id",
            "draw_assignments",
            ["replaces_assignment_id"],
            unique=False,
        )
    if "uq_draw_event_active_song" not in draw_indexes:
        op.create_index(
            "uq_draw_event_active_song",
            "draw_assignments",
            ["event_id", "song_id"],
            unique=True,
            postgresql_where=sa.text("status = 'active'"),
            sqlite_where=sa.text("status = 'active'"),
        )

    if "swap_rounds" not in inspector.get_table_names():
        op.create_table(
            "swap_rounds",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("event_id", sa.Integer(), sa.ForeignKey("events.id", ondelete="CASCADE"), nullable=False),
            sa.Column("round_number", sa.Integer(), server_default="1", nullable=False),
            sa.Column("starts_at", sa.DateTime(), nullable=False),
            sa.Column("ends_at", sa.DateTime(), nullable=False),
            sa.Column("status", sa.String(length=20), server_default="open", nullable=False),
            sa.Column("random_seed", sa.String(length=128), nullable=False),
            sa.Column("finalized_at", sa.DateTime(), nullable=True),
            *_timestamps(),
            sa.UniqueConstraint("event_id", "round_number", name="uq_swap_round_event_number"),
        )
        op.create_index("ix_swap_rounds_event_id", "swap_rounds", ["event_id"], unique=False)

    inspector = sa.inspect(bind)
    if "swap_requests" not in inspector.get_table_names():
        op.create_table(
            "swap_requests",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("round_id", sa.Integer(), sa.ForeignKey("swap_rounds.id", ondelete="CASCADE"), nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("status", sa.String(length=20), server_default="pending", nullable=False),
            sa.Column("error_message", sa.String(length=500), server_default="", nullable=False),
            *_timestamps(),
            sa.UniqueConstraint("round_id", "user_id", name="uq_swap_request_round_user"),
        )
        op.create_index("ix_swap_requests_round_id", "swap_requests", ["round_id"], unique=False)
        op.create_index("ix_swap_requests_user_id", "swap_requests", ["user_id"], unique=False)

    inspector = sa.inspect(bind)
    if "swap_request_items" not in inspector.get_table_names():
        op.create_table(
            "swap_request_items",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("request_id", sa.Integer(), sa.ForeignKey("swap_requests.id", ondelete="CASCADE"), nullable=False),
            sa.Column(
                "original_assignment_id",
                sa.Integer(),
                sa.ForeignKey("draw_assignments.id", ondelete="RESTRICT"),
                nullable=False,
            ),
            sa.Column(
                "replacement_assignment_id",
                sa.Integer(),
                sa.ForeignKey("draw_assignments.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("position", sa.Integer(), nullable=False),
            *_timestamps(),
            sa.UniqueConstraint("request_id", "original_assignment_id", name="uq_swap_item_request_assignment"),
            sa.UniqueConstraint("request_id", "position", name="uq_swap_item_request_position"),
        )
        op.create_index("ix_swap_request_items_request_id", "swap_request_items", ["request_id"], unique=False)
        op.create_index(
            "ix_swap_request_items_original_assignment_id",
            "swap_request_items",
            ["original_assignment_id"],
            unique=False,
        )
        op.create_index(
            "ix_swap_request_items_replacement_assignment_id",
            "swap_request_items",
            ["replacement_assignment_id"],
            unique=False,
        )

    inspector = sa.inspect(bind)
    submission_columns = {column["name"] for column in inspector.get_columns("submissions")}
    with op.batch_alter_table("submissions") as batch:
        if "public_storage_path" not in submission_columns:
            batch.add_column(sa.Column("public_storage_path", sa.String(length=500), nullable=True))
        if "track_duration_seconds" not in submission_columns:
            batch.add_column(sa.Column("track_duration_seconds", sa.Float(), nullable=True))

    submission_checks = {item.get("name") for item in sa.inspect(bind).get_check_constraints("submissions")}
    with op.batch_alter_table("submissions") as batch:
        if "ck_submission_track_type" not in submission_checks:
            batch.create_check_constraint(
                "ck_submission_track_type",
                "track IN ('normal', 'j', 'exhibition')",
            )
        if "ck_submission_source_song_required" not in submission_checks:
            batch.create_check_constraint(
                "ck_submission_source_song_required",
                "track = 'exhibition' OR source_song_id IS NOT NULL",
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    submission_columns = {column["name"] for column in inspector.get_columns("submissions")}
    submission_checks = {item.get("name") for item in inspector.get_check_constraints("submissions")}
    with op.batch_alter_table("submissions") as batch:
        if "ck_submission_source_song_required" in submission_checks:
            batch.drop_constraint("ck_submission_source_song_required", type_="check")
        if "ck_submission_track_type" in submission_checks:
            batch.drop_constraint("ck_submission_track_type", type_="check")
        if "track_duration_seconds" in submission_columns:
            batch.drop_column("track_duration_seconds")
        if "public_storage_path" in submission_columns:
            batch.drop_column("public_storage_path")

    for table_name in ("swap_request_items", "swap_requests", "swap_rounds", "event_phases"):
        if table_name in sa.inspect(bind).get_table_names():
            op.drop_table(table_name)

    inspector = sa.inspect(bind)
    draw_indexes = {item.get("name") for item in inspector.get_indexes("draw_assignments")}
    if "uq_draw_event_active_song" in draw_indexes:
        op.drop_index("uq_draw_event_active_song", table_name="draw_assignments")
    if "ix_draw_assignments_replaces_assignment_id" in draw_indexes:
        op.drop_index("ix_draw_assignments_replaces_assignment_id", table_name="draw_assignments")
    draw_columns = {column["name"] for column in inspector.get_columns("draw_assignments")}
    draw_uniques = {item.get("name") for item in inspector.get_unique_constraints("draw_assignments")}
    with op.batch_alter_table("draw_assignments") as batch:
        if "uq_draw_event_song" not in draw_uniques:
            batch.create_unique_constraint("uq_draw_event_song", ["event_id", "song_id"])
        if "replaces_assignment_id" in draw_columns:
            batch.drop_column("replaces_assignment_id")
        if "draw_kind" in draw_columns:
            batch.drop_column("draw_kind")
        if "status" in draw_columns:
            batch.drop_column("status")

    setting_columns = {column["name"] for column in sa.inspect(bind).get_columns("event_settings")}
    with op.batch_alter_table("event_settings") as batch:
        if "manual_phase" in setting_columns:
            batch.drop_column("manual_phase")
        if "phase_mode" in setting_columns:
            batch.drop_column("phase_mode")
