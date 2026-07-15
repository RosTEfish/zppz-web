"""remove reveal and closed phases

Revision ID: 0010_remove_reveal_closed_phases
Revises: 0009_remove_legacy_phase_settings
Create Date: 2026-07-15
"""

from alembic import op
import sqlalchemy as sa


revision = "0010_remove_reveal_closed_phases"
down_revision = "0009_remove_legacy_phase_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    phases = sa.table("event_phases", sa.column("phase", sa.String()))
    settings = sa.table(
        "event_settings",
        sa.column("phase_mode", sa.String()),
        sa.column("manual_phase", sa.String()),
    )
    bind.execute(sa.delete(phases).where(phases.c.phase.in_(("reveal", "closed"))))
    bind.execute(
        sa.update(settings)
        .where(settings.c.manual_phase.in_(("reveal", "closed")))
        .values(phase_mode="auto", manual_phase=None)
    )


def downgrade() -> None:
    # Removed phase windows cannot be reconstructed without a deployment backup.
    pass
