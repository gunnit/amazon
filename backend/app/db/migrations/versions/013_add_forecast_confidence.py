"""Add forecast confidence and data quality fields.

Revision ID: 013_add_forecast_confidence
Revises: 012_add_last_refreshed_at
Create Date: 2026-04-14
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "013_add_forecast_confidence"
down_revision = "012_add_last_refreshed_at"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("forecasts", sa.Column("confidence_level", sa.String(length=20), nullable=True))
    op.add_column("forecasts", sa.Column("data_quality_notes", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("forecasts", "data_quality_notes")
    op.drop_column("forecasts", "confidence_level")
