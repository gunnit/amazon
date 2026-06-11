"""Add historical backfill tracking columns to amazon_accounts.

Revision ID: 032_account_backfill_tracking
Revises: 031_brand_intelligence
Create Date: 2026-06-11
"""
from alembic import op
import sqlalchemy as sa

revision = "032_account_backfill_tracking"
down_revision = "031_brand_intelligence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("amazon_accounts", sa.Column("last_backfill_status", sa.String(20), nullable=True))
    op.add_column("amazon_accounts", sa.Column("last_backfill_started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("amazon_accounts", sa.Column("last_backfill_completed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("amazon_accounts", sa.Column("last_backfill_records", sa.Integer(), nullable=True))
    op.add_column("amazon_accounts", sa.Column("last_backfill_windows_skipped", sa.Integer(), nullable=True))
    op.add_column("amazon_accounts", sa.Column("last_backfill_error", sa.Text(), nullable=True))
    op.add_column("amazon_accounts", sa.Column("last_backfill_range_start", sa.Date(), nullable=True))
    op.add_column("amazon_accounts", sa.Column("last_backfill_range_end", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("amazon_accounts", "last_backfill_range_end")
    op.drop_column("amazon_accounts", "last_backfill_range_start")
    op.drop_column("amazon_accounts", "last_backfill_error")
    op.drop_column("amazon_accounts", "last_backfill_windows_skipped")
    op.drop_column("amazon_accounts", "last_backfill_records")
    op.drop_column("amazon_accounts", "last_backfill_completed_at")
    op.drop_column("amazon_accounts", "last_backfill_started_at")
    op.drop_column("amazon_accounts", "last_backfill_status")
