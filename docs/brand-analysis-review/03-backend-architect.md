# Brand Analysis & Brand Pulse — Backend Architecture Review

**Author:** Backend Architect Agent
**Scope:** services, data model, async pipeline, automation, data-coverage integration, notifications.
**Branch:** `master` (HEAD `156536c`). All anchors `file:line`.

---

## 1. Findings (grounded in the code)

### 1.1 The monolith is real and structurally load-bearing

`app/services/brand_analysis_service.py` is **3596 lines** carrying seven unrelated concerns in one module: column parsing (`parse_brand_export` `:569`), metric math (`calculate_brand_metrics` `:1300`, ~530 lines), provenance (`build_metric_provenance` `:680`, `build_metric_source_registry` `:813`, `enrich_metric_provenance` `:949`, `validate_metric_provenance_for_deck` `:998`), LLM narrative (`BrandAnalysisNarrativeService` `:1984`), the entire PPTX builder (`BrandAnalysisPptxBuilder` `:2413`, ~600 lines + a ~300-line `PPTX_STATIC_STRINGS` table `:2109`), the CRUD service (`BrandAnalysisService` `:3039`), and the background processor (`process_brand_analysis_job` `:3219`). Nothing here is coupled by necessity — these are seven files glued by proximity.

### 1.2 The async pipeline reinvents infra that already exists, worse

`process_brand_analysis_job` (`:3219`) hand-rolls its own engine + event loop:

```python
_local_engine = create_async_engine(_db_url, echo=settings.APP_DEBUG, pool_size=2, max_overflow=1)  # :3229
...
loop = asyncio.new_event_loop(); asyncio.set_event_loop(loop)                                        # :3590
loop.run_until_complete(_process())
```

The codebase already has the **canonical** version of exactly this: `run_async(coro_factory)` in `workers/tasks/scheduled_reports.py:17`, which calls `reset_engine_for_worker()` and disposes the engine in a `finally`. Brand Analysis duplicates the pattern but skips `reset_engine_for_worker()`, so it depends on building a private engine to avoid cross-loop asyncpg futures — a fragile workaround for a solved problem.

### 1.3 Status/progress is a triple source of truth and self-contradicts

- `STATUS_PROGRESS` map (`:47-70`) declares `collecting_source_data: 30`, but the actual calls pass `25` then `40` (`:3438`, `:3441`). `enriching_catalog` is mapped `55` but `_set_status("enriching_catalog", ...)` at `:3475` passes no pct, so it resolves `55` — while the call at `:3483` (`generating_metrics`) passes no pct and resolves `70` from the map. The pct argument and the map disagree case-by-case.
- The set of "running" statuses is **triplicated**: `STATUS_PROGRESS` keys (`:47`), `schemas/brand_analysis.py` status literals, and the inline `running_statuses` set in `brand_analysis.py:216-234`. Adding a status means editing three places; today the `start` guard's `running_statuses` even lists legacy statuses (`exporting_2024`, `configuring_market`) that the processor never emits.

### 1.4 There is no way to cancel, and no way to clean up

- **No Celery task ID is ever persisted.** `process_brand_analysis.delay(...)` (`brand_analysis.py:263`) returns an `AsyncResult` whose `.id` is discarded. A grep for `revoke`/`AsyncResult`/`celery_task_id` across `app/` and `workers/` finds only JWT token revocation — nothing for Celery. **Cancellation is therefore impossible today**: you cannot revoke a task whose id you never stored, and there is no cooperative cancel flag the `_process()` loop checks.
- `DELETE /brand-analysis/{job_id}` (`brand_analysis.py:329`) deletes the row via `service.delete_job` (`:3097`, plain `db.delete`) but cannot stop an in-flight task/thread. Worse, `_process()` re-`SELECT`s the job at `:3310` and commits at `:3572` **without re-checking existence** — a job deleted mid-run can be **resurrected** by the worker's final commit (the `UPDATE` in `_set_status` is a no-op on a deleted row, but the ORM `db.commit()` at `:3572` re-inserts via the still-attached `job` object's dirty state only if it's still in the identity map; in practice the row is gone so the UPDATE silently affects 0 rows — but the artifact bytes and S3 object are orphaned with no GC).
- **No stuck-job recovery.** The sync-retry columns exist (`next_retry_at` `models:45`, `sync_attempt_count` `:43`) but **nothing ever polls `next_retry_at`** — there is no beat task analogous to `recover_stuck_scheduled_report_runs` (`scheduled_reports.py:96`). A worker crash between `:3438` and `:3572` leaves the job wedged in `generating_metrics`/`generating_pptx` forever; the UI polls a status that never advances.
- **No artifact GC.** PPTX bytes live inline in `brand_analysis_jobs.artifact_data` (`LargeBinary`, `models:60`) by default (`BRAND_ANALYSIS_STORAGE_BACKEND="db"`). Raw uploads live in `brand_analysis_source_files.file_data` (`models:175`). Nothing ever prunes old jobs/artifacts/`asin_offer_snapshots`.

