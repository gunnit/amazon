# Brand Analysis + Brand Pulse — Backend Discovery Map

Discovery agent output. Deep map of the backend for Brand Analysis, Brand Pulse, the
data-source/capability layer, and the reporting infra they could reuse. All anchors are
`file:line` against the working tree at branch `master`.

---

## 0. Module inventory & responsibilities

| Module | Lines | Role |
|---|---|---|
| `app/services/brand_analysis_service.py` | 3596 | **MONOLITH.** Parsing, metric calc, provenance/limitation logic, narrative LLM service, the entire PPTX builder, the `BrandAnalysisService` CRUD class, AND the background processor `process_brand_analysis_job`. |
| `app/services/brand_analysis_sources.py` | 742 | Data-source adapters: `AmazonAccountDataSource` (internal SP-API path), `ManualUploadDataSource`, deprecated `Helium10ApiDataSource`. All yield `ParsedBrandExport`. |
| `app/services/brand_analysis_capabilities.py` | 363 | Capability PROBE of 11 SP-API capabilities; persists `BrandAnalysisCapability` snapshot with TTL cache. |
| `app/services/brand_analysis_storage.py` | 143 | `BrandAnalysisStorage` db/s3 backend for source files + PPTX artifacts; `StorageRef`. |
| `app/services/brand_pulse_service.py` | 191 | `BrandPulseService` — composes AnalyticsService primitives into a rolling snapshot. **Overlaps Performance Analytics (see §7).** |
| `app/api/v1/brand_analysis.py` | 343 | REST surface for jobs (create/list/upload/start/download/get/delete). |
| `app/api/v1/brand_pulse.py` | 46 | Single GET endpoint; no persistence. |
| `app/models/brand_analysis.py` | 190 | `BrandAnalysisJob`, `BrandAnalysisCapability`, `AsinOfferSnapshot`, `BrandAnalysisSourceFile`. |
| `app/schemas/brand_analysis.py` | 156 | Status/mode/error-code literals + request/response models. |
| `app/schemas/brand_pulse.py` | 79 | Pulse response models. |
| `workers/tasks/brand_analysis.py` | 21 | Thin Celery wrapper → `process_brand_analysis_job`. |
| `workers/tasks/market_research.py` | 33 | Thin Celery wrapper → `process_report_background`. |

---

## 1. End-to-end pipeline (request → task → sources → metrics → narrative → pptx → storage)

### 1.1 Create + upload + start (API)
- `POST /brand-analysis` → `create_brand_analysis_job` (`brand_analysis.py:116`) → `BrandAnalysisService.create_job` (`brand_analysis_service.py:3039`). Validates account ownership, `market_type==asin` needs `asin_list`, `brand` needs `market_query|brand_name`. Persists `BrandAnalysisJob` with `status="pending"`.
- `POST /brand-analysis/{job_id}/upload/{year}` (`brand_analysis.py:152`) → `BrandAnalysisService.save_source_file` (`brand_analysis_service.py:3105`). Year must be 2024/2025; size capped at `settings.BRAND_ANALYSIS_MAX_UPLOAD_MB` (25). Parses immediately via `parse_brand_export`, deletes any prior file for that year (unique `(job_id, year)`), stores raw bytes in `file_data` + column validation report.
- `POST /brand-analysis/{job_id}/start` (`brand_analysis.py:204`) — guards against a `running_statuses` set (returns 409), validates mode prerequisites (manual needs both years; internal needs `account_id`), resets job to `pending`/progress 0, then:
  - `process_brand_analysis.delay(...)` (Celery). **On Celery failure → in-process `threading.Thread` fallback** running `process_brand_analysis_job` directly (`brand_analysis.py:269-274`). This is the same in-process-fallback pattern the scheduled reports use.

### 1.2 Background processor — `process_brand_analysis_job(job_id)` (`brand_analysis_service.py:3219`)
The single entry point for both Celery and thread execution. It builds its **own** async engine/session (`create_async_engine(_db_url, pool_size=2, max_overflow=1)`, `:3229`) because it runs outside the request loop, then runs `_process()` in a fresh event loop (`:3588-3596`). Sequence:

