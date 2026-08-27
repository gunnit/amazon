# API surface
> Generated from the source by `backend/scripts/gen_tech_docs.py`. Re-run it after changing the code; do not edit this page by hand.

149 endpoints across 15 routers, all under `/api/v1`.

## accounts

Prefix `/accounts`.

| Method | Path |
| --- | --- |
| GET | `/accounts` |
| POST | `/accounts` |
| POST | `/accounts/oauth/start` |
| GET | `/accounts/oauth/callback` |
| GET | `/accounts/summary` |
| POST | `/accounts/advertising/profiles` |
| GET | `/accounts/{account_id}` |
| PUT | `/accounts/{account_id}` |
| DELETE | `/accounts/{account_id}` |
| POST | `/accounts/{account_id}/test-connection` |
| POST | `/accounts/{account_id}/sync` |
| POST | `/accounts/sync-all` |
| POST | `/accounts/{account_id}/backfill` |
| POST | `/accounts/backfill-all` |
| GET | `/accounts/{account_id}/status` |

## alerts

Prefix `/alerts`.

| Method | Path |
| --- | --- |
| GET | `/alerts/rules` |
| POST | `/alerts/rules` |
| GET | `/alerts/rules/{rule_id}` |
| PUT | `/alerts/rules/{rule_id}` |
| DELETE | `/alerts/rules/{rule_id}` |
| GET | `/alerts/summary` |
| GET | `/alerts` |
| GET | `/alerts/history` |
| GET | `/alerts/unread-count` |
| PATCH | `/alerts` |
| POST | `/alerts/mark-all-read` |
| PATCH | `/alerts/{alert_id}` |
| PATCH | `/alerts/{alert_id}/read` |

## analytics

Prefix `/analytics`.

| Method | Path |
| --- | --- |
| GET | `/analytics/dashboard` |
| GET | `/analytics/ads-vs-organic` |
| GET | `/analytics/trends` |
| GET | `/analytics/returns` |
| GET | `/analytics/comparison` |
| GET | `/analytics/top-performers` |
| GET | `/analytics/per-product-performance` |
| GET | `/analytics/product-trends` |
| GET | `/analytics/product-trends/insights` |
| GET | `/analytics/orders-by-hour` |
| GET | `/analytics/advertising` |
| GET | `/analytics/admin/data-health` |
| GET | `/analytics/today` |
| GET | `/analytics/profitability` |

## auth

Prefix `/auth`.

| Method | Path |
| --- | --- |
| POST | `/auth/register` |
| POST | `/auth/login` |
| POST | `/auth/refresh` |
| POST | `/auth/logout` |
| POST | `/auth/forgot-password` |
| POST | `/auth/reset-password` |
| GET | `/auth/me` |
| PUT | `/auth/me` |
| PUT | `/auth/me/password` |
| GET | `/auth/me/notifications` |
| PUT | `/auth/me/notifications` |
| GET | `/auth/me/email-status` |
| DELETE | `/auth/me` |
| POST | `/auth/organization` |
| GET | `/auth/organization` |
| PUT | `/auth/organization` |
| GET | `/auth/organization/api-keys` |
| PUT | `/auth/organization/api-keys` |
| DELETE | `/auth/organization/api-keys` |

## brand_analysis

Prefix `/brand-analysis`.

| Method | Path |
| --- | --- |
| POST | `/brand-analysis` |
| GET | `/brand-analysis` |
| POST | `/brand-analysis/{job_id}/upload/{year}` |
| POST | `/brand-analysis/{job_id}/start` |
| POST | `/brand-analysis/{job_id}/cancel` |
| GET | `/brand-analysis/{job_id}/download` |
| GET | `/brand-analysis/{job_id}` |
| DELETE | `/brand-analysis/{job_id}` |

## brand_intelligence

Prefix `/brand-intelligence`.

| Method | Path |
| --- | --- |
| GET | `/brand-intelligence/reports` |
| GET | `/brand-intelligence/reports/latest` |
| GET | `/brand-intelligence/reports/{report_id}` |
| POST | `/brand-intelligence/generate` |
| GET | `/brand-intelligence/schedule` |
| PUT | `/brand-intelligence/schedule` |

## brand_pulse

Prefix `/brand-pulse`.