### 1.5 The in-process thread fallback is untracked and unsafe

`start_brand_analysis_processing` falls back to `threading.Thread(target=process_brand_analysis_job, ..., daemon=True)` (`brand_analysis.py:269-274`) when Celery enqueue fails. This is **fire-and-forget**: a daemon thread inside the FastAPI web process, holding a private DB engine, invisible to any monitoring, killed silently on web-process restart (Render redeploys constantly). It exists because the system can't trust its own queue, which is itself a finding.

### 1.6 The capability probe gathers intelligence nobody uses

`detect_brand_analysis_capabilities` (`capabilities.py:124`) probes **11** capabilities (`CAPABILITY_KEYS` `:23`) and persists them. But `calculate_brand_metrics` only consumes catalog/pricing/fees/aplus enrichment. `data_kiosk`, `brand_analytics`, `finance_reports`, `settlement_reports`, `listings` are probed, persisted, surfaced in the UI capability matrix — and **never read by any metric**. `search_*_share` is hardcoded `None` (`service.py:1804`). `missing_roles` flows only into the limitation summary. We pay for the probe round-trips and render a matrix that promises data we don't ingest.

### 1.7 `AsinOfferSnapshot` is write-only dead weight

`AmazonAccountDataSource` writes one `AsinOfferSnapshot` per ASIN during enrichment (`sources.py:615`), but the table has **no unique constraint** (`models:122`), **no read path anywhere**, and Buy-Box history is hardcoded unavailable (`service.py:1748-1759`). Every analysis appends rows nobody queries.

### 1.8 Brand Pulse is ~90% a re-skin of Performance Analytics

`BrandPulseService.build_pulse` (`brand_pulse_service.py:36`) delegates every number to `AnalyticsService`: `compute_dashboard_kpis` (`:49`, same call the dashboard KPI endpoint uses), `asin_sales_breakdown` (`:63`, the exact Performance drilldown primitive), `_asin_titles` (`:104`), `compute_advertising_metrics` (`:165`). Pulse-local logic is only the period framing, `_top_asins`/`_declining_asins` (`:106`/`:125`) with decline thresholds **copied** from AnalyticsService (`DECLINE_THRESHOLD_PCT = -5.0` `:25` — a drift hazard), and a recommendation overlay. There is **no persistence, no job, no caching** — `build_pulse` recomputes on every GET (`brand_pulse.py:39`). It cannot answer "what changed since last week" because it stores nothing.

### 1.9 No notification system exists

There is an `Alert`/`AlertRule` model (`models/alert.py`) — a good shape to mirror (`is_read` `:76`, `dedup_key` `:72`, a **partial index on unread** `ix_alerts_rule_unread_triggered_at` `:55-60`) — but it is wired to alert rules, not job-completion events. There is **no `Notification` table, no notifications API, no SSE/WebSocket** (grep confirms `StreamingResponse` is only used for file downloads in `reports.py`/`exports.py`/`brand_analysis.py`/`catalog.py`). When an analysis completes, the only signal is the UI's 3000ms poll.

### 1.10 Reusable infra is sitting right there

`scheduled_report_service.py` + `workers/tasks/scheduled_reports.py` + `models/scheduled_report.py` already implement: a beat scanner (`scan_scheduled_reports_due` `:42`, `crontab(minute="*/5")` `celery_app.py:101`), a `frequency` field (`weekly`/`monthly`, `scheduled_report.py:38`), `next_run_at` indexed (`:51`), a richer run model with separate `generation_status`/`delivery_status`/`progress_step` (`:84-86`), in-process scheduler fallback, and stuck-run recovery (`recover_stuck_scheduled_report_runs` `:96`). Brand Pulse's "weekly intelligence" requirement maps onto this almost 1:1.

---

## 2. Problems Identified (ranked)

