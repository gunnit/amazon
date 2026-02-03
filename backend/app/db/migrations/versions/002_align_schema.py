"""Align schema with SQLAlchemy models

Revision ID: 002_align_schema
Revises: 001_initial
Create Date: 2024-01-15

This migration aligns the database schema with the current SQLAlchemy models:
- Adds missing tables: competitors, competitor_history, sync_jobs
- Renames inventory_snapshots -> inventory_data with new structure
- Fixes column types and constraints across multiple tables
- Adds settings/updated_at to organizations
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '002_align_schema'
down_revision = '001_initial'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Note: organizations already has 'settings' and 'updated_at' from 001_initial

    # 1. Drop and recreate inventory with correct name and structure
    op.drop_table('inventory_snapshots')
    op.create_table('inventory_data',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('account_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('snapshot_date', sa.Date(), nullable=False),
        sa.Column('asin', sa.String(20), nullable=False),
        sa.Column('sku', sa.String(100), nullable=True),
        sa.Column('fnsku', sa.String(20), nullable=True),
        sa.Column('afn_fulfillable_quantity', sa.Integer(), server_default='0', nullable=True),
        sa.Column('afn_inbound_working_quantity', sa.Integer(), server_default='0', nullable=True),
        sa.Column('afn_inbound_shipped_quantity', sa.Integer(), server_default='0', nullable=True),
        sa.Column('afn_reserved_quantity', sa.Integer(), server_default='0', nullable=True),
        sa.Column('afn_total_quantity', sa.Integer(), server_default='0', nullable=True),
        sa.Column('mfn_fulfillable_quantity', sa.Integer(), server_default='0', nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['account_id'], ['amazon_accounts.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('account_id', 'snapshot_date', 'asin', name='uq_inventory_account_date_asin')
    )
    op.create_index('ix_inventory_data_account_id', 'inventory_data', ['account_id'])
    op.create_index('ix_inventory_data_snapshot_date', 'inventory_data', ['snapshot_date'])
    op.create_index('ix_inventory_data_asin', 'inventory_data', ['asin'])

    # 3. Drop and recreate sales_data with correct structure
    op.drop_table('sales_data')
    op.create_table('sales_data',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('account_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('asin', sa.String(20), nullable=False),
        sa.Column('sku', sa.String(100), nullable=True),
        sa.Column('units_ordered', sa.Integer(), server_default='0', nullable=True),
        sa.Column('units_ordered_b2b', sa.Integer(), server_default='0', nullable=True),
        sa.Column('ordered_product_sales', sa.Numeric(12, 2), server_default='0', nullable=True),
        sa.Column('ordered_product_sales_b2b', sa.Numeric(12, 2), server_default='0', nullable=True),
        sa.Column('total_order_items', sa.Integer(), server_default='0', nullable=True),
        sa.Column('currency', sa.String(3), server_default="'EUR'", nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['account_id'], ['amazon_accounts.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('account_id', 'date', 'asin', name='uq_sales_data_account_date_asin')
    )
    op.create_index('ix_sales_data_account_id', 'sales_data', ['account_id'])
    op.create_index('ix_sales_data_date', 'sales_data', ['date'])
    op.create_index('ix_sales_data_asin', 'sales_data', ['asin'])

    # 4. Drop and recreate bsr_history with correct structure
    op.drop_table('bsr_history')
    op.create_table('bsr_history',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('product_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('category', sa.String(255), nullable=True),
        sa.Column('bsr', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('product_id', 'date', 'category', name='uq_bsr_product_date_category')
    )
    op.create_index('ix_bsr_history_product_id', 'bsr_history', ['product_id'])
    op.create_index('ix_bsr_history_date', 'bsr_history', ['date'])

    # 5. Adjust products table
    op.alter_column('products', 'title', type_=sa.Text(), existing_type=sa.String(500), existing_nullable=True)
    op.alter_column('products', 'brand', type_=sa.String(255), existing_type=sa.String(200), existing_nullable=True)
    op.alter_column('products', 'category', type_=sa.String(255), existing_type=sa.String(200), existing_nullable=True)
    op.add_column('products', sa.Column('subcategory', sa.String(255), nullable=True))
    op.add_column('products', sa.Column('review_count', sa.Integer(), nullable=True))
    op.add_column('products', sa.Column('rating', sa.Numeric(3, 2), nullable=True))
    op.drop_column('products', 'image_url')
    op.drop_constraint('uq_account_asin', 'products', type_='unique')
    op.create_unique_constraint('uq_product_account_asin', 'products', ['account_id', 'asin'])
    op.drop_index('ix_products_account_asin', table_name='products')
    op.create_index('ix_products_account_id', 'products', ['account_id'])
    op.create_index('ix_products_asin', 'products', ['asin'])

    # 6. Adjust advertising_campaigns table
    op.alter_column('advertising_campaigns', 'campaign_id', type_=sa.String(50), existing_type=sa.String(100))
    op.alter_column('advertising_campaigns', 'campaign_name', nullable=True, existing_nullable=False)
    op.alter_column('advertising_campaigns', 'campaign_type', nullable=True, existing_nullable=False)
    op.alter_column('advertising_campaigns', 'state', type_=sa.String(20), existing_type=sa.String(50), existing_nullable=True)
    op.add_column('advertising_campaigns', sa.Column('targeting_type', sa.String(50), nullable=True))
    op.drop_column('advertising_campaigns', 'start_date')
    op.drop_column('advertising_campaigns', 'end_date')
    op.drop_column('advertising_campaigns', 'updated_at')
    op.drop_constraint('uq_campaign_account_id', 'advertising_campaigns', type_='unique')
    op.create_unique_constraint('uq_ad_campaign_account_campaign', 'advertising_campaigns', ['account_id', 'campaign_id'])

    # 7. Drop and recreate advertising_metrics with correct structure
    op.drop_table('advertising_metrics')
    op.create_table('advertising_metrics',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('campaign_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('impressions', sa.Integer(), server_default='0', nullable=True),
        sa.Column('clicks', sa.Integer(), server_default='0', nullable=True),
        sa.Column('cost', sa.Numeric(10, 2), server_default='0', nullable=True),
        sa.Column('attributed_sales_1d', sa.Numeric(10, 2), server_default='0', nullable=True),
        sa.Column('attributed_sales_7d', sa.Numeric(10, 2), server_default='0', nullable=True),
        sa.Column('attributed_sales_14d', sa.Numeric(10, 2), server_default='0', nullable=True),
        sa.Column('attributed_sales_30d', sa.Numeric(10, 2), server_default='0', nullable=True),
        sa.Column('attributed_units_ordered_1d', sa.Integer(), server_default='0', nullable=True),
        sa.Column('attributed_units_ordered_7d', sa.Integer(), server_default='0', nullable=True),
        sa.Column('attributed_units_ordered_14d', sa.Integer(), server_default='0', nullable=True),
        sa.Column('attributed_units_ordered_30d', sa.Integer(), server_default='0', nullable=True),
        sa.Column('ctr', sa.Numeric(8, 4), nullable=True),
        sa.Column('cpc', sa.Numeric(8, 4), nullable=True),
        sa.Column('acos', sa.Numeric(8, 4), nullable=True),
        sa.Column('roas', sa.Numeric(8, 4), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['campaign_id'], ['advertising_campaigns.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('campaign_id', 'date', name='uq_ad_metrics_campaign_date')
    )
    op.create_index('ix_advertising_metrics_campaign_id', 'advertising_metrics', ['campaign_id'])
    op.create_index('ix_advertising_metrics_date', 'advertising_metrics', ['date'])

    # 8. Adjust forecasts table
    op.alter_column('forecasts', 'predictions', nullable=True, existing_nullable=False)
    op.add_column('forecasts', sa.Column('forecast_horizon_days', sa.Integer(), nullable=True))
    op.drop_column('forecasts', 'horizon_days')

    # 9. Drop and recreate alert_rules with model structure
    op.drop_table('alerts')  # Must drop first due to FK
    op.drop_table('alert_rules')
    op.create_table('alert_rules',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('organization_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('alert_type', sa.String(50), nullable=False),
        sa.Column('conditions', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('applies_to_accounts', postgresql.ARRAY(postgresql.UUID(as_uuid=True)), nullable=True),
        sa.Column('applies_to_asins', postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column('notification_channels', postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column('notification_emails', postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column('webhook_url', sa.String(500), nullable=True),
        sa.Column('is_enabled', sa.Boolean(), server_default='true', nullable=True),
        sa.Column('last_triggered_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_alert_rules_organization_id', 'alert_rules', ['organization_id'])

    # 10. Recreate alerts table (aligned with new Alert model)
    op.create_table('alerts',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('rule_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('account_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('asin', sa.String(20), nullable=True),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('severity', sa.String(20), server_default="'warning'", nullable=True),
        sa.Column('is_read', sa.Boolean(), server_default='false', nullable=True),
        sa.Column('triggered_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['rule_id'], ['alert_rules.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['account_id'], ['amazon_accounts.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_alerts_rule_id', 'alerts', ['rule_id'])

    # 11. Create competitors table
    op.create_table('competitors',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('organization_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('asin', sa.String(20), nullable=False),
        sa.Column('marketplace', sa.String(10), nullable=False),
        sa.Column('title', sa.Text(), nullable=True),
        sa.Column('brand', sa.String(255), nullable=True),
        sa.Column('current_price', sa.Numeric(10, 2), nullable=True),
        sa.Column('current_bsr', sa.Integer(), nullable=True),
        sa.Column('review_count', sa.Integer(), nullable=True),
        sa.Column('rating', sa.Numeric(3, 2), nullable=True),
        sa.Column('is_tracking', sa.Boolean(), server_default='true', nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('organization_id', 'asin', 'marketplace', name='uq_competitor_org_asin_marketplace')
    )
    op.create_index('ix_competitors_organization_id', 'competitors', ['organization_id'])
    op.create_index('ix_competitors_asin', 'competitors', ['asin'])

    # 12. Create competitor_history table
    op.create_table('competitor_history',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('competitor_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('price', sa.Numeric(10, 2), nullable=True),
        sa.Column('bsr', sa.Integer(), nullable=True),
        sa.Column('review_count', sa.Integer(), nullable=True),
        sa.Column('rating', sa.Numeric(3, 2), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['competitor_id'], ['competitors.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('competitor_id', 'date', name='uq_competitor_history_competitor_date')
    )
    op.create_index('ix_competitor_history_competitor_id', 'competitor_history', ['competitor_id'])
    op.create_index('ix_competitor_history_date', 'competitor_history', ['date'])

    # 13. Create sync_jobs table
    op.create_table('sync_jobs',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('account_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('job_type', sa.String(50), nullable=False),
        sa.Column('schedule_cron', sa.String(100), nullable=True),
        sa.Column('is_enabled', sa.Boolean(), server_default='true', nullable=True),
        sa.Column('last_run_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_run_status', sa.String(20), nullable=True),
        sa.Column('last_run_error', sa.Text(), nullable=True),
        sa.Column('last_run_records_processed', sa.Integer(), nullable=True),
        sa.Column('next_run_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['account_id'], ['amazon_accounts.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_sync_jobs_account_id', 'sync_jobs', ['account_id'])


def downgrade() -> None:
    # Drop new tables
    op.drop_table('sync_jobs')
    op.drop_table('competitor_history')
    op.drop_table('competitors')
    op.drop_table('alerts')
    op.drop_table('alert_rules')

    # Recreate old alert_rules structure
    op.create_table('alert_rules',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('organization_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('metric_type', sa.String(100), nullable=False),
        sa.Column('condition', sa.String(50), nullable=False),
        sa.Column('threshold', sa.Float(), nullable=False),
        sa.Column('scope_type', sa.String(50), nullable=False),
        sa.Column('scope_ids', postgresql.ARRAY(postgresql.UUID(as_uuid=True)), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=True),
        sa.Column('notification_channels', postgresql.ARRAY(sa.String()), server_default="'{email}'", nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_alert_rules_org_id', 'alert_rules', ['organization_id'])

    # Recreate old alerts structure
    op.create_table('alerts',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('rule_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('account_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('asin', sa.String(20), nullable=True),
        sa.Column('current_value', sa.Float(), nullable=False),
        sa.Column('threshold_value', sa.Float(), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('severity', sa.String(20), server_default="'warning'", nullable=True),
        sa.Column('is_read', sa.Boolean(), server_default='false', nullable=True),
        sa.Column('is_resolved', sa.Boolean(), server_default='false', nullable=True),
        sa.Column('triggered_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['rule_id'], ['alert_rules.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['account_id'], ['amazon_accounts.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_alerts_rule_triggered', 'alerts', ['rule_id', 'triggered_at'])

    # Revert forecasts
    op.add_column('forecasts', sa.Column('horizon_days', sa.Integer(), nullable=False))
    op.drop_column('forecasts', 'forecast_horizon_days')
    op.alter_column('forecasts', 'predictions', nullable=False, existing_nullable=True)

    # Revert advertising_metrics
    op.drop_table('advertising_metrics')
    op.create_table('advertising_metrics',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('campaign_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('impressions', sa.BigInteger(), server_default='0', nullable=True),
        sa.Column('clicks', sa.Integer(), server_default='0', nullable=True),
        sa.Column('cost', sa.Numeric(12, 2), server_default='0', nullable=True),
        sa.Column('attributed_sales_14d', sa.Numeric(12, 2), server_default='0', nullable=True),
        sa.Column('attributed_units_14d', sa.Integer(), server_default='0', nullable=True),
        sa.Column('acos', sa.Numeric(8, 4), nullable=True),
        sa.Column('roas', sa.Numeric(8, 4), nullable=True),
        sa.Column('ctr', sa.Numeric(8, 4), nullable=True),
        sa.Column('cpc', sa.Numeric(8, 4), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['campaign_id'], ['advertising_campaigns.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('campaign_id', 'date', name='uq_metrics_campaign_date')
    )
    op.create_index('ix_metrics_campaign_date', 'advertising_metrics', ['campaign_id', 'date'])

    # Revert advertising_campaigns
    op.drop_constraint('uq_ad_campaign_account_campaign', 'advertising_campaigns', type_='unique')
    op.create_unique_constraint('uq_campaign_account_id', 'advertising_campaigns', ['account_id', 'campaign_id'])
    op.drop_column('advertising_campaigns', 'targeting_type')
    op.add_column('advertising_campaigns', sa.Column('start_date', sa.Date(), nullable=True))
    op.add_column('advertising_campaigns', sa.Column('end_date', sa.Date(), nullable=True))
    op.add_column('advertising_campaigns', sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True))
    op.alter_column('advertising_campaigns', 'state', type_=sa.String(50), existing_type=sa.String(20))
    op.alter_column('advertising_campaigns', 'campaign_type', nullable=False, existing_nullable=True)
    op.alter_column('advertising_campaigns', 'campaign_name', nullable=False, existing_nullable=True)
    op.alter_column('advertising_campaigns', 'campaign_id', type_=sa.String(100), existing_type=sa.String(50))

    # Revert products
    op.drop_index('ix_products_asin', table_name='products')
    op.drop_index('ix_products_account_id', table_name='products')
    op.create_index('ix_products_account_asin', 'products', ['account_id', 'asin'])
    op.drop_constraint('uq_product_account_asin', 'products', type_='unique')
    op.create_unique_constraint('uq_account_asin', 'products', ['account_id', 'asin'])
    op.add_column('products', sa.Column('image_url', sa.String(500), nullable=True))
    op.drop_column('products', 'rating')
    op.drop_column('products', 'review_count')
    op.drop_column('products', 'subcategory')
    op.alter_column('products', 'category', type_=sa.String(200), existing_type=sa.String(255))
    op.alter_column('products', 'brand', type_=sa.String(200), existing_type=sa.String(255))
    op.alter_column('products', 'title', type_=sa.String(500), existing_type=sa.Text())

    # Revert bsr_history
    op.drop_table('bsr_history')
    op.create_table('bsr_history',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('product_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('bsr_rank', sa.Integer(), nullable=False),
        sa.Column('category', sa.String(200), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_bsr_history_product_date', 'bsr_history', ['product_id', 'date'])

    # Revert sales_data
    op.drop_table('sales_data')
    op.create_table('sales_data',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('account_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('asin', sa.String(20), nullable=False),
        sa.Column('sku', sa.String(100), nullable=True),
        sa.Column('units_ordered', sa.Integer(), server_default='0', nullable=True),
        sa.Column('units_shipped', sa.Integer(), server_default='0', nullable=True),
        sa.Column('ordered_product_sales', sa.Numeric(12, 2), server_default='0', nullable=True),
        sa.Column('shipped_product_sales', sa.Numeric(12, 2), server_default='0', nullable=True),
        sa.Column('total_order_items', sa.Integer(), server_default='0', nullable=True),
        sa.Column('browser_sessions', sa.Integer(), server_default='0', nullable=True),
        sa.Column('mobile_sessions', sa.Integer(), server_default='0', nullable=True),
        sa.Column('page_views', sa.Integer(), server_default='0', nullable=True),
        sa.Column('buy_box_percentage', sa.Numeric(5, 2), nullable=True),
        sa.Column('session_percentage', sa.Numeric(5, 2), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['account_id'], ['amazon_accounts.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('account_id', 'date', 'asin', name='uq_sales_account_date_asin')
    )
    op.create_index('ix_sales_data_account_date', 'sales_data', ['account_id', 'date'])
    op.create_index('ix_sales_data_asin', 'sales_data', ['asin'])

    # Revert inventory
    op.drop_table('inventory_data')
    op.create_table('inventory_snapshots',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('account_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('snapshot_date', sa.Date(), nullable=False),
        sa.Column('asin', sa.String(20), nullable=False),
        sa.Column('sku', sa.String(100), nullable=True),
        sa.Column('fulfillment_channel', sa.String(20), nullable=False),
        sa.Column('available_quantity', sa.Integer(), server_default='0', nullable=True),
        sa.Column('inbound_quantity', sa.Integer(), server_default='0', nullable=True),
        sa.Column('reserved_quantity', sa.Integer(), server_default='0', nullable=True),
        sa.Column('unfulfillable_quantity', sa.Integer(), server_default='0', nullable=True),
        sa.Column('total_quantity', sa.Integer(), server_default='0', nullable=True),
        sa.Column('days_of_supply', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['account_id'], ['amazon_accounts.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('account_id', 'snapshot_date', 'asin', 'fulfillment_channel', name='uq_inventory_account_date_asin_fc')
    )
    op.create_index('ix_inventory_account_date', 'inventory_snapshots', ['account_id', 'snapshot_date'])

    # Note: organizations 'settings' and 'updated_at' were already in 001_initial, no need to drop
