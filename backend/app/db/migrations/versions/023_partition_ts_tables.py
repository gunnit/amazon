"""Partition time-series tables (sales_data, advertising_metrics, advertising_metrics_by_asin, bsr_history).

Converts plain tables to `PARTITION BY RANGE (date)` so the
`ensure_monthly_partition()` UDF installed in 015 actually creates partitions
(it short-circuits on non-partitioned tables). Composite primary key
`(id, date)` is required by PostgreSQL — the partition key must be in the PK.

Each table's conversion is wrapped in a `DO` block that checks `relkind` and
skips if already partitioned, so this migration is idempotent. The same
pattern was previously available only via `backend/scripts/enable_time_series_partitioning.sql`,
which had to be run manually. This migration brings the four tables listed
above into the automatic Alembic flow.

Bootstraps partitions for the next 24 months via `ensure_monthly_partition()`
so the daily `manage_partitions` Celery task has runway even after a long
pause.

Note: `inventory_data` and `orders` are intentionally NOT converted here.
Those remain on the manual script path because `orders` requires a
coordinated change to `order_items.order_id` (composite FK), which warrants
operator review.

Revision ID: 023_partition_ts_tables
Revises: 021_ba_capabilities
Create Date: 2026-05-28
"""
from __future__ import annotations

from alembic import op


revision = "023_partition_ts_tables"
# Lands downstream of the catalog audit-log migration so the Alembic chain
# stays single-head once both PRs merge.
down_revision = "022_catalog_change_log"
branch_labels = None
depends_on = None


# Per-table conversion. Each block is idempotent (skips if relkind = 'p').
# Patterned after backend/scripts/enable_time_series_partitioning.sql.
_PARTITION_SALES_DATA = """
DO $$
DECLARE
    is_partitioned boolean;
    min_date date;
    max_date date;
    cur date;
    end_bound date;
    partition_name text;
BEGIN
    SELECT relkind = 'p' INTO is_partitioned
    FROM pg_class WHERE relname = 'sales_data' AND relnamespace = 'public'::regnamespace;

    IF COALESCE(is_partitioned, false) THEN
        RAISE NOTICE 'sales_data already partitioned, skipping';
        RETURN;
    END IF;

    CREATE TABLE sales_data_new (LIKE sales_data INCLUDING DEFAULTS INCLUDING CONSTRAINTS)
        PARTITION BY RANGE (date);
    ALTER TABLE sales_data_new DROP CONSTRAINT IF EXISTS sales_data_pkey;
    ALTER TABLE sales_data_new ADD PRIMARY KEY (id, date);

    SELECT COALESCE(MIN(date), CURRENT_DATE) INTO min_date FROM sales_data;
    SELECT COALESCE(MAX(date), CURRENT_DATE) INTO max_date FROM sales_data;

    cur := date_trunc('month', min_date)::date;
    end_bound := (date_trunc('month', max_date) + INTERVAL '1 month')::date;
    WHILE cur < end_bound LOOP
        partition_name := format('sales_data_y%sm%s', extract(year from cur)::int,
                                 lpad(extract(month from cur)::text, 2, '0'));
        EXECUTE format(
            'CREATE TABLE %I PARTITION OF sales_data_new FOR VALUES FROM (%L) TO (%L)',
            partition_name, cur, (cur + INTERVAL '1 month')::date
        );
        cur := (cur + INTERVAL '1 month')::date;
    END LOOP;

    EXECUTE 'CREATE TABLE sales_data_default PARTITION OF sales_data_new DEFAULT';

    INSERT INTO sales_data_new SELECT * FROM sales_data;
    ALTER SEQUENCE sales_data_id_seq OWNED BY NONE;
    DROP TABLE sales_data;
    ALTER TABLE sales_data_new RENAME TO sales_data;
    ALTER SEQUENCE sales_data_id_seq OWNED BY sales_data.id;

    ALTER TABLE sales_data
        ADD CONSTRAINT sales_data_account_id_fkey
        FOREIGN KEY (account_id) REFERENCES amazon_accounts(id) ON DELETE CASCADE;

    CREATE INDEX IF NOT EXISTS ix_sales_data_account_id ON sales_data (account_id);
    CREATE INDEX IF NOT EXISTS ix_sales_data_date ON sales_data (date);
    CREATE INDEX IF NOT EXISTS ix_sales_data_asin ON sales_data (asin);
    ALTER TABLE sales_data
        ADD CONSTRAINT uq_sales_data_account_date_asin UNIQUE (account_id, date, asin);
END $$;
"""

