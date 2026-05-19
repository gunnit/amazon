"""Add advertising_metrics_by_asin table for ASIN-level ad performance.

Revision ID: 017_ad_asin_metrics
Revises: 016_strategic_recs
Create Date: 2026-05-06
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "017_ad_asin_metrics"
down_revision = "016_strategic_recs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "advertising_metrics_by_asin",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("asin", sa.String(20), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("impressions", sa.Integer(), server_default="0", nullable=False),
        sa.Column("clicks", sa.Integer(), server_default="0", nullable=False),
        sa.Column("cost", sa.Numeric(10, 2), server_default="0", nullable=False),
        sa.Column("attributed_sales_7d", sa.Numeric(10, 2), server_default="0", nullable=False),
        sa.Column("attributed_units_ordered_7d", sa.Integer(), server_default="0", nullable=False),
        sa.Column("ctr", sa.Numeric(8, 4), nullable=True),
        sa.Column("cpc", sa.Numeric(8, 4), nullable=True),
        sa.Column("acos", sa.Numeric(8, 4), nullable=True),
        sa.Column("roas", sa.Numeric(8, 4), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["account_id"], ["amazon_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["campaign_id"], ["advertising_campaigns.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("campaign_id", "asin", "date", name="uq_ad_asin_metrics_campaign_asin_date"),
    )
    op.create_index("ix_ad_asin_metrics_account_id", "advertising_metrics_by_asin", ["account_id"])
    op.create_index("ix_ad_asin_metrics_campaign_id", "advertising_metrics_by_asin", ["campaign_id"])
    op.create_index("ix_ad_asin_metrics_asin", "advertising_metrics_by_asin", ["asin"])
    op.create_index("ix_ad_asin_metrics_date", "advertising_metrics_by_asin", ["date"])


def downgrade() -> None:
    op.drop_table("advertising_metrics_by_asin")
