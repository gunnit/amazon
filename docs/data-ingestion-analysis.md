# Amazon Data Ingestion — Analysis & Roadmap (2026-06-11)

Scope: account backfill, automatic sales updates, new SP-API data sources, and the
product improvements they unlock. Companion code changes shipped with this doc:
backfill status tracking + bulk backfill endpoint (see §1.3).

---

## 1. Backfill on account connect

### 1.1 Current state (verified in code)

The first-connect pipeline already exists and covers most requirements:

- `POST /api/v1/accounts` → `initial_sync_in_thread()` (`app/api/v1/accounts.py:328`)
  fires automatically when a new account with credentials is created.
- Phase 1 (`extraction_runner._initial_sync_one`): full current sync — sales,
  inventory, orders, returns, advertising, products. Optional steps are
  best-effort and never abort the sync.
- Phase 2: historical sales backfill over the **maximum window Amazon allows**:
  24 calendar months, clamped in `_resolve_backfill_window()` (Sales & Traffic
  reports cap at 2 years).
- **No duplicates / idempotent**: all sales writes go through
  `ON CONFLICT (account_id, date, asin) DO UPDATE` (`_upsert_sales_record`);
  vendor months are fetch-first/replace-on-success; the backfill commits per
  month so re-runs converge instead of double-counting.
- Throttle resilience: seller windows retry on `THROTTLED` with cooldown
  (`SELLER_BACKFILL_MAX_WINDOW_ATTEMPTS`), vendor months pause between requests.
- Manual re-run: `POST /api/v1/accounts/{id}/backfill?months=24`.

### 1.2 Gaps found

1. **No persistent backfill status** — outcome only visible in logs. A failed or
   partial backfill (skipped windows) was indistinguishable from success in the
   API/UI. `sync_status` only reflects the *daily sync*, and phase 2 is
   deliberately best-effort so it never sets ERROR.
2. **No bulk path for already-connected accounts** — only the per-account
   endpoint existed.

### 1.3 Shipped in this change

- `amazon_accounts` gains backfill lifecycle columns (migration
  `032_account_backfill_tracking`): `last_backfill_status`
  (`running|success|partial|error`), `last_backfill_started_at/completed_at`,
  `last_backfill_records`, `last_backfill_windows_skipped`,
  `last_backfill_error`, `last_backfill_range_start/end`.
- `DataExtractionService` counts skipped windows during both seller and vendor
  backfills (`backfill_windows_skipped`); the runner stamps `partial` when any
  window inside the requested range had to be skipped.
- `POST /api/v1/accounts/backfill-all?months=24` — re-syncs + backfills every
  active connected account in the org, **sequentially in one background
  thread** so N accounts never compete for the same Reports API quota.
- All `last_backfill_*` fields exposed on `AccountStatusResponse`
  (`/accounts/summary`, `/accounts/{id}/status`, `/accounts/{id}/backfill`).

Run for existing accounts: after deploy, call `POST /api/v1/accounts/backfill-all`
once per organization, then watch `/accounts/summary` until every account shows
`last_backfill_status = success` (or inspect `partial` ones via
`last_backfill_windows_skipped`).

### 1.4 Remaining hardening (not blocking)

- Backfill currently covers **sales** history only; orders backfill (Orders API
  allows much older `CreatedAfter`) and finance/settlement history would extend
  it (see §3).
- A `backfill_jobs` table (one row per run with per-window results) would give a
  full audit trail; the per-account columns cover the operational need today.
- If the web process restarts mid-backfill the daemon thread dies; status stays
  `running`. A recovery sweep (mark `running` older than N hours as `error`,
  optionally re-trigger) mirrors the existing brand-analysis recovery pattern.

---

## 2. Automatic sales updates

### 2.1 Are sales updated automatically? — Yes

Two schedulers exist, selected by deployment:

