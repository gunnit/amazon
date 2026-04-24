"""Optimize alert query paths.

Revision ID: 007_optimize_alert_queries
Revises: 006_add_scheduled_reports
Create Date: 2026-04-02
"""
from alembic import op
import sqlalchemy as sa


revision = "007_optimize_alert_queries"
down_revision = "006_add_scheduled_reports"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_alert_rules_org_type_id",
        "alert_rules",
        ["organization_id", "alert_type", "id"],
        unique=False,
    )
    op.create_index(
        "ix_alerts_rule_triggered_at",
        "alerts",
        ["rule_id", "triggered_at"],
        unique=False,
    )
    op.create_index(
        "ix_alerts_rule_unread_triggered_at",
        "alerts",
        ["rule_id", "triggered_at"],
        unique=False,
        postgresql_where=sa.text("is_read = false"),
    )
    op.create_index(op.f("ix_alerts_account_id"), "alerts", ["account_id"], unique=False)
    op.create_index(op.f("ix_alerts_asin"), "alerts", ["asin"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_alerts_asin"), table_name="alerts")
    op.drop_index(op.f("ix_alerts_account_id"), table_name="alerts")
    op.drop_index("ix_alerts_rule_unread_triggered_at", table_name="alerts")
    op.drop_index("ix_alerts_rule_triggered_at", table_name="alerts")
    op.drop_index("ix_alert_rules_org_type_id", table_name="alert_rules")
