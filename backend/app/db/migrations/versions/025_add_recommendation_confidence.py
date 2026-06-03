"""Add confidence level to strategic recommendations.

Revision ID: 025_add_recommendation_confidence
Revises: 024_sales_data_traffic_cols
Create Date: 2026-06-03
"""
from alembic import op
import sqlalchemy as sa


revision = "025_add_recommendation_confidence"
down_revision = "024_sales_data_traffic_cols"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "strategic_recommendations",
        sa.Column("confidence", sa.String(length=16), nullable=False, server_default="medium"),
    )


def downgrade() -> None:
    op.drop_column("strategic_recommendations", "confidence")
