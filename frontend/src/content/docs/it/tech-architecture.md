# Architecture decisions

The other `tech-*` pages are generated from the source by `backend/scripts/gen_tech_docs.py` and describe *what* the system does. This page is hand-written and covers *why*, because the reasons live in commit messages and incidents, not in the code.

Every statement below is traceable to a comment, a commit, or the code itself.

## No Celery in production

The platform ships Celery tasks under `backend/workers/tasks/`, but production runs **none of them**. There is no worker and no Redis. Instead the API process starts an APScheduler `BackgroundScheduler` in its FastAPI lifespan when `ENABLE_INPROCESS_SCHEDULER` is true (`app/main.py`), and every job is registered there.

This was not the original design. Commit *"Port Celery-only jobs to the in-process scheduler"* lists what was silently dead before: weekly forecasts, weekly strategic recommendations, brand-intelligence scan and recovery, the daily digest, the hourly alert-rule checks (`low_stock`, `price_change`, `bsr_drop`, `sync_failure`), scheduled-report recovery, the Google Sheets scan, and partition creation. They existed only in Celery beat, so in a worker-less deploy they never ran and the artifacts they produce just went stale without any error.

Consequences you need to know before touching anything:

- **Adding a task to `workers/tasks/` does not make it run.** It needs a `run_*` entrypoint and a `scheduler.add_job(...)` line in `app/main.py`, or it is dead code in production.
- **On-demand long jobs also run in-process.** `settings.run_tasks_inline` is true whenever the in-process scheduler is on (`app/config.py`), so brand analysis and market research execute in a daemon thread inside the API process instead of dispatching to Celery.
- **A thread dies with the process.** A deploy mid-run kills whatever was running, which is why there are recovery sweeps: `run_backfill_recovery_sweep`, `run_brand_analysis_recovery`, `run_brand_intelligence_recovery`, `run_scheduled_report_recovery`.
- **Every entrypoint builds its own engine and event loop.** The shared asyncpg pool is bound to the FastAPI event loop and cannot be reused safely from another thread (`app/services/extraction_runner.py` module docstring). Never pass the request-scoped session into a scheduler job.
- **Redis is optional, not absent-by-design in code.** The auth rate limiter counts in Redis when available and falls back to an in-process counter otherwise; that fallback is per-process and documented as fine for a single-instance API (`app/api/deps.py`).

### The trap: never port data retention

`app/services/db_maintenance.py` is a **creation-only** mirror of the Celery `manage_partitions` task. Partition drops and `manage_data_retention` are deliberately not ported: `DATA_RETENTION_MONTHS` is 24, and the client's vendor account carries roughly 4 years of history that is a stated requirement to keep. Porting those two jobs "for completeness" would delete real data. Nothing in production may delete time-series rows.

## Credentials are per account, on purpose

`resolve_credentials` in `app/core/amazon/credentials.py` treats the two halves of an Amazon credential very differently, and the docstring explains why.

**The LWA refresh token is strictly per account. There is no fallback.** The refresh token is what determines *which seller's data Amazon returns*. A shared or environment-level token would therefore sync some other seller's data into this account — and that is exactly what happened: an account created without credentials backfilled a different store's history through the old environment fallback. The fallback was removed. An account without its own token raises `MISSING_CREDENTIALS` and does not sync.

**`client_id` / `client_secret` may fall back to the environment.** Order is organization settings (encrypted JSONB) → global env vars. This is safe because those values identify the *application*, not the seller.

The same shape applies to the Advertising API (`resolve_advertising_credentials`): the ads refresh token is per account (`MISSING_ADVERTISING_REFRESH_TOKEN`), while client id/secret resolve org → env.

Two related guards in the OAuth callback (commit *"Reject cross-seller reconnects and stop duplicating accounts"*):

- The callback **refuses** a token whose returned selling partner differs from the `seller_id` already stored on the account. Before this, reauthorizing while logged in as a different seller overwrote `seller_id` and pulled that seller's history in.
- A callback without an `account_id` now looks up an existing account by `seller_id` + marketplace instead of creating a new one, because the "connect" button produced a duplicate account and a second full backfill on every reconnect. The lookup takes the oldest row with `limit(1)`: duplicates from the old behaviour already exist in production and must not raise here.
- The `client_id`/`client_secret` check moved into `/oauth/start`, so a missing app credential fails *before* the user is sent to Amazon rather than after they grant consent.