_PARTITION_ADVERTISING_METRICS = """
DO $$
DECLARE
    is_partitioned boolean;
    min_date date;
    max_date date;
    cur date;
    end_bound date;
    partition_name text;
BEGIN
    SELECT relkind = 'p' INTO is_partitioned
    FROM pg_class WHERE relname = 'advertising_metrics' AND relnamespace = 'public'::regnamespace;

    IF COALESCE(is_partitioned, false) THEN
        RAISE NOTICE 'advertising_metrics already partitioned, skipping';
        RETURN;
    END IF;

    CREATE TABLE advertising_metrics_new (LIKE advertising_metrics INCLUDING DEFAULTS INCLUDING CONSTRAINTS)
        PARTITION BY RANGE (date);
    ALTER TABLE advertising_metrics_new DROP CONSTRAINT IF EXISTS advertising_metrics_pkey;
    ALTER TABLE advertising_metrics_new ADD PRIMARY KEY (id, date);

    SELECT COALESCE(MIN(date), CURRENT_DATE) INTO min_date FROM advertising_metrics;
    SELECT COALESCE(MAX(date), CURRENT_DATE) INTO max_date FROM advertising_metrics;

    cur := date_trunc('month', min_date)::date;
    end_bound := (date_trunc('month', max_date) + INTERVAL '1 month')::date;
    WHILE cur < end_bound LOOP
        partition_name := format('advertising_metrics_y%sm%s', extract(year from cur)::int,
                                 lpad(extract(month from cur)::text, 2, '0'));
        EXECUTE format(
            'CREATE TABLE %I PARTITION OF advertising_metrics_new FOR VALUES FROM (%L) TO (%L)',
            partition_name, cur, (cur + INTERVAL '1 month')::date
        );
        cur := (cur + INTERVAL '1 month')::date;
    END LOOP;

    EXECUTE 'CREATE TABLE advertising_metrics_default PARTITION OF advertising_metrics_new DEFAULT';

    INSERT INTO advertising_metrics_new SELECT * FROM advertising_metrics;
    ALTER SEQUENCE advertising_metrics_id_seq OWNED BY NONE;
    DROP TABLE advertising_metrics;
    ALTER TABLE advertising_metrics_new RENAME TO advertising_metrics;
    ALTER SEQUENCE advertising_metrics_id_seq OWNED BY advertising_metrics.id;

    ALTER TABLE advertising_metrics
        ADD CONSTRAINT advertising_metrics_campaign_id_fkey
        FOREIGN KEY (campaign_id) REFERENCES advertising_campaigns(id) ON DELETE CASCADE;

    CREATE INDEX IF NOT EXISTS ix_advertising_metrics_campaign_id ON advertising_metrics (campaign_id);
    CREATE INDEX IF NOT EXISTS ix_advertising_metrics_date ON advertising_metrics (date);
    ALTER TABLE advertising_metrics
        ADD CONSTRAINT uq_ad_metrics_campaign_date UNIQUE (campaign_id, date);
END $$;
"""