| # | Problem | Severity | Evidence |
|---|---|---|---|
| P-1 | **No cancel + no stuck-job recovery.** Task id never stored; no cooperative cancel flag; `next_retry_at` never polled; mid-run crash wedges job forever. | **Critical** | `brand_analysis.py:263`; `service.py:3308-3572`; no recovery beat task |
| P-2 | **3596-line monolith** blocks every downstream goal (PPTX redesign, dynamic slides, testing). Can't unit-test metrics without importing python-pptx + Anthropic. | **High** | whole `brand_analysis_service.py` |
| P-3 | **Delete cannot stop work + orphans artifacts.** Resurrection risk; no S3/DB GC. | **High** | `brand_analysis.py:329`; `service.py:3097`; `:3572` |
| P-4 | **Untracked daemon-thread fallback** runs heavy work in the web process, dies on redeploy, invisible. | **High** | `brand_analysis.py:269-274` |
| P-5 | **Status/progress triple-source-of-truth**, pct contradicts map; brittle to extend. | **Medium** | `service.py:47-70` vs `:3438/3441`; `brand_analysis.py:216-234` |
| P-6 | **Brand Pulse stores nothing** → cannot compute week-over-week change; ~90% duplicates Performance Analytics. | **High** (for the reposition) | `brand_pulse_service.py:36-96` |
| P-7 | **Capability probe vs usage mismatch** — 5 capabilities probed, persisted, displayed, never consumed; `search_*_share` always None. | **Medium** | `capabilities.py:23`; `service.py:1804` |
| P-8 | **Artifact bytes inline in Postgres by default** — row bloat, slow `list`/`get`, CASCADE-coupled deletion. | **Medium** | `models:60,175`; `config BRAND_ANALYSIS_STORAGE_BACKEND="db"` |
| P-9 | **`AsinOfferSnapshot` write-only**, no unique constraint, unbounded growth. | **Low** | `sources.py:615`; `models:122` |
| P-10 | **No notifications** — completion only discoverable by polling. | **Medium** | no Notification model/API/SSE |
| P-11 | **Sequential inline SP-API enrichment** — N×(catalog+fees+aplus) serial, no pool. | **Medium** | `sources.py:581-583` |

---

## 3. Recommendations (priority + effort)

| ID | Recommendation | Priority | Effort | Rebuild/Refactor |
|---|---|---|---|---|
| R-1 | Decompose monolith into a `brand_analysis/` package (parse/metrics/provenance/narrative/pptx/orchestration). | P0 | L | Refactor (mechanical move) |
| R-2 | Add a job state machine + cooperative cancel + Celery task-id persistence + revoke. | P0 | M | Refactor + extend |
| R-3 | Add a `recover_stuck_brand_analysis_jobs` beat task (mirror `recover_stuck_scheduled_report_runs`). | P0 | S | New, by analogy |
| R-4 | Harden delete: cancel-then-delete; GC S3/DB artifacts; existence-recheck guard before final commit. | P0 | S | Refactor |
| R-5 | Replace private-engine/loop with `run_async`; route the thread fallback through a tracked record or remove it. | P1 | S | Refactor |
| R-6 | Collapse status into one `JobStatus` enum + a single `STATUS_PROGRESS`; delete the inline `running_statuses` set. | P1 | S | Refactor |
| R-7 | **Rebuild Brand Pulse** as `BrandIntelligenceReport` — scheduled, persisted, diff-based, LLM-synthesized weekly report on the scheduled_reports pattern. | P0 | XL | **Rebuild** |
| R-8 | Notifications: new `notifications` table + API + **polling unread-count** (defer SSE). Emit on terminal job transitions. | P1 | M | New |
| R-9 | Data coverage: wire Data Kiosk + Brand Analytics into a `BrandSignalProvider` layer; integrate Finance/Settlement for margin; parallelize enrichment. | P1 | L | Extend |
| R-10 | Externalize PPTX strings + slide spec to a registry/theme module (precondition for the PPTX redesign owned by the PPTX agent). | P1 | M | Refactor |
| R-11 | Drop or repurpose `AsinOfferSnapshot`; add unique `(account,asin,observed_date)` + a read path, or delete the write. | P2 | XS | Decide |
| R-12 | Move artifacts to S3 by default; keep DB only as small-file fallback; nightly GC of jobs older than N days. | P2 | S | Refactor |

---

## 4. Technical Implementation Plan

### 4.1 Monolith decomposition (R-1, R-10) — REFACTOR

Target package layout. **Pure move-and-re-export first** (no behaviour change), so existing imports `from app.services.brand_analysis_service import ...` keep working via a thin shim during migration.

```
app/services/brand_analysis/
  __init__.py            # re-exports public names for back-compat
  parsing.py             # parse_brand_export, COLUMN_ALIASES, NUMERIC_COLUMNS, _parse_number, ParsedBrandExport
  metrics.py             # calculate_brand_metrics, assess_data_completeness
  provenance.py          # build_metric_provenance, build_metric_source_registry,
                         #   enrich_metric_provenance, validate_metric_provenance_for_deck,
                         #   build_limitation_summary, DECK_NUMERIC_PROVENANCE_KEYS
  narrative.py           # BrandAnalysisNarrativeService, build_fallback_narrative, build_priority_actions
  pptx/
    __init__.py          # build_brand_analysis_pptx, validate_pptx_bytes
    theme.py             # palette/spacing/typography tokens (kills ~40 inline RGB literals)
    primitives.py        # _rect/_text/_table/_kpi/_body_box/_title (today service.py:2917-3030)
    strings.py           # PPTX_STATIC_STRINGS (today :2109-2410) → i18n-loadable
    slides.py            # slide-spec registry: ordered list of (build_fn, gate_fn)
  crud.py                # BrandAnalysisService (create/get/list/delete/save_source_file)
  orchestration.py       # process_brand_analysis_job, _set_status, _resolve_adapter, STATUS_PROGRESS
  state.py               # JobStatus enum, TERMINAL_STATUSES, RUNNING_STATUSES, STATUS_PROGRESS (single source)
```

