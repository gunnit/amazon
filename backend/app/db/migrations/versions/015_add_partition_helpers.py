"""Install partition management helper functions.

Ships a pair of PostgreSQL functions used by workers.tasks.maintenance.manage_partitions
to create future monthly partitions on tables that have already been converted to
range-partitioned tables (partitioning is an operational choice — see
backend/scripts/enable_time_series_partitioning.sql).

If a table is not partitioned (the default), the helpers return gracefully
without modifying anything, so this migration is safe to apply on any database.

Revision ID: 015_add_partition_helpers
Revises: 014_add_product_availability
Create Date: 2026-04-16
"""
from alembic import op


revision = "015_add_partition_helpers"
down_revision = "014_add_product_availability"
branch_labels = None
depends_on = None


ENSURE_MONTHLY_PARTITION_FN = """
CREATE OR REPLACE FUNCTION public.ensure_monthly_partition(
    parent_table text,
    target_year int,
    target_month int
) RETURNS text
LANGUAGE plpgsql AS $$
DECLARE
    is_partitioned boolean;
    start_date date;
    end_date   date;
    partition_name text;
    full_partition_name text;
BEGIN
    SELECT relkind = 'p' INTO is_partitioned
    FROM pg_class
    WHERE relname = parent_table AND relnamespace = 'public'::regnamespace;

    IF NOT COALESCE(is_partitioned, false) THEN
        RETURN format('skipped: %s is not partitioned', parent_table);
    END IF;

    start_date := make_date(target_year, target_month, 1);
    end_date   := (start_date + INTERVAL '1 month')::date;
    partition_name := format('%s_y%sm%s', parent_table, target_year,
                             lpad(target_month::text, 2, '0'));
    full_partition_name := format('public.%I', partition_name);

    IF EXISTS (SELECT 1 FROM pg_class
               WHERE relname = partition_name
                 AND relnamespace = 'public'::regnamespace) THEN
        RETURN format('exists: %s', partition_name);
    END IF;

    EXECUTE format(
        'CREATE TABLE %s PARTITION OF public.%I FOR VALUES FROM (%L) TO (%L)',
        full_partition_name, parent_table, start_date, end_date
    );
    RETURN format('created: %s', partition_name);
END;
$$;
"""

LIST_PARTITIONED_FN = """
CREATE OR REPLACE FUNCTION public.list_partitioned_tables()
RETURNS TABLE(table_name text)
LANGUAGE sql AS $$
    SELECT relname::text
    FROM pg_class
    WHERE relkind = 'p' AND relnamespace = 'public'::regnamespace
    ORDER BY relname;
$$;
"""


def upgrade() -> None:
    op.execute(ENSURE_MONTHLY_PARTITION_FN)
    op.execute(LIST_PARTITIONED_FN)


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS public.list_partitioned_tables()")
    op.execute("DROP FUNCTION IF EXISTS public.ensure_monthly_partition(text, int, int)")