1. **Status helper** `_set_status(status, step, pct)` (`:3242`) issues a raw `UPDATE brand_analysis_jobs SET status,progress_step,progress_pct,updated_at` on a fresh short-lived session. `pct` defaults to `STATUS_PROGRESS.get(status, 0)` — **this is where the magic numbers like `'generating_pptx': 90` resolve** (the map lives at `:47-70`).
2. **Adapter resolution** `_resolve_adapter(job, source_by_year)` (`:3263`): canonicalizes mode; if `manual` OR both manual files present → `ManualUploadDataSource`; if `internal` + `account_id` → `AmazonAccountDataSource` (db set later at `:3434-3435`); legacy/unknown → manual.
3. **Internal-only preamble** (`:3325-3431`), only when `_canonical_mode == "internal"`:
   - `capability_checking` (8): `detect_brand_analysis_capabilities(db, account, force_refresh=True)` → stored on `job.capability_matrix`.
   - `preflight_checking` (14): `inspect_internal_sales_data_coverage(db, account)` → `job.data_coverage`.
   - **Auto-sync loop** (`:3351`): if coverage `needs_sync` AND `sync_attempt_count < settings.BRAND_ANALYSIS_MAX_SYNC_ATTEMPTS` (default **1**) AND idempotency key differs → bumps attempt count, sets `internal_sync_requested` (20) → `syncing_internal_data` (28), then calls `DataExtractionService.sync_vendor_sales_data` / `sync_sales_data` per recoverable window. Re-inspects coverage, records `sync_result`, sets `internal_sync_completed` (34) or `internal_sync_failed` (34). On hard failure: rollback, re-fetch job, set `internal_sync_failed`, `next_retry_at = now + 1h`.
4. **Source fetch** (`:3438-3466`): `collecting_source_data` (25) → `adapter.fetch_year(2024)` → (40) → `fetch_year(2025)`. **`InsufficientDataError` is caught here** → job → `waiting_for_user_action` (50) with a structured `error_code` (`missing_2024_data`/`missing_2025_data`/`internal_data_missing`/`insufficient_yearly_data`) and **returns early** (no exception bubbles).
5. Persist column-validation reports back onto manual source rows (`:3469-3472`).
6. `enriching_catalog` (55) status only when source is not manual (`:3474-3475`).
7. **Metrics** `generating_metrics` (70): `calculate_brand_metrics(parsed_2024, parsed_2025, brand_name=...)` (`:3484`). Then bolts on `data_completeness`, `capability_matrix`, `data_coverage`, and (internal only) `data_readiness` + `history_incomplete_years`. Builds `limitations` (`build_limitation_summary`), `metric_source_registry`, and `provenance` (`enrich_metric_provenance(build_metric_provenance(...))`). **Hard gate** `validate_metric_provenance_for_deck` (`:3517`) raises `BrandAnalysisDataError` if any deck-numeric family lacks provenance.
8. **Narrative** `generating_narrative` (82): `BrandAnalysisNarrativeService().generate(metrics, language, provenance=, limitations=)` (`:3520`).
9. **PPTX** `generating_pptx` (90): `build_brand_analysis_pptx(metrics, narrative, language)` (`:3528`) → **re-opens the bytes** via `validate_pptx_bytes` (`:3534`); structural failure is converted to a job failure.
10. **Persist + storage** (`:3542-3572`): filename `brand_analysis_{safe_brand}_{date}.pptx`; `storage.save_artifact(...)`; writes `metrics/metric_provenance/capability_matrix/data_coverage/limitations/narrative/artifact_data/artifact_filename/artifact_content_type/storage_ref`. Terminal status = `completed_with_limitations` if `limitations.has_limitations OR completion_code` else `completed`; `progress_pct=100`; `error_code` set to the `completion_code` (e.g. `catalog_enrichment_partial`, `analysis_completed_with_missing_optional_fields`).
11. **Failure path** (`:3573-3586`): rollback, open a **separate** session, set `status="failed"`, `error_message=str(exc)[:1000]`, `progress_pct=100`, `completed_at`.