| Scheduler | When used | Jobs |
|---|---|---|
| **In-process APScheduler** (`app/main.py` lifespan, `ENABLE_INPROCESS_SCHEDULER=true`) | **Production** (Render, no Redis worker) | Daily full sync 02:00 UTC; seller Sales & Traffic refresh at 00/06/12/18:15 UTC; scheduled-report scan every 10 min |
| **Celery beat** (`workers/celery_app.py`) | Deployments with Redis | Same daily + intraday jobs, plus forecasts, retention, partitions, alerts, digests |

The intraday refresh (`run_recent_seller_sales_sync_all`) re-pulls the rolling
30-day Sales & Traffic window 4×/day without the heavier inventory/orders/ads
steps, guarded by a lock so it never overlaps the daily full sync.

### 2.2 Does the API allow near-real-time?

- **Sales & Traffic report (sellers)**: no. Data publishes with ~24h latency and
  Amazon **restates recent days** for up to ~2 weeks. This is why the refresh
  re-pulls a rolling 30-day window (restatements are absorbed by the upsert).
- **Orders API (sellers)**: near-real-time (minutes). Already synced
  incrementally each daily sync with a 2-minute buffer and 7-day fallback window
  (`_resolve_orders_sync_window`). This is the right source for a "today so far"
  metric — not the S&T report.
- **Vendor sales report**: monthly granularity, only settled months, several
  days of lag. Intraday refresh is pointless for vendors (correctly excluded).

### 2.3 Recommended frequency (vs API limits)

Current cadence is close to optimal:

- **Keep** daily full sync + 4×/day seller S&T refresh. Report creation is
  throttled (~1 request/min burst, low hourly quotas shared across report
  types); 4 refreshes/day/account is comfortably inside limits even with many
  accounts, since accounts run sequentially.
- **Add (quick win)**: an hourly *orders-only* refresh for sellers (Orders API
  rates are per-seller, `getOrders` ~0.0167 rps sustained but burst 20 — an
  hourly incremental window is trivial) to power a same-day sales tile. Reuse
  `sync_orders` standalone; do not touch the S&T pipeline.
- Going beyond 4–6 S&T refreshes/day buys nothing: the underlying data only
  changes when Amazon republishes (~daily), you just burn report quota.

### 2.4 What to change for reliability

1. **Gap detection** (highest value): nightly job that scans `sales_data` for
   missing `__DAILY_TOTAL__` dates per account over the last 60 days and
   re-pulls only the missing windows. Today a silently failed window heals only
   if it falls back inside the 30-day rolling refresh.
2. **Recovery sweep for stuck `running` backfills** (§1.4).
3. **Restatement depth**: 30-day rolling refresh already exceeds Amazon's
   restatement horizon — no change needed, but document it as a guarantee.
4. Longer term: move scheduling back to Celery/Redis when the infra budget
   allows; the in-process scheduler dies with web deploys (mitigated today by
   `misfire_grace_time` + next-day catch-up, but mid-run syncs are lost).

---

## 3. API-by-API availability

Legend — *Integrated*: ingested and stored. *Wrapper*: client method exists
(`sp_api_client.py`) but used on-demand only / not persisted. *Probe*: only the
capability check in `brand_analysis_capabilities.py` touches it.

