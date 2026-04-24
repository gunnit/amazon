"""Add persisted Amazon orders tables.

Revision ID: 009_add_orders_tables
Revises: 008_add_google_sheets
Create Date: 2026-04-13
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "009_add_orders_tables"
down_revision = "008_add_google_sheets"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "orders",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("amazon_order_id", sa.String(length=50), nullable=False),
        sa.Column("purchase_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("order_status", sa.String(length=50), nullable=False),
        sa.Column("fulfillment_channel", sa.String(length=50), nullable=True),
        sa.Column("order_total", sa.Numeric(12, 2), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("marketplace_id", sa.String(length=50), nullable=True),
        sa.Column("number_of_items", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["account_id"], ["amazon_accounts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_orders_account_purchase_date", "orders", ["account_id", "purchase_date"], unique=False)
    op.create_index("ix_orders_amazon_order_id", "orders", ["amazon_order_id"], unique=True)

    op.create_table(
        "order_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("asin", sa.String(length=20), nullable=True),
        sa.Column("sku", sa.String(length=100), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("item_price", sa.Numeric(12, 2), nullable=True),
        sa.Column("item_tax", sa.Numeric(12, 2), nullable=True),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_order_items_order_id"), "order_items", ["order_id"], unique=False)
    op.create_index(op.f("ix_order_items_asin"), "order_items", ["asin"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_order_items_asin"), table_name="order_items")
    op.drop_index(op.f("ix_order_items_order_id"), table_name="order_items")
    op.drop_table("order_items")
    op.drop_index("ix_orders_amazon_order_id", table_name="orders")
    op.drop_index("ix_orders_account_purchase_date", table_name="orders")
    op.drop_table("orders")