## Amazon expires the client secret every 180 days

Amazon forces a rotation of the LWA client secret every 180 days. When the deadline passes the API rejects every request, while the LWA token endpoint keeps issuing access tokens — so nothing in the response distinguishes it from a plain bad credential.

It has already cost this installation **16 days of data, unnoticed**, because the only warning would have gone out by email (commit *"Make the account flow reachable and explain Amazon's secret rotation"*).

That is why it gets its own terminal error code, `LWA_SECRET_EXPIRED`, in `classify_sync_exception` (`app/core/sync_health.py`):

- The fix is *rotate the secret in Seller Central*, not *reconnect the account*. Two different user actions need two different codes.
- Detection is a **substring match** on `"lwa secret token you provided has expired"` — Amazon ships no machine-readable code for it.
- It lives in `classify_sync_exception` rather than in the in-process runner because the Celery path shares that function.

The UI age indicator does not need a migration: the age is read from the **Fernet timestamp embedded in the stored token** (bytes 1..9, no decryption). It therefore measures when the secret was *saved here*, not when Amazon *issued* it, so it under-estimates the true age — which is why the preventive notice in Settings starts at 120 days, well before 180.

## Real window caps per data source

These numbers are not guesses; they are Amazon's limits, several of them measured live against the API. They live as commented constants in `app/services/data_extraction.py` and `app/services/extraction_runner.py`.

| Source | Cap | Constant |
| --- | --- | --- |
| Seller sales history | 24 months (Sales & Traffic hard 2-year cap) | `DEFAULT_BACKFILL_MONTHS` |
| Vendor sales history | 48 months — verified live: 48 months back returned data, 51 months FATALed | `VENDOR_BACKFILL_MAX_MONTHS` |
| Vendor sales report, `reportPeriod=DAY` | 15 days per request; Amazon FATALs on longer windows | `VENDOR_DAY_WINDOW_MAX_DAYS` |
| Vendor publish lag | 4 days — the current incomplete period is never requested | `VENDOR_REPORT_LAG_DAYS` |
| Routine vendor sync window | 35 days rolling, to absorb restatements | `VENDOR_SYNC_DEFAULT_DAYS` |
| Ads report request | 31 days per report | `ADS_REPORT_MAX_WINDOW_DAYS` |
| Ads lookback, per product | SP 95 / SB 60 / SD 65 days from today | `ADS_LOOKBACK_DAYS` |
| Daily ads sync | trailing 7 days only | `ADS_SYNC_WINDOW_DAYS` |
| Sales gap repair | 730 days back, 2-day publish lag, max 5 re-pulled windows per account per run | `SALES_GAP_*` |

Throttling is handled with explicit cooldowns rather than generic retries: `createReport` defaults to roughly one request per minute, so a backfill waits a full quota window (65s) before giving up on a month — 3 attempts for seller windows, 2 for vendor ones, with a short pause between windows.

The vendor inventory report has its own shape constraint: a **Sunday-aligned weekly window**, because Amazon FATALs on anything else (commit *"Vendor inventory sync"*).

### The trap: ads data older than 7 days is unreachable

The daily ads sync only re-pulls a trailing 7-day window. Anything older is unreachable **unless the history backfill runs**. A 16-day auth outage produced exactly that hole. The backfill guard used to look only at the oldest stored row, so once coverage reached Amazon's retention bound it skipped forever and the hole was permanent. `_ads_backfill_needed` now requires coverage at **both ends** and re-runs when the newest row falls outside the sync window.

## Backfill: phases, resume, and what PARTIAL means

`_initial_sync_one` runs two phases. Phase 1 is a full current sync (inventory, orders, ads, products, recent sales) and also sets the account sync status. Phase 2 fills older sales history for forecasting, plus orders, economics and returns history for sellers. The backfill is best-effort and never downgrades a successful sync; its outcome lives in the `last_backfill_*` columns.

Details that exist because something broke:

- **The window is resolved before phase 1**, since vendors get a deeper window than the seller report's 2-year cap allows.
- **The backfill is stamped as started before phase 1.** A phase-1 failure used to return before stamping, leaving `last_backfill_status` NULL — and neither recovery sweep claims NULL, so the account stayed on the rolling 30-day window forever.
- **Each history extra runs in its own session and try/except**, so one failure never affects the others.
- **Failures of non-sales sources degrade the status to PARTIAL** and record which sources failed, reusing the existing status column and counter rather than adding new columns. Before this, orders, economics, returns and ads could all fail while the UI reported a completed backfill.
- **Ads history runs even when the sales backfill failed**, because it has its own API and its own lookback caps — and ads-only accounts have no SP-API token at all.

`PARTIAL` means: the backfill finished, but at least one monthly window was skipped — throttled past its retries, or Amazon had no report for it — so the stored history may have **gaps inside the requested range** (`BackfillStatus` docstring in `app/models/amazon_account.py`). It is not "still running" and not "failed".

The hourly recovery sweep (`run_backfill_recovery_sweep`) does two things:

1. Anything still `running` after 6 hours is assumed to be a thread lost to a process restart and is marked `error`.
2. Errored backfills at least 1 hour old are re-claimed, re-marked `running` and re-stamped — which makes the retry rate naturally one attempt per hour. The resume restarts from the **first missing daily-total date** inside the recorded range, staying behind the publish lag so trailing unpublished days are not mistaken for holes (that would re-pull the tail window every hour). When the range has no holes, the backfill is marked successful without calling Amazon at all.

## There is no object storage

Production has **no S3/R2 bucket, by decision**. The consequence was a whole feature: the catalog image-management tab could only ever show an "unavailable" message, so the tab, the upload UI, the images API client, the three `/catalog/products/{asin}/images` endpoints and `ImageService` were all deleted (commit *"Remove the catalog image-management feature"*).

What this means for anything you build:

- Binary artifacts live in the database. `app/services/brand_analysis_storage.py` supports a `db` and an `s3` backend; `db` is the default and keeps bytes in the existing `LargeBinary` columns. The `s3` path exists but is not the production configuration.
- Exports (Excel, PowerPoint, CSV) are generated per request and returned as a `StreamingResponse` from `app/api/v1/exports.py`. Nothing is persisted to a bucket.
- `render.yaml` still declares `AWS_S3_BUCKET` and the AWS keys as `sync: false`, i.e. unset.

Do not design a feature around "we'll just put the file in S3".

## OpenAPI is off in production

`docs_url`, `redoc_url` and `openapi_url` are all gated on `settings.APP_DEBUG` in `app/main.py`. Disabling `docs_url` alone still leaves `/openapi.json` public, which hands out the full endpoint and schema inventory; nothing consumes it in production. This came out of the security wave that also fixed a cross-tenant alert-rule leak and refresh-token rotation.

Related fail-fast guards in `validate_production_settings` (`app/config.py`): production refuses to start with a `*` in `CORS_ORIGINS`, with `APP_DEBUG` true, or without an `ENCRYPTION_KEY` — without that key Amazon credentials can neither be stored nor read.

## Deploying on Render

`render.yaml` declares three things: the API web service (Python, Frankfurt), the static frontend, and PostgreSQL.

**Neither the API nor the database can be on a free plan**, and the file says why:

- The API runs the in-process scheduler that replaces Celery, and free instances spin down when idle — which would stop every cron job.
- Free databases expire after 30 days.

**Migrations run in the start command**: `alembic upgrade head && uvicorn app.main:app`. So every deploy migrates before serving, and a bad migration fails the service at startup rather than at build time.

The blueprint drifted from the code once already (commit *"Fix the Render blueprint so a clean deploy would work"*): it declared `AMAZON_SP_CLIENT_ID`/`SECRET` while the app reads `AMAZON_SP_API_*`, omitted `AMAZON_SP_API_APP_ID`, `APP_API_URL`, `APP_FRONTEND_URL` and `ENABLE_INPROCESS_SCHEDULER` entirely, and declared an `S3_BUCKET_NAME` that is never read (the setting is `AWS_S3_BUCKET`). Applying it would have shipped a service where connecting an account cannot work.

`app/config.py` is the authority on environment variable names. If the blueprint and the settings class disagree, the settings class wins and the blueprint is the bug.
