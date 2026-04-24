"""Add is_available flag to products for manual availability overrides.

Revision ID: 014_add_product_availability
Revises: 013_add_forecast_confidence
Create Date: 2026-04-16
"""
from alembic import op
import sqlalchemy as sa


revision = "014_add_product_availability"
down_revision = "013_add_forecast_confidence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "products",
        sa.Column("is_available", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )


def downgrade() -> None:
    op.drop_column("products", "is_available")
