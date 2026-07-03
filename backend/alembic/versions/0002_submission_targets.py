"""add candidate-linked submissions and submission phase

Revision ID: 0002_submission_targets
Revises: 0001_initial
Create Date: 2026-07-03
"""

from pathlib import Path
import os

from alembic import op
import sqlalchemy as sa


revision = "0002_submission_targets"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def _safe_unlink(root: Path, relative_path: str) -> None:
    try:
        path = (root / relative_path).resolve()
        path.relative_to(root)
        path.unlink(missing_ok=True)
    except (OSError, ValueError):
        pass


def _purge_current_event_legacy_submissions() -> None:
    bind = op.get_bind()
    event_ids = [row[0] for row in bind.execute(sa.text("SELECT id FROM events WHERE is_current = true"))]
    if not event_ids:
        return

    data_dir = Path(os.getenv("DATA_DIR", "/data")).resolve()
    for event_id in event_ids:
        submission_paths = [
            row[0]
            for row in bind.execute(
                sa.text("SELECT storage_path FROM submissions WHERE event_id = :event_id"),
                {"event_id": event_id},
            )
        ]
        submission_paths.extend(
            row[0]
            for row in bind.execute(
                sa.text("SELECT storage_path FROM j_track_submissions WHERE event_id = :event_id"),
                {"event_id": event_id},
            )
        )
        chart_rows = list(
            bind.execute(
                sa.text(
                    "SELECT id, cover_path FROM guess_charts "
                    "WHERE event_id = :event_id "
                    "AND source_submission_type IN ('normal', 'j') "
                    "AND source_submission_id IS NOT NULL"
                ),
                {"event_id": event_id},
            )
        )
        chart_ids = [row[0] for row in chart_rows]
        if chart_ids:
            placeholders = ",".join(str(int(chart_id)) for chart_id in chart_ids)
            bind.execute(sa.text(f"DELETE FROM guess_author_guesses WHERE chart_id IN ({placeholders})"))
            bind.execute(sa.text(f"DELETE FROM guess_comments WHERE chart_id IN ({placeholders})"))
            bind.execute(sa.text(f"DELETE FROM guess_votes WHERE chart_id IN ({placeholders})"))
            bind.execute(sa.text(f"DELETE FROM guess_charts WHERE id IN ({placeholders})"))
        bind.execute(
            sa.text("DELETE FROM import_issues WHERE event_id = :event_id AND source_type IN ('normal', 'j')"),
            {"event_id": event_id},
        )
        bind.execute(sa.text("DELETE FROM submissions WHERE event_id = :event_id"), {"event_id": event_id})
        bind.execute(sa.text("DELETE FROM j_track_submissions WHERE event_id = :event_id"), {"event_id": event_id})

        for storage_path in submission_paths:
            if storage_path:
                _safe_unlink(data_dir, storage_path)
        for _, cover_path in chart_rows:
            prefix = "/api/v1/assets/guess-covers/"
            if cover_path and cover_path.startswith(prefix):
                _safe_unlink(data_dir, f"assets/guess-covers/{Path(cover_path).name}")


def upgrade() -> None:
    _purge_current_event_legacy_submissions()
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    event_columns = {column["name"] for column in inspector.get_columns("event_settings")}
    if "submissions_open" not in event_columns:
        with op.batch_alter_table("event_settings") as batch:
            batch.add_column(sa.Column("submissions_open", sa.Boolean(), server_default=sa.false(), nullable=False))

    submission_columns = {column["name"] for column in inspector.get_columns("submissions")}
    constraint_names = {item.get("name") for item in inspector.get_unique_constraints("submissions")}
    foreign_keys = inspector.get_foreign_keys("submissions")
    has_source_song_fk = any(item.get("constrained_columns") == ["source_song_id"] for item in foreign_keys)
    with op.batch_alter_table("submissions") as batch:
        if "source_song_id" not in submission_columns:
            batch.add_column(sa.Column("source_song_id", sa.Integer(), nullable=True))
        if "source_kind" not in submission_columns:
            batch.add_column(sa.Column("source_kind", sa.String(length=20), server_default="", nullable=False))
        if "track" not in submission_columns:
            batch.add_column(sa.Column("track", sa.String(length=20), server_default="normal", nullable=False))
        if not has_source_song_fk:
            batch.create_foreign_key("fk_submissions_source_song_id", "songs", ["source_song_id"], ["id"], ondelete="RESTRICT")
        if "uq_submission_event_user_song" not in constraint_names:
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
    op.drop_index("ix_admin_guess_archives_event_id", table_name="admin_guess_archives")
    op.drop_table("admin_guess_archives")
    op.drop_index("ix_submissions_source_song_id", table_name="submissions")
    op.drop_index("uq_submission_event_user_j_track", table_name="submissions")
    with op.batch_alter_table("submissions") as batch:
        batch.drop_constraint("uq_submission_event_user_song", type_="unique")
        batch.drop_constraint("fk_submissions_source_song_id", type_="foreignkey")
        batch.drop_column("track")
        batch.drop_column("source_kind")
        batch.drop_column("source_song_id")
    with op.batch_alter_table("event_settings") as batch:
        batch.drop_column("submissions_open")
