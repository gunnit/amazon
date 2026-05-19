"""Brand analysis capabilities, readiness and offer snapshots.

Revision ID: 021_ba_capabilities
Revises: 020_ba_err_code
Create Date: 2026-05-19
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "021_ba_capabilities"
down_revision = "020_ba_err_code"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("brand_analysis_jobs", sa.Column("sync_attempt_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("brand_analysis_jobs", sa.Column("last_sync_error", sa.Text(), nullable=True))
    op.add_column("brand_analysis_jobs", sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("brand_analysis_jobs", sa.Column("sync_idempotency_key", sa.String(length=255), nullable=True))
    op.add_column("brand_analysis_jobs", sa.Column("capability_matrix", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("brand_analysis_jobs", sa.Column("data_coverage", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("brand_analysis_jobs", sa.Column("limitations", postgresql.JSONB(astext_type=sa.Text()), nullable=True))

    op.create_table(
        "brand_analysis_capabilities",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("marketplace_id", sa.String(length=50), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sales_and_traffic_available", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("data_kiosk_available", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("brand_analytics_available", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("brand_registry_available_or_inferred", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("product_pricing_available", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("product_fees_available", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("aplus_available", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("finance_reports_available", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("settlement_reports_available", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("catalog_items_available", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("listings_available", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("missing_roles", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("last_error_by_capability", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("raw_diagnostics", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(["account_id"], ["amazon_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "account_id",
            "marketplace_id",
            name="uq_brand_analysis_capabilities_org_account_marketplace",
        ),
    )
    op.create_index("ix_brand_analysis_capabilities_organization_id", "brand_analysis_capabilities", ["organization_id"])
    op.create_index("ix_brand_analysis_capabilities_account_id", "brand_analysis_capabilities", ["account_id"])
    op.create_index("ix_brand_analysis_capabilities_marketplace_id", "brand_analysis_capabilities", ["marketplace_id"])

    op.create_table(
        "asin_offer_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("marketplace_id", sa.String(length=50), nullable=False),
        sa.Column("asin", sa.String(length=20), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("seller_count", sa.Integer(), nullable=True),
        sa.Column("offer_count", sa.Integer(), nullable=True),
        sa.Column("buy_box_owner_name", sa.String(length=255), nullable=True),
        sa.Column("buy_box_seller_id", sa.String(length=100), nullable=True),
        sa.Column("buy_box_price", sa.Numeric(12, 2), nullable=True),
        sa.Column("fulfillment_channel", sa.String(length=50), nullable=True),
        sa.Column("is_fba", sa.Boolean(), nullable=True),
        sa.Column("source", sa.String(length=80), nullable=False),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(["account_id"], ["amazon_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_asin_offer_snapshots_organization_id", "asin_offer_snapshots", ["organization_id"])
    op.create_index("ix_asin_offer_snapshots_account_id", "asin_offer_snapshots", ["account_id"])
    op.create_index("ix_asin_offer_snapshots_marketplace_id", "asin_offer_snapshots", ["marketplace_id"])
    op.create_index("ix_asin_offer_snapshots_asin", "asin_offer_snapshots", ["asin"])


def downgrade() -> None:
    op.drop_index("ix_asin_offer_snapshots_asin", table_name="asin_offer_snapshots")
    op.drop_index("ix_asin_offer_snapshots_marketplace_id", table_name="asin_offer_snapshots")
    op.drop_index("ix_asin_offer_snapshots_account_id", table_name="asin_offer_snapshots")
    op.drop_index("ix_asin_offer_snapshots_organization_id", table_name="asin_offer_snapshots")
    op.drop_table("asin_offer_snapshots")

    op.drop_index("ix_brand_analysis_capabilities_marketplace_id", table_name="brand_analysis_capabilities")
    op.drop_index("ix_brand_analysis_capabilities_account_id", table_name="brand_analysis_capabilities")
    op.drop_index("ix_brand_analysis_capabilities_organization_id", table_name="brand_analysis_capabilities")
    op.drop_table("brand_analysis_capabilities")

    op.drop_column("brand_analysis_jobs", "limitations")
    op.drop_column("brand_analysis_jobs", "data_coverage")
    op.drop_column("brand_analysis_jobs", "capability_matrix")
    op.drop_column("brand_analysis_jobs", "sync_idempotency_key")
    op.drop_column("brand_analysis_jobs", "next_retry_at")
    op.drop_column("brand_analysis_jobs", "last_sync_error")
    op.drop_column("brand_analysis_jobs", "sync_attempt_count")
