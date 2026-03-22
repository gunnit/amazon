"""Add market_research_reports table

Revision ID: 003_market_research
Revises: 002_align_schema
Create Date: 2026-03-20
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '003_market_research'
down_revision = '002_align_schema'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'market_research_reports',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('organization_id', postgresql.UUID(as_uuid=True),
                   sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('created_by_id', postgresql.UUID(as_uuid=True),
                   sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('account_id', postgresql.UUID(as_uuid=True),
                   sa.ForeignKey('amazon_accounts.id', ondelete='CASCADE'), nullable=False),
        sa.Column('source_asin', sa.String(20), nullable=False),
        sa.Column('marketplace', sa.String(10), nullable=True),
        sa.Column('language', sa.String(5), nullable=False, server_default='en'),
        sa.Column('title', sa.String(500), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('product_snapshot', postgresql.JSONB(), nullable=True),
        sa.Column('competitor_data', postgresql.JSONB(), nullable=True),
        sa.Column('ai_analysis', postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_market_research_reports_organization_id',
                     'market_research_reports', ['organization_id'])
    op.create_index('ix_market_research_reports_account_id',
                     'market_research_reports', ['account_id'])


def downgrade() -> None:
    op.drop_index('ix_market_research_reports_account_id')
    op.drop_index('ix_market_research_reports_organization_id')
    op.drop_table('market_research_reports')
