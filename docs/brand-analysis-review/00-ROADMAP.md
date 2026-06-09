# Brand Analysis & Brand Pulse — Master Implementation Roadmap

**Owner:** Technical Lead (consolidation of 6 specialist reviews)
**Date:** 2026-06-09 · branch `master` @ `156536c`
**Source reviews:** [01-product-manager](01-product-manager.md) · [02-amazon-data](02-amazon-data.md) · [03-backend-architect](03-backend-architect.md) · [04-frontend-ux](04-frontend-ux.md) · [05-pptx-reporting](05-pptx-reporting.md) · [06-qa](06-qa.md)

This is the authoritative execution document. Where specialists disagreed, the conflict and my decision are called out explicitly in **§0.2**. All `file:line` anchors are inherited from the specialist reports and spot-verified.

---

## 1. Executive Summary (for leadership)

Inthezon ships four overlapping "brand + account + ASINs → insight" surfaces — Performance, Market Research, Brand Analysis, Brand Pulse — and a customer cannot tell which to open on a Monday morning. The cure is not four redesigns; it is **one coherent intelligence ladder by cadence**: Performance (live/daily), Weekly Brand Intelligence (weekly AI digest), Market Research (on-demand competitive), and the Brand Strategy Deck (quarterly/annual PPTX). Two products carry the rework: **Brand Pulse must be rebuilt as a product** (today its 190-line service is a re-skin of Performance Analytics with no reason to exist), and **Brand Analysis must keep its strong data pipeline while we rebuild its input flow, its PPTX output, and its AI-looking chrome**.

The engineering reality is more favorable than the brief implied. The backend already has the canonical async-job, scheduler, stuck-recovery, and beat-scanner machinery (`scheduled_reports`) that the weekly Brand Intelligence product maps onto almost 1:1; the SP-API report poller (`request_and_download_report`) already exists, so the single highest-value data gap — **Brand Analytics search/market share, currently hardcoded `None`** — is wiring (~3-4 days), not a build; and the frontend already has a **complete, mounted NotificationBell** wired to the alerts API, so in-app completion notifications collapse from a feared XL to an S. Two of the brief's premises are stale and verified-done: there is **zero Portuguese text** anywhere on master, and the notification UI already exists.

Three problems are non-negotiable to fix first because they are correctness bugs, not polish: the Brand Analysis pipeline has **no way to cancel a job and no stuck-job recovery** (a crashed run wedges forever); `delete_job` has **no running-status guard** and the processor's success path can **resurrect a deleted row**; and the **`__DAILY_TOTAL__` double-count** gotcha is untested in both modules. The PPTX rebuild's premise (variable, dynamic slide count) is structurally blocked by three hard-coded slide-count assertions — including a production hard-gate (`validate_pptx_bytes` 12-16) — that must be replaced with a section-contract test before the redesign starts.

