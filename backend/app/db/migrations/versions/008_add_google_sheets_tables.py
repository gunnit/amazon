"""Add Google Sheets integration tables.

Revision ID: 008_add_google_sheets
Revises: 008_add_sync_health_fields
Create Date: 2026-04-02
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "008_add_google_sheets"
down_revision = "008_add_sync_health_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- google_sheets_connections ---
    op.create_table(
        "google_sheets_connections",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("google_email", sa.String(length=255), nullable=False),
        sa.Column("refresh_token_encrypted", sa.Text(), nullable=False),
        sa.Column("access_token_encrypted", sa.Text(), nullable=True),
        sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scopes", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("connected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "organization_id", name="uq_gsheets_conn_user_org"),
    )
    op.create_index(op.f("ix_google_sheets_connections_user_id"), "google_sheets_connections", ["user_id"], unique=False)
    op.create_index(op.f("ix_google_sheets_connections_organization_id"), "google_sheets_connections", ["organization_id"], unique=False)

    # --- google_sheets_syncs ---
    op.create_table(
        "google_sheets_syncs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("connection_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("spreadsheet_id", sa.String(length=255), nullable=True),
        sa.Column("spreadsheet_url", sa.Text(), nullable=True),
        sa.Column("frequency", sa.String(length=20), nullable=False),
        sa.Column("sync_mode", sa.String(length=20), nullable=False),
        sa.Column("data_types", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("account_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("parameters", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("schedule_config", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("timezone", sa.String(length=64), nullable=False, server_default="UTC"),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_run_status", sa.String(length=20), nullable=True),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["connection_id"], ["google_sheets_connections.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index(op.f("ix_google_sheets_syncs_organization_id"), "google_sheets_syncs", ["organization_id"], unique=False)
    op.create_index(op.f("ix_google_sheets_syncs_connection_id"), "google_sheets_syncs", ["connection_id"], unique=False)
    op.create_index(op.f("ix_google_sheets_syncs_next_run_at"), "google_sheets_syncs", ["next_run_at"], unique=False)

    # --- google_sheets_sync_runs ---
    op.create_table(
        "google_sheets_sync_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("sync_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("progress_step", sa.String(length=100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("triggered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rows_written", sa.Integer(), nullable=True),
        sa.Column("spreadsheet_url", sa.Text(), nullable=True),
        sa.Column("data_types_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.ForeignKeyConstraint(["sync_id"], ["google_sheets_syncs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
    )
    op.create_index(op.f("ix_google_sheets_sync_runs_sync_id"), "google_sheets_sync_runs", ["sync_id"], unique=False)
    op.create_index(op.f("ix_google_sheets_sync_runs_organization_id"), "google_sheets_sync_runs", ["organization_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_google_sheets_sync_runs_organization_id"), table_name="google_sheets_sync_runs")
    op.drop_index(op.f("ix_google_sheets_sync_runs_sync_id"), table_name="google_sheets_sync_runs")
    op.drop_table("google_sheets_sync_runs")
    op.drop_index(op.f("ix_google_sheets_syncs_next_run_at"), table_name="google_sheets_syncs")
    op.drop_index(op.f("ix_google_sheets_syncs_connection_id"), table_name="google_sheets_syncs")
    op.drop_index(op.f("ix_google_sheets_syncs_organization_id"), table_name="google_sheets_syncs")
    op.drop_table("google_sheets_syncs")
    op.drop_index(op.f("ix_google_sheets_connections_organization_id"), table_name="google_sheets_connections")
    op.drop_index(op.f("ix_google_sheets_connections_user_id"), table_name="google_sheets_connections")
    op.drop_table("google_sheets_connections")
