"""Add brand analysis automation tables.

Revision ID: 018_brand_analysis
Revises: 017_ad_asin_metrics
Create Date: 2026-05-14
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "018_brand_analysis"
down_revision = "017_ad_asin_metrics"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "brand_analysis_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("brand_name", sa.String(length=255), nullable=False),
        sa.Column("language", sa.String(length=5), nullable=False),
        sa.Column("mode", sa.String(length=20), nullable=False),
        sa.Column("market_type", sa.String(length=20), nullable=False),
        sa.Column("market_query", sa.String(length=500), nullable=True),
        sa.Column("asin_list", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("progress_step", sa.String(length=255), nullable=True),
        sa.Column("progress_pct", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("narrative", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("artifact_filename", sa.String(length=255), nullable=True),
        sa.Column("artifact_content_type", sa.String(length=120), nullable=True),
        sa.Column("artifact_data", sa.LargeBinary(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["account_id"], ["amazon_accounts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_brand_analysis_jobs_account_id", "brand_analysis_jobs", ["account_id"])
    op.create_index("ix_brand_analysis_jobs_organization_id", "brand_analysis_jobs", ["organization_id"])
    op.create_index("ix_brand_analysis_jobs_status", "brand_analysis_jobs", ["status"])

    op.create_table(
        "brand_analysis_source_files",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("uploaded_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=120), nullable=True),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("file_data", sa.LargeBinary(), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=True),
        sa.Column("columns", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["brand_analysis_jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["uploaded_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id", "year", name="uq_brand_analysis_source_files_job_year"),
    )
    op.create_index("ix_brand_analysis_source_files_job_id", "brand_analysis_source_files", ["job_id"])
    op.create_index(
        "ix_brand_analysis_source_files_organization_id",
        "brand_analysis_source_files",
        ["organization_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_brand_analysis_source_files_organization_id", table_name="brand_analysis_source_files")
    op.drop_index("ix_brand_analysis_source_files_job_id", table_name="brand_analysis_source_files")
    op.drop_table("brand_analysis_source_files")
    op.drop_index("ix_brand_analysis_jobs_status", table_name="brand_analysis_jobs")
    op.drop_index("ix_brand_analysis_jobs_organization_id", table_name="brand_analysis_jobs")
    op.drop_index("ix_brand_analysis_jobs_account_id", table_name="brand_analysis_jobs")
    op.drop_table("brand_analysis_jobs")
