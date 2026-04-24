"""Add last_refreshed_at to market research reports.

Revision ID: 012_add_last_refreshed_at
Revises: 011_add_brin_indexes_for_retention
Create Date: 2026-04-14
"""
from alembic import op
import sqlalchemy as sa


revision = "012_add_last_refreshed_at"
down_revision = "011_add_brin_indexes_for_retention"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "market_research_reports",
        sa.Column("last_refreshed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("market_research_reports", "last_refreshed_at")
