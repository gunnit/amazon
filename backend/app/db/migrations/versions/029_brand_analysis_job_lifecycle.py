"""Brand analysis job lifecycle: cancel + heartbeat + task tracking.

Revision ID: 029_brand_analysis_job_lifecycle
Revises: 028_vendor_shipped_metrics
Create Date: 2026-06-09
"""
from alembic import op
import sqlalchemy as sa


revision = "029_brand_analysis_job_lifecycle"
down_revision = "028_vendor_shipped_metrics"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("brand_analysis_jobs", sa.Column("celery_task_id", sa.String(length=155), nullable=True))
    op.add_column(
        "brand_analysis_jobs",
        sa.Column("cancel_requested", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("brand_analysis_jobs", sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("brand_analysis_jobs", sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index(
        "ix_brand_analysis_jobs_status_heartbeat",
        "brand_analysis_jobs",
        ["status", "heartbeat_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_brand_analysis_jobs_status_heartbeat", table_name="brand_analysis_jobs")
    op.drop_column("brand_analysis_jobs", "heartbeat_at")
    op.drop_column("brand_analysis_jobs", "started_at")
    op.drop_column("brand_analysis_jobs", "cancel_requested")
    op.drop_column("brand_analysis_jobs", "celery_task_id")
