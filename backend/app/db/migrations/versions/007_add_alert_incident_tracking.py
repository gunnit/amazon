"""Add alert incident tracking fields.

Revision ID: 007_add_alert_incident_tracking
Revises: 006_add_scheduled_reports
Create Date: 2026-04-02
"""
from alembic import op


revision = "007_add_alert_incident_tracking"
down_revision = "006_add_scheduled_reports"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE alerts ADD COLUMN IF NOT EXISTS details JSONB NOT NULL DEFAULT '{}'::jsonb")
    op.execute("ALTER TABLE alerts ADD COLUMN IF NOT EXISTS event_kind VARCHAR(64) NOT NULL DEFAULT 'generic'")
    op.execute("ALTER TABLE alerts ADD COLUMN IF NOT EXISTS dedup_key VARCHAR(255) NOT NULL DEFAULT 'legacy'")
    op.execute("ALTER TABLE alerts ADD COLUMN IF NOT EXISTS last_seen_at TIMESTAMPTZ NULL")
    op.execute("ALTER TABLE alerts ADD COLUMN IF NOT EXISTS notification_status VARCHAR(20) NOT NULL DEFAULT 'pending'")
    op.execute("ALTER TABLE alerts ADD COLUMN IF NOT EXISTS last_notification_attempt_at TIMESTAMPTZ NULL")
    op.execute("ALTER TABLE alerts ADD COLUMN IF NOT EXISTS notification_sent_at TIMESTAMPTZ NULL")
    op.execute("ALTER TABLE alerts ADD COLUMN IF NOT EXISTS notification_error TEXT NULL")

    op.execute("UPDATE alerts SET details = '{}'::jsonb WHERE details IS NULL")
    op.execute("UPDATE alerts SET event_kind = 'legacy' WHERE event_kind IS NULL OR event_kind = ''")
    op.execute("UPDATE alerts SET dedup_key = CONCAT('legacy:', id::text) WHERE dedup_key IS NULL OR dedup_key = '' OR dedup_key = 'legacy'")
    op.execute("UPDATE alerts SET last_seen_at = COALESCE(last_seen_at, triggered_at)")
    op.execute("UPDATE alerts SET notification_status = COALESCE(notification_status, 'pending')")

    op.execute("CREATE INDEX IF NOT EXISTS ix_alerts_event_kind ON alerts (event_kind)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_alerts_dedup_key ON alerts (dedup_key)")
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_alerts_open_rule_dedup
        ON alerts (rule_id, dedup_key)
        WHERE resolved_at IS NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_alerts_open_rule_dedup")
    op.execute("DROP INDEX IF EXISTS ix_alerts_dedup_key")
    op.execute("DROP INDEX IF EXISTS ix_alerts_event_kind")
    op.execute("ALTER TABLE alerts DROP COLUMN IF EXISTS notification_error")
    op.execute("ALTER TABLE alerts DROP COLUMN IF EXISTS notification_sent_at")
    op.execute("ALTER TABLE alerts DROP COLUMN IF EXISTS last_notification_attempt_at")
    op.execute("ALTER TABLE alerts DROP COLUMN IF EXISTS notification_status")
    op.execute("ALTER TABLE alerts DROP COLUMN IF EXISTS last_seen_at")
    op.execute("ALTER TABLE alerts DROP COLUMN IF EXISTS dedup_key")
    op.execute("ALTER TABLE alerts DROP COLUMN IF EXISTS event_kind")
    op.execute("ALTER TABLE alerts DROP COLUMN IF EXISTS details")
