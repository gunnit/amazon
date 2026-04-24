-- Convert time-series tables to monthly range-partitioned tables.
--
-- RUN MANUALLY IN A MAINTENANCE WINDOW. This rewrites the tables.
-- For databases with significant data volume (> 5M rows), run during off-hours
-- and expect table-level locks for the duration of the INSERT ... SELECT step.
--
-- Idempotent: each block detects whether the table is already partitioned and
-- skips the conversion if so.
--
-- Safe order: sales_data, inventory_data, advertising_metrics first
-- (no inbound FKs). `orders` is converted last because `order_items.order_id`
-- is also rewired to a composite key.
--
-- After running this script, manage_partitions() in workers/tasks/maintenance.py
-- will start creating the next months' partitions automatically every night.

BEGIN;

-- ---------------------------------------------------------------------------
-- sales_data (partition key: date)
-- ---------------------------------------------------------------------------
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

    EXECUTE format(
        'CREATE TABLE sales_data_default PARTITION OF sales_data_new DEFAULT'
    );

    INSERT INTO sales_data_new SELECT * FROM sales_data;

    DROP TABLE sales_data;
    ALTER TABLE sales_data_new RENAME TO sales_data;

    ALTER TABLE sales_data
        ADD CONSTRAINT sales_data_account_id_fkey
        FOREIGN KEY (account_id) REFERENCES amazon_accounts(id) ON DELETE CASCADE;

    CREATE INDEX IF NOT EXISTS ix_sales_data_account_id ON sales_data (account_id);
    CREATE INDEX IF NOT EXISTS ix_sales_data_date ON sales_data (date);
    CREATE INDEX IF NOT EXISTS ix_sales_data_asin ON sales_data (asin);
    CREATE UNIQUE INDEX IF NOT EXISTS uq_sales_data_account_date_asin
        ON sales_data (account_id, date, asin);
END $$;

-- ---------------------------------------------------------------------------
-- inventory_data (partition key: snapshot_date)
-- ---------------------------------------------------------------------------
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
    FROM pg_class WHERE relname = 'inventory_data' AND relnamespace = 'public'::regnamespace;

    IF COALESCE(is_partitioned, false) THEN
        RAISE NOTICE 'inventory_data already partitioned, skipping';
        RETURN;
    END IF;

    CREATE TABLE inventory_data_new (LIKE inventory_data INCLUDING DEFAULTS INCLUDING CONSTRAINTS)
        PARTITION BY RANGE (snapshot_date);
    ALTER TABLE inventory_data_new DROP CONSTRAINT IF EXISTS inventory_data_pkey;
    ALTER TABLE inventory_data_new ADD PRIMARY KEY (id, snapshot_date);

    SELECT COALESCE(MIN(snapshot_date), CURRENT_DATE) INTO min_date FROM inventory_data;
    SELECT COALESCE(MAX(snapshot_date), CURRENT_DATE) INTO max_date FROM inventory_data;

    cur := date_trunc('month', min_date)::date;
    end_bound := (date_trunc('month', max_date) + INTERVAL '1 month')::date;
    WHILE cur < end_bound LOOP
        partition_name := format('inventory_data_y%sm%s', extract(year from cur)::int,
                                 lpad(extract(month from cur)::text, 2, '0'));
        EXECUTE format(
            'CREATE TABLE %I PARTITION OF inventory_data_new FOR VALUES FROM (%L) TO (%L)',
            partition_name, cur, (cur + INTERVAL '1 month')::date
        );
        cur := (cur + INTERVAL '1 month')::date;
    END LOOP;

    EXECUTE format(
        'CREATE TABLE inventory_data_default PARTITION OF inventory_data_new DEFAULT'
    );

    INSERT INTO inventory_data_new SELECT * FROM inventory_data;

    DROP TABLE inventory_data;
    ALTER TABLE inventory_data_new RENAME TO inventory_data;

    ALTER TABLE inventory_data
        ADD CONSTRAINT inventory_data_account_id_fkey
        FOREIGN KEY (account_id) REFERENCES amazon_accounts(id) ON DELETE CASCADE;

    CREATE INDEX IF NOT EXISTS ix_inventory_data_account_id ON inventory_data (account_id);
    CREATE INDEX IF NOT EXISTS ix_inventory_data_snapshot_date ON inventory_data (snapshot_date);
    CREATE INDEX IF NOT EXISTS ix_inventory_data_asin ON inventory_data (asin);
    CREATE UNIQUE INDEX IF NOT EXISTS uq_inventory_account_date_asin
        ON inventory_data (account_id, snapshot_date, asin);
END $$;

