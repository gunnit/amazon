"""Track where a product row originated (sync vs manual import).

Revision ID: 027_product_source
Revises: 026_widen_alembic_version
Create Date: 2026-06-04
"""
from alembic import op
import sqlalchemy as sa


revision = "027_product_source"
down_revision = "026_widen_alembic_version"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "products",
        sa.Column("source", sa.String(32), nullable=True, server_default="amazon_sync"),
    )


def downgrade() -> None:
    op.drop_column("products", "source")
