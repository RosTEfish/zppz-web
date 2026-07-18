"""merge the swap window into Stage2 without dropping event history

Revision ID: 0014_stage2_continuous_swap
Revises: 0013_ban_parser_version
Create Date: 2026-07-18
"""

from alembic import op
import sqlalchemy as sa


revision = "0014_stage2_continuous_swap"
down_revision = "0013_ban_parser_version"
branch_labels = None
depends_on = None


MIGRATION_REVISION = revision


def _snapshot_phase_rows(bind) -> None:
    rows = list(
        bind.execute(
            sa.text(
                """
                SELECT id, event_id, phase, starts_at, ends_at
                FROM event_phases
                WHERE phase IN ('draw', 'swap', 'submission_2')
                ORDER BY id
                """
            )
        ).mappings()
    )
    for row in rows:
        exists = bind.execute(
            sa.text(
                """
                SELECT 1
                FROM event_phase_snapshots
                WHERE migration_revision = :revision
                  AND source_id = :source_id
                LIMIT 1
                """
            ),
            {"revision": MIGRATION_REVISION, "source_id": row["id"]},
        ).first()
        if exists:
            continue
        bind.execute(
            sa.text(
                """
                INSERT INTO event_phase_snapshots
                    (event_id, original_phase, starts_at, ends_at, source_id, migration_revision, created_at, updated_at)
                VALUES
                    (:event_id, :phase, :starts_at, :ends_at, :source_id, :revision, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """
            ),
            {
                "event_id": row["event_id"],
                "phase": row["phase"],
                "starts_at": row["starts_at"],
                "ends_at": row["ends_at"],
                "source_id": row["id"],
                "revision": MIGRATION_REVISION,
            },
        )


def _merge_phase_windows(bind) -> None:
    event_ids = [row[0] for row in bind.execute(sa.text("SELECT DISTINCT event_id FROM event_phases"))]
    for event_id in event_ids:
        rows = list(
            bind.execute(
                sa.text(
                    """
                    SELECT id, phase, starts_at, ends_at
                    FROM event_phases
                    WHERE event_id = :event_id AND phase IN ('draw', 'swap', 'submission_2')
                    ORDER BY id
                    """
                ),
                {"event_id": event_id},
            ).mappings()
        )
        by_phase = {row["phase"]: row for row in rows}
        old_swap = by_phase.get("swap")
        stage2 = by_phase.get("submission_2")
        if old_swap:
            if stage2:
                starts_at = old_swap["starts_at"]
                ends_at = stage2["ends_at"]
                bind.execute(
                    sa.text(
                        "UPDATE event_phases SET starts_at = :starts_at, ends_at = :ends_at WHERE id = :id"
                    ),
                    {"starts_at": starts_at, "ends_at": ends_at, "id": stage2["id"]},
                )
                bind.execute(sa.text("DELETE FROM event_phases WHERE id = :id"), {"id": old_swap["id"]})
            else:
                bind.execute(
                    sa.text(
                        "UPDATE event_phases SET phase = 'submission_2' WHERE id = :id"
                    ),
                    {"id": old_swap["id"]},
                )

        draw = by_phase.get("draw")
        if draw:
            bind.execute(sa.text("DELETE FROM event_phases WHERE id = :id"), {"id": draw["id"]})

    bind.execute(
        sa.text(
            "UPDATE event_settings SET phase_mode = 'auto', manual_phase = NULL WHERE manual_phase = 'draw'"
        )
    )
    bind.execute(
        sa.text(
            "UPDATE event_settings SET manual_phase = 'submission_2' WHERE manual_phase = 'swap'"
        )
    )


def _backfill_exclusions(bind) -> None:
    bind.execute(
        sa.text(
            """
            INSERT INTO swap_excluded_songs
                (event_id, user_id, song_id, created_at, updated_at)
            SELECT DISTINCT
                rounds.event_id,
                requests.user_id,
                assignments.song_id,
                CURRENT_TIMESTAMP,
                CURRENT_TIMESTAMP
            FROM swap_request_items AS items
            JOIN swap_requests AS requests ON requests.id = items.request_id
            JOIN swap_rounds AS rounds ON rounds.id = requests.round_id
            JOIN draw_assignments AS assignments ON assignments.id = items.original_assignment_id
            WHERE requests.status = 'completed'
              AND NOT EXISTS (
                  SELECT 1
                  FROM swap_excluded_songs AS existing
                  WHERE existing.event_id = rounds.event_id
                    AND existing.user_id = requests.user_id
                    AND existing.song_id = assignments.song_id
              )
            """
        )
    )


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "event_phase_snapshots" not in inspector.get_table_names():
        op.create_table(
            "event_phase_snapshots",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("event_id", sa.Integer(), sa.ForeignKey("events.id", ondelete="CASCADE"), nullable=False),
            sa.Column("original_phase", sa.String(length=30), nullable=False),
            sa.Column("starts_at", sa.DateTime(), nullable=False),
            sa.Column("ends_at", sa.DateTime(), nullable=False),
            sa.Column("source_id", sa.Integer(), nullable=True),
            sa.Column("migration_revision", sa.String(length=64), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_event_phase_snapshots_event_id", "event_phase_snapshots", ["event_id"], unique=False)

    swap_round_columns = {column["name"] for column in inspector.get_columns("swap_rounds")}
    with op.batch_alter_table("swap_rounds") as batch:
        if "roll_ends_at" not in swap_round_columns:
            batch.add_column(sa.Column("roll_ends_at", sa.DateTime(), nullable=True))
        if "round_kind" not in swap_round_columns:
            batch.add_column(sa.Column("round_kind", sa.String(length=20), server_default="continuous", nullable=False))

    bind.execute(sa.text("UPDATE swap_rounds SET round_kind = 'legacy', roll_ends_at = ends_at"))

    if "swap_excluded_songs" not in sa.inspect(bind).get_table_names():
        op.create_table(
            "swap_excluded_songs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("event_id", sa.Integer(), sa.ForeignKey("events.id", ondelete="CASCADE"), nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("song_id", sa.Integer(), sa.ForeignKey("songs.id", ondelete="CASCADE"), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("event_id", "user_id", "song_id", name="uq_swap_excluded_event_user_song"),
        )
        op.create_index("ix_swap_excluded_songs_event_id", "swap_excluded_songs", ["event_id"], unique=False)
        op.create_index("ix_swap_excluded_songs_user_id", "swap_excluded_songs", ["user_id"], unique=False)
        op.create_index("ix_swap_excluded_songs_song_id", "swap_excluded_songs", ["song_id"], unique=False)
        op.create_index("ix_swap_excluded_event_user", "swap_excluded_songs", ["event_id", "user_id"], unique=False)

    unique_names = {item.get("name") for item in sa.inspect(bind).get_unique_constraints("swap_requests")}
    if "uq_swap_request_round_user" in unique_names:
        with op.batch_alter_table("swap_requests") as batch:
            batch.drop_constraint("uq_swap_request_round_user", type_="unique")

    _snapshot_phase_rows(bind)
    _merge_phase_windows(bind)
    _backfill_exclusions(bind)


def downgrade() -> None:
    # The migration deliberately keeps its snapshots and new history tables on
    # downgrade rather than silently deleting event audit data.
    raise RuntimeError("0014_stage2_continuous_swap is data-preserving and cannot be downgraded automatically")