### 1.3 Download
- `GET /brand-analysis/{job_id}/download` (`brand_analysis.py:280`): requires `completed`/`completed_with_limitations`; loads bytes via `BrandAnalysisStorage().load(ref, fallback=job.artifact_data)`; streams with the OOXML media type.

---

## 2. Status / progress model (where `'generating_pptx': 90` lives)

- Canonical map: `STATUS_PROGRESS` (`brand_analysis_service.py:47-70`). Key values:
  `pending 0, capability_checking 8, preflight_checking 14, internal_sync_requested 20, syncing_internal_data 28, internal_sync_completed/failed 34, collecting_source_data 30, enriching_catalog 55, generating_metrics 70, generating_narrative 82, analyzing 70, generating_pptx 90, completed/completed_with_limitations 100, failed 100, waiting_for_user_action 50`. Plus legacy `configuring_market/waiting_for_ready/exporting_2025/exporting_2024`.
- **Inconsistency / tech-debt:** `_set_status` calls pass explicit `pct` that sometimes *disagree* with the map — e.g. `collecting_source_data` is mapped to **30** but called with **25** then **40** (`:3438`,`:3441`); the map's value is effectively dead for those calls. Two sources of truth for the same progress.
- Status literal duplicated in **3 places**: `STATUS_PROGRESS` keys, `schemas/brand_analysis.py:15-38` (`BrandAnalysisStatus`), and the `running_statuses` set in `brand_analysis.py:216-234`. Any new status must be added to all three or the start-guard / serialization drifts.
- No streaming/event progress — UI must **poll** `GET /brand-analysis/{job_id}`.

---

## 3. Data model (tables, columns, JSONB blobs)

### `brand_analysis_jobs` (`models/brand_analysis.py:15`; migrations 018 + 021)
- Identity/scope: `id`, `organization_id` (CASCADE), `created_by_id` (SET NULL), `account_id` (SET NULL).
- Request: `brand_name`, `language`, `mode` (default `internal`), `market_type` (default `brand`), `market_query`, `asin_list` (JSONB).
- Lifecycle: `status` (indexed), `progress_step`, `progress_pct`, `error_message`, `error_code`.
- Sync state (021): `sync_attempt_count`, `last_sync_error`, `next_retry_at`, `sync_idempotency_key`.
- **JSONB blobs (the heavy payloads):** `metrics`, `narrative`, `metric_provenance`, `capability_matrix`, `data_coverage`, `limitations`, `storage_ref`.
- Artifact: `artifact_filename`, `artifact_content_type`, `artifact_data` (`LargeBinary` — **PPTX bytes stored inline in the DB row by default**).
- Relationship `source_files` cascade `all, delete-orphan`.

### `brand_analysis_source_files` (`:152`)
- Unique `(job_id, year)`. Stores raw upload bytes in `file_data` (`LargeBinary`), `row_count`, `columns` (JSONB), `column_validation` (JSONB), `storage_ref` (JSONB, present on model but the `save_source` S3 path returns `db` by default).

### `brand_analysis_capabilities` (`:79`; migration 021)
- Unique `(organization_id, account_id, marketplace_id)`. 11 boolean capability columns (see §4). `missing_roles`/`last_error_by_capability`/`raw_diagnostics` JSONB. `checked_at` drives the TTL cache.

### `asin_offer_snapshots` (`:122`; migration 021)
- Per-ASIN Buy Box/offer snapshot written during internal enrichment (`AmazonAccountDataSource._save_offer_snapshot`). Columns: `seller_count`, `offer_count`, `buy_box_owner_name`, `buy_box_seller_id`, `buy_box_price` (Numeric), `fulfillment_channel`, `is_fba`, `source`, `raw_payload` (JSONB). **No unique constraint / no read path** — written but the only consumer (`buy_box_owner_history`) reports it as `unavailable` (see §6 tech-debt).

> Brand Pulse has **no tables** — fully derived at request time.

---

## 4. Capability probe — coverage vs the 10 target sources (`brand_analysis_capabilities.py`)