-- ---------------------------------------------------------------------------
-- advertising_metrics (partition key: date)
-- ---------------------------------------------------------------------------
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

    EXECUTE format(
        'CREATE TABLE advertising_metrics_default PARTITION OF advertising_metrics_new DEFAULT'
    );

    INSERT INTO advertising_metrics_new SELECT * FROM advertising_metrics;

    DROP TABLE advertising_metrics;
    ALTER TABLE advertising_metrics_new RENAME TO advertising_metrics;

    ALTER TABLE advertising_metrics
        ADD CONSTRAINT advertising_metrics_campaign_id_fkey
        FOREIGN KEY (campaign_id) REFERENCES advertising_campaigns(id) ON DELETE CASCADE;

    CREATE INDEX IF NOT EXISTS ix_advertising_metrics_campaign_id ON advertising_metrics (campaign_id);
    CREATE INDEX IF NOT EXISTS ix_advertising_metrics_date ON advertising_metrics (date);
    CREATE UNIQUE INDEX IF NOT EXISTS uq_ad_metrics_campaign_date
        ON advertising_metrics (campaign_id, date);
END $$;

-- ---------------------------------------------------------------------------
-- orders (partition key: purchase_date)
-- ---------------------------------------------------------------------------
-- Requires schema change on order_items so the FK can point at the new
-- composite primary key (id, purchase_date).
--
-- If this block fails mid-way, the outer transaction rollback returns the
-- database to the pre-run state.
-- ---------------------------------------------------------------------------
DO $$
DECLARE
    is_partitioned boolean;
    min_date timestamptz;
    max_date timestamptz;
    cur date;
    end_bound date;
    partition_name text;
BEGIN
    SELECT relkind = 'p' INTO is_partitioned
    FROM pg_class WHERE relname = 'orders' AND relnamespace = 'public'::regnamespace;

    IF COALESCE(is_partitioned, false) THEN
        RAISE NOTICE 'orders already partitioned, skipping';
        RETURN;
    END IF;

    -- Drop FK from order_items first so we can repoint it after the swap
    ALTER TABLE order_items DROP CONSTRAINT IF EXISTS order_items_order_id_fkey;

    -- Add purchase_date mirror column to order_items (needed for composite FK)
    ALTER TABLE order_items ADD COLUMN IF NOT EXISTS purchase_date timestamptz;
    UPDATE order_items oi SET purchase_date = o.purchase_date
        FROM orders o WHERE oi.order_id = o.id AND oi.purchase_date IS NULL;
    ALTER TABLE order_items ALTER COLUMN purchase_date SET NOT NULL;

    CREATE TABLE orders_new (LIKE orders INCLUDING DEFAULTS INCLUDING CONSTRAINTS)
        PARTITION BY RANGE (purchase_date);
    ALTER TABLE orders_new DROP CONSTRAINT IF EXISTS orders_pkey;
    ALTER TABLE orders_new ADD PRIMARY KEY (id, purchase_date);

    SELECT COALESCE(MIN(purchase_date), NOW()) INTO min_date FROM orders;
    SELECT COALESCE(MAX(purchase_date), NOW()) INTO max_date FROM orders;

    cur := date_trunc('month', min_date)::date;
    end_bound := (date_trunc('month', max_date) + INTERVAL '1 month')::date;
    WHILE cur < end_bound LOOP
        partition_name := format('orders_y%sm%s', extract(year from cur)::int,
                                 lpad(extract(month from cur)::text, 2, '0'));
        EXECUTE format(
            'CREATE TABLE %I PARTITION OF orders_new FOR VALUES FROM (%L) TO (%L)',
            partition_name, cur, (cur + INTERVAL '1 month')::date
        );
        cur := (cur + INTERVAL '1 month')::date;
    END LOOP;

    EXECUTE format(
        'CREATE TABLE orders_default PARTITION OF orders_new DEFAULT'
    );

    INSERT INTO orders_new SELECT * FROM orders;

    DROP TABLE orders;
    ALTER TABLE orders_new RENAME TO orders;

    ALTER TABLE orders
        ADD CONSTRAINT orders_account_id_fkey
        FOREIGN KEY (account_id) REFERENCES amazon_accounts(id) ON DELETE CASCADE;
    CREATE UNIQUE INDEX IF NOT EXISTS uq_orders_amazon_order_id
        ON orders (amazon_order_id, purchase_date);
    CREATE INDEX IF NOT EXISTS ix_orders_account_purchase_date
        ON orders (account_id, purchase_date);

    -- Re-add FK from order_items now referencing the composite key
    ALTER TABLE order_items
        ADD CONSTRAINT order_items_order_fkey
        FOREIGN KEY (order_id, purchase_date)
        REFERENCES orders (id, purchase_date) ON DELETE CASCADE;
    CREATE INDEX IF NOT EXISTS ix_order_items_order_id ON order_items (order_id);
END $$;

COMMIT;

-- Post-run: give the planner fresh stats
VACUUM ANALYZE sales_data;
VACUUM ANALYZE inventory_data;
VACUUM ANALYZE advertising_metrics;
VACUUM ANALYZE orders;