**Migration path (each step independently shippable, green tests between):**
1. Create the package; `__init__.py` does `from .legacy import *` where `legacy.py` is the renamed original file. Update `tests/test_brand_analysis_service.py` import only if needed (it imports symbols, not the module path — verify).
2. Extract `state.py` (enum + maps) — smallest, highest-leverage; fix the pct/map contradiction here.
3. Extract `parsing.py` then `metrics.py` then `provenance.py` (pure functions, easiest, most-tested).
4. Extract `narrative.py`.
5. Extract `pptx/` package; introduce `theme.py` tokens + `slides.py` registry — this is the seam the PPTX agent's redesign plugs into.
6. Extract `crud.py` and `orchestration.py` last (they import everything).
7. Delete `legacy.py`; flip `__init__.py` to explicit re-exports.

**Slide registry shape** (enables dynamic generation — "no data → no slide" — owned by PPTX agent, but the backend seam is this):

```python
@dataclass(frozen=True)
class SlideSpec:
    key: str
    build: Callable[["DeckContext"], None]
    gate: Callable[[dict], bool] = lambda metrics: True   # returns False → slide omitted entirely
BRAND_DECK_SLIDES: list[SlideSpec] = [...]
```

### 4.2 Job lifecycle: cancel + recovery + cleanup (R-2..R-5) — REFACTOR + EXTEND

**Migration `022_brand_analysis_job_lifecycle.py`:**

```python
op.add_column("brand_analysis_jobs", sa.Column("celery_task_id", sa.String(155), nullable=True))
op.add_column("brand_analysis_jobs", sa.Column("cancel_requested", sa.Boolean, server_default="false", nullable=False))
op.add_column("brand_analysis_jobs", sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))
op.add_column("brand_analysis_jobs", sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True))
op.create_index("ix_brand_analysis_jobs_status_heartbeat", "brand_analysis_jobs", ["status", "heartbeat_at"])
```

**State machine** (`state.py`):

```python
class JobStatus(str, Enum):
    PENDING="pending"; CAPABILITY_CHECKING="capability_checking"; PREFLIGHT_CHECKING="preflight_checking"
    SYNCING="syncing_internal_data"; COLLECTING="collecting_source_data"; ENRICHING="enriching_catalog"
    GENERATING_METRICS="generating_metrics"; GENERATING_NARRATIVE="generating_narrative"
    GENERATING_PPTX="generating_pptx"; WAITING_FOR_USER="waiting_for_user_action"
    COMPLETED="completed"; COMPLETED_WITH_LIMITATIONS="completed_with_limitations"
    FAILED="failed"; CANCELLED="cancelled"

TERMINAL = {COMPLETED, COMPLETED_WITH_LIMITATIONS, FAILED, CANCELLED, WAITING_FOR_USER}
RUNNING  = {CAPABILITY_CHECKING, PREFLIGHT_CHECKING, SYNCING, COLLECTING, ENRICHING,
            GENERATING_METRICS, GENERATING_NARRATIVE, GENERATING_PPTX}
```

`start` persists the task id:

```python
async_result = process_brand_analysis.delay(str(job.id))
job.celery_task_id = async_result.id
job.started_at = utcnow()
await db.commit()
```

**Cancel endpoint** — `POST /brand-analysis/{job_id}/cancel`:

```python
@router.post("/{job_id}/cancel", response_model=BrandAnalysisJobResponse)
async def cancel_brand_analysis_job(job_id, current_user, organization, db):
    job = await service.get_job(job_id, organization.id)
    if not job: raise HTTPException(404, ...)
    if job.status in TERMINAL: raise HTTPException(409, "Job already finished")
    job.cancel_requested = True                      # cooperative flag (DB-visible to the worker)
    await db.commit()
    if job.celery_task_id:
        from workers.celery_app import celery_app
        celery_app.control.revoke(job.celery_task_id, terminate=True, signal="SIGTERM")  # hard stop
    # If worker already gone, the recovery beat task will move it to CANCELLED.
    return _job_to_response(job)
```

**Cooperative cancel inside `_process()`** — check between phases (a hard `revoke(terminate=True)` may not fire mid-asyncio):

```python
async def _check_cancel(db, job_id) -> bool:
    row = (await db.execute(sa_text(
        "SELECT cancel_requested FROM brand_analysis_jobs WHERE id=:rid"), {"rid": job_id})).scalar_one_or_none()
    return bool(row)
# After each _set_status phase boundary:
if await _check_cancel(db, job_id):
    await _set_status(JobStatus.CANCELLED, "Cancelled by user", 100); return
```