`CAPABILITY_KEYS` (`:23`) = 11 keys (sales_and_traffic + the 10 commonly cited "target sources"):
`sales_and_traffic_available, data_kiosk_available, brand_analytics_available, brand_registry_available_or_inferred, product_pricing_available, product_fees_available, aplus_available, finance_reports_available, settlement_reports_available, catalog_items_available, listings_available`.

`detect_brand_analysis_capabilities` (`:124`):
- **TTL cache** keyed on `(org, account, marketplace)` via `BRAND_ANALYSIS_CAPABILITY_CACHE_TTL_HOURS` (24); bypassed by `force_refresh` (the processor always forces).
- **Warehouse-first:** `_has_sales_data` → `sales_and_traffic_available=True` even when no remote probe is possible (`:189-191`).
- Builds the client via `client_factory` or `DataExtractionService(db)._create_sp_api_client(account, organization)` (`:194-199`). Credential failure short-circuits and records `sp_api_credentials` in `missing_roles`.
- `probe(capability, op, role_name=)` (`:208`) runs a small read; success flips the bool + stores a summarized payload; failure records `last_error_by_capability`, and **only `_is_permission_error` failures** (`:70`, looks for 401/403/forbidden/not authorized/restricted markers) are appended to `missing_roles`.
- Probe map → SP-API endpoints:
  - sales_and_traffic / brand_analytics / settlement: `reports_get(report_type)` → `client._reports_api().get_reports(...)` (`:220-253`).
  - finance: `client._finances_api().list_financial_event_groups` (`:255`).
  - data_kiosk: `client._data_kiosk_api().get_queries` (`:260`).
  - catalog_items: `client._catalog_api().get_catalog_item(...)` (needs `sample_asin`) (`:266`).
  - product_pricing: `client._products_api().get_item_offers(...)` — **seller-only**, skipped for vendor (`:275-282`).
  - product_fees: `client._product_fees_api().get_product_fees_estimate_for_asin(...)` — needs ASIN+price, seller-only (`:287-302`).
  - aplus: `client._aplus_content_api().search_content_documents(...)` (`:304-311`); `brand_registry_available_or_inferred` is **inferred** = aplus result (`:312`).
  - listings: `client._listings_api().get_listings_item(...)` — needs `seller_id`+`sku` (`:316-326`).
- `persist_brand_analysis_capabilities` (`:345`) does a Postgres `INSERT ... ON CONFLICT DO UPDATE` on the unique constraint.

**Gap vs analysis use:** the probe records availability but the pipeline barely *gates* on it — e.g. `data_kiosk_available`/`brand_analytics_available`/`finance_reports_available`/`settlement_reports_available`/`listings_available` are probed and persisted, but the actual metric calc never reads Data Kiosk, Brand Analytics search shares (always `None`, `service.py:1804-1807`), settlement, or listings. Only catalog/pricing/fees/aplus are actually consumed (via the enrichment path, not the capability flags). `missing_roles` only flows into the limitation summary (`service.py:1042-1044`).

---

## 5. SP-API client builders (where `_data_kiosk_api`/`_finances_api`/… live)

All on `SPAPIClient` in `app/core/amazon/sp_api_client.py`:
- `_reports_api` `:211`, `_inventories_api` `:216`, `_catalog_api(version="2022-04-01")` `:221`, `_products_api` `:226`, `_orders_api` `:231`, `_vendor_orders_api` `:236`, `_listings_api` `:241`, `_product_fees_api` `:246`, `_aplus_content_api` `:251`, `_finances_api` `:256`, `_data_kiosk_api` `:261`. Each lazily constructs the `python-amazon-sp-api` client with `self._api_kwargs` and raises `AmazonAPIError("…not available…")` if the dependency is missing.
- `is_vendor` property `:207`.
- Higher-level helpers consumed by Brand Analysis: `estimate_fba_fee_for_asin` `:1286`, `get_aplus_content_for_asin` `:1382`, `search_catalog_by_keyword` `:1533`.
- Client is constructed inside the adapter at `brand_analysis_sources.py:545` (`_build_sp_api_client`) using `resolve_credentials` + `resolve_marketplace`, NOT via DataExtractionService. The capability probe uses `DataExtractionService(db)._create_sp_api_client`. **Two different client-build code paths** — minor duplication.

