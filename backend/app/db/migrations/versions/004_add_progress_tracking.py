"""Add progress tracking columns to market_research_reports

Revision ID: 004_progress_tracking
Revises: 003_market_research
Create Date: 2026-03-29
"""
from alembic import op
import sqlalchemy as sa

revision = '004_progress_tracking'
down_revision = '003_market_research'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('market_research_reports',
                  sa.Column('progress_step', sa.String(100), nullable=True))
    op.add_column('market_research_reports',
                  sa.Column('progress_pct', sa.Integer(), nullable=True, server_default='0'))


def downgrade() -> None:
    op.drop_column('market_research_reports', 'progress_pct')
    op.drop_column('market_research_reports', 'progress_step')
