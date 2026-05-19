"""Brand analysis — structured error_code column.

Revision ID: 020_ba_err_code
Revises: 019_ba_v2
Create Date: 2026-05-15
"""
from alembic import op
import sqlalchemy as sa


revision = "020_ba_err_code"
down_revision = "019_ba_v2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "brand_analysis_jobs",
        sa.Column("error_code", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("brand_analysis_jobs", "error_code")
