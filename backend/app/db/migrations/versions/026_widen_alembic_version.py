"""Widen alembic_version.version_num so longer revision ids fit.

Revision ID: 026_widen_alembic_version
Revises: 025_recommendation_confidence
Create Date: 2026-06-04
"""
from alembic import op
import sqlalchemy as sa


revision = "026_widen_alembic_version"
down_revision = "025_recommendation_confidence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "alembic_version",
        "version_num",
        type_=sa.String(255),
        existing_type=sa.String(32),
        existing_nullable=False,
    )


def downgrade() -> None:
    # No-op: narrowing version_num could truncate a stored revision id.
    pass
