"""Extend alerts for rule-less, org-scoped job notifications.

Lets an Alert exist without an owning AlertRule (``rule_id`` nullable) and
carry its own ``organization_id`` so completion notifications can be scoped
to the org directly. Adds an org-scoped partial unread index that mirrors
the existing rule-scoped one.

Revision ID: 030_alert_notifications_extend
Revises: 029_brand_analysis_job_lifecycle
Create Date: 2026-06-09
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "030_alert_notifications_extend"
down_revision = "029_brand_analysis_job_lifecycle"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "alerts",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    # Backfill org from the owning rule for existing rule-bound alerts.
    op.execute(
        "UPDATE alerts a SET organization_id = r.organization_id "
        "FROM alert_rules r WHERE a.rule_id = r.id AND a.organization_id IS NULL"
    )
    op.create_foreign_key(
        "fk_alerts_organization_id",
        "alerts",
        "organizations",
        ["organization_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_alerts_organization_id", "alerts", ["organization_id"])

    op.alter_column("alerts", "rule_id", existing_type=postgresql.UUID(as_uuid=True), nullable=True)

    op.create_index(
        "ix_alerts_org_unread_triggered_at",
        "alerts",
        ["organization_id", "triggered_at"],
        postgresql_where=sa.text("is_read = false"),
    )


def downgrade() -> None:
    op.drop_index("ix_alerts_org_unread_triggered_at", table_name="alerts")
    op.alter_column("alerts", "rule_id", existing_type=postgresql.UUID(as_uuid=True), nullable=False)
    op.drop_index("ix_alerts_organization_id", table_name="alerts")
    op.drop_constraint("fk_alerts_organization_id", "alerts", type_="foreignkey")
    op.drop_column("alerts", "organization_id")
