"""Add BRIN indexes for retention-managed date columns.

Revision ID: 011_add_brin_indexes_for_retention
Revises: 010_add_returns_data
Create Date: 2026-04-14
"""
from alembic import op


revision = "011_brin_retention_indexes"
down_revision = "010_add_returns_data"
branch_labels = None
depends_on = None


BRIN_INDEXES = (
    ("ix_sales_data_date_brin", "sales_data", "date"),
    ("ix_inventory_data_snapshot_date_brin", "inventory_data", "snapshot_date"),
    ("ix_advertising_metrics_date_brin", "advertising_metrics", "date"),
    ("ix_returns_data_return_date_brin", "returns_data", "return_date"),
)


def _create_brin_index_if_missing(index_name: str, table_name: str, column_name: str) -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_class idx
                JOIN pg_index i ON i.indexrelid = idx.oid
                JOIN pg_class tbl ON tbl.oid = i.indrelid
                JOIN pg_namespace ns ON ns.oid = tbl.relnamespace
                JOIN pg_am am ON am.oid = idx.relam
                JOIN pg_attribute att
                  ON att.attrelid = tbl.oid
                 AND att.attnum = ANY(i.indkey)
                WHERE ns.nspname = current_schema()
                  AND tbl.relname = '{table_name}'
                  AND am.amname = 'brin'
                  AND att.attname = '{column_name}'
            ) THEN
                CREATE INDEX {index_name}
                ON {table_name} USING BRIN ({column_name});
            END IF;
        END
        $$;
        """
    )


def upgrade() -> None:
    for index_name, table_name, column_name in BRIN_INDEXES:
        _create_brin_index_if_missing(index_name, table_name, column_name)


def downgrade() -> None:
    for index_name, _, _ in BRIN_INDEXES:
        op.execute(f"DROP INDEX IF EXISTS {index_name}")