_PARTITION_ADVERTISING_METRICS_BY_ASIN = """
DO $$
DECLARE
    is_partitioned boolean;
    min_date date;
    max_date date;
    cur date;
    end_bound date;
    partition_name text;
BEGIN
    SELECT relkind = 'p' INTO is_partitioned
    FROM pg_class WHERE relname = 'advertising_metrics_by_asin' AND relnamespace = 'public'::regnamespace;

    IF COALESCE(is_partitioned, false) THEN
        RAISE NOTICE 'advertising_metrics_by_asin already partitioned, skipping';
        RETURN;
    END IF;

    CREATE TABLE advertising_metrics_by_asin_new (LIKE advertising_metrics_by_asin INCLUDING DEFAULTS INCLUDING CONSTRAINTS)
        PARTITION BY RANGE (date);
    ALTER TABLE advertising_metrics_by_asin_new DROP CONSTRAINT IF EXISTS advertising_metrics_by_asin_pkey;
    ALTER TABLE advertising_metrics_by_asin_new ADD PRIMARY KEY (id, date);

    SELECT COALESCE(MIN(date), CURRENT_DATE) INTO min_date FROM advertising_metrics_by_asin;
    SELECT COALESCE(MAX(date), CURRENT_DATE) INTO max_date FROM advertising_metrics_by_asin;

    cur := date_trunc('month', min_date)::date;
    end_bound := (date_trunc('month', max_date) + INTERVAL '1 month')::date;
    WHILE cur < end_bound LOOP
        partition_name := format('advertising_metrics_by_asin_y%sm%s', extract(year from cur)::int,
                                 lpad(extract(month from cur)::text, 2, '0'));
        EXECUTE format(
            'CREATE TABLE %I PARTITION OF advertising_metrics_by_asin_new FOR VALUES FROM (%L) TO (%L)',
            partition_name, cur, (cur + INTERVAL '1 month')::date
        );
        cur := (cur + INTERVAL '1 month')::date;
    END LOOP;

    EXECUTE 'CREATE TABLE advertising_metrics_by_asin_default PARTITION OF advertising_metrics_by_asin_new DEFAULT';

    INSERT INTO advertising_metrics_by_asin_new SELECT * FROM advertising_metrics_by_asin;
    ALTER SEQUENCE advertising_metrics_by_asin_id_seq OWNED BY NONE;
    DROP TABLE advertising_metrics_by_asin;
    ALTER TABLE advertising_metrics_by_asin_new RENAME TO advertising_metrics_by_asin;
    ALTER SEQUENCE advertising_metrics_by_asin_id_seq OWNED BY advertising_metrics_by_asin.id;

    ALTER TABLE advertising_metrics_by_asin
        ADD CONSTRAINT advertising_metrics_by_asin_account_id_fkey
        FOREIGN KEY (account_id) REFERENCES amazon_accounts(id) ON DELETE CASCADE;
    ALTER TABLE advertising_metrics_by_asin
        ADD CONSTRAINT advertising_metrics_by_asin_campaign_id_fkey
        FOREIGN KEY (campaign_id) REFERENCES advertising_campaigns(id) ON DELETE CASCADE;

    CREATE INDEX IF NOT EXISTS ix_advertising_metrics_by_asin_account_id ON advertising_metrics_by_asin (account_id);
    CREATE INDEX IF NOT EXISTS ix_advertising_metrics_by_asin_campaign_id ON advertising_metrics_by_asin (campaign_id);
    CREATE INDEX IF NOT EXISTS ix_advertising_metrics_by_asin_asin ON advertising_metrics_by_asin (asin);
    CREATE INDEX IF NOT EXISTS ix_advertising_metrics_by_asin_date ON advertising_metrics_by_asin (date);
    ALTER TABLE advertising_metrics_by_asin
        ADD CONSTRAINT uq_ad_asin_metrics_campaign_asin_date UNIQUE (campaign_id, asin, date);
END $$;
"""