| Source | Amazon API | App access today | Required roles / setup | Limitations | Backend work to ingest |
|---|---|---|---|---|---|
| **Sales & Traffic** | Reports API `GET_SALES_AND_TRAFFIC_REPORT` | ✅ Integrated (daily + intraday, backfill 24 mo) | Brand Analytics role (already granted — it works in prod) | ~24h latency, restatements, 2-year history cap, per-ASIN rows are window aggregates | None (done) |
| **Data Kiosk** | SP-API Data Kiosk (GraphQL: `analytics_salesAndTraffic_2024_04_24`, `analytics_economics_2024_03_15`) | Probe only (`_data_kiosk_api`) | Brand Analytics role; no extra review if S&T already works | Query → poll → JSONL download flow; daily granularity; economics dataset = fees+ads cost per ASIN | New `DataKioskService` (submit/poll/download), reuse `sales_data` + new `asin_economics` table. **This is the strategic replacement for the S&T report and the cheapest path to per-ASIN profitability** |
| **Brand Analytics** | Reports API `GET_BRAND_ANALYTICS_SEARCH_TERMS_REPORT`, `_MARKET_BASKET_`, `_REPEAT_PURCHASE_` | Wrapper (search terms + market basket used on-demand in Brand Analysis; not stored) | Brand Analytics role **+ the seller must be Brand Registry enrolled** | Seller accounts only; weekly/monthly periods; search-terms report is large | Weekly scheduled pull → `brand_search_terms` time-series table; market-basket + repeat-purchase snapshots |
| **Brand Registry availability** | No public API for registry status | ✅ Inferred via BA probe (`brand_analysis_capabilities`) | n/a | Can only infer: BA report access ⇒ registered | None — already surfaced as capability flag |
| **Product Pricing** | SP-API Product Pricing v0 (`getCompetitivePricing`, `getItemOffers`, batch) | ✅ Integrated (product sync + market research) | Pricing role (granted) | 0.5 rps; v0 partially deprecated → plan migration to 2022-05-01 (`getFeaturedOfferExpectedPrice`) | Persist time-series `price_snapshots` (currently only latest price on `products`) to unlock Buy Box/price-trend analytics |
| **Product Fees** | SP-API Product Fees (`getMyFeesEstimateForASIN`) | Wrapper (on-demand in Brand Analysis) | Pricing role (granted) | Estimates, not actuals; 1 rps; per-marketplace | Nightly fee snapshot per active ASIN → `fee_estimates` table; join with price for margin |
| **A+ Content** | SP-API A+ Content API | Wrapper (on-demand in Brand Analysis) | Product Listing role + seller Brand Registry | Brand-registered sellers only; vendor A+ not exposed | Weekly coverage snapshot per ASIN (`has_aplus`, modules count) → listing-quality score |
| **Finance Reports** | SP-API Finances (`listFinancialEvents`, event groups) | Probe only | **Finance and Accounting role — likely needs to be added to the app + sellers re-authorize** | 180-day event window per request; paginated; event taxonomy is wide (fees, promos, refunds, adjustments) | New `financial_events` ingestion (incremental by `PostedAfter`) — actual fees per order, the ground truth for profitability |
| **Settlement Reports** | Reports API `GET_V2_SETTLEMENT_REPORT_DATA_FLAT_FILE_V2` | Probe only | Finance and Accounting role | **Cannot be requested** — Amazon schedules them (bi-weekly); you list + download; 90-day list window | Poller that lists new settlement reports per account → `settlement_reports` + `settlement_lines`; reconciliation vs `financial_events` |
| **Catalog Items** | SP-API Catalog Items 2022-04-01 | ✅ Integrated (product sync, keyword search, change log) | Product Listing role (granted) | 2 rps; attribute coverage varies by marketplace | None (done) |
| **Listings** | SP-API Listings Items + `GET_MERCHANT_LISTINGS_ALL_DATA` | ✅ Integrated (read + write: price/quantity/images/attributes) | Product Listing role (granted) | Seller accounts; writes need `seller_id` (auto-resolved) | Listing-quality scoring on top of existing data (no new ingestion) |

### Required Amazon app configuration changes

1. **Add the "Finance and Accounting" role** to the SP-API app in Developer
   Central (unlocks Finances API + settlement reports). Roles changes trigger an
   app review by Amazon; afterwards **existing sellers must re-authorize** for
   the new role to appear in their tokens.
2. Nothing else: Brand Analytics, Pricing, Product Listing, Inventory/Orders
   roles are demonstrably already granted (the integrations work in prod).
3. Per-seller prerequisites (not app config): Brand Registry enrollment gates
   Brand Analytics reports and A+ Content for that seller.
4. Ads API is a separate app/credential set (already handled per-account).

---

## 4. Product improvements unlocked

### New tables (proposed)

