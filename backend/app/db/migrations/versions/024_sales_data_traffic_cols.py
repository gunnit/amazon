"""Add traffic columns to sales_data (browser_sessions, mobile_sessions, page_views).

These columns exist on the SalesData model (used by the dashboard conversion-rate
metrics) but were never added by a migration, so analytics queries against
sales_data failed with UndefinedColumnError. server_default='0' backfills the
existing rows; the model keeps a client-side default.

Revision ID: 024_sales_data_traffic_cols
Revises: 023_partition_ts_tables
Create Date: 2026-06-02
"""
from alembic import op
import sqlalchemy as sa


revision = "024_sales_data_traffic_cols"
down_revision = "023_partition_ts_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sales_data", sa.Column("browser_sessions", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("sales_data", sa.Column("mobile_sessions", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("sales_data", sa.Column("page_views", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("sales_data", "page_views")
    op.drop_column("sales_data", "mobile_sessions")
    op.drop_column("sales_data", "browser_sessions")
