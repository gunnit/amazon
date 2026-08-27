# Scheduled jobs
> Generated from the source by `backend/scripts/gen_tech_docs.py`. Re-run it after changing the code; do not edit this page by hand.

The API process runs its own scheduler, so there is no Celery worker in production. 21 jobs are registered in `app/main.py`.

## Job table

| Job id | Entrypoint | Trigger |
| --- | --- | --- |
| `daily-account-sync` | `run_daily_sync_all` | `CronTrigger(hour=settings.INPROCESS_SYNC_HOUR_UTC, minute=settings.INPROCESS_SYNC_MINUTE_UTC)` |
| `recent-seller-sales-refresh` | `run_recent_seller_sales_sync_all` | `CronTrigger(hour=settings.INPROCESS_SALES_REFRESH_HOURS_UTC, minute=settings.INPROCESS_SALES_REFRESH_MINUTE_UTC)` |
| `scheduled-report-scan` | `run_scheduled_report_scan` | `IntervalTrigger(minutes=settings.SCHEDULED_REPORT_SCAN_INTERVAL_MINUTES)` |
| `backfill-recovery-sweep` | `run_backfill_recovery_sweep` | `IntervalTrigger(hours=1)` |
| `sales-gap-repair` | `run_sales_gap_repair_all` | `CronTrigger(hour=4, minute=30)` |
| `recent-orders-refresh` | `run_recent_orders_sync_all` | `CronTrigger(minute=45)` |
| `asin-economics-sync` | `run_asin_economics_sync_all` | `CronTrigger(hour=5, minute=30)` |
| `market-snapshot` | `run_market_snapshot_all` | `CronTrigger(hour=6, minute=30)` |
| `competitor-tracking` | `run_competitor_tracking_all` | `CronTrigger(hour=7, minute=15)` |
| `brand-search-terms-sync` | `run_brand_search_terms_sync_all` | `CronTrigger(day_of_week='wed', hour=7, minute=0)` |
| `listing-quality-snapshot` | `run_listing_quality_snapshot_all` | `CronTrigger(day_of_week='sun', hour=7, minute=30)` |
| `brand-analysis-recovery` | `run_brand_analysis_recovery` | `IntervalTrigger(minutes=settings.BRAND_ANALYSIS_RECOVERY_INTERVAL_MINUTES)` |
| `hourly-alert-check` | `run_alert_check` | `CronTrigger(minute=5)` |
| `daily-digest` | `run_daily_digest` | `CronTrigger(hour=8, minute=0)` |
| `weekly-forecasts` | `run_weekly_forecast_generation` | `CronTrigger(day_of_week='sun', hour=3, minute=0)` |
| `weekly-strategic-recommendations` | `run_weekly_recommendations` | `CronTrigger(day_of_week='mon', hour=6, minute=0)` |
| `brand-intelligence-scan` | `run_brand_intelligence_scan` | `IntervalTrigger(minutes=15)` |
| `brand-intelligence-recovery` | `run_brand_intelligence_recovery` | `IntervalTrigger(minutes=30)` |
| `scheduled-report-recovery` | `run_scheduled_report_recovery` | `IntervalTrigger(minutes=15)` |
| `google-sheets-sync-scan` | `run_google_sheets_scan` | `IntervalTrigger(minutes=5)` |
| `partition-ensure` | `run_partition_ensure` | `CronTrigger(hour=3, minute=30)` |
