"""repair partially applied submission schema

Revision ID: 0003_schema_repair
Revises: 0002_submission_targets
Create Date: 2026-07-03
"""

from alembic import op
import sqlalchemy as sa


revision = "0003_schema_repair"
down_revision = "0002_submission_targets"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    event_columns = {column["name"] for column in inspector.get_columns("event_settings")}
    if "submissions_open" not in event_columns:
        with op.batch_alter_table("event_settings") as batch:
            batch.add_column(sa.Column("submissions_open", sa.Boolean(), server_default=sa.false(), nullable=False))

    inspector = sa.inspect(bind)
    submission_columns = {column["name"] for column in inspector.get_columns("submissions")}
    unique_constraints = inspector.get_unique_constraints("submissions")
    foreign_keys = inspector.get_foreign_keys("submissions")
    has_song_unique = any(
        set(item.get("column_names") or []) == {"event_id", "user_id", "source_song_id"}
        for item in unique_constraints
    )
    has_source_song_fk = any(
        item.get("constrained_columns") == ["source_song_id"]
        for item in foreign_keys
    )
    with op.batch_alter_table("submissions") as batch:
        if "source_song_id" not in submission_columns:
            batch.add_column(sa.Column("source_song_id", sa.Integer(), nullable=True))
        if "source_kind" not in submission_columns:
            batch.add_column(sa.Column("source_kind", sa.String(length=20), server_default="", nullable=False))
        if "track" not in submission_columns:
            batch.add_column(sa.Column("track", sa.String(length=20), server_default="normal", nullable=False))
        if not has_source_song_fk:
            batch.create_foreign_key(
                "fk_submissions_source_song_id",
                "songs",
                ["source_song_id"],
                ["id"],
                ondelete="RESTRICT",
            )
        if not has_song_unique:
            batch.create_unique_constraint(
                "uq_submission_event_user_song",
                ["event_id", "user_id", "source_song_id"],
            )

    inspector = sa.inspect(bind)
    index_names = {item.get("name") for item in inspector.get_indexes("submissions")}
    if "uq_submission_event_user_j_track" not in index_names:
        op.create_index(
            "uq_submission_event_user_j_track",
            "submissions",
            ["event_id", "user_id"],
            unique=True,
            postgresql_where=sa.text("track = 'j'"),
            sqlite_where=sa.text("track = 'j'"),
        )
    if "ix_submissions_source_song_id" not in index_names:
        op.create_index("ix_submissions_source_song_id", "submissions", ["source_song_id"], unique=False)

    inspector = sa.inspect(bind)
    if "admin_guess_archives" not in inspector.get_table_names():
        op.create_table(
            "admin_guess_archives",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("event_id", sa.Integer(), sa.ForeignKey("events.id", ondelete="CASCADE"), nullable=False),
            sa.Column("uploaded_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("file_name", sa.String(length=255), nullable=False),
            sa.Column("storage_path", sa.String(length=500), nullable=False),
            sa.Column("file_size", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_admin_guess_archives_event_id", "admin_guess_archives", ["event_id"], unique=False)


def downgrade() -> None:
    # This revision only reconciles schema objects owned by 0002.
    pass
