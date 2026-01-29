"""Initial schema

Revision ID: 001_initial
Revises:
Create Date: 2024-01-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '001_initial'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Organizations table
    op.create_table(
        'organizations',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('slug', sa.String(100), nullable=False, unique=True),
        sa.Column('settings', postgresql.JSONB, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_organizations_slug', 'organizations', ['slug'])

    # Users table
    op.create_table(
        'users',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('email', sa.String(255), nullable=False, unique=True),
        sa.Column('hashed_password', sa.String(255), nullable=False),
        sa.Column('full_name', sa.String(255), nullable=True),
        sa.Column('is_active', sa.Boolean, default=True, nullable=False),
        sa.Column('is_superuser', sa.Boolean, default=False, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_users_email', 'users', ['email'])

    # Organization Members table
    op.create_table(
        'organization_members',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('organization_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('role', sa.String(50), default='member', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('organization_id', 'user_id', name='uq_org_user'),
    )
    op.create_index('ix_organization_members_org_id', 'organization_members', ['organization_id'])

    # Amazon Accounts table
    op.create_table(
        'amazon_accounts',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('organization_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('account_name', sa.String(255), nullable=False),
        sa.Column('account_type', sa.String(50), nullable=False),
        sa.Column('marketplace_id', sa.String(50), nullable=False),
        sa.Column('marketplace_country', sa.String(10), nullable=False),
        sa.Column('seller_id', sa.String(100), nullable=True),
        sa.Column('sp_api_refresh_token_encrypted', sa.Text, nullable=True),
        sa.Column('ads_api_refresh_token_encrypted', sa.Text, nullable=True),
        sa.Column('login_email_encrypted', sa.Text, nullable=True),
        sa.Column('login_password_encrypted', sa.Text, nullable=True),
        sa.Column('sync_status', sa.String(50), default='pending', nullable=False),
        sa.Column('last_sync_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('sync_error_message', sa.Text, nullable=True),
        sa.Column('is_active', sa.Boolean, default=True, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_amazon_accounts_org_id', 'amazon_accounts', ['organization_id'])

    # Products table
    op.create_table(
        'products',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('account_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('amazon_accounts.id', ondelete='CASCADE'), nullable=False),
        sa.Column('asin', sa.String(20), nullable=False),
        sa.Column('sku', sa.String(100), nullable=True),
        sa.Column('title', sa.String(500), nullable=True),
        sa.Column('brand', sa.String(200), nullable=True),
        sa.Column('category', sa.String(200), nullable=True),
        sa.Column('current_price', sa.Numeric(10, 2), nullable=True),
        sa.Column('current_bsr', sa.Integer, nullable=True),
        sa.Column('image_url', sa.String(500), nullable=True),
        sa.Column('is_active', sa.Boolean, default=True, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('account_id', 'asin', name='uq_account_asin'),
    )
    op.create_index('ix_products_account_asin', 'products', ['account_id', 'asin'])

    # BSR History table
    op.create_table(
        'bsr_history',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('product_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('products.id', ondelete='CASCADE'), nullable=False),
        sa.Column('date', sa.Date, nullable=False),
        sa.Column('bsr_rank', sa.Integer, nullable=False),
        sa.Column('category', sa.String(200), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_bsr_history_product_date', 'bsr_history', ['product_id', 'date'])

    # Sales Data table
    op.create_table(
        'sales_data',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('account_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('amazon_accounts.id', ondelete='CASCADE'), nullable=False),
        sa.Column('date', sa.Date, nullable=False),
        sa.Column('asin', sa.String(20), nullable=False),
        sa.Column('sku', sa.String(100), nullable=True),
        sa.Column('units_ordered', sa.Integer, default=0, nullable=False),
        sa.Column('units_shipped', sa.Integer, default=0, nullable=False),
        sa.Column('ordered_product_sales', sa.Numeric(12, 2), default=0, nullable=False),
        sa.Column('shipped_product_sales', sa.Numeric(12, 2), default=0, nullable=False),
        sa.Column('total_order_items', sa.Integer, default=0, nullable=False),
        sa.Column('browser_sessions', sa.Integer, default=0, nullable=False),
        sa.Column('mobile_sessions', sa.Integer, default=0, nullable=False),
        sa.Column('page_views', sa.Integer, default=0, nullable=False),
        sa.Column('buy_box_percentage', sa.Numeric(5, 2), nullable=True),
        sa.Column('session_percentage', sa.Numeric(5, 2), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('account_id', 'date', 'asin', name='uq_sales_account_date_asin'),
    )
    op.create_index('ix_sales_data_account_date', 'sales_data', ['account_id', 'date'])
    op.create_index('ix_sales_data_asin', 'sales_data', ['asin'])

    # Inventory Snapshots table
    op.create_table(
        'inventory_snapshots',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('account_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('amazon_accounts.id', ondelete='CASCADE'), nullable=False),
        sa.Column('snapshot_date', sa.Date, nullable=False),
        sa.Column('asin', sa.String(20), nullable=False),
        sa.Column('sku', sa.String(100), nullable=True),
        sa.Column('fulfillment_channel', sa.String(20), nullable=False),
        sa.Column('available_quantity', sa.Integer, default=0, nullable=False),
        sa.Column('inbound_quantity', sa.Integer, default=0, nullable=False),
        sa.Column('reserved_quantity', sa.Integer, default=0, nullable=False),
        sa.Column('unfulfillable_quantity', sa.Integer, default=0, nullable=False),
        sa.Column('total_quantity', sa.Integer, default=0, nullable=False),
        sa.Column('days_of_supply', sa.Integer, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('account_id', 'snapshot_date', 'asin', 'fulfillment_channel', name='uq_inventory_account_date_asin_fc'),
    )
    op.create_index('ix_inventory_account_date', 'inventory_snapshots', ['account_id', 'snapshot_date'])

    # Advertising Campaigns table
    op.create_table(
        'advertising_campaigns',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('account_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('amazon_accounts.id', ondelete='CASCADE'), nullable=False),
        sa.Column('campaign_id', sa.String(100), nullable=False),
        sa.Column('campaign_name', sa.String(255), nullable=False),
        sa.Column('campaign_type', sa.String(50), nullable=False),
        sa.Column('state', sa.String(50), default='enabled', nullable=False),
        sa.Column('daily_budget', sa.Numeric(10, 2), nullable=True),
        sa.Column('start_date', sa.Date, nullable=True),
        sa.Column('end_date', sa.Date, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('account_id', 'campaign_id', name='uq_campaign_account_id'),
    )
    op.create_index('ix_campaigns_account_id', 'advertising_campaigns', ['account_id'])

    # Advertising Metrics table
    op.create_table(
        'advertising_metrics',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('campaign_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('advertising_campaigns.id', ondelete='CASCADE'), nullable=False),
        sa.Column('date', sa.Date, nullable=False),
        sa.Column('impressions', sa.BigInteger, default=0, nullable=False),
        sa.Column('clicks', sa.Integer, default=0, nullable=False),
        sa.Column('cost', sa.Numeric(12, 2), default=0, nullable=False),
        sa.Column('attributed_sales_14d', sa.Numeric(12, 2), default=0, nullable=False),
        sa.Column('attributed_units_14d', sa.Integer, default=0, nullable=False),
        sa.Column('acos', sa.Numeric(8, 4), nullable=True),
        sa.Column('roas', sa.Numeric(8, 4), nullable=True),
        sa.Column('ctr', sa.Numeric(8, 4), nullable=True),
        sa.Column('cpc', sa.Numeric(8, 4), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('campaign_id', 'date', name='uq_metrics_campaign_date'),
    )
    op.create_index('ix_metrics_campaign_date', 'advertising_metrics', ['campaign_id', 'date'])

    # Forecasts table
    op.create_table(
        'forecasts',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('account_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('amazon_accounts.id', ondelete='CASCADE'), nullable=False),
        sa.Column('forecast_type', sa.String(50), nullable=False),
        sa.Column('asin', sa.String(20), nullable=True),
        sa.Column('model_used', sa.String(50), nullable=False),
        sa.Column('horizon_days', sa.Integer, nullable=False),
        sa.Column('predictions', postgresql.JSONB, nullable=False),
        sa.Column('mape', sa.Float, nullable=True),
        sa.Column('rmse', sa.Float, nullable=True),
        sa.Column('confidence_interval', sa.Float, default=0.95, nullable=False),
        sa.Column('generated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_forecasts_account_type', 'forecasts', ['account_id', 'forecast_type'])

    # Alert Rules table
    op.create_table(
        'alert_rules',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('organization_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('metric_type', sa.String(100), nullable=False),
        sa.Column('condition', sa.String(50), nullable=False),
        sa.Column('threshold', sa.Float, nullable=False),
        sa.Column('scope_type', sa.String(50), nullable=False),
        sa.Column('scope_ids', postgresql.ARRAY(postgresql.UUID(as_uuid=True)), nullable=True),
        sa.Column('is_active', sa.Boolean, default=True, nullable=False),
        sa.Column('notification_channels', postgresql.ARRAY(sa.String), default=['email'], nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_alert_rules_org_id', 'alert_rules', ['organization_id'])

    # Alerts table
    op.create_table(
        'alerts',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('rule_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('alert_rules.id', ondelete='CASCADE'), nullable=False),
        sa.Column('account_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('amazon_accounts.id', ondelete='SET NULL'), nullable=True),
        sa.Column('asin', sa.String(20), nullable=True),
        sa.Column('current_value', sa.Float, nullable=False),
        sa.Column('threshold_value', sa.Float, nullable=False),
        sa.Column('message', sa.Text, nullable=False),
        sa.Column('severity', sa.String(20), default='warning', nullable=False),
        sa.Column('is_read', sa.Boolean, default=False, nullable=False),
        sa.Column('is_resolved', sa.Boolean, default=False, nullable=False),
        sa.Column('triggered_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_alerts_rule_triggered', 'alerts', ['rule_id', 'triggered_at'])


def downgrade() -> None:
    op.drop_table('alerts')
    op.drop_table('alert_rules')
    op.drop_table('forecasts')
    op.drop_table('advertising_metrics')
    op.drop_table('advertising_campaigns')
    op.drop_table('inventory_snapshots')
    op.drop_table('sales_data')
    op.drop_table('bsr_history')
    op.drop_table('products')
    op.drop_table('amazon_accounts')
    op.drop_table('organization_members')
    op.drop_table('users')
    op.drop_table('organizations')
