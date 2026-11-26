"""Track variation references recovered from approved child listings."""

from alembic import op
import sqlalchemy as sa

revision = "035_partial_variation_references"
down_revision = "034_catalog_monitor"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "variation_family_baselines",
        sa.Column("is_partial", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("variation_family_baselines", "is_partial")
