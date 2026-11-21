"""Catalogue monitoring tables (listing quality rules, content protection,
variation baselines, change requests, PTD cache, image checks, API capabilities)
and Product main keyword columns.

Revision ID: 034_catalog_monitor
Revises: 033_ingestion_expansion
Create Date: 2026-11-21
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "034_catalog_monitor"
down_revision = "033_ingestion_expansion"
branch_labels = None
depends_on = None


def _account_fk():
    return sa.Column(
        "account_id",
        UUID(as_uuid=True),
        sa.ForeignKey("amazon_accounts.id", ondelete="CASCADE"),
        nullable=False,
    )


def _org_fk():
    return sa.Column(
        "organization_id",
        UUID(as_uuid=True),
        sa.ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )


def _user_fk(name: str):
    return sa.Column(
        name, UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


def upgrade() -> None:
    op.create_table(
        "listing_content_versions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        _account_fk(),
        sa.Column("asin", sa.String(20), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("content", JSONB(), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_listing_content_versions_account_asin_last_seen",
        "listing_content_versions",
        ["account_id", "asin", "last_seen_at"],
    )

    op.create_table(
        "listing_content_baselines",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        _account_fk(),
        sa.Column("asin", sa.String(20), nullable=False),
        sa.Column("content", JSONB(), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        _user_fk("approved_by_user_id"),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("account_id", "asin", name="uq_listing_content_baseline_account_asin"),
    )

    op.create_table(
        "variation_family_baselines",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        _account_fk(),
        sa.Column("parent_asin", sa.String(20), nullable=False),
        sa.Column("variation_theme", sa.String(100), nullable=True),
        sa.Column("child_asins", JSONB(), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("account_id", "parent_asin", name="uq_variation_baseline_account_parent"),
    )

    op.create_table(
        "catalog_anomalies",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        _account_fk(),
        sa.Column("asin", sa.String(20), nullable=False),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("field", sa.String(80), nullable=False),
        sa.Column("baseline_value", JSONB(), nullable=True),
        sa.Column("live_value", JSONB(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("change_request_id", UUID(as_uuid=True), nullable=True),
    )
    op.create_index(
        "uq_catalog_anomalies_open",
        "catalog_anomalies",
        ["account_id", "asin", "kind", "field"],
        unique=True,
        postgresql_where=sa.text("status <> 'resolved'"),
    )

    op.create_table(
        "catalog_change_requests",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        _org_fk(),
        _account_fk(),
        sa.Column("batch_id", UUID(as_uuid=True), nullable=False),
        sa.Column("asin", sa.String(20), nullable=True),
        sa.Column("sku", sa.String(100), nullable=True),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("operation", sa.String(16), nullable=False),
        sa.Column("product_type", sa.String(100), nullable=True),
        sa.Column("payload", JSONB(), nullable=False),
        sa.Column("summary", JSONB(), nullable=True),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("validation_issues", JSONB(), nullable=True),
        sa.Column("submission_result", JSONB(), nullable=True),
        sa.Column("feed_id", sa.String(64), nullable=True),
        _user_fk("created_by_user_id"),
        _user_fk("approved_by_user_id"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_catalog_change_requests_batch_id", "catalog_change_requests", ["batch_id"]
    )

    op.create_table(
        "listing_quality_rules",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        _org_fk(),
        sa.Column("marketplace_id", sa.String(20), nullable=True),
        sa.Column("product_type", sa.String(100), nullable=True),
        sa.Column("rule_key", sa.String(40), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("mandatory", sa.Boolean(), nullable=False),
        sa.Column("params", JSONB(), nullable=True),
        _user_fk("updated_by_user_id"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "uq_listing_quality_rules_scope",
        "listing_quality_rules",
        [
            "organization_id",
            sa.text("coalesce(marketplace_id, '')"),
            sa.text("coalesce(product_type, '')"),
            "rule_key",
        ],
        unique=True,
    )

    op.create_table(
        "product_type_definitions_cache",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("marketplace_id", sa.String(20), nullable=False),
        sa.Column("product_type", sa.String(100), nullable=False),
        sa.Column("required_attributes", JSONB(), nullable=False),
        sa.Column("property_names", JSONB(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("marketplace_id", "product_type", name="uq_ptd_cache_marketplace_type"),
    )

    op.create_table(
        "image_checks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("url_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("white_background", sa.Boolean(), nullable=True),
        sa.Column("fill_ratio", sa.Float(), nullable=True),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "catalog_api_capabilities",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "account_id",
            UUID(as_uuid=True),
            sa.ForeignKey("amazon_accounts.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("results", JSONB(), nullable=False),
        sa.Column("vendor_code", sa.String(40), nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.add_column("products", sa.Column("main_keyword", sa.String(255), nullable=True))
    op.add_column("products", sa.Column("main_keyword_source", sa.String(20), nullable=True))


def downgrade() -> None:
    op.drop_column("products", "main_keyword_source")
    op.drop_column("products", "main_keyword")
    op.drop_table("catalog_api_capabilities")
    op.drop_table("image_checks")
    op.drop_table("product_type_definitions_cache")
    op.drop_index("uq_listing_quality_rules_scope", table_name="listing_quality_rules")
    op.drop_table("listing_quality_rules")
    op.drop_index("ix_catalog_change_requests_batch_id", table_name="catalog_change_requests")
    op.drop_table("catalog_change_requests")
    op.drop_index("uq_catalog_anomalies_open", table_name="catalog_anomalies")
    op.drop_table("catalog_anomalies")
    op.drop_table("variation_family_baselines")
    op.drop_table("listing_content_baselines")
    op.drop_index(
        "ix_listing_content_versions_account_asin_last_seen",
        table_name="listing_content_versions",
    )
    op.drop_table("listing_content_versions")
