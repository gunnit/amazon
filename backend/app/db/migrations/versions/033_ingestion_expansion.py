"""New ingestion tables: ASIN economics, fee/price snapshots, brand search terms,
listing quality snapshots.

Revision ID: 033_ingestion_expansion
Revises: 032_account_backfill_tracking
Create Date: 2026-06-11
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "033_ingestion_expansion"
down_revision = "032_account_backfill_tracking"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "asin_economics",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "account_id",
            UUID(as_uuid=True),
            sa.ForeignKey("amazon_accounts.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("date", sa.Date(), nullable=False, index=True),
        sa.Column("asin", sa.String(20), nullable=False, index=True),
        sa.Column("units_ordered", sa.Integer(), nullable=True),
        sa.Column("units_refunded", sa.Integer(), nullable=True),
        sa.Column("net_units_sold", sa.Integer(), nullable=True),
        sa.Column("ordered_product_sales", sa.Numeric(12, 2), nullable=True),
        sa.Column("net_product_sales", sa.Numeric(12, 2), nullable=True),
        sa.Column("currency", sa.String(8), nullable=True),
        sa.Column("total_fees", sa.Numeric(12, 2), nullable=True),
        sa.Column("ads_spend", sa.Numeric(12, 2), nullable=True),
        sa.Column("net_proceeds_total", sa.Numeric(12, 2), nullable=True),
        sa.Column("net_proceeds_per_unit", sa.Numeric(12, 4), nullable=True),
        sa.Column("fee_breakdown", JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("account_id", "date", "asin", name="uq_asin_economics_account_date_asin"),
    )
    op.create_index(
        "ix_asin_economics_account_date", "asin_economics", ["account_id", "date"]
    )

    op.create_table(
        "fee_estimates",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "account_id",
            UUID(as_uuid=True),
            sa.ForeignKey("amazon_accounts.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("asin", sa.String(20), nullable=False, index=True),
        sa.Column("snapshot_date", sa.Date(), nullable=False, index=True),
        sa.Column("price_basis", sa.Numeric(10, 2), nullable=True),
        sa.Column("currency", sa.String(8), nullable=True),
        sa.Column("estimated_fees", sa.Numeric(10, 2), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("account_id", "asin", "snapshot_date", name="uq_fee_estimates_account_asin_date"),
    )

    op.create_table(
        "price_snapshots",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "account_id",
            UUID(as_uuid=True),
            sa.ForeignKey("amazon_accounts.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("asin", sa.String(20), nullable=False, index=True),
        sa.Column("snapshot_date", sa.Date(), nullable=False, index=True),
        sa.Column("our_price", sa.Numeric(10, 2), nullable=True),
        sa.Column("buy_box_price", sa.Numeric(10, 2), nullable=True),
        sa.Column("buy_box_seller_id", sa.String(100), nullable=True),
        sa.Column("is_buy_box_ours", sa.Boolean(), nullable=True),
        sa.Column("offer_count", sa.Integer(), nullable=True),
        sa.Column("is_fba", sa.Boolean(), nullable=True),
        sa.Column("currency", sa.String(8), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("account_id", "asin", "snapshot_date", name="uq_price_snapshots_account_asin_date"),
    )

    op.create_table(
        "brand_search_terms",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "account_id",
            UUID(as_uuid=True),
            sa.ForeignKey("amazon_accounts.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("week_start", sa.Date(), nullable=False, index=True),
        sa.Column("week_end", sa.Date(), nullable=False),
        sa.Column("search_term", sa.String(500), nullable=False),
        sa.Column("search_frequency_rank", sa.Integer(), nullable=True),
        sa.Column("department", sa.String(255), nullable=True),
        sa.Column("top_clicked", JSONB(), nullable=True),
        sa.Column("contains_account_asin", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "account_id", "week_start", "search_term", name="uq_brand_search_terms_account_week_term"
        ),
    )

    op.create_table(
        "listing_quality_snapshots",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "account_id",
            UUID(as_uuid=True),
            sa.ForeignKey("amazon_accounts.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("asin", sa.String(20), nullable=False, index=True),
        sa.Column("snapshot_date", sa.Date(), nullable=False, index=True),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("components", JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "account_id", "asin", "snapshot_date", name="uq_listing_quality_account_asin_date"
        ),
    )


def downgrade() -> None:
    op.drop_table("listing_quality_snapshots")
    op.drop_table("brand_search_terms")
    op.drop_table("price_snapshots")
    op.drop_index("ix_asin_economics_account_date", table_name="asin_economics")
    op.drop_table("fee_estimates")
    op.drop_table("asin_economics")
