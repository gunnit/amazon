"""Add Amazon Advertising credential fields to amazon_accounts.

Revision ID: 009_add_advertising_credentials
Revises: 008_add_google_sheets
Create Date: 2026-04-13
"""
from alembic import op
import sqlalchemy as sa


revision = "009_add_advertising_credentials"
down_revision = "008_add_google_sheets"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_name = 'amazon_accounts'
                  AND column_name = 'ads_api_refresh_token_encrypted'
            ) THEN
                ALTER TABLE amazon_accounts
                RENAME COLUMN ads_api_refresh_token_encrypted TO advertising_refresh_token_encrypted;
            ELSIF NOT EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_name = 'amazon_accounts'
                  AND column_name = 'advertising_refresh_token_encrypted'
            ) THEN
                ALTER TABLE amazon_accounts
                ADD COLUMN advertising_refresh_token_encrypted TEXT NULL;
            END IF;
        END
        $$;
        """
    )

    op.execute(
        """
        ALTER TABLE amazon_accounts
        ADD COLUMN IF NOT EXISTS advertising_profile_id VARCHAR(50) NULL
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE amazon_accounts
        DROP COLUMN IF EXISTS advertising_profile_id
        """
    )

    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_name = 'amazon_accounts'
                  AND column_name = 'advertising_refresh_token_encrypted'
            ) AND NOT EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_name = 'amazon_accounts'
                  AND column_name = 'ads_api_refresh_token_encrypted'
            ) THEN
                ALTER TABLE amazon_accounts
                RENAME COLUMN advertising_refresh_token_encrypted TO ads_api_refresh_token_encrypted;
            END IF;
        END
        $$;
        """
    )