---

## 6. Internal data source — `AmazonAccountDataSource` (`brand_analysis_sources.py:62`)

`fetch_year(year)` (`:102`):
1. `_resolve_scope_asins` (`:322`) — cached for the adapter lifetime so 2024/2025 share the universe. ASIN-list mode is deterministic; brand mode unions `_discover_asins_from_local_products` (`Product` table, brand/title fuzzy match via `brand_matches`) + `_discover_asins_via_market_research` (`client.search_catalog_by_keyword(..., max_results=80)`). Discovery seeds `_catalog_cache` with `_discovery_snapshot` rows.
2. Aggregates `sales_data` per ASIN: `units = SUM(display_units_expr()) + SUM(units_ordered_b2b)`, `revenue = SUM(display_revenue_expr()) + SUM(ordered_product_sales_b2b)`, excluding `DAILY_TOTAL_ASIN` (`:108-131`). Scoped via `WHERE asin IN scope` when scope present.
3. `InsufficientDataError` raised on several no-data branches (`:148`, `:155`, `:170`, `:254`) — these are what trigger `waiting_for_user_action`.
4. Per-ASIN enrichment `_get_catalog` (`:495`) → `_fetch_catalog_from_local_products` then `_fetch_catalog_via_market_research` (`:574`) which calls Market Research's `_fetch_product_data(client, asin)` (synchronous, run inline — **N sequential SP-API calls, no thread pool**, noted as future work at `:581-583`), plus `estimate_fba_fee_for_asin` and `get_aplus_content_for_asin`. Each enriched ASIN writes an `AsinOfferSnapshot` (`:615`).
5. **Status rule:** revenue>0 ⇒ `active`, else `inactive` — zero-revenue discovered ASINs are kept as inactive rows (legacy prompt rule, `:197-200`).
6. `enrichment_partial` (`:315`) True when ≥20% of attempted catalog lookups failed → drives `catalog_enrichment_partial` error code.
7. `describe_readiness` (`:663`) → `metrics["data_readiness"]` (discovered counts, enrichment attempts/failures, per-year diagnostics, discovery errors).

**Tech-debt flag:** `AsinOfferSnapshot` rows are written every run but never read; `seller_buy_box_summary.buy_box_owner_history_*` and `buy_box_percentage` are hardcoded `unavailable`/`None` (`service.py:1748-1759`). The snapshot table is write-only dead weight today.

---

## 7. Brand Pulse — computation & exact Performance-Analytics overlap

`BrandPulseService.build_pulse` (`brand_pulse_service.py:36`):
- Window: trailing `window_days` (default 30) ending `end_date`; previous window is the immediately preceding equal span.
- **Everything is delegated to `AnalyticsService`** (constructed in `__init__`, `:33`):
  - `overview = analytics.compute_dashboard_kpis(account_ids, start, end)` (`:49`) — the **same** call the dashboard KPI endpoint uses (`analytics_service.py:24`, totals from `DAILY_TOTAL_ASIN` sentinel + active-ASIN distinct count).
  - `granularity = analytics._resolve_granularity(...)` (`:57`) → monthly-vendor "awaiting_data" gate (`:58-61`).
  - `current_map/previous_map = analytics.asin_sales_breakdown(...)` (`:63-68`, `analytics_service.py:250`) — snapshot-aware per-ASIN map (vendor sum vs seller latest-snapshot). **This is the exact same primitive the Performance/Analytics drilldown uses.**
  - titles via `analytics._asin_titles` (`:104`, `analytics_service.py:679`).
  - ads via `analytics.compute_advertising_metrics(...)` (`:165`, `analytics_service.py:300`) — same impressions/clicks/cost/`attributed_sales_7d`/ACOS/ROAS.
