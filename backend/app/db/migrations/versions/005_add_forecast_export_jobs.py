"""Add forecast export jobs table.

Revision ID: 005_forecast_export_jobs
Revises: 004_progress_tracking
Create Date: 2026-03-30
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "005_forecast_export_jobs"
down_revision = "004_progress_tracking"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "forecast_export_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("forecast_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("progress_step", sa.String(length=100), nullable=True),
        sa.Column("progress_pct", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("template", sa.String(length=20), nullable=False, server_default="corporate"),
        sa.Column("language", sa.String(length=5), nullable=False, server_default="en"),
        sa.Column("include_insights", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("artifact_filename", sa.String(length=255), nullable=True),
        sa.Column("artifact_content_type", sa.String(length=100), nullable=True),
        sa.Column("artifact_data", sa.LargeBinary(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["forecast_id"], ["forecasts.id"], ondelete="CASCADE"),
    )
    op.create_index(op.f("ix_forecast_export_jobs_organization_id"), "forecast_export_jobs", ["organization_id"], unique=False)
    op.create_index(op.f("ix_forecast_export_jobs_forecast_id"), "forecast_export_jobs", ["forecast_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_forecast_export_jobs_forecast_id"), table_name="forecast_export_jobs")
    op.drop_index(op.f("ix_forecast_export_jobs_organization_id"), table_name="forecast_export_jobs")
    op.drop_table("forecast_export_jobs")