Also add a **heartbeat**: `_set_status` writes `heartbeat_at = utcnow()` on every transition (one extra column in the existing `UPDATE`).

**Existence + cancel recheck before final commit** (fixes resurrection): before `:3572`'s commit, re-`SELECT id` and bail if gone or cancelled.

**Recovery beat task** `workers/tasks/brand_analysis.py`:

```python
@celery_app.task
def recover_stuck_brand_analysis_jobs():
    # heartbeat_at < now-15m and status in RUNNING → FAILED ("stalled"), or re-enqueue if pending & no task
    # cancel_requested & status in RUNNING & heartbeat stale → CANCELLED
    return run_async(_recover)
```

Register in `celery_app.py` beat_schedule: `crontab(minute="*/10")`. Also add a daily `cleanup_brand_analysis_artifacts` (delete jobs older than `BRAND_ANALYSIS_RETENTION_DAYS`, removing S3 keys via `BrandAnalysisStorage`).

**Delete hardening** (`crud.delete_job`): if status in RUNNING → set `cancel_requested=True` + revoke first, then delete row + `storage.delete(ref)` (new method on `BrandAnalysisStorage` that issues `delete_object` for `s3` refs).

**Replace private engine/loop** in `orchestration.process_brand_analysis_job` with the shared `run_async` from `scheduled_reports.py` (move `run_async` to a neutral home like `app/db/worker_loop.py` and import from both).

### 4.3 Data-coverage integration (R-9) — EXTEND

Introduce a **provider layer** so new sources plug in uniformly instead of bolting onto `AmazonAccountDataSource`. Each provider declares the capability key it needs and yields a typed signal block; the orchestrator runs only providers whose capability probed `True`.

```python
# app/services/brand_analysis/signals/base.py
class BrandSignalProvider(Protocol):
    capability_key: str            # maps to CAPABILITY_KEYS
    async def fetch(self, ctx: SignalContext) -> dict | None: ...   # None ⇒ section omitted
```

Per-source assessment for the **10 untested sources** (Availability / API / Permissions / Limitations / Effort / Report value):

| Source | Availability | API / report | Permissions (role) | Limitations | Effort | Report value |
|---|---|---|---|---|---|---|
| **Data Kiosk** | Probed via `_data_kiosk_api().get_queries` (`capabilities.py:261`) | Data Kiosk GraphQL (`createQuery`→poll→`getDocument`) | "Selling Partner Insights" + report roles | **Async**: submit query, poll `processingStatus`, download document URL — needs a poll loop like scheduled reports; GraphQL schema versioned | **L** | **High** — single source for sales+traffic+economics; replaces several legacy report pulls; gives glance views & sessions/conversion the deck lacks |
| **Brand Analytics** | Probed via `GET_BRAND_ANALYTICS_SEARCH_TERMS_REPORT` (`:246`) | Reports API (Search Terms, Market Basket, Repeat Purchase, Item Comparison) | **Brand Registry**-gated reports role | Brand Registry required; weekly/quarterly granularity; large flat files | **L** | **Very High** — the only first-party source for **search/market share** (`search_*_share` is `None` today `service.py:1804`); fills the market-share slide that currently needs an external upload |
| **Brand Registry** | **Inferred** = aplus result (`:312`) | No direct API; inferred via A+/Brand Analytics access | n/a (inference) | Not a real probe — it's an alias; can falsely report available/unavailable | **XS** | Low standalone; it's a gate for Brand Analytics/A+ — keep as inference but label "inferred" in UI |
| **Product Pricing** | Probed seller-only (`:278`); vendor → "seller-only" (`:282`) | Product Pricing `getItemOffers`/`getCompetitivePricing` | Pricing role; **seller accounts only** | No vendor support; rate-limited; point-in-time (no history) | **M** | Medium — Buy-Box %, offer/seller counts (the `AsinOfferSnapshot` fields that are written but unused) → powers the **channel/Buy-Box slide** properly |
| **Product Fees** | Probed seller-only w/ price (`:290`) | Product Fees `getMyFeesEstimateForASIN` | Fees role; seller only | Estimate not actual; needs a price input | **S** (mostly wired in `estimate_fba_fee_for_asin`) | Medium — true contribution margin per ASIN vs the current estimate→unavailable fallback |
| **A+ Content** | Probed (`:306`) | A+ Content API `searchContentDocuments` | Brand Registry / A+ role | Content presence only, not quality | **S** (already integrated) | Medium — already feeds content-health; extend to A+ coverage % across catalog |
| **Finance Reports** | Probed via `list_financial_event_groups` (`:256`) | Finances API events | Finance role | Event-level, high volume, complex reconciliation | **L** | High — **real net proceeds, fees, refunds, reimbursements** → moves deck from revenue to **profit**; biggest differentiator vs Helium10 |
| **Settlement Reports** | Probed via `GET_V2_SETTLEMENT_REPORT_DATA_FLAT_FILE` (`:251`) | Reports API settlement flat file | Reports/Finance role | Bi-weekly cadence; can't request arbitrary windows (Amazon pushes them) | **M** | High — authoritative settled cash; pairs with Finance for margin truth |
| **Catalog Items** | Probed (`:268`) | Catalog Items 2022-04-01 | Catalog role | Per-ASIN; rate-limited | **S** (integrated) | Already core to enrichment — keep |
| **Listings** | Probed seller+SKU (`:319`) | Listings Items API | Listings role; **seller_id + SKU** | Seller only; needs SKU mapping | **M** | Medium — listing quality/issues, suppressed-listing detection → an "operational hygiene" slide |

