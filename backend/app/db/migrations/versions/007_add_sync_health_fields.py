"""Add sync health fields for account state.

Revision ID: 008_add_sync_health_fields
Revises: 007_add_alert_incident_tracking, 007_optimize_alert_queries
Create Date: 2026-04-02
"""
from alembic import op
import sqlalchemy as sa


revision = "008_add_sync_health_fields"
down_revision = ("007_add_alert_incident_tracking", "007_optimize_alert_queries")
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("amazon_accounts", sa.Column("last_sync_started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("amazon_accounts", sa.Column("last_sync_succeeded_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("amazon_accounts", sa.Column("last_sync_failed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("amazon_accounts", sa.Column("last_sync_attempt_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("amazon_accounts", sa.Column("last_sync_heartbeat_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("amazon_accounts", sa.Column("sync_error_code", sa.String(length=100), nullable=True))
    op.add_column("amazon_accounts", sa.Column("sync_error_kind", sa.String(length=20), nullable=True))

    op.execute(
        """
        UPDATE amazon_accounts
        SET last_sync_succeeded_at = last_sync_at
        WHERE last_sync_at IS NOT NULL
        """
    )

def downgrade() -> None:
    op.drop_column("amazon_accounts", "sync_error_kind")
    op.drop_column("amazon_accounts", "sync_error_code")
    op.drop_column("amazon_accounts", "last_sync_heartbeat_at")
    op.drop_column("amazon_accounts", "last_sync_attempt_at")
    op.drop_column("amazon_accounts", "last_sync_failed_at")
    op.drop_column("amazon_accounts", "last_sync_succeeded_at")
    op.drop_column("amazon_accounts", "last_sync_started_at")
