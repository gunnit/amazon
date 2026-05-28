"""Catalog change audit log table.

Revision ID: 022_catalog_change_log
Revises: 021_ba_capabilities
Create Date: 2026-05-28
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "022_catalog_change_log"
down_revision = "021_ba_capabilities"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "catalog_change_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("asin", sa.String(length=20), nullable=True),
        sa.Column("sku", sa.String(length=100), nullable=True),
        sa.Column("field", sa.String(length=32), nullable=False),
        sa.Column("old_value", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("new_value", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("sp_api_status", sa.String(length=16), nullable=False),
        sa.Column("sp_api_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["account_id"], ["amazon_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_catalog_change_log_account_asin_created_at",
        "catalog_change_log",
        ["account_id", "asin", "created_at"],
    )
    op.create_index(
        "ix_catalog_change_log_organization_id",
        "catalog_change_log",
        ["organization_id"],
    )
    op.create_index(
        "ix_catalog_change_log_user_id",
        "catalog_change_log",
        ["user_id"],
    )
    op.create_index(
        "ix_catalog_change_log_asin",
        "catalog_change_log",
        ["asin"],
    )


def downgrade() -> None:
    op.drop_index("ix_catalog_change_log_asin", table_name="catalog_change_log")
    op.drop_index("ix_catalog_change_log_user_id", table_name="catalog_change_log")
    op.drop_index("ix_catalog_change_log_organization_id", table_name="catalog_change_log")
    op.drop_index("ix_catalog_change_log_account_asin_created_at", table_name="catalog_change_log")
    op.drop_table("catalog_change_log")