**Prioritization:** Brand Analytics (search/market share) and Finance+Settlement (profit) are the two highest-value gaps because they unlock slides the deck **cannot currently produce** (market share is `None`; deck is revenue-only). Data Kiosk is the strategic long-term consolidation but is the heaviest (async query lifecycle). Recommended order: **Brand Analytics → Finance/Settlement → Data Kiosk → Listings/Pricing**.

**Async report polling**: Brand Analytics and Settlement are Reports-API documents (request → poll `processingStatus` → download). Reuse the **same poll-loop shape** as the sync windows already in `_process` (`:3372`); factor a `ReportPoller` helper. Data Kiosk needs its own GraphQL submit/poll. These run inside the orchestrator phase `collecting_source_data`, gated by capability.

**Caching**: persist fetched signal blocks keyed `(account, marketplace, source, period)` with a TTL (Brand Analytics is weekly — cache a week; Settlement is bi-weekly). A `brand_signal_cache` table (JSONB payload, `fetched_at`, `expires_at`) avoids re-pulling multi-MB reports per analysis. Per-tenant credentials/roles flow through the existing `_create_sp_api_client` + capability probe — providers must **never** call a source whose capability is `False` (the missing-role reason is already captured in `last_error_by_capability`).

**Parallelize enrichment (R-11/P-11)**: `_fetch_catalog_via_market_research` runs catalog+fees+aplus serially per ASIN (`sources.py:581-583`). Wrap in a bounded `asyncio.Semaphore(8)` + `asyncio.gather` over ASINs; respects SP-API rate limits while cutting wall-clock from O(N) to O(N/8).

### 4.4 Brand Pulse → Weekly Brand Intelligence (R-7) — **REBUILD**