| Table | Source | Grain |
|---|---|---|
| `asin_economics` | Data Kiosk economics dataset | account × ASIN × day: fees, ads cost, net proceeds |
| `financial_events` | Finances API | account × event (typed: fee, refund, promo, adjustment) |
| `settlement_reports` / `settlement_lines` | Settlement flat files | settlement period × line |
| `fee_estimates` | Product Fees | account × ASIN × snapshot date |
| `price_snapshots` | Product Pricing | account × ASIN × snapshot (own price, Buy Box, lowest offer) |
| `brand_search_terms` | Brand Analytics | marketplace × week × search term × rank/share |
| `listing_quality_snapshots` | Listings + Catalog + A+ | account × ASIN × week (score components) |

### Feature map

- **Profitability & margin** (biggest gap today): revenue exists, costs don't.
  Data Kiosk economics (estimates, easy) → Finances events (actuals, deeper)
  gives per-ASIN net margin, fee trend alerts, "margin killers" ranking.
- **Organic vs advertising**: `advertising_metrics_by_asin` already exists;
  joining with per-ASIN sales gives organic share = (total − ad-attributed).
  Mostly an analytics/dashboard task, no new ingestion.
- **Fees & settlement reconciliation**: settlement lines vs expected
  (orders + fee estimates) → discrepancy report; FBA reimbursement candidates.
- **Pricing intelligence**: price_snapshots time series → Buy Box win rate,
  price-vs-velocity curves, repricing recommendations (write path already
  exists via `update_listing_price`).
- **Listing quality**: score = title/bullets/images completeness (Catalog) +
  A+ presence + suppressed/incomplete status (merchant listings report) →
  ranked fix list with expected impact.
- **Brand performance / Weekly Brand Intelligence**: feed search-term rank
  share, repeat-purchase rate, and market-basket affinities into the existing
  `brand_intelligence` weekly pipeline — turns it from internal-data-only into
  true market-share intelligence with Source/Confidence/Evidence per claim.
- **Brand Analysis PDF**: add margin waterfall, search-term share trend, and
  listing-quality sections from the same tables.
- **Inventory recommendations**: existing forecast + fee data → restock value
  ranked by margin (not just units), long-term storage fee warnings.

---

## 5. Prioritized roadmap

**Shipped 2026-06-11 (this wave)**
1. ~~Backfill status + bulk backfill~~ (`last_backfill_*`, `POST /accounts/backfill-all`, migration 032).
2. ~~Stuck-`running` backfill recovery sweep~~ (hourly).
3. ~~Sales gap-detection + repair job~~ (daily 04:30 UTC, 60-day lookback, 5 windows/account cap).
4. ~~Hourly incremental orders refresh~~ + `GET /analytics/today` + "Today so far" dashboard tile.
5. ~~Organic-vs-ads~~ — verified already complete end-to-end (`/analytics/ads-vs-organic` + Performance/ProductAnalytics pages).
6. ~~Data Kiosk economics ingestion~~ (`asin_economics`, daily 05:30 UTC, 30-day first pull / 14-day rolling) + `GET /analytics/profitability`.
7. ~~Fee estimates + price/Buy Box snapshots~~ (`fee_estimates`, `price_snapshots`, daily 06:30 UTC, 200 ASINs/account cap).
8. ~~Brand Analytics weekly ingestion~~ (`brand_search_terms`, Wednesdays 07:00 UTC, stores terms where an account ASIN is top-3 clicked).
9. ~~Listing quality scoring~~ (`listing_quality_snapshots` weekly Sundays + live `GET /catalog/listing-quality` fix list).
All tables in migration 033; every job wired in both the in-process APScheduler and Celery beat.

**Operational next steps**
10. Deploy + `alembic upgrade head`; run `POST /accounts/backfill-all` once per org.
11. Verify the first economics run: if the GraphQL query is rejected (schema drift), the job logs `DATA_KIOSK_FATAL` with the error document — adjust the query in `economics_service._build_query`.
12. Request the Finance and Accounting role; plan seller re-authorization.

**Advanced (after role approval)**
13. Finances event ingestion → actual-cost P&L per ASIN.
14. Settlement ingestion + reconciliation engine.
15. Repricing recommendations with one-click apply (Listings write API).
16. Pricing v0 → 2022-05-01 migration (featured-offer expected price).
17. Frontend pages for profitability (margin dashboard) and listing-quality fix list (endpoints already live).
