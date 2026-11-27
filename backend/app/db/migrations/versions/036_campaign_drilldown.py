"""Persist campaign purchases and daily Sponsored Products keyword performance."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "036_campaign_drilldown"
down_revision = "035_partial_variation_references"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("advertising_metrics", "advertising_metrics_by_asin"):
        op.add_column(table, sa.Column("attributed_orders", sa.Integer(), nullable=True))
    op.create_table(
        "advertising_keyword_metrics",
        sa.Column("campaign_id", UUID(as_uuid=True),
                  sa.ForeignKey("advertising_campaigns.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("date", sa.Date(), primary_key=True),
        sa.Column("keyword", sa.String(), primary_key=True),
        sa.Column("match_type", sa.String(50), primary_key=True),
        sa.Column("impressions", sa.Integer(), nullable=False),
        sa.Column("clicks", sa.Integer(), nullable=False),
        sa.Column("cost", sa.Numeric(10, 2), nullable=False),
        sa.Column("attributed_sales_7d", sa.Numeric(10, 2), nullable=False),
        sa.Column("attributed_units_ordered_7d", sa.Integer(), nullable=False),
        sa.Column("attributed_orders", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("advertising_keyword_metrics")
    for table in ("advertising_metrics_by_asin", "advertising_metrics"):
        op.drop_column(table, "attributed_orders")