- Pulse-local logic (the only non-AnalyticsService code):
  - `_top_asins` (`:106`): sort current_map desc, attach `change_percent` via `_change_percent` (`:187`).
  - `_declining_asins` (`:125`): previous>0 filter, `change <= DECLINE_THRESHOLD_PCT` (-5.0), `trend_class` split at `DECLINE_FAST_THRESHOLD_PCT` (-20.0). Thresholds are **copied** from AnalyticsService (comment `:24-26`) — duplicated constants, drift risk.
  - `_ads_block` (`:157`): availability gate (`impressions|clicks|cost`), computes `tacos = spend/total_revenue*100`.
  - `recommendations = build_pulse_recommendations(payload, language)` (`:95`, `strategic_recommendations_service.py:131`).
- **No persistence, no job, no caching** — recomputed every request; the endpoint (`brand_pulse.py:17`) resolves/authorizes account IDs and calls the service synchronously.

**Overlap summary (for the reposition decision):** Brand Pulse is ~90% a thin re-presentation of Performance Analytics primitives (dashboard KPIs, ASIN breakdown deltas, top/declining ASINs, ads ACOS/TACOS). Its only differentiated outputs are the period framing, the declining-ASIN trend classes (duplicated thresholds), and the recommendation overlay. This is the concrete overlap the Brand Analysis reposition direction calls out.

---

## 8. Metric calc & narrative internals (the parts a reposition will touch)

- `parse_brand_export` (`service.py:569`) — flexible column-alias mapping (`COLUMN_ALIASES` `:198`, `NUMERIC_COLUMNS` `:411`), locale-aware `_parse_number` (`:471`), groups by ASIN. Requires `asin`+`revenue` only.
- `calculate_brand_metrics` (`service.py:1300`) — ~530 lines, fully deterministic. Computes revenue YoY, active/inactive, weighted rating, price, top-5/10 shares, subcategory YoY, seller/Buy-Box summary, content health, review/rating weaknesses, fulfillment, FBA fee summary (actual→estimate→unavailable), market size/share (only when a broad external competitor export is present — `broad_market_available` `:1646`), growth projection scenarios (fixed ±% multipliers `:1686`), and a `rules.can_mention_vine` gate (`:1811`, revenue ≥ €100k). Output is `_json_safe`-d (`:1833`).
- Provenance system (auditability spine): `build_metric_provenance` (`:680`), `build_metric_source_registry` (`:813`, assigns `quality: exact|proxy|estimated|unavailable` + preferred/fallback sources), `enrich_metric_provenance` (`:949`), `validate_metric_provenance_for_deck` (`:998`, hard gate over `DECK_NUMERIC_PROVENANCE_KEYS` `:963`). `build_limitation_summary` (`:1015`) aggregates market/fee/aplus/seller/coverage/missing-role limitations.
- `BrandAnalysisNarrativeService` (`service.py:1984`) — **Anthropic only**, model **`claude-sonnet-4-6`**, `max_tokens=2200` (`:2050-2054`). Prompt injects full metrics+provenance+limitations JSON, instructs "do not calculate/infer/invent numbers", enforces the Vine rule, requires a fixed JSON shape validated by `_validate` (`:2070`). Falls back to `build_fallback_narrative` (`:1861`, deterministic) when no API key or on any exception. `_remove_vine_mentions` post-filters when Vine is disallowed. `build_priority_actions` (`:1941`) emits brand-specific, metric-grounded actions (EN/IT).

---

## 9. PPTX builder — the hardest-to-evolve seam (`service.py:2413`)

