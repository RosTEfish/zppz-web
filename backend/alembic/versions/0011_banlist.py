"""add historical Ban song imports and matching data

Revision ID: 0011_banlist
Revises: 0010_remove_reveal_closed_phases
Create Date: 2026-07-15
"""

from alembic import op
import sqlalchemy as sa


revision = "0011_banlist"
down_revision = "0010_remove_reveal_closed_phases"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The first migration creates the model metadata wholesale on a fresh
    # database, so these tables already exist in that path. Existing 0010
    # databases need the explicit additions below.
    bind = op.get_bind()
    if "ban_imports" in sa.inspect(bind).get_table_names():
        return
    op.create_table(
        "ban_imports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("file_sha256", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="draft"),
        sa.Column("entry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("issue_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("preview_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("uploaded_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("published_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_ban_imports_file_sha256", "ban_imports", ["file_sha256"], unique=False)
    op.create_index("ix_ban_imports_status_published_at", "ban_imports", ["status", "published_at"], unique=False)

    op.create_table(
        "ban_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("import_id", sa.Integer(), sa.ForeignKey("ban_imports.id", ondelete="CASCADE"), nullable=False),
        sa.Column("round_label", sa.String(length=120), nullable=False),
        sa.Column("song_name", sa.String(length=200), nullable=False),
        sa.Column("artist", sa.String(length=200), nullable=False),
        sa.Column("remark", sa.String(length=500), nullable=False, server_default=""),
        sa.Column("normalized_song_name", sa.String(length=200), nullable=False),
        sa.Column("normalized_artist", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_ban_entries_import_id", "ban_entries", ["import_id"], unique=False)
    op.create_index("ix_ban_entries_import_normalized", "ban_entries", ["import_id", "normalized_song_name", "normalized_artist"], unique=False)
    op.create_index("ix_ban_entries_import_round", "ban_entries", ["import_id", "round_label"], unique=False)

    op.create_table(
        "ban_aliases",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("entry_id", sa.Integer(), sa.ForeignKey("ban_entries.id", ondelete="CASCADE"), nullable=False),
        sa.Column("song_name", sa.String(length=200), nullable=False),
        sa.Column("artist", sa.String(length=200), nullable=False),
        sa.Column("normalized_song_name", sa.String(length=200), nullable=False),
        sa.Column("normalized_artist", sa.String(length=200), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False, server_default="admin"),
        sa.Column("confirmed_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("entry_id", "normalized_song_name", "normalized_artist", name="uq_ban_alias_entry_keys"),
    )
    op.create_index("ix_ban_aliases_entry_id", "ban_aliases", ["entry_id"], unique=False)
    op.create_index("ix_ban_aliases_normalized", "ban_aliases", ["normalized_song_name", "normalized_artist"], unique=False)

    op.create_table(
        "ban_external_evidence",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("import_id", sa.Integer(), sa.ForeignKey("ban_imports.id", ondelete="CASCADE"), nullable=False),
        sa.Column("entry_id", sa.Integer(), sa.ForeignKey("ban_entries.id", ondelete="SET NULL"), nullable=True),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("query_text", sa.String(length=500), nullable=False),
        sa.Column("source_url", sa.String(length=1000), nullable=False, server_default=""),
        sa.Column("summary", sa.String(length=1000), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_ban_external_evidence_import_id", "ban_external_evidence", ["import_id"], unique=False)
    op.create_index("ix_ban_external_evidence_entry_id", "ban_external_evidence", ["entry_id"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    if "ban_imports" not in sa.inspect(bind).get_table_names():
        return
    op.drop_index("ix_ban_external_evidence_entry_id", table_name="ban_external_evidence")
    op.drop_index("ix_ban_external_evidence_import_id", table_name="ban_external_evidence")
    op.drop_table("ban_external_evidence")
    op.drop_index("ix_ban_aliases_normalized", table_name="ban_aliases")
    op.drop_index("ix_ban_aliases_entry_id", table_name="ban_aliases")
    op.drop_table("ban_aliases")
    op.drop_index("ix_ban_entries_import_round", table_name="ban_entries")
    op.drop_index("ix_ban_entries_import_normalized", table_name="ban_entries")
    op.drop_index("ix_ban_entries_import_id", table_name="ban_entries")
    op.drop_table("ban_entries")
    op.drop_index("ix_ban_imports_status_published_at", table_name="ban_imports")
    op.drop_index("ix_ban_imports_file_sha256", table_name="ban_imports")
    op.drop_table("ban_imports")
