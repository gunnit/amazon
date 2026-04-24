"""Add strategic_recommendations table (US-7.5).

Revision ID: 016_add_strategic_recommendations
Revises: 015_add_partition_helpers
Create Date: 2026-04-16
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "016_add_strategic_recommendations"
down_revision = "015_add_partition_helpers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "strategic_recommendations",
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
            nullable=True,
        ),
        sa.Column(
            "created_by_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("priority", sa.String(16), nullable=False, server_default="medium"),
        sa.Column("priority_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("expected_impact", sa.Text(), nullable=True),
        sa.Column("context", postgresql.JSONB(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("implemented_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("outcome_notes", sa.Text(), nullable=True),
        sa.Column("generated_by", sa.String(32), nullable=False, server_default="ai_analysis"),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_strategic_recommendations_organization_id",
        "strategic_recommendations",
        ["organization_id"],
    )
    op.create_index(
        "ix_strategic_recommendations_account_id",
        "strategic_recommendations",
        ["account_id"],
    )
    op.create_index(
        "ix_strategic_recommendations_category",
        "strategic_recommendations",
        ["category"],
    )
    op.create_index(
        "ix_strategic_recommendations_status",
        "strategic_recommendations",
        ["status"],
    )
    op.create_index(
        "ix_strategic_recommendations_org_status_generated",
        "strategic_recommendations",
        ["organization_id", "status", "generated_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_strategic_recommendations_org_status_generated", table_name="strategic_recommendations")
    op.drop_index("ix_strategic_recommendations_status", table_name="strategic_recommendations")
    op.drop_index("ix_strategic_recommendations_category", table_name="strategic_recommendations")
    op.drop_index("ix_strategic_recommendations_account_id", table_name="strategic_recommendations")
    op.drop_index("ix_strategic_recommendations_organization_id", table_name="strategic_recommendations")
    op.drop_table("strategic_recommendations")