- `BrandAnalysisPptxBuilder` builds a 10×5.625in deck with **python-pptx primitives only** (no template file). `PPTX_TEMPLATE_VERSION = 'brand-analysis-pptx-v2'` (`:30`).
- All copy is in a **massive hardcoded `PPTX_STATIC_STRINGS` dict** (`service.py:2109-2410`, ~300 lines, EN+IT side-by-side). `_t(key)` (`:2427`) resolves with EN fallback.
- `build()` (`:2445`) wires fixed primitives (`RGBColor/PP_ALIGN/Inches/Pt`) and a **hardcoded ordered list of `_slide_*` methods** (`:2462-2478`), each gated by a boolean (`_has_channel_data`, `_has_market_share`). `_slide_catalog_audit` and `_slide_approach` exist (`:2637`, `:2820`) but are **not in the build list** — dead/legacy slide methods.
- ~18 `_slide_*` methods, each laying out hardcoded `Inches(...)` coordinates inline: `_slide_cover/_as_is/_revenue_yoy/_catalog_health/_active_inactive/_top_performers/_content_audit/_review_image_weaknesses/_subcategory_performance/_operational_gap/_channel_gap/_concentration_risk/_market_share/_projection/_roadmap/_conclusions` (+ the two unused). Helpers: `_kpi/_body_box/_table/_rect/_text/_cell_font/_title/_add_header/_footer/_badge` (`:2917-3030`). Quality badges come from `metric_source_registry[...].quality` via `_badge` (`:2431`).
- `validate_pptx_bytes` (`:3187`) re-opens and asserts **12–16 slides** (range because N/A slides are skipped).
- **Seam assessment:** the slide order, slide gating, layout coordinates, and bilingual copy are all hardcoded in this one class. Any "new deck layout / new slides / theme" reposition work means editing dozens of inline coordinate literals and the 300-line string table. This is the #1 refactor target if the deck output is being reworked — candidates: extract a slide-spec/registry, externalize strings to i18n, or move to a real `.pptx` template (the `document-skills:pptx` approach) instead of primitive drawing.

---

## 10. Storage (`brand_analysis_storage.py`)

