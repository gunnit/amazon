"""Add vendor shipped (sell-through) metrics to sales_data.

Revision ID: 028_vendor_shipped_metrics
Revises: 027_product_source
Create Date: 2026-06-08
"""
from alembic import op
import sqlalchemy as sa


revision = "028_vendor_shipped_metrics"
down_revision = "027_product_source"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # sales_data is RANGE-partitioned on date (migration 023); adding a column
    # to the parent propagates to all partitions.
    op.add_column("sales_data", sa.Column("shipped_revenue", sa.Numeric(12, 2), nullable=True))
    op.add_column("sales_data", sa.Column("shipped_units", sa.Integer(), nullable=True))
    op.add_column("sales_data", sa.Column("shipped_cogs", sa.Numeric(12, 2), nullable=True))


def downgrade() -> None:
    op.drop_column("sales_data", "shipped_cogs")
    op.drop_column("sales_data", "shipped_units")
    op.drop_column("sales_data", "shipped_revenue")
