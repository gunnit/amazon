"""Add scheduled reports tables.

Revision ID: 006_add_scheduled_reports
Revises: 005_forecast_export_jobs
Create Date: 2026-03-31
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "006_add_scheduled_reports"
down_revision = "005_forecast_export_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scheduled_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("frequency", sa.String(length=20), nullable=False),
        sa.Column("format", sa.String(length=20), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False, server_default="UTC"),
        sa.Column("report_types", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("account_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("recipients", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("schedule_config", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("parameters", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_run_status", sa.String(length=20), nullable=True),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index(op.f("ix_scheduled_reports_organization_id"), "scheduled_reports", ["organization_id"], unique=False)
    op.create_index(op.f("ix_scheduled_reports_next_run_at"), "scheduled_reports", ["next_run_at"], unique=False)

    op.create_table(
        "scheduled_report_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("scheduled_report_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("generation_status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("delivery_status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("progress_step", sa.String(length=100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("triggered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("report_name", sa.String(length=255), nullable=False),
        sa.Column("format", sa.String(length=20), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False, server_default="UTC"),
        sa.Column("recipients_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("parameters_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("report_types_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("artifact_filename", sa.String(length=255), nullable=True),
        sa.Column("artifact_content_type", sa.String(length=100), nullable=True),
        sa.Column("artifact_data", sa.LargeBinary(), nullable=True),
        sa.ForeignKeyConstraint(["scheduled_report_id"], ["scheduled_reports.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
    )
    op.create_index(op.f("ix_scheduled_report_runs_scheduled_report_id"), "scheduled_report_runs", ["scheduled_report_id"], unique=False)
    op.create_index(op.f("ix_scheduled_report_runs_organization_id"), "scheduled_report_runs", ["organization_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_scheduled_report_runs_organization_id"), table_name="scheduled_report_runs")
    op.drop_index(op.f("ix_scheduled_report_runs_scheduled_report_id"), table_name="scheduled_report_runs")
    op.drop_table("scheduled_report_runs")
    op.drop_index(op.f("ix_scheduled_reports_next_run_at"), table_name="scheduled_reports")
    op.drop_index(op.f("ix_scheduled_reports_organization_id"), table_name="scheduled_reports")
    op.drop_table("scheduled_reports")
