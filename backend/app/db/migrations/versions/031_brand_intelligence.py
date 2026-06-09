"""Weekly Brand Intelligence: persisted reports + weekly schedule.

Adds ``brand_intelligence_reports`` (one diff-based, LLM-synthesized report per
account/week) and ``brand_intelligence_schedules`` (opt-in weekly automation).
The report shape mirrors ``scheduled_report_runs`` so the same beat-scanner /
stuck-recovery machinery applies.

Revision ID: 031_brand_intelligence
Revises: 030_alert_notifications_extend
Create Date: 2026-06-09
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "031_brand_intelligence"
down_revision = "030_alert_notifications_extend"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "brand_intelligence_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("amazon_accounts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("brand_label", sa.String(255), nullable=False, server_default="Brand"),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("previous_start", sa.Date(), nullable=False),
        sa.Column("previous_end", sa.Date(), nullable=False),
        sa.Column("window_days", sa.Integer(), nullable=False, server_default="7"),
        sa.Column("week_label", sa.String(64), nullable=False, server_default=""),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("generated_by", sa.String(20), nullable=False, server_default="manual"),
        sa.Column("model", sa.String(64), nullable=True),
        sa.Column("coverage_note", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("snapshot", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("diff", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("intelligence", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "account_id", "period_start", "period_end", name="uq_bir_account_period"
        ),
    )
    op.create_index(
        "ix_brand_intelligence_reports_organization_id",
        "brand_intelligence_reports",
        ["organization_id"],
    )
    op.create_index(
        "ix_brand_intelligence_reports_account_id",
        "brand_intelligence_reports",
        ["account_id"],
    )
    op.create_index(
        "ix_brand_intelligence_reports_status",
        "brand_intelligence_reports",
        ["status"],
    )
    op.create_index(
        "ix_bir_account_period_end",
        "brand_intelligence_reports",
        ["account_id", "period_end"],
    )
    op.create_index(
        "ix_bir_status_heartbeat",
        "brand_intelligence_reports",
        ["status", "heartbeat_at"],
    )

    op.create_table(
        "brand_intelligence_schedules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("amazon_accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("day_of_week", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("timezone", sa.String(64), nullable=False, server_default="UTC"),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("account_id", name="uq_bis_account"),
    )
    op.create_index(
        "ix_brand_intelligence_schedules_organization_id",
        "brand_intelligence_schedules",
        ["organization_id"],
    )
    op.create_index(
        "ix_brand_intelligence_schedules_account_id",
        "brand_intelligence_schedules",
        ["account_id"],
    )
    op.create_index(
        "ix_brand_intelligence_schedules_next_run_at",
        "brand_intelligence_schedules",
        ["next_run_at"],
    )
    op.create_index(
        "ix_bis_enabled_next_run",
        "brand_intelligence_schedules",
        ["is_enabled", "next_run_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_bis_enabled_next_run", table_name="brand_intelligence_schedules")
    op.drop_index(
        "ix_brand_intelligence_schedules_next_run_at",
        table_name="brand_intelligence_schedules",
    )
    op.drop_index(
        "ix_brand_intelligence_schedules_account_id",
        table_name="brand_intelligence_schedules",
    )
    op.drop_index(
        "ix_brand_intelligence_schedules_organization_id",
        table_name="brand_intelligence_schedules",
    )
    op.drop_table("brand_intelligence_schedules")

    op.drop_index("ix_bir_status_heartbeat", table_name="brand_intelligence_reports")
    op.drop_index("ix_bir_account_period_end", table_name="brand_intelligence_reports")
    op.drop_index(
        "ix_brand_intelligence_reports_status", table_name="brand_intelligence_reports"
    )
    op.drop_index(
        "ix_brand_intelligence_reports_account_id",
        table_name="brand_intelligence_reports",
    )
    op.drop_index(
        "ix_brand_intelligence_reports_organization_id",
        table_name="brand_intelligence_reports",
    )
    op.drop_table("brand_intelligence_reports")
