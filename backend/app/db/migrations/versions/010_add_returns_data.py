"""Add persisted Amazon returns table.

Revision ID: 010_add_returns_data
Revises: 009_add_advertising_credentials, 009_add_orders_tables
Create Date: 2026-04-13
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "010_add_returns_data"
down_revision = ("009_add_advertising_credentials", "009_add_orders_tables")
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "returns_data",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("amazon_order_id", sa.String(length=50), nullable=True),
        sa.Column("asin", sa.String(length=20), nullable=True),
        sa.Column("sku", sa.String(length=100), nullable=True),
        sa.Column("return_date", sa.Date(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("reason", sa.String(length=255), nullable=True),
        sa.Column("disposition", sa.String(length=255), nullable=True),
        sa.Column("detailed_disposition", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["account_id"], ["amazon_accounts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_returns_data_account_return_date",
        "returns_data",
        ["account_id", "return_date"],
        unique=False,
    )
    op.create_index("ix_returns_data_asin", "returns_data", ["asin"], unique=False)
    op.create_index(
        "ix_returns_data_amazon_order_id",
        "returns_data",
        ["amazon_order_id"],
        unique=False,
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_returns_data_account_event
        ON returns_data (
            account_id,
            return_date,
            COALESCE(amazon_order_id, ''),
            COALESCE(asin, ''),
            COALESCE(sku, ''),
            COALESCE(reason, ''),
            COALESCE(disposition, ''),
            COALESCE(detailed_disposition, '')
        )
        """
    )


def downgrade() -> None:
    op.drop_index("uq_returns_data_account_event", table_name="returns_data")
    op.drop_index("ix_returns_data_amazon_order_id", table_name="returns_data")
    op.drop_index("ix_returns_data_asin", table_name="returns_data")
    op.drop_index("ix_returns_data_account_return_date", table_name="returns_data")
    op.drop_table("returns_data")