Brand Pulse must be **rebuilt**, not refactored: today it stores nothing, so it structurally cannot compute "what changed since last week" — the core requirement. Keep the AnalyticsService primitives (they're correct and shared), throw away the request-time-only delivery model.

**New model `BrandIntelligenceReport`** (migration `023_brand_intelligence.py`) — mirror `ScheduledReportRun` shape:

```python
class BrandIntelligenceReport(Base):
    __tablename__ = "brand_intelligence_reports"
    id, organization_id(FK CASCADE, index), account_id(FK SET NULL, index)
    period_start: Date; period_end: Date; window_days: int
    cadence: str                      # weekly
    status: str                       # pending|aggregating|diffing|generating|completed|failed (indexed)
    progress_step, error_message
    snapshot: JSONB                   # deterministic metrics for THIS period (top/declining asins, ads, kpis)
    diff: JSONB                       # week-over-week deltas computed vs the previous report's snapshot
    intelligence: JSONB              # LLM output: market_changes, brand_evolution, competitor_activity,
                                      #   opportunities, risks, product_trends, category_movements, recommendations
    generated_by: str                 # 'scheduler' | 'manual'
    created_at, completed_at
    __table_args__ = (UniqueConstraint("account_id","period_start","period_end",
                      name="uq_bir_account_period"),
                      Index("ix_bir_account_period_end","account_id","period_end"))

class BrandIntelligenceSchedule(Base):     # opt-in weekly automation per account/org
    id, organization_id, account_ids: JSONB, language, day_of_week, is_enabled, next_run_at(indexed), timezone
```

**Pipeline** `app/services/brand_intelligence_service.py` (`process_brand_intelligence_run_job(report_id)` via `run_async`):

1. **Aggregate** (`status=aggregating`): reuse `AnalyticsService.compute_dashboard_kpis` / `asin_sales_breakdown` / `compute_advertising_metrics` for `[period_start, period_end]` → write `snapshot`. (Same primitives as `brand_pulse_service.py` — extract the shared computation into a `BrandSnapshotBuilder` so Pulse-logic isn't duplicated against AnalyticsService anymore; **single source for decline thresholds**.)
2. **Diff** (`status=diffing`): load the previous report for the same `account_id` (`ORDER BY period_end DESC LIMIT 1`), compute deltas per ASIN / category / ads → `diff`. New entrants, dropped ASINs, accelerating declines, category share moves. This is the part Pulse cannot do today.
3. **Generate intelligence** (`status=generating`): single Anthropic call (reuse the narrative-service pattern — Anthropic, JSON-validated, deterministic fallback). Prompt is fed `snapshot` + `diff` + capability-gated competitor/market signals (Brand Analytics search share when available). Output JSON sections: `market_changes, brand_evolution, competitor_activity, emerging_opportunities, risks, product_trends, category_movements, strategic_recommendations` — each item carrying **Source / Confidence / Evidence** (the pattern already proven in `build_pulse_recommendations` and surfaced in the Brand Pulse UI).
4. **Persist** `status=completed`, emit a notification (§4.5).

**Weekly automation** — reuse the scheduled-reports machinery, don't invent a new scheduler:
- Beat task `scan_brand_intelligence_due` (`crontab(minute="*/15")`) selects `BrandIntelligenceSchedule WHERE is_enabled AND next_run_at <= now`, creates a `BrandIntelligenceReport(status=pending)`, enqueues `process_brand_intelligence_run.delay(report_id)`, advances `next_run_at` by 7 days.
- `recover_stuck_brand_intelligence_runs` (`crontab(minute="*/30")`) mirrors `recover_stuck_scheduled_report_runs`.

**API** `app/api/v1/brand_intelligence.py` (replaces `brand_pulse.py`; keep the old route as a 410/redirect for one release):

```
GET  /brand-intelligence/reports?account_id=&limit=        → list (newest first)
GET  /brand-intelligence/reports/{id}                       → full report (snapshot+diff+intelligence)
GET  /brand-intelligence/reports/latest?account_id=         → most recent completed
POST /brand-intelligence/generate {account_ids,window_days} → on-demand run (status pending; poll like BA)
GET  /brand-intelligence/schedule / PUT (upsert) / DELETE   → weekly opt-in config
```

### 4.5 In-app notifications (R-8) — NEW, polling first

Recommendation: **polling unread-count, not SSE/WebSocket.** The frontend already polls jobs every 3000ms; a `GET /notifications/unread-count` on the same cadence is the simplest robust option. No new infra (no Redis pub/sub, no sticky sessions behind Render's load balancer, no WebSocket lifecycle). SSE can come later behind the same API.

**Migration `024_notifications.py`** — mirror the `Alert` shape (unread partial index):

```python
class Notification(Base):
    __tablename__ = "notifications"
    id; organization_id(FK CASCADE, index); user_id(FK CASCADE, index, nullable)  # null ⇒ org-wide
    kind: str            # brand_analysis_completed | brand_analysis_failed | brand_intelligence_ready | ...
    title: str; body: Text
    resource_type: str   # brand_analysis_job | brand_intelligence_report
    resource_id: UUID    # deep-link target
    severity: str        # info|success|warning|error
    is_read: bool = False
    dedup_key: str       # f"{kind}:{resource_id}" — idempotent emission
    created_at; read_at
    __table_args__ = (
        UniqueConstraint("organization_id","dedup_key", name="uq_notifications_org_dedup"),
        Index("ix_notifications_user_unread","user_id","created_at",
              postgresql_where=text("is_read = false")),   # same trick as ix_alerts_rule_unread_triggered_at
    )
```

**Service** `app/services/notification_service.py`:

```python
async def emit(db, *, org_id, user_id, kind, title, body, resource_type, resource_id, severity, dedup_key):
    # pg_insert(...).on_conflict_do_nothing(constraint="uq_notifications_org_dedup")  → idempotent
```

**Emission points** (terminal transitions only): in `orchestration.process_brand_analysis_job` after final commit for `completed`/`completed_with_limitations`/`failed`, and in `brand_intelligence_service` on completion. Emit **inside the worker's own session**, after commit, dedup by `f"{kind}:{job_id}"` so retries don't double-notify.

**API** `app/api/v1/notifications.py`:

```
GET    /notifications?unread_only=&limit=&offset=     → list
GET    /notifications/unread-count                    → {"count": n}   ← the polled endpoint
POST   /notifications/{id}/read                       → mark one read
POST   /notifications/read-all                        → mark all read
DELETE /notifications/{id}                            → dismiss
```

**Delivery decision table:**

| Option | Infra cost | Render fit | Latency | Verdict |
|---|---|---|---|---|
| **Polling unread-count** | none (reuses query loop) | perfect | ≤3s | **Chosen** |
| SSE (`text/event-stream`) | per-conn open request, needs broadcast bus across workers | awkward (multiple web instances) | instant | Phase 2 |
| WebSocket | sticky sessions / Redis pub-sub | poor on Render static-ish topology | instant | Avoid |

### 4.6 Storage & dead-weight cleanup (R-11, R-12)

- Flip default `BRAND_ANALYSIS_STORAGE_BACKEND` to `s3` when creds present; keep `db` as small-file fallback. Add `BrandAnalysisStorage.delete(ref)` (`delete_object` for `s3`) and call it from delete + GC.
- `AsinOfferSnapshot`: either (a) add `UniqueConstraint(account_id, asin, observed_date)` + upsert + a read path that feeds the Buy-Box slide (currently hardcoded unavailable `service.py:1748-1759`), or (b) delete the write (`sources.py:615`) and the table. Given Pricing is seller-only and the slide is gated, **(b) unless Pricing integration (R-9) lands** — don't keep a write-only table.

---

## 5. Estimated Effort

| Workstream | Effort | Notes |
|---|---|---|
| R-1 Monolith decomposition (incl. pptx theme/registry seam) | **8–10 dev-days** | Mechanical but wide; gated on test coverage |
| R-2..R-5 Job lifecycle (cancel/recovery/cleanup/loop) | **5–6 dev-days** | Migration + 2 beat tasks + endpoint + cooperative cancel |
| R-6 Status consolidation | **1 dev-day** | Folds into R-1 |
| R-7 Brand Intelligence rebuild (model+pipeline+scheduler+API) | **10–12 dev-days** | New LLM step + diff engine + scheduler reuse |
| R-8 Notifications (model+service+API, polling) | **3–4 dev-days** | |
| R-9 Data coverage (provider layer + Brand Analytics + Finance/Settlement + parallelize) | **10–14 dev-days** | Brand Analytics + Finance are the bulk; Data Kiosk deferred |
| R-11/R-12 Storage/dead-weight | **2 dev-days** | |
| **Total (backend)** | **~39–49 dev-days** (~8–10 weeks, 1 engineer) | Excludes PPTX visual redesign (PPTX agent) and FE (frontend agent) |

Sequencing: **R-1 → R-6 → R-2..R-5 → R-8** (foundation), then **R-7** and **R-9** in parallel, **R-11/R-12** as cleanup.

---

## 6. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| **Decomposition regresses the deck** (subtle import/order coupling). | Lock behaviour first: `validate_pptx_bytes` fingerprint + golden-deck text snapshot test before moving anything; move-and-re-export, run tests between each step. |
| **`revoke(terminate=True)` doesn't stop an asyncio coroutine mid-call.** | Defence in depth: cooperative `cancel_requested` flag checked at every phase boundary + heartbeat + recovery beat task that force-finalizes stale jobs. Don't rely on revoke alone. |
| **Brand Analytics/Settlement gated by Brand Registry** — many tenants won't have it. | Provider layer is capability-gated; absent → section omitted (the "no data → no slide" requirement). Surface the missing role in the limitation summary (already captured in `last_error_by_capability`). |
| **Data Kiosk async query lifecycle** adds a long-poll that can stall the job. | Time-boxed poll with a hard cap; on timeout, omit the Data Kiosk signal and continue (degraded, not failed). Run last so it never blocks core metrics. |
| **LLM cost/latency on weekly intelligence** at scale (per-account weekly). | One call per report, JSON-validated, deterministic fallback (reuse narrative pattern); cache aggregated signals; only run for opted-in `BrandIntelligenceSchedule` rows. |
| **Thread fallback removal** could drop jobs if Celery is down. | Keep a fallback but make it tracked: write a `pending`/`celery_task_id=NULL` row and let `recover_stuck_brand_analysis_jobs` re-enqueue, instead of an untracked daemon thread. |
| **S3 default flip** breaks local/CI without creds. | `BrandAnalysisStorage` already silently falls back to `db` (`storage.py:71`); keep that, gate the default on creds-present. |
| **Notification spam** on retries. | `on_conflict_do_nothing` on `(org, dedup_key)`; emit only on terminal transition, after commit. |
| **Migrations on a large `artifact_data` table** (adding columns locks). | New columns are nullable with server defaults (no rewrite); `CREATE INDEX CONCURRENTLY` for the new indexes. |

---

## 7. Rebuild vs Improve — verdict per area

- **Monolith** → **Refactor** (mechanical decomposition; logic is sound, only the packaging is wrong).
- **Job lifecycle** → **Refactor + extend** (state machine + cancel/recovery on the existing row).
- **PPTX builder** → **Refactor the seam** (extract theme/strings/registry) so the PPTX agent can redesign on top; the rendering layer itself is the PPTX agent's call.
- **Brand Pulse** → **Rebuild** as Brand Intelligence (storage-less design can't meet the week-over-week requirement; primitives are reused, delivery model is replaced).
- **Capability probe** → **Improve** (good bones; close the probe-vs-consume gap by wiring Brand Analytics/Finance into the provider layer).
- **Notifications** → **New** (none exists; mirror the `Alert` table shape).
- **Storage** → **Improve** (flip default to S3, add delete + GC).