| Method | Path |
| --- | --- |
| GET | `/brand-pulse` |

## catalog

Prefix `/catalog`.

| Method | Path |
| --- | --- |
| GET | `/catalog/products` |
| GET | `/catalog/products/{asin}` |
| PUT | `/catalog/products/{asin}` |
| POST | `/catalog/backfill-titles` |
| GET | `/catalog/bulk-update/template` |
| POST | `/catalog/bulk-update` |
| GET | `/catalog/import/template` |
| POST | `/catalog/import` |
| POST | `/catalog/prices` |
| PATCH | `/catalog/products/{asin}/availability` |
| GET | `/catalog/products/{asin}/history` |
| GET | `/catalog/listing-quality` |

## competitors

Prefix `/competitors`.

| Method | Path |
| --- | --- |
| GET | `/competitors` |
| POST | `/competitors` |
| DELETE | `/competitors/{competitor_id}` |
| GET | `/competitors/{competitor_id}/history` |

## exports

Prefix `/exports`.

| Method | Path |
| --- | --- |
| POST | `/exports/csv` |
| POST | `/exports/bundle` |
| POST | `/exports/excel-bundle` |
| POST | `/exports/excel` |
| POST | `/exports/powerpoint` |
| POST | `/exports/forecast-excel` |
| POST | `/exports/forecast-csv` |
| POST | `/exports/forecast-package` |
| GET | `/exports/forecast-package/{job_id}` |
| GET | `/exports/forecast-package/{job_id}/download` |
| POST | `/exports/market-research-pdf` |
| POST | `/exports/recommendations-xlsx` |
| GET | `/exports/{export_id}/download` |

## forecasts

Prefix `/forecasts`.

| Method | Path |
| --- | --- |
| GET | `/forecasts` |
| GET | `/forecasts/available-products` |
| POST | `/forecasts/generate` |
| GET | `/forecasts/{forecast_id}` |
| GET | `/forecasts/products/{asin}` |

## google_sheets

Prefix `/google-sheets`.

| Method | Path |
| --- | --- |
| GET | `/google-sheets/oauth/authorize` |
| GET | `/google-sheets/oauth/callback` |
| GET | `/google-sheets/connection` |
| DELETE | `/google-sheets/connection` |
| POST | `/google-sheets/export` |
| GET | `/google-sheets/syncs` |
| POST | `/google-sheets/syncs` |
| PUT | `/google-sheets/syncs/{sync_id}` |
| POST | `/google-sheets/syncs/{sync_id}/toggle` |
| DELETE | `/google-sheets/syncs/{sync_id}` |
| POST | `/google-sheets/syncs/{sync_id}/run-now` |
| GET | `/google-sheets/syncs/{sync_id}/runs` |

## market_research

Prefix `/market-research`.

| Method | Path |
| --- | --- |
| POST | `/market-research/generate` |
| GET | `/market-research` |
| GET | `/market-research/{report_id}` |
| POST | `/market-research/{report_id}/refresh` |
| GET | `/market-research/{report_id}/comparison-matrix` |
| DELETE | `/market-research/{report_id}` |
| POST | `/market-research/market-search` |

## recommendations

Prefix `/recommendations`.

| Method | Path |
| --- | --- |
| GET | `/recommendations` |
| GET | `/recommendations/{rec_id}` |
| PATCH | `/recommendations/{rec_id}` |
| DELETE | `/recommendations/{rec_id}` |
| POST | `/recommendations/generate` |

## reports

Prefix `/reports`.

| Method | Path |
| --- | --- |
| GET | `/reports/email-status` |
| GET | `/reports/sales` |
| GET | `/reports/sales/aggregated` |
| GET | `/reports/orders` |
| GET | `/reports/inventory` |
| GET | `/reports/advertising` |
| GET | `/reports/schedules` |
| POST | `/reports/schedules` |
| GET | `/reports/schedules/{schedule_id}` |
| PUT | `/reports/schedules/{schedule_id}` |
| DELETE | `/reports/schedules/{schedule_id}` |
| POST | `/reports/schedules/{schedule_id}/toggle` |
| GET | `/reports/schedules/{schedule_id}/runs` |
| POST | `/reports/schedules/{schedule_id}/run-now` |
| GET | `/reports/schedules/runs/{run_id}/download` |
