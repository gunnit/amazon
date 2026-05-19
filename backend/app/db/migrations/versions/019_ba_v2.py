"""Brand analysis v2 — data source provenance, validation report, storage ref.

Revision ID: 019_ba_v2
Revises: 018_brand_analysis
Create Date: 2026-05-15
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "019_ba_v2"
down_revision = "018_brand_analysis"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "brand_analysis_jobs",
        sa.Column("data_source_name", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "brand_analysis_jobs",
        sa.Column("metric_provenance", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "brand_analysis_jobs",
        sa.Column("storage_ref", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "brand_analysis_source_files",
        sa.Column("column_validation", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "brand_analysis_source_files",
        sa.Column("storage_ref", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("brand_analysis_source_files", "storage_ref")
    op.drop_column("brand_analysis_source_files", "column_validation")
    op.drop_column("brand_analysis_jobs", "storage_ref")
    op.drop_column("brand_analysis_jobs", "metric_provenance")
    op.drop_column("brand_analysis_jobs", "data_source_name")