The total program is roughly **14-18 calendar weeks** with a 4-person squad (1 BE-platform, 1 BE-data, 1 FE, 1 QA) working in parallel tracks, fronted by a **2-3 week Quick-Wins + Foundation sprint** that de-risks everything downstream and ships visible customer value (delete/cancel, de-AI'd UI, terminology fix, notifications) immediately. We sequence the monolith decomposition and job-lifecycle hardening as the foundation, then run the PPTX rebuild, Brand Intelligence rebuild, and data-coverage integration as parallel tracks on top.

---

## 0.2 Conflicts between specialists — resolved decisively

These are the points where the six reviews disagreed or where the brief was wrong. Each has one ruling that the team executes.

| # | Conflict | Positions | **Ruling (Tech Lead)** |
|---|---|---|---|
| **C-1** | **Notification storage** | PM: extend `Alert` table (nullable `rule_id`, new `event_kind`). Backend/PPTX/QA: build a **new `notifications` table** to avoid contorting the rule-scoped Alert model. FE: the `NotificationBell` already exists and is wired to `alertsApi` — reusing alerts = zero bell rebuild. | **Extend `Alert` — do NOT build a parallel `notifications` table.** Verified: `Alert` already has `event_kind` (String 64, `alert.py:71`), `dedup_key` (`:72`), `details` JSONB, `is_read`, nullable `account_id`/`asin`. The only blockers are `rule_id NOT NULL` (`:64`) and the unread partial index being rule-scoped (`:55-60`). One migration makes `rule_id` nullable and adds an org-scoped unread index. The mounted `NotificationBell` (257 lines, polls `alertsApi.getUnreadCount`) then renders completion events with a **one-line `alertTypeLabel` addition** and zero new inbox. QA's cross-tenant concern is satisfied by the existing org scoping on the alerts query, gated by a release test. This overturns the "new table" recommendation from 3 of 6 reviews on the strength of the FE finding they did not have. |
| **C-2** | **Migration numbers** | PM/Backend/PPTX/QA all wrote migrations `022`, `023`, `024`. | **All of those numbers are already taken.** Verified: head is `028_vendor_shipped_metrics`; `022_catalog_change_log`, `023_partition_ts_tables`, `024_sales_data_traffic_cols` exist. The specialists worked from a stale assumption that head was 021. **New sequence starts at `029`** (see §7). |
| **C-3** | **Brand Pulse deliverable format** | PPTX: in-app report **+ one-click PDF export** on `scheduled_report_pdf_service` rails. PM/Backend/FE: in-app **report reader**, persisted weekly, no PDF mentioned. | **Ship in-app reader first (v1); PDF export is a fast-follow (v1.1), not v1 scope.** The weekly product's primary value is the on-screen Monday read + the notification. PDF is a forward/share convenience that reuses the existing reportlab palette cheaply — but it must not gate the v1 launch. Build the section JSON contract so the same content model renders to both HTML and (later) PDF. |
| **C-4** | **Data-coverage priority order** | Amazon-data: Brand Analytics → **Ads search-term** → offer-snapshot read → Data Kiosk → Finance. Backend: Brand Analytics → **Finance/Settlement** → Data Kiosk → Listings. | **Adopt the Amazon-data ordering.** Both agree Brand Analytics is #1. The tiebreaker on #2: the **Ads search-term report is S-effort (one config entry, no new poller, no Brand Registry gate)** and directly unlocks competitive intelligence for the weekly product, whereas Finance is L-effort and only matters if profitability is an explicit product goal (it isn't yet). Order: **Brand Analytics → Ads search-term + purchased-product → AsinOfferSnapshot read path → parallelize enrichment → Data Kiosk (seller) → Finance → vendor Data Kiosk → Listings/Settlement.** Finance/Settlement drop to P2. |
| **C-5** | **Settlement vs Finance** | Amazon-data and Backend both flag overlap. | **Pick Finance, skip Settlement.** Settlement cannot be requested ad hoc (Amazon pushes bi-weekly), its cadence doesn't fit the weekly product, and it's redundant with Finance which gives ASIN granularity. Settlement is **dropped from the roadmap** unless a settled-cash reconciliation feature is later requested. |
| **C-6** | **"Remove Portuguese text"** | PM, FE, and QA independently verified **zero Portuguese on master** (two grep passes each). | **Mark DONE-by-verification. Do not hunt.** Reallocate the budget to the one real i18n bug: the hardcoded `"Market Tracker 360"` literal at `MarketTracker.tsx:177`. |
| **C-7** | **AsinOfferSnapshot — keep or delete** | Backend: delete unless Pricing integration lands. Amazon-data: keep, add unique constraint + read path (Pulse competitive deltas). | **Keep and wire it.** Because the Amazon-data plan (C-4) gives the snapshot a concrete consumer — week-over-week new-seller / Buy-Box-loss / price-move signals in the weekly product — the write is no longer dead weight. Add the unique constraint + read path. (Had C-4 deferred Pricing, Backend's delete would win.) |
| **C-8** | **PPTX rebuild strategy** | PPTX/PM/FE/QA: rebuild. Backend: refactor the *seam* (theme/strings/registry) so the PPTX agent rebuilds on top. | **No conflict — these compose.** Backend extracts the package seam (`deck/` with a SlideSpec/block registry) as part of the monolith decomposition; the PPTX agent rebuilds the rendering layer (charts, blocks, theme) inside that seam. Sequenced: decomposition first, then the block/chart rebuild. |
| **C-9** | **Cancellation mechanism** | Backend: `revoke(terminate=True)`. PM/QA: cooperative `cancel_requested` flag + checkpoint. Backend risk note: revoke may not interrupt an asyncio coroutine. | **Defence in depth — cooperative flag is the primary mechanism, revoke is best-effort.** A `cancel_requested` column checked at every phase boundary in `_process()`, PLUS `celery_app.control.revoke()`, PLUS a heartbeat-driven recovery beat task that force-finalizes stale jobs. Never rely on revoke alone; never hard-kill mid-write. |
| **C-10** | **Thread-fallback when Celery enqueue fails** | Backend: replace untracked daemon thread with a tracked `pending` row that recovery re-enqueues. QA: it's un-revocable, a liability. | **Replace the untracked daemon thread with a tracked pending row.** The recovery beat task (which we're building anyway) re-enqueues it. No fire-and-forget heavy work in the web process. |

---

## 2. Prioritized Roadmap (P0 → P3) with dependencies & rebuild-vs-improve verdicts

> **Effort key:** XS ≈ <0.5d · S ≈ 0.5-1d · M ≈ 2-4d · L ≈ 1-2w · XL ≈ 3w+. Priorities are program priorities across all six lenses.

### P0 — Foundation & correctness (everything else depends on these)

| ID | Item | Verdict | Effort | Depends on | Owner |
|---|---|---|---|---|---|
| P0-1 | **Test-harness foundation** — `conftest.py`, transactional DB fixture, `ASGITransport` client, shared factories; `asyncio_mode=auto`. Retire `asyncio.run`-per-test. | Rebuild | L | — | QA |
| P0-2 | **Section-manifest PPTX contract** — builder emits `{section_id, present, reason}`; replace the three slide-count assertions (`== 15` ×2, `validate_pptx_bytes` 12-16 gate) with per-section integrity + no-empty-placeholder assertions. **Land before any deck redesign.** | Rebuild | M | P0-1 | QA + PPTX |
| P0-3 | **Job lifecycle: cancel + recovery + heartbeat** — migration adds `celery_task_id`, `cancel_requested`, `started_at`, `heartbeat_at`; persist `AsyncResult.id`; `POST /{id}/cancel`; cooperative checkpoint in `_process()`; `recover_stuck_brand_analysis_jobs` beat task. (C-9, C-10) | Refactor+extend | M | P0-1 | BE-platform |
| P0-4 | **Harden delete (fix resurrection)** — running-status guard on `delete_job`; re-select-or-abort before the processor's final commit; `BrandAnalysisStorage.delete()` + artifact GC. | Refactor | S | P0-3 | BE-platform |
| P0-5 | **`__DAILY_TOTAL__` invariant tests** — BA exclusion + Pulse `sum(top) ≤ overview` + sentinel absence + threshold-equality assertion. | Improve/keep | S | P0-1 | QA |
| P0-6 | **Decompose the 3596-line monolith** into a `brand_analysis/` package (parse/metrics/provenance/narrative/pptx/crud/orchestration/state), behind a golden-deck snapshot test. Extract the `deck/` seam (theme/strings/SlideSpec registry). | Refactor | L | P0-1, P0-2 | BE-platform |
| P0-7 | **Brand Analytics fetch → metrics** — `get_brand_analytics_search_terms/market_basket` on the existing report poller; populate the already-coded `search_*_share` keys (`service.py:845-865`); flip market-share slide on. (C-4) | Build-new-on-existing | M | — | BE-data |

### P1 — Core rework (the headline customer-facing changes)

| ID | Item | Verdict | Effort | Depends on | Owner |
|---|---|---|---|---|---|
| P1-1 | **Brand Analysis input flow rebuild** — 3-noun model (Brand / Source / Coverage); kill `marketQuery` as a field; explicit Data-source segmented control; Scope → Advanced disclosure; 2-step layout. | Rebuild (form) | M | — | FE |
| P1-2 | **De-AI Brand Analysis chrome** — strip decorative gradients, remove Sparkles-as-AI, delete fake "Recommended actions" cards, collapse double progress into one `JobProgress`, KPI color by value not label. | Improve | M | — | FE |
| P1-3 | **Delete + Cancel in the UI** — wire the existing delete endpoint with an `AlertDialog`; Cancel button + `cancelling`/`cancelled` states (gated behind the P0-3 endpoint). Replace faux-grid history with a real `ReportTable`. | Rebuild (history) | S-M | P0-3, P0-4 | FE |
| P1-4 | **In-app completion notifications** — extend `Alert` (nullable `rule_id`, `event_kind=report_ready/report_failed`, org-scoped unread index); emit on BA + BI terminal states; add one `alertTypeLabel` entry; page toast via `usePolledJob.onComplete`. (C-1) | Improve/extend | M | P0-3 | BE-platform + FE |
| P1-5 | **PPTX dynamic block rebuild** — `deck/` package: block registry with per-block `is_available()` gate (no empty placeholders), matplotlib→PNG chart layer, `DeckTheme` tokens + embedded font, keyed-by-block narrative contract, exec-summary + methodology appendix. | Rebuild | XL | P0-2, P0-6 | PPTX |
| P1-6 | **Brand Pulse → Weekly Brand Intelligence (backend)** — `BrandIntelligenceReport` + `BrandIntelligenceSchedule` models; aggregate→diff→LLM pipeline; beat scanner + stuck-recovery on the `scheduled_reports` pattern; new `/brand-intelligence` API. | Rebuild | XL | P0-6, P0-7 | BE-data + BE-platform |
| P1-7 | **Brand Intelligence reader (frontend)** — new `BrandIntelligence.tsx` report reader (week picker, exec summary, sectioned narrative, WoW deltas, subscribe toggle); built against a typed `WeeklyReport` fixture. | Rebuild | XL | (fixture contract) | FE |
| P1-8 | **Ads search-term + purchased-product reports** — two `AdvertisingReportConfig` entries (no new poller); feed Pulse competitor signals. (C-4) | Extend | S | — | BE-data |
| P1-9 | **AsinOfferSnapshot read path + unique constraint** — Pulse offer deltas (new sellers / Buy-Box lost / price moved). (C-7) | Improve | S | P1-6 | BE-data |
| P1-10 | **Parallelize per-ASIN enrichment** — bounded `Semaphore(<=5)`/thread pool + `with_throttle_retry`; removes the ASIN ceiling. | Improve | S | — | BE-data |
| P1-11 | **Capability honesty: detected vs integrated** — split the booleans so the UI matrix stops showing green for probe-only sources. | Improve | XS | P0-7 | BE-data |
| P1-12 | **Cross-module nav IA + renames** — group sidebar into Analytics / Brand Intelligence / Operations; rename "Brand Analysis"→"Brand Strategy Deck", "Brand Pulse"→"Weekly Brand Intelligence"; swap Sparkles icon; redirect old `/brand-pulse`. | Improve | S | P1-7 | FE |
| P1-13 | **Shared FE component library** — `usePolledJob`, `KpiStat`, `JobProgress`, `StatusBadge`, `ReportTable`, `ConfirmDelete`; `lib/brand-ui.ts` tokens. | Rebuild-once | M | — | FE |

### P2 — Depth & polish

| ID | Item | Verdict | Effort | Owner |
|---|---|---|---|---|
| P2-1 | Charts in the Brand Analysis metrics preview (revenue YoY bar, active/inactive donut, top-ASIN bar) — recharts, ≥2-point guard. | Improve | M | FE |
| P2-2 | Data Kiosk bulk traffic + economics (seller schema) — `submit/poll/download_jsonl`; traffic/conversion only, keep `sales_data` as revenue source of truth. | Build-new | L | BE-data |
| P2-3 | Finance Reports → actual fees/refunds/net per ASIN (only if profitability becomes a product goal). (C-5) | Build-new | L | BE-data |
| P2-4 | Brand Intelligence **PDF export** (fast-follow per C-3) on `scheduled_report_pdf_service` rails. | Build-new | M | PPTX |
| P2-5 | Replace canned projection slide — ground in real category/trend growth, or lead with `build_priority_actions`. | Rebuild | M | PPTX |
| P2-6 | Move artifacts to S3 by default (creds-present) + nightly GC; flip `BRAND_ANALYSIS_STORAGE_BACKEND`. | Improve | S | BE-platform |
| P2-7 | First-run onboarding cards per module (what it is, cadence, audience, one CTA). | Improve | S | FE |
| P2-8 | Yearly-export upload redesign (drag-and-drop per year, row-count/error states). | Improve | S | FE |
| P2-9 | Full test depth: API contract suite, processor integration, new-source mock contracts (golden envelopes), BI pipeline + LLM-guardrail tests, notification org-scoping. | Build-new | L | QA |

### P3 — Long tail / optional

| ID | Item | Verdict | Effort | Owner |
|---|---|---|---|---|
| P3-1 | Vendor Data Kiosk / vendor traffic parity (vendor GraphQL schemas + probe branch). | Build-new | M-L | BE-data |
| P3-2 | Listings health per SKU (overlaps content audit — lowest priority). | Build-new | S-M | BE-data |
| P3-3 | Visual-regression baseline for the deck (libreoffice→PNG pixel-diff, nightly only). | Build-new | M | QA |
| P3-4 | Fix `MarketTracker.tsx:177` hardcoded literal (the real i18n bug from C-6). | Fix | XS | FE |
| P3-5 | Narrative guardrail unit tests (no number invention, Vine stripping, malformed-JSON fallback). | Build-new | S | QA |

---

## 3. Quick Wins (high value, low effort — shippable now)

These ship in the first 2-3 weeks and deliver visible value without waiting on the big rebuilds. Several are corrections of stale-brief assumptions.

| Quick win | Effort | Why now |
|---|---|---|
| **"Remove Portuguese" → DONE-by-verification** (C-6). Document the non-issue; reallocate to `MarketTracker.tsx:177`. | XS | Closes a brief item at zero cost; stops wasted hunting. |
| **Delete in the Brand Analysis history UI** — the `DELETE` endpoint and `brandAnalysisApi.delete` already exist; only a `Trash2` + `ConfirmDelete` is missing (Market Research already has it). | XS | Visible gap; one of the explicit requirements. |
| **De-AI pass** — strip decorative gradients, remove Sparkles-as-AI signifier, delete the fake "Recommended actions" nav-cards, collapse the double progress bar+stepper. | S-M | Directly fixes the "feels AI-generated" complaint; pure FE. |
| **Kill `marketQuery` as a visible field** — it already defaults to `brandName` server-side; collapse to an Advanced override. Removes the most confusing of the three "brand" inputs with no backend change. | S | Biggest terminology win for the least work. |
| **`__DAILY_TOTAL__` invariant tests** (P0-5) — pin the team's known recurring gotcha in both modules. | S | Cheap insurance against the bug that has bitten before. |
| **Completion toast + bell wiring** — the `NotificationBell` is already built and mounted; emit an alert row on completion + add one `alertTypeLabel` entry + a page toast. | S | The "notifications" requirement is ~70% already done. |
| **Capability matrix honesty** (P1-11) — stop showing green for probe-only sources. | XS | Aligns the UI with the Source/Confidence/Evidence direction. |
| **Cancel (cooperative)** — the lifecycle migration + checkpoint + endpoint also fixes the delete-resurrection bug in the same PR. | M | Required feature + correctness fix in one. |

---

## 4. Medium-Term Improvements

- **Brand Analytics live market share** (P0-7) — flips the deck's dark `_slide_market_share` to real search-purchase/click/cart-add share and top-competitor-ASINs-per-term. The single most valuable competitive output, currently `None`.
- **Ads search-term intelligence** (P1-8) — cheapest competitive unlock with no Brand Registry gate; feeds "competitors on your terms" into the weekly product.
- **Brand Analysis input flow + chrome rebuild** (P1-1, P1-2, P1-13) — the 3-noun model and the shared component library make the surface look like an Amazon-native enterprise tool, not AI slop.
- **PPTX dynamic block rebuild** (P1-5) — charts, dynamic-or-omit composition, exec summary, methodology appendix; turns "missing data" into a transparency feature.
- **Weekly Brand Intelligence v1** (P1-6, P1-7) — the new product on the proven `scheduled_reports` rails; persisted, diff-based, LLM-synthesized, push-notified.
- **Enrichment parallelization + offer-snapshot reads** (P1-9, P1-10) — removes the ASIN ceiling and gives the weekly product real competitive deltas from data we already pay to fetch.

## 5. Long-Term Vision

- **The intelligence ladder is the product strategy.** Four surfaces, four cadences, four artifacts, no cannibalization: Performance (live), Weekly Brand Intelligence (weekly digest), Market Research (on-demand), Brand Strategy Deck (quarterly PPTX). The nav IA (P1-12) makes the ladder visible.
- **Data Kiosk as the bulk-data backbone** (P2-2, P3-1) — replace the N-call per-ASIN catalog loop with one bulk traffic+economics pull; vendor parity so vendors (usually brand owners) get their richest first-party data.
- **True profitability** (P2-3) — Finance-actuals move the deck from a revenue story to a margin story; the biggest differentiator vs a Helium10 export.
- **Provider-layer architecture** — a capability-gated `BrandSignalProvider` interface so every new source plugs in uniformly (declares its capability key, returns `None` to omit its section), keeping the dynamic-or-omit discipline end-to-end.
- **PDF + share surface** (P2-4) for the weekly product; later, push-to-Slack/webhook once SendGrid/transport blockers clear.

---

## 6. Technical Architecture Changes

### 6.1 Decompose the 3596-line monolith (P0-6)

`brand_analysis_service.py` glues seven unrelated concerns. Target package (move-and-re-export first; `__init__.py` keeps `from app.services.brand_analysis_service import ...` working during migration):

```
app/services/brand_analysis/
  __init__.py          # back-compat re-exports
  state.py             # JobStatus enum, TERMINAL/RUNNING sets, single STATUS_PROGRESS (fixes the pct/map contradiction + triplicated running_statuses)
  parsing.py           # parse_brand_export, COLUMN_ALIASES, ParsedBrandExport
  metrics.py           # calculate_brand_metrics, assess_data_completeness
  provenance.py        # build_metric_provenance/_source_registry/_enrich/_validate_for_deck
  narrative.py         # BrandAnalysisNarrativeService, build_fallback_narrative, build_priority_actions
  crud.py              # BrandAnalysisService (create/get/list/delete/save_source_file)
  orchestration.py     # process_brand_analysis_job, _set_status, _resolve_adapter (uses shared run_async)
  signals/             # provider layer (base.py BrandSignalProvider + per-source providers)
  deck/                # PPTX rebuild target (see §10)
```

**Migration order (green tests between each):** `state.py` → `parsing/metrics/provenance` (pure, most-tested) → `narrative` → `deck/` (the PPTX agent's seam) → `crud`/`orchestration` last. Lock behaviour first with a golden-deck text snapshot + `validate_pptx_bytes` fingerprint.

### 6.2 Job lifecycle state machine (P0-3, P0-4)

- `JobStatus` enum with explicit `TERMINAL`/`RUNNING` sets in `state.py` — kills the triple source of truth across `STATUS_PROGRESS`, `schemas`, and the inline `running_statuses`.
- Persist `celery_task_id` on `start`; `_set_status` writes `heartbeat_at` on every transition.
- Cooperative cancel: `_check_cancel(db, job_id)` at every phase boundary; `revoke()` as best-effort (C-9).
- `recover_stuck_brand_analysis_jobs` beat task (`crontab */10`): stale-heartbeat RUNNING → `failed`; `cancel_requested` + stale → `cancelled`; tracked-pending (Celery-down fallback, C-10) → re-enqueue.
- Existence + cancel re-check before the final commit (fixes resurrection, P0-4).

### 6.3 Shared worker loop

Move `run_async` from `workers/tasks/scheduled_reports.py:17` to `app/db/worker_loop.py`; use it in `process_brand_analysis_job` instead of the hand-rolled `create_async_engine` + `new_event_loop`. Removes the fragile private-engine workaround.

### 6.4 Provider layer for data coverage (P0-7, P1-8/9/10, P2-2/3)

`signals/base.py` `BrandSignalProvider` declares `capability_key` and `async fetch(ctx) -> dict | None` (None ⇒ section omitted). The orchestrator runs only providers whose capability probed `True`. Add a `brand_signal_cache` table (JSONB, `expires_at`) keyed `(account, marketplace, source, period)` so multi-MB reports aren't re-pulled per analysis. **Note:** PII is not a concern for any of the 10 sources (Finance/Settlement are amounts, not buyer data) — no Restricted Data Token flow needed.

### 6.5 Weekly Brand Intelligence on `scheduled_reports` rails (P1-6)

Reuse the beat-scanner + stuck-recovery + `frequency`/`next_run_at` machinery rather than inventing a scheduler. Pipeline: `aggregate` (AnalyticsService primitives, **import decline thresholds, don't copy**) → `diff` (vs previous report's snapshot) → `generate` (one JSON-validated Anthropic call with the BA guardrails: never-invent-numbers gate, Source/Confidence/Evidence per claim, deterministic fallback) → `persist + notify`.

---

## 7. Database Changes

**Migration sequence starts at `029`** (head is `028`; the specialists' 022-024 are taken — C-2). Use nullable columns with server defaults (no table rewrite) and `CREATE INDEX CONCURRENTLY` on the large `artifact_data`-bearing table.

| Migration | Change |
|---|---|
| **`029_brand_analysis_job_lifecycle`** | `ALTER brand_analysis_jobs ADD celery_task_id VARCHAR(155) NULL`, `cancel_requested BOOL NOT NULL DEFAULT false`, `started_at TIMESTAMPTZ NULL`, `heartbeat_at TIMESTAMPTZ NULL`; `CREATE INDEX CONCURRENTLY ix_brand_analysis_jobs_status_heartbeat ON (status, heartbeat_at)`. |
| **`030_alert_notifications_extend`** (C-1) | `ALTER alerts ALTER rule_id DROP NOT NULL`; add partial index `ix_alerts_org_unread_triggered_at ON (organization_id, triggered_at) WHERE is_read = false` (org-scoped, complements the existing rule-scoped one). No new table. New `event_kind` values `report_ready`/`report_failed` are data, not schema. |
| **`031_asin_offer_snapshot_uq`** (C-7) | `ADD CONSTRAINT uq_asin_offer_snapshots_org_account_asin_observed UNIQUE (organization_id, account_id, asin, observed_at)` to enable upsert + a read path. |
| **`032_brand_intelligence`** (P1-6) | New `brand_intelligence_reports` (`id`, `organization_id` FK CASCADE, `account_id` FK SET NULL, `period_start`, `period_end`, `window_days`, `cadence`, `status` indexed, `progress_step`, `error_message`, `snapshot` JSONB, `diff` JSONB, `intelligence` JSONB, `generated_by`, `created_at`, `completed_at`; `UNIQUE(account_id, period_start, period_end)`; `INDEX (account_id, period_end)`). New `brand_intelligence_schedules` (`organization_id`, `account_ids` JSONB, `language`, `day_of_week`, `is_enabled`, `next_run_at` indexed, `timezone`). |
| **`033_brand_signal_cache`** (P0-7 caching) | New `brand_signal_cache` (`organization_id`, `account_id`, `marketplace`, `source`, `period`, `payload` JSONB, `fetched_at`, `expires_at`; unique on the key tuple). |

**Explicitly NOT created:** a `notifications` table (overruled — C-1); a Settlement table (dropped — C-5).

---

## 8. API Changes

| Endpoint | Change |
|---|---|
| `POST /brand-analysis/{job_id}/cancel` | **New.** 404 if missing, 409 if terminal; sets `cancel_requested=true`, persists, `revoke(task_id)`; returns job. |
| `DELETE /brand-analysis/{job_id}` | **Changed.** Now guards running status (offer cancel instead); cascades artifact GC via `BrandAnalysisStorage.delete()`. |
| `POST /brand-analysis` (create) | **Unchanged signature.** `market_query` still defaults to `brand_name` server-side; no terminology change touches the contract. |
| `GET /brand-intelligence/reports?account_id=&limit=` | **New** (replaces `/brand-pulse`). List newest-first. |
| `GET /brand-intelligence/reports/{id}` | **New.** Full report (snapshot+diff+intelligence). |
| `GET /brand-intelligence/reports/latest?account_id=` | **New.** Most recent completed. |
| `POST /brand-intelligence/generate` | **New.** On-demand run (status `pending`, poll like BA). |
| `GET/PUT/DELETE /brand-intelligence/schedule` | **New.** Weekly opt-in config. |
| `GET /brand-pulse` (legacy) | **Deprecated** → 410/redirect to `/brand-intelligence` for one release. |
| `GET /alerts`, `GET /alerts/unread-count`, `PATCH` bulk-read | **Reused as-is** for notifications (C-1) — no new notifications API. New `event_kind` filter values only. |
| `brandAnalyticsApi` SP-API client | **New methods** `get_brand_analytics_search_terms/market_basket` (P0-7); two new `AdvertisingReportConfig` entries (P1-8). Internal, not HTTP. |

---

## 9. Frontend Changes (Brand Analysis + Brand Pulse rebuild)

### 9.1 Brand Analysis — improve-the-data, rebuild-the-shell

- **Setup form (rebuild):** the 3-noun model — one `Brand name` field, an explicit `Data source` segmented control (Connected account / Upload exports), an Advanced disclosure for scope (Brand vs ASIN list). **Remove `marketQuery` from JSX** (server gets `market_query=brand`). Kills the implicit mode. New `components/brand-analysis/{AnalysisSetupCard, SourceSelect, YearlyExportUpload}`.
- **De-AI chrome (improve):** `lib/brand-ui.ts` tokens (`deltaTone` by value, flat eyebrow); strip gradients; remove Sparkles; delete fake "Recommended actions"; one `JobProgress` (compact bar + step, stepper only in detail); KPI color encodes value.
- **History (rebuild):** replace the faux-grid + duplicated desktop/mobile renderers with one responsive `ReportTable` carrying status/source/created/completed/progress + a row action menu (open/download/re-run/delete) gated by status.
- **Delete + Cancel:** `ConfirmDelete` (wraps existing `alert-dialog.tsx`); Cancel button behind the P0-3 endpoint (disabled tooltip until it exists — never a dead control).
- **Charts (P2-1):** revenue-YoY bar, active/inactive donut, top-ASIN bar via recharts; only render with ≥2 points, else an explicit empty card.

### 9.2 Brand Pulse → Brand Intelligence — rebuild the product

- **New page `pages/BrandIntelligence.tsx`** — a report *reader*, not a dashboard: brand picker + ISO week selector + weekly-subscribe toggle + generate; `ReportReader` with `ExecSummary` (WoW deltas) and sections Market & category / Brand evolution / Competitor activity / Opportunities / Risks / Product-trend movements / Strategic recommendations. Poll generation via `usePolledJob`.
- **Salvage from BrandPulse.tsx:** the `RecCard` Source/Confidence/Evidence badges (the only place in the app matching the intelligence direction), window-defaulting, and the awaiting-data gate — ported verbatim.
- **Build against a typed `WeeklyReport` fixture** so the reader is done before the backend pipeline lands (mitigates the cross-track dependency).
- **Nav (P1-12):** relabel to "Weekly Brand Intelligence", Radar/Telescope icon, moved out of the performance neighborhood; redirect `/brand-pulse`.

### 9.3 Shared (P1-13)

`components/shared/{usePolledJob, KpiStat, JobProgress, StatusBadge, ReportTable, ConfirmDelete}` — replaces the 3 duplicated KpiTiles, 2 status-badge dialects, copy-pasted polling, and the re-defined `downloadBlob`. `usePolledJob` fires `onComplete` once on terminal transition to drive the completion toast.

### 9.4 Notifications

Bell is **reused as-is**. The only FE change is one `alertTypeLabel` entry for `report_ready`/`report_failed` + the page toast. No new inbox (C-1).

---

## 10. PPTX Generation Changes (dynamic block architecture)

**Verdict: rebuild the builder** inside the `deck/` seam carved out by the decomposition (C-8). The current builder is 100% hand-drawn rectangles with no chart layer, a static slide list, 3 unguarded tables that render header-only "broken" tables, 2 dead slide methods, ~50% wasted LLM output, and canned per-brand-identical projections.

### 10.1 Package

```
brand_analysis/deck/
  theme.py         # DeckTheme: palette (single source for the ~40 inline RGBs), 8pt type floor, 12-col grid, embedded Nunito (OFL)
  format.py        # € symbol + IT locale grouping; one EMPTY token (kills "EUR 1,234"/"N/A"/"New")
  primitives.py    # rect/text/table/kpi on the grid (no absolute inches)
  charts.py        # matplotlib→PNG (Agg, 2x DPI): donut, hbar, waterfall, treemap, lollipop, bullet
  block.py         # Block protocol: id, section, priority, required_keys, is_available(ctx), render()
  registry.py      # ordered blocks + SectionDivider grouping
  composer.py      # renders only available blocks; suppresses empty-section dividers; collects skipped → methodology
  blocks/          # one module per block
```

`build_brand_analysis_pptx(metrics, narrative, language)` keeps its **exact signature** → 3-line shim to `DeckComposer`. The processor is untouched.

### 10.2 Dynamic slide list (≈10-18 slides, data-driven)

| # | Block | Chart | `is_available` gate |
|---|---|---|---|
| 1 | Cover | — | always |
| 2 | **Exec Summary** | KPI strip | always |
| 3 | Agenda (sections present in *this* deck) | — | always |
| — | *Divider: Performance* | band | section non-empty |
| 4 | Revenue YoY | waterfall / paired bar | rev present |
| 5 | Catalog Health | donut | always |
| 6 | Active/Inactive | donut | active > 0 |
| 7 | Top Performers | horizontal bar | **≥3 ASINs** (header-only impossible) |
| — | *Divider: Catalog & Content* | band | section non-empty |
| 8 | Content/SEO Audit | lollipop | ≥1 gap metric |
| 9 | Review/Image Weakness | hbar | weakness present |
| 10 | Subcategory Mix | treemap | **≥2 subcats** |
| — | *Divider: Channel & Risk* | band | section non-empty |
| 11 | Operational Gap | 2×2 KPI | always |
| 12 | Channel Gap | reseller bar | `_has_channel_data` |
| 13 | Concentration Risk | bullet/gauge | **share present & ≥3 ASINs** |
| — | *Divider: Market* | band | section non-empty |
| 14 | Market Share | donut + competitor bars | `_has_market_share` (now lit by P0-7 Brand Analytics) |
| — | *Divider: Strategy* | band | section non-empty |
| 15 | Priority Actions | numbered list | ≥1 action (already dynamic — keep) |
| 16 | Roadmap | 3-phase timeline | ≥1 phase |
| 17 | Conclusions | 4-quadrant | ≥1 array non-empty |
| 18 | **Methodology / Provenance** | quality table | always (drives transparency from `metric_source_registry` + `limitations` + `skipped_blocks`) |

### 10.3 Narrative contract

LLM returns a dict **keyed by block id** (`insight` + `recommendation` per available block) + `exec_summary.headline`, constrained to composer-computed `available_block_ids`. Kills the dead `strengths`/`weaknesses`/`approach_pillars` fields. Missing key → deterministic per-block fallback from the metric. Guardrails (never-invent-numbers, Vine gate, no-proxy-to-revenue) preserved verbatim.

### 10.4 Migrate behind a flag

Ship `DeckComposer` at parity with the current 15 slides first (golden snapshot), then swap blocks to charts one section at a time. The per-block contract test (P0-2) replaces the slide-count assertions.

---

## 11. Final Sprint Breakdown

> 4-person squad: **BE-platform** (lifecycle/monolith/notifications), **BE-data** (sources/Brand Intelligence pipeline), **FE**, **QA**. Two-week sprints. PPTX work is taken by BE-platform after the decomposition lands (or a 5th specialist if available). Effort is rough; the long poles are the PPTX rebuild (P1-5, ~3.5-4w) and the Brand Intelligence rebuild (P1-6/P1-7, ~3-4w).

### Sprint 1 — Foundation & Quick Wins
**Theme:** De-risk the rework and ship visible value immediately.
- QA: P0-1 test-harness foundation; P0-5 `__DAILY_TOTAL__` invariants; P0-2 section-manifest contract (with PPTX).
- BE-platform: P0-3 job lifecycle (cancel/recovery/heartbeat) + P0-4 delete hardening (one PR — also fixes resurrection).
- FE: Quick-win delete-in-UI; de-AI pass (gradients/Sparkles/fake recs/double progress); kill `marketQuery` field; C-6 documented + `MarketTracker.tsx:177` fix.
- BE-data: P0-7 Brand Analytics fetch → `search_*_share` keys (unblocks the dark market-share slide).
- **Exit:** delete/cancel work; UI no longer looks AI-generated; no test asserts a literal slide count; Brand Analytics lights up.

### Sprint 2 — Decomposition & Notifications
**Theme:** Carve the seam; turn on completion notifications.
- BE-platform: P0-6 monolith decomposition (behind golden-deck snapshot); extract `deck/` seam; P1-4 extend `Alert` + emit on terminal states.
- FE: P1-13 shared component library; P1-1 input-flow rebuild (3-noun model); P1-4 toast + `alertTypeLabel` entry.
- BE-data: P1-8 Ads search-term/purchased-product configs; P1-10 parallelize enrichment; P1-11 capability detected-vs-integrated.
- QA: P0-2 dynamic-PPTX contract tests land; P2-9 API contract + processor integration tests begin.
- **Exit:** monolith is a package with green tests; notifications fire end-to-end; setup form is the 3-noun model.

### Sprint 3 — PPTX rebuild (track A) + Brand Intelligence backend (track B)
**Theme:** The two big rebuilds run in parallel on the new foundation.
- PPTX (BE-platform): P1-5 `deck/` — theme + `charts.py` matplotlib helper + block registry + composer at parity, then first charts.
- BE-data + BE-platform: P1-6 `BrandIntelligenceReport`/`Schedule` models (mig 032), aggregate→diff→LLM pipeline, beat scanner + recovery; new `/brand-intelligence` API.
- FE: P1-2 finish chrome; P1-3 `ReportTable` history + Cancel wired; P1-7 BrandIntelligence reader against the typed fixture.
- QA: BI pipeline + LLM-guardrail tests; per-block PPTX contract tests.
- **Exit:** deck composes dynamically with first charts; BI pipeline persists a weekly report; reader renders the fixture.

### Sprint 4 — Wire it together
**Theme:** Connect reader↔pipeline; finish the deck; integrate competitive data.
- PPTX: port all blocks to charts; exec-summary + methodology appendix; keyed-by-block narrative; format/locale + provenance chips.
- BE-data: P1-9 AsinOfferSnapshot read path → Pulse offer deltas; P0-7 caching (mig 033); feed Brand Analytics + Ads signals into the BI pipeline.
- FE: P1-7 reader wired to live API; P1-12 nav IA + renames + `/brand-pulse` redirect.
- QA: new-source mock-contract suite (golden envelopes); notification org-scoping release gate.
- **Exit:** Weekly Brand Intelligence v1 live (in-app reader + weekly automation + notification); consulting-grade deck with charts and no empty placeholders.

### Sprint 5 — Depth, polish & hardening
**Theme:** Close the long tail; lock regression safety.
- BE-data: P2-2 Data Kiosk bulk pull (seller); begin P2-3 Finance (if profitability is greenlit).
- FE: P2-1 BA charts; P2-7 onboarding cards; P2-8 upload redesign; P3-4 confirm.
- BE-platform: P2-6 S3 default + nightly GC; P2-4 BI PDF export (fast-follow).
- QA: P2-9 full depth; P3-5 narrative guardrails; P3-3 visual-regression baseline (nightly).
- PPTX: P2-5 replace canned projections.
- **Exit:** release-gating checklist green (variable-count PPTX, no empty placeholders, delete/cancel race, `__DAILY_TOTAL__`, API guard matrix, notification org-scoping); program complete.

---

### Appendix — Rebuild vs Improve at a glance

| Area | Verdict |
|---|---|
| BA pipeline / readiness / provenance / metrics | **Improve / keep** (genuine assets) |
| BA input form | **Rebuild** (3-noun model) |
| BA chrome | **Improve** (de-AI) |
| BA history list | **Rebuild** (ReportTable) |
| BA PPTX builder | **Rebuild** (block registry + charts) inside a **refactored** package seam |
| Monolith packaging | **Refactor** (mechanical decomposition) |
| Job lifecycle | **Refactor + extend** (cancel/recovery/heartbeat) |
| Brand Pulse product | **Rebuild** → Weekly Brand Intelligence |
| `brand_pulse_service.py` code | **Discard** (190-line re-skin; only RecCard shape + period framing survive) |
| Capability probe | **Improve** (detected-vs-integrated + provider layer) |
| Brand Pulse data layer | **Rebuild** (new spine: Brand Analytics + Ads search-term + offer deltas) |
| Notifications | **Improve / extend** the existing Alert table + mounted bell (NOT a new table) |
| Weekly automation | **Reuse** `scheduled_reports` beat machinery |
| Test strategy | **Rebuild** the harness; **keep** the deterministic-core tests verbatim |
