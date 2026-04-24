-- Seed synthetic data for the mcp-tester organization
-- Idempotent: drops anything previously created with these stable ids.

DO $$
DECLARE
  v_org_id uuid := '5be2ce2e-ecdb-4a4c-80ad-488382e1403f';
  v_acc_id uuid := '11111111-1111-1111-1111-111111111111';
  v_camp_id uuid := '22222222-2222-2222-2222-222222222222';
  v_fc_id uuid := '33333333-3333-3333-3333-333333333333';
  v_rule_id uuid := '44444444-4444-4444-4444-444444444444';
  v_today date := CURRENT_DATE;
  i int;
  d date;
  asin_list text[] := ARRAY['B0SEED0001','B0SEED0002','B0SEED0003','B0SEED0004','B0SEED0005'];
  title_list text[] := ARRAY['Seed Speaker Pro','Seed Cable Bundle','Seed Yoga Mat','Seed Coffee Press','Seed Desk Lamp'];
  category_list text[] := ARRAY['Electronics','Electronics','Sports','Home','Home'];
  price_list numeric[] := ARRAY[39.90, 12.50, 29.00, 24.99, 34.50];
  asin text;
  title text;
  category text;
  price numeric;
BEGIN
  -- Clean prior seed data (children first)
  DELETE FROM forecasts WHERE id = v_fc_id;
  DELETE FROM advertising_metrics WHERE campaign_id = v_camp_id;
  DELETE FROM advertising_campaigns WHERE id = v_camp_id;
  DELETE FROM sales_data WHERE account_id = v_acc_id;
  DELETE FROM inventory_data WHERE account_id = v_acc_id;
  DELETE FROM products WHERE account_id = v_acc_id;
  DELETE FROM alerts WHERE rule_id = v_rule_id;
  DELETE FROM alert_rules WHERE id = v_rule_id;
  DELETE FROM amazon_accounts WHERE id = v_acc_id;

  -- Account
  INSERT INTO amazon_accounts (
    id, organization_id, account_name, account_type, marketplace_id, marketplace_country,
    sync_status, is_active, created_at, updated_at
  ) VALUES (
    v_acc_id, v_org_id, 'MCP Seed Account (IT)', 'SELLER', 'APJ6JRA9NG5V4', 'IT',
    'SUCCESS', true, now(), now()
  );

  -- Products
  FOR i IN 1..array_length(asin_list, 1) LOOP
    asin := asin_list[i];
    title := title_list[i];
    category := category_list[i];
    price := price_list[i];
    INSERT INTO products (
      id, account_id, asin, sku, title, brand, category, current_price, current_bsr,
      review_count, rating, is_active, is_available
    ) VALUES (
      gen_random_uuid(), v_acc_id, asin, 'SKU-' || asin, title, 'SeedBrand', category,
      price, 1000 + i*100, 50 + i*30, 4.0 + i*0.1, true, true
    );
  END LOOP;

  -- Sales: 30 days, vary by ASIN
  FOR i IN 0..29 LOOP
    d := v_today - i;
    FOR j IN 1..array_length(asin_list, 1) LOOP
      INSERT INTO sales_data (
        account_id, date, asin, sku, units_ordered, units_ordered_b2b,
        ordered_product_sales, ordered_product_sales_b2b, total_order_items, currency
      ) VALUES (
        v_acc_id, d, asin_list[j], 'SKU-' || asin_list[j],
        (5 + (i % 7) + j*2)::int, ((j+i) % 3)::int,
        ((5 + (i % 7) + j*2) * price_list[j])::numeric(12,2),
        (((j+i) % 3) * price_list[j])::numeric(12,2),
        (5 + (i % 7) + j*2)::int, 'EUR'
      );
    END LOOP;
  END LOOP;

  -- Inventory: latest snapshot only
  FOR j IN 1..array_length(asin_list, 1) LOOP
    INSERT INTO inventory_data (
      account_id, snapshot_date, asin, sku, fnsku,
      afn_fulfillable_quantity, afn_inbound_working_quantity, afn_inbound_shipped_quantity,
      afn_reserved_quantity, afn_total_quantity, mfn_fulfillable_quantity
    ) VALUES (
      v_acc_id, v_today, asin_list[j], 'SKU-' || asin_list[j], 'FNSKU' || j,
      (CASE WHEN j = 2 THEN 3 ELSE 50 + j*10 END), 5, 0, 2, 50 + j*10 + 7, 0
    );
  END LOOP;

  -- Advertising campaign + 14 days of metrics
  INSERT INTO advertising_campaigns (id, account_id, campaign_id, campaign_name, campaign_type, state, daily_budget)
  VALUES (v_camp_id, v_acc_id, 'CAMP-SEED-001', 'Seed Sponsored Products', 'sponsoredProducts', 'enabled', 25.00);

  FOR i IN 0..13 LOOP
    d := v_today - i;
    INSERT INTO advertising_metrics (
      campaign_id, date,
      impressions, clicks, cost,
      attributed_sales_1d, attributed_sales_7d, attributed_sales_14d, attributed_sales_30d,
      attributed_units_ordered_1d, attributed_units_ordered_7d, attributed_units_ordered_14d, attributed_units_ordered_30d,
      ctr, cpc, acos, roas
    ) VALUES (
      v_camp_id, d,
      1000 + i*40, 50 + i*2, (10 + i*0.5)::numeric(10,2),
      (40 + i)::numeric, (60 + i*1.5)::numeric, (80 + i*1.8)::numeric, (120 + i*2)::numeric,
      2, 3 + (i % 2), 4, 5,
      (0.05)::numeric, (0.20)::numeric, (0.18)::numeric, (5.0)::numeric
    );
  END LOOP;

  -- Forecast (sales, 30 days)
  INSERT INTO forecasts (
    id, account_id, forecast_type, asin, model_used,
    predictions, mape, rmse, confidence_interval, forecast_horizon_days, confidence_level, data_quality_notes
  ) VALUES (
    v_fc_id, v_acc_id, 'sales', NULL, 'prophet',
    (SELECT jsonb_agg(jsonb_build_object(
      'date', (v_today + g)::text,
      'value', 100 + g*1.5,
      'lower', 80 + g*1.2,
      'upper', 120 + g*1.8
    )) FROM generate_series(1, 30) g),
    8.4, 12.7, 0.9, 30, 'medium', '[]'::jsonb
  );

  -- Alert rule + one triggered alert
  INSERT INTO alert_rules (
    id, organization_id, name, alert_type, conditions, applies_to_accounts,
    notification_channels, is_enabled
  ) VALUES (
    v_rule_id, v_org_id, 'Low stock seed rule', 'low_stock',
    '{"threshold": 10}'::jsonb, ARRAY[v_acc_id]::uuid[],
    ARRAY['email']::varchar[], true
  );

  INSERT INTO alerts (
    id, rule_id, account_id, asin, event_kind, dedup_key, message, details,
    severity, is_read, triggered_at, last_seen_at
  ) VALUES (
    gen_random_uuid(), v_rule_id, v_acc_id, asin_list[2],
    'low_stock', 'low_stock:' || v_acc_id || ':' || asin_list[2],
    'Inventory for ' || asin_list[2] || ' below threshold (3 units)',
    jsonb_build_object('current', 3, 'threshold', 10),
    'warning', false, now(), now()
  );

  RAISE NOTICE 'Seed complete for org %', v_org_id;
END $$;

SELECT 'accounts:' AS k, count(*) FROM amazon_accounts WHERE id = '11111111-1111-1111-1111-111111111111'
UNION ALL SELECT 'products:', count(*) FROM products WHERE account_id = '11111111-1111-1111-1111-111111111111'
UNION ALL SELECT 'sales_rows:', count(*) FROM sales_data WHERE account_id = '11111111-1111-1111-1111-111111111111'
UNION ALL SELECT 'inv_rows:', count(*) FROM inventory_data WHERE account_id = '11111111-1111-1111-1111-111111111111'
UNION ALL SELECT 'ad_metric_rows:', count(*) FROM advertising_metrics WHERE campaign_id = '22222222-2222-2222-2222-222222222222'
UNION ALL SELECT 'forecasts:', count(*) FROM forecasts WHERE id = '33333333-3333-3333-3333-333333333333'
UNION ALL SELECT 'alerts:', count(*) FROM alerts WHERE rule_id = '44444444-4444-4444-4444-444444444444';
