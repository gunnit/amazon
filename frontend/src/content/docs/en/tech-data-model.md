# Data model
> Generated from the source by `backend/scripts/gen_tech_docs.py`. Re-run it after changing the code; do not edit this page by hand.

40 tables, read from the SQLAlchemy metadata.

## Tables

| Table | Columns | References |
| --- | --- | --- |
| `advertising_campaigns` | 9 | `amazon_accounts` |
| `advertising_metrics` | 19 | `advertising_campaigns` |
| `advertising_metrics_by_asin` | 15 | `advertising_campaigns`, `amazon_accounts` |
| `alert_rules` | 13 | `organizations` |
| `alerts` | 18 | `alert_rules`, `amazon_accounts`, `organizations` |
| `amazon_accounts` | 33 | `organizations` |
| `asin_economics` | 17 | `amazon_accounts` |
| `asin_offer_snapshots` | 15 | `amazon_accounts`, `organizations` |
| `brand_analysis_capabilities` | 19 | `amazon_accounts`, `organizations` |
| `brand_analysis_jobs` | 37 | `amazon_accounts`, `organizations`, `users` |
| `brand_analysis_source_files` | 14 | `brand_analysis_jobs`, `organizations`, `users` |
| `brand_intelligence_reports` | 21 | `amazon_accounts`, `organizations` |
| `brand_intelligence_schedules` | 9 | `amazon_accounts`, `organizations` |
| `brand_search_terms` | 10 | `amazon_accounts` |
| `bsr_history` | 6 | `products` |
| `catalog_change_log` | 12 | `amazon_accounts`, `organizations`, `users` |
| `competitor_history` | 8 | `competitors` |
| `competitors` | 12 | `organizations` |
| `fee_estimates` | 8 | `amazon_accounts` |
| `forecast_export_jobs` | 16 | `forecasts`, `organizations`, `users` |
| `forecasts` | 13 | `amazon_accounts` |
| `google_sheets_connections` | 13 | `organizations`, `users` |
| `google_sheets_sync_runs` | 11 | `google_sheets_syncs`, `organizations` |
| `google_sheets_syncs` | 20 | `google_sheets_connections`, `organizations`, `users` |
| `inventory_data` | 13 | `amazon_accounts` |
| `listing_quality_snapshots` | 7 | `amazon_accounts` |
| `market_research_reports` | 18 | `amazon_accounts`, `organizations`, `users` |
| `order_items` | 8 | `orders` |
| `orders` | 11 | `amazon_accounts` |
| `organization_members` | 5 | `organizations`, `users` |
| `organizations` | 6 | — |
| `price_snapshots` | 12 | `amazon_accounts` |
| `products` | 17 | `amazon_accounts` |
| `returns_data` | 11 | `amazon_accounts` |
| `sales_data` | 18 | `amazon_accounts` |
| `scheduled_report_runs` | 21 | `organizations`, `scheduled_reports` |
| `scheduled_reports` | 18 | `organizations`, `users` |
| `strategic_recommendations` | 20 | `amazon_accounts`, `organizations`, `users` |
| `sync_jobs` | 11 | `amazon_accounts` |
| `users` | 8 | — |

## Migrations

36 revisions, applied on deploy by `alembic upgrade head` in the start command.

- `001_initial_schema`
- `002_align_schema`
- `003_add_market_research_reports`
- `004_add_progress_tracking`
- `005_add_forecast_export_jobs`
- `006_add_scheduled_reports`
- `007_add_alert_incident_tracking`
- `007_add_sync_health_fields`
- `007_optimize_alert_queries`
- `008_add_google_sheets_tables`
- `009_add_advertising_credentials`
- `009_add_orders_tables`
- `010_add_returns_data`
- `011_add_brin_indexes_for_retention`
- `012_add_last_refreshed_at`
- `013_add_forecast_confidence`
- `014_add_product_availability`
- `015_add_partition_helpers`
- `016_add_strategic_recommendations`
- `017_add_advertising_metrics_by_asin`
- `018_add_brand_analysis`
- `019_ba_v2`
- `020_ba_err_code`
- `021_brand_analysis_capabilities_snapshots`
- `022_catalog_change_log`
- `023_partition_ts_tables`
- `024_sales_data_traffic_cols`
- `025_add_recommendation_confidence`
- `026_widen_alembic_version`
- `027_product_source`
- `028_vendor_shipped_metrics`
- `029_brand_analysis_job_lifecycle`
- `030_alert_notifications_extend`
- `031_brand_intelligence`
- `032_account_backfill_tracking`
- `033_ingestion_expansion`