_PARTITION_BSR_HISTORY = """
DO $$
DECLARE
    is_partitioned boolean;
    min_date date;
    max_date date;
    cur date;
    end_bound date;
    partition_name text;
BEGIN
    SELECT relkind = 'p' INTO is_partitioned
    FROM pg_class WHERE relname = 'bsr_history' AND relnamespace = 'public'::regnamespace;

    IF COALESCE(is_partitioned, false) THEN
        RAISE NOTICE 'bsr_history already partitioned, skipping';
        RETURN;
    END IF;

    CREATE TABLE bsr_history_new (LIKE bsr_history INCLUDING DEFAULTS INCLUDING CONSTRAINTS)
        PARTITION BY RANGE (date);
    ALTER TABLE bsr_history_new DROP CONSTRAINT IF EXISTS bsr_history_pkey;
    ALTER TABLE bsr_history_new ADD PRIMARY KEY (id, date);

    SELECT COALESCE(MIN(date), CURRENT_DATE) INTO min_date FROM bsr_history;
    SELECT COALESCE(MAX(date), CURRENT_DATE) INTO max_date FROM bsr_history;

    cur := date_trunc('month', min_date)::date;
    end_bound := (date_trunc('month', max_date) + INTERVAL '1 month')::date;
    WHILE cur < end_bound LOOP
        partition_name := format('bsr_history_y%sm%s', extract(year from cur)::int,
                                 lpad(extract(month from cur)::text, 2, '0'));
        EXECUTE format(
            'CREATE TABLE %I PARTITION OF bsr_history_new FOR VALUES FROM (%L) TO (%L)',
            partition_name, cur, (cur + INTERVAL '1 month')::date
        );
        cur := (cur + INTERVAL '1 month')::date;
    END LOOP;

    EXECUTE 'CREATE TABLE bsr_history_default PARTITION OF bsr_history_new DEFAULT';

    INSERT INTO bsr_history_new SELECT * FROM bsr_history;
    ALTER SEQUENCE bsr_history_id_seq OWNED BY NONE;
    DROP TABLE bsr_history;
    ALTER TABLE bsr_history_new RENAME TO bsr_history;
    ALTER SEQUENCE bsr_history_id_seq OWNED BY bsr_history.id;

    ALTER TABLE bsr_history
        ADD CONSTRAINT bsr_history_product_id_fkey
        FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE;

    CREATE INDEX IF NOT EXISTS ix_bsr_history_product_id ON bsr_history (product_id);
    CREATE INDEX IF NOT EXISTS ix_bsr_history_date ON bsr_history (date);
    ALTER TABLE bsr_history
        ADD CONSTRAINT uq_bsr_product_date_category UNIQUE (product_id, date, category);
END $$;
"""

# After conversion, seed partitions for the next 24 months via the UDF
# installed in migration 015. The UDF is itself idempotent — if a partition
# already exists for a given (table, year, month) it returns 'exists: ...'
# without raising.
_BOOTSTRAP_FUTURE_PARTITIONS = """
DO $$
DECLARE
    managed_table text;
    cur date := date_trunc('month', CURRENT_DATE)::date;
    bound date := (date_trunc('month', CURRENT_DATE) + INTERVAL '24 months')::date;
    iter date;
BEGIN
    FOREACH managed_table IN ARRAY ARRAY[
        'sales_data',
        'advertising_metrics',
        'advertising_metrics_by_asin',
        'bsr_history'
    ] LOOP
        iter := cur;
        WHILE iter < bound LOOP
            PERFORM public.ensure_monthly_partition(
                managed_table,
                extract(year from iter)::int,
                extract(month from iter)::int
            );
            iter := (iter + INTERVAL '1 month')::date;
        END LOOP;
    END LOOP;
END $$;
"""


def upgrade() -> None:
    op.execute(_PARTITION_SALES_DATA)
    op.execute(_PARTITION_ADVERTISING_METRICS)
    op.execute(_PARTITION_ADVERTISING_METRICS_BY_ASIN)
    op.execute(_PARTITION_BSR_HISTORY)
    op.execute(_BOOTSTRAP_FUTURE_PARTITIONS)


def downgrade() -> None:
    # Reverting a partitioned table to a plain table is destructive and
    # cannot be expressed safely as a generic downgrade — `DETACH PARTITION`
    # alone does not reconstruct the original `id`-only primary key, and
    # blindly copying data back risks losing any inserts made while
    # partitioned. If a real rollback is needed, do it manually:
    #   1. CREATE TABLE <name>_legacy (LIKE <name> EXCLUDING CONSTRAINTS);
    #   2. ALTER TABLE <name>_legacy ADD PRIMARY KEY (id);
    #   3. INSERT INTO <name>_legacy SELECT * FROM <name>;
    #   4. DROP TABLE <name> CASCADE; ALTER TABLE <name>_legacy RENAME TO <name>;
    #   5. Recreate FKs and indexes.
    raise NotImplementedError(
        "Downgrade is destructive and must be performed manually. "
        "See comment in 023_partition_ts_tables.py."
    )