- Backend chosen by `settings.BRAND_ANALYSIS_STORAGE_BACKEND` (default **`db`**). `s3` lazily builds a boto3 client and **silently falls back to `db`** if boto3/creds missing (`:71-73`).
- `db` backend: save is a no-op (bytes live in `LargeBinary` columns); `load` returns the `fallback` (the model's bytes). `s3` keys: `brand-analysis/{org}/{job}/sources|artifacts/...`. `load` returns S3 bytes or falls back to DB bytes on error.
- Default deployment therefore stores **full PPTX + raw upload bytes inside Postgres rows** — fine for small decks, but a scaling/bloat concern and couples job deletion to artifact deletion (handled by CASCADE).

---

## 11. Async-job / cancel / cleanup affordances (and their absence)

- **Job tracking:** status + progress on the row, updated via raw SQL `_set_status`; sync retry state (`sync_attempt_count`/`next_retry_at`/`sync_idempotency_key`) exists but **`next_retry_at` is never polled by any scheduler** — there is no beat task that re-drives stalled/`internal_sync_failed`/`pending` Brand Analysis jobs (unlike scheduled reports, which have `recover_stuck_scheduled_report_runs`, `scheduled_reports.py:96`). A crash mid-run leaves a job stuck in a non-terminal status with no recovery.
- **No cancel endpoint.** `DELETE /brand-analysis/{job_id}` (`brand_analysis.py:329`) deletes the row (+ cascade), but cannot stop an in-flight Celery task / thread; the running task may resurrect/overwrite a deleted row's state (no `job` existence re-check before the final commit in `_process`).
- **Celery config:** `process_brand_analysis` `max_retries=1`, `countdown=60` (`workers/tasks/brand_analysis.py:11-20`). The in-process-thread fallback in `start` (`brand_analysis.py:269`) is **fire-and-forget, un-tracked** — no way to know it died.
- **Cleanup:** none for old completed jobs / artifacts / `asin_offer_snapshots`. No TTL/GC task.

---

## 12. Reusable reporting & async-job infra (skim — what already exists to reuse)

- **`scheduled_report_service.py`** (617 lines) is the cleanest reusable async-job pattern:
  - `run_scheduled_report_scan` (`:369`) in-process scheduler entry (APScheduler-friendly: private engine + own loop).
  - `process_scheduled_report_run_job(run_id)` (`:417`) — the canonical "build artifact in a private engine/loop, set generation_status, then enqueue delivery, fall back to in-process delivery" pattern. **This is the template Brand Analysis's processor loosely follows but didn't formalize.**
  - `deliver_scheduled_report_run_job` (email delivery), `RUN_TERMINAL_STATUS`, `utcnow` helpers.
- **`workers/tasks/scheduled_reports.py`** (137 lines): `scan_scheduled_reports_due` (beat), `process_scheduled_report_run_task`, `deliver_scheduled_report_run_task`, and crucially `recover_stuck_scheduled_report_runs` (`:96`) — the **stuck-run recovery** Brand Analysis lacks. `run_async(coro_factory)` (`:17`) resets the worker engine to avoid cross-loop asyncpg futures — a cleaner version of what `process_brand_analysis_job` does ad hoc.
- **`export_service.py`** (`ExportService` `:372`): `generate_excel_report` (`:378`), `generate_powerpoint_report` (`:450`, a trivial title-only deck — **not** the Brand Analysis builder), `generate_csv_package` (`:477`, ZIP), `generate_bundle_package` (`:509`), `generate_excel_bundle` (`:544`). Useful for non-PPTX export formats if the reposition wants Excel/CSV brand outputs.
- **`scheduled_report_pdf_service.py`** (162) + **`strategic_recommendations_export.py`** (282) — PDF/recommendation export builders; a reposition that wants a PDF brand report could lean on these instead of bespoke code.
- **`models/scheduled_report.py`** (122): `ScheduledReport` + `ScheduledReportRun` (run has `generation_status`/`delivery_status`/`progress_step`/`artifact_*`/`error_message`/`triggered_at`/`completed_at`). A richer run model than Brand Analysis's single-row status — a good shape to copy if Brand Analysis needs scheduled/recurring generation.

---

## 13. Tech-debt & refactor seams (prioritized)

1. **3596-line monolith** mixes 7 concerns (parse, metrics, provenance, narrative/LLM, PPTX, CRUD service, background processor). Natural split: `brand_analysis_parse.py`, `brand_analysis_metrics.py`, `brand_analysis_provenance.py`, `brand_analysis_narrative.py`, `brand_analysis_pptx/` (builder + strings + slide specs), `brand_analysis_processor.py`. The processor (`process_brand_analysis_job`) and `BrandAnalysisService` are the easiest to lift out first (clear boundaries).
2. **PPTX builder (§9):** hardcoded slide order/coords/strings; two dead slide methods (`_slide_catalog_audit`, `_slide_approach`); 300-line inline string table. Highest-effort surface for any deck redesign.
3. **Progress model double source of truth (§2):** `STATUS_PROGRESS` map vs explicit `pct` args disagree; status literal triplicated across three files.
4. **Write-only `asin_offer_snapshots` (§6):** persisted but never read; Buy-Box history features are hardcoded unavailable. Either wire the read path or stop writing.
5. **Capability probe vs usage mismatch (§4):** 5+ capabilities probed/persisted but never consumed by metric calc (Data Kiosk, Brand Analytics search shares, settlement, finance, listings). `search_*_share` always `None`.
6. **No stuck-job recovery / cancel / cleanup (§11):** unlike scheduled reports. `next_retry_at` is dead. In-process thread fallback is untracked. No GC of DB-stored artifacts.
7. **Sequential inline SP-API enrichment (§6):** N ASINs × (catalog + fees + aplus) sequential calls per analysis, no concurrency/bounded pool. A large brand universe is slow and serial.
8. **Duplicated client-build paths (§5)** and **duplicated decline thresholds (§7)** between Pulse and AnalyticsService.
9. **Two-engine / fresh-loop boilerplate** in `process_brand_analysis_job` reimplements what `run_async` in scheduled_reports already encapsulates — consolidate.
10. **Frontend leftover Portuguese** in `BrandAnalysis.tsx` (noted in task brief; not a backend file but surfaced by the same feature).

---

## 14. Config knobs (`app/config.py:85-90`)
`BRAND_ANALYSIS_MAX_UPLOAD_MB=25`, `BRAND_ANALYSIS_STORAGE_BACKEND="db"`, `BRAND_ANALYSIS_SALES_TRAFFIC_RECOVERY_DAYS=730`, `BRAND_ANALYSIS_PARTIAL_USABLE_MONTHS=3`, `BRAND_ANALYSIS_MAX_SYNC_ATTEMPTS=1`, `BRAND_ANALYSIS_CAPABILITY_CACHE_TTL_HOURS=24`. (No Brand Pulse settings — it has none.)
