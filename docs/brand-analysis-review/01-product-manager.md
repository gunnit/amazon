# Brand Analysis & Brand Pulse — Product Manager Review

**Author:** Product Manager Agent
**Date:** 2026-06-09
**Branch:** `master` (commit `156536c`)
**Scope:** Product/UX coherence of Brand Analysis + Brand Pulse, end-to-end. Terminology, input flow, lifecycle (delete/cancel), Brand Pulse repositioning, cross-module IA, in-app notifications.

---

## 0. Executive narrative (the version an exec approves)

Inthezon today ships **four** "brand + account + ASINs → insight" surfaces that a sales engineer or a customer cannot tell apart: **Performance**, **Market Research**, **Brand Analysis**, **Brand Pulse** (`Layout.tsx:33-38`). Two of them (Brand Pulse and Performance) compute the *same numbers from the same primitives* — Brand Pulse is ~90% a re-presentation of `AnalyticsService` (`brand_pulse_service.py:49,63,165`). One of them (Brand Analysis) is a once-a-year PPTX generator dressed up with so much gradient-and-`Sparkles` chrome that it reads as AI-generated. Customers don't have a "I have four brand tools" problem; they have a **"which one do I open on Monday morning?"** problem.

The product fix is not four redesigns. It is **one coherent intelligence ladder**:

| Cadence | Product | Question it answers | Output |
|---|---|---|---|
| **Daily / live** | **Performance** | "How is my account doing right now?" | Live dashboards |
| **Weekly** | **Brand Pulse → "Weekly Brand Intelligence"** | "What *changed* this week, and what should I do about it?" | AI narrative digest + in-app notification |
| **On-demand / competitive** | **Market Research** | "How do I stack up against competitors / a market?" | Comparative report (PDF) |
| **Quarterly / annual** | **Brand Analysis → "Brand Strategy Deck"** | "What is the full-year strategic story for a client review?" | Consulting-grade PPTX |

Each rung has a distinct **cadence**, **audience**, and **artifact**. That is the only durable way to stop them cannibalizing each other. Everything below executes against that ladder.

**Two verdicts up front:**
- **Brand Pulse: REBUILD the product (not just the code).** Its current spec is a thinner Performance dashboard with no reason to exist. Reposition it to the weekly AI intelligence digest — that is a net-new product with its own JTBD, not a refactor.
- **Brand Analysis: IMPROVE the flow + REBUILD the PPTX + the input mental model.** The pipeline, provenance spine, and capability probe are genuinely good engineering. The *input form* and the *deck* are the two things to tear down.

---

## 1. Findings (grounded in code)

### 1.1 Terminology: three "brand" inputs, no clear mental model
The setup form (`BrandAnalysis.tsx:751-852`) asks for, in order:

1. **Brand name** — `field.brandName` = `"Brand name"`, placeholder `"e.g. Zwilling"` (`en.ts:924-925`). This is the deck's subject and title (`_slide_cover`, `service.py:2507`).
2. **Amazon account** — `field.account` = `"Amazon account"`, defaults to `"none"` (`BrandAnalysis.tsx:329,788`). Optional in the UI but **conditionally required**: internal mode rejects `"none"` (`validateForm`, `BrandAnalysis.tsx:404`) and the backend 422s without it (`brand_analysis.py:247-251`).
3. **Scope** — `field.marketType` = `"Scope"` rendered as two `ChoiceTile` cards "Brand" / "ASIN list" (`BrandAnalysis.tsx:803-819`). Means "how to define the ASIN universe," but the label never says so.
4. **Brand or market query** — `field.marketQuery` = `"Brand or market query"`, placeholder `"Defaults to the brand name"` (`en.ts:931-932`). On submit: `market_query: marketQuery.trim() || brandName.trim()` (`BrandAnalysis.tsx:418`) — i.e. **the user types the brand a second time, or leaves it blank to silently mirror field #1.**

So the word "brand" appears as a label or value in **four** of the form's controls (Brand name, Scope→Brand, Brand or market query, plus `marketType.asin` = `"ASIN list"` which *also* duplicates `field.asinList` = `"ASIN list"` verbatim, `en.ts:933,940`). There is no copy anywhere that explains *why* there are two brand text fields.

### 1.2 The Portuguese claim is stale
The brief says "Remove Portuguese texts from Upload External Yearly Market Exports." The frontend discovery agent ran an exhaustive diacritic + PT-function-word scan across pages, components, and i18n → **0 hits**. `it.ts:924-1061` is genuine Italian; `en.ts` genuine English. The upload-panel strings (`mode.manual` = `"Upload external yearly exports"`, `upload.*` at `en.ts:937-952`) are clean English. **There is no Portuguese to remove.** The likely source of the report: an earlier draft, or a screenshot taken with the Italian locale (which an English-only reviewer may have mistaken for Portuguese). The one real i18n bug is unrelated: a hardcoded literal `"Market Tracker 360"` at `MarketTracker.tsx:177`.

### 1.3 Delete exists in API, missing in UI; Cancel missing entirely
- **Delete:** `DELETE /brand-analysis/{job_id}` exists (`brand_analysis.py:329-342`) and `api.ts:1108` wraps it, but **the history list renders no delete control** (frontend map §2: "No delete in UI"). By contrast Market Research *has* per-row delete with `confirm()` (frontend map §4). Brand Analysis is the only one of the three missing it.
- **Cancel:** There is **no cancel concept at all.** A running job can only be left to finish. `DELETE` removes the row but **cannot stop an in-flight Celery task or the fire-and-forget thread fallback** (`brand_analysis.py:262-274`), and `_process` doesn't re-check job existence before its final commit (backend map §11) — so deleting a running job can **resurrect a deleted row**. There is also no `next_retry_at` poller and no stuck-job recovery (backend map §11), so a crashed job hangs in a non-terminal state forever with no UI affordance to clear it.

### 1.4 Brand Pulse is a re-skin of Performance Analytics
`BrandPulseService.build_pulse` (`brand_pulse_service.py:36`) delegates **every number** to `AnalyticsService`: `compute_dashboard_kpis` (`:49` — the same call the dashboard KPI endpoint uses), `asin_sales_breakdown` (`:63,66` — the exact Performance drilldown primitive), `_asin_titles` (`:104`), `compute_advertising_metrics` (`:165`). Pulse-local logic is only: period framing, `_top_asins`/`_declining_asins` with thresholds `-5.0`/`-20.0` **copy-pasted** from `AnalyticsService` (`:25-26`, comment "Mirror AnalyticsService's trend thresholds"), TACOS = `spend/revenue` (`:180`), and a recommendation overlay (`build_pulse_recommendations`, `:95`). **No table, no job, no persistence — recomputed live per request** (`brand_pulse.py` single GET). It does carry the one good seed for the future: Source/Confidence/Evidence recommendation badges (frontend map §3), which is the only place the MEMORY "AI w/ Source/Confidence/Evidence" direction exists today.

### 1.5 Brand Analysis "feels AI-generated" — concentrated in presentation
Frontend map §10 is precise: decorative `bg-gradient-to-br` with no information (`:706,927,310`), `Sparkles` as an AI signifier in nav + hero + "Recommended actions" (`:707,1167`), ~26 lucide icons imported, card-in-card-in-card density, a 6-up KPI grid tone-coded by lookup table not by value, redundant progress (linear bar *and* 9-step stepper render the same `progress_pct` simultaneously, `:962,1041`), and "Recommended actions" that are really four nav shortcuts dressed as AI recommendations (`:1163-1197`). Its siblings Brand Pulse (plain cards) and Market Research (functional tables) look like a calmer, more credible product — Brand Analysis is the visual outlier.

### 1.6 The PPTX is mostly a static template, not a dynamic analysis
13 of 15 slides always render in fixed order; only `_slide_channel_gap` and `_slide_market_share` gate on data (pptx map §3). Three slides have **no empty guard** → header-only "broken-looking" tables when the list is empty (`_slide_top_performers`, `_slide_subcategory_performance`, `_slide_concentration_risk`; pptx map §6.1). Projections are **fixed multipliers identical for every brand** (×1.10–1.55, `service.py:1686-1705`). Two slides (`_slide_catalog_audit`, `_slide_approach`) are fully built but **not in the build list — dead code** (pptx map §3). The LLM generates `strengths`, `weaknesses`, `approach_pillars` that are **never rendered** (pptx map §4) — paying tokens for nothing.

### 1.7 The substrate for the new behaviors already exists
- **In-app notifications:** the `Alert` model already has `is_read`, `severity`, `event_kind`, `dedup_key`, `notification_status`, `details` JSONB, `triggered_at` (`models/alert.py:50-86`), and the alerts API already exposes `GET /alerts`, `GET /alerts/unread-count`, `GET /alerts/summary`, and bulk read-mutation (`alerts.py:642,729,600,739`). The frontend nav already has a `Bell` icon at `/alerts` (`Layout.tsx:41`). **In-app notifications are a small extension of an existing system, not a new build.**
- **Weekly automation:** `ScheduledReport` + `ScheduledReportRun` already model `frequency` ("weekly"/"monthly"), `schedule_config` JSONB, `generation_status`/`delivery_status`, `progress_step`, `artifact_*`, and the beat scanner `scan_scheduled_reports_due` + **stuck-run recovery** `recover_stuck_scheduled_report_runs` exist (`scheduled_reports.py:96`). This is the exact pattern Brand Pulse's weekly automation should copy.

---

## 2. Problems Identified (ranked)

| # | Problem | Severity | Evidence |
|---|---|---|---|
| P-1 | **Brand Pulse has no reason to exist** as specced — it's a thinner Performance. Customers won't open both. | **Critical** | `brand_pulse_service.py:49-165` delegates everything to `AnalyticsService` |
| P-2 | **Four overlapping nav entries** with no cadence/audience distinction → choice paralysis, cannibalization. | **Critical** | `Layout.tsx:33-38` |
| P-3 | **Terminology is incoherent** — "brand" appears in 4 controls; `marketQuery` is a redundant second brand field; "Scope" is opaque; "ASIN list" labels two different things. | **High** | `BrandAnalysis.tsx:418,751-852`; `en.ts:924-940` |
| P-4 | **No cancel; no UI delete; deleting a running job can resurrect it.** Users can't clean up or stop work. | **High** | `brand_analysis.py:262-274,329-342`; frontend map §2 |
| P-5 | **PPTX is a static template with empty-table failure modes**, dead slides, wasted LLM tokens, canned projections — not consulting-grade. | **High** | pptx map §3-6 |
| P-6 | **Brand Analysis UI reads as AI-generated**, undermining the "enterprise intelligence" positioning. | **High** | frontend map §10 |
| P-7 | **No completion feedback.** Analysis can take minutes; user must keep the tab open and poll; no notification when done. | **Medium** | polling only, `BrandAnalysis.tsx:369-372`; no notification wiring |
| P-8 | **Stale/incorrect requirement** ("remove Portuguese") risks wasted effort and signals a stale brief. | **Medium** | frontend map §7 |
| P-9 | **No report management** in Brand Analysis (rename, re-run with same config, status filter, no delete). | **Medium** | frontend map §2.7 |
| P-10 | **Onboarding/empty-state is weak** across both — new users see a form, not a "what is this and why" first-run. | **Medium** | `BrandAnalysis.tsx` history empty = Presentation icon; BrandPulse = noAccount Alert |

---

## 3. Recommendations (priority + effort)

> Effort key: XS ≈ <0.5d, S ≈ 0.5–1d, M ≈ 2–4d, L ≈ 1–2w, XL ≈ 3w+. Priorities are product priorities, not just engineering.

### A. Brand Analysis — terminology & flow

| # | Recommendation | Priority | Effort |
|---|---|---|---|
| A-1 | **Kill `marketQuery` as a user-facing field.** Default it server-side to `brand_name`; expose it only as an optional "Advanced → market keyword" override. | **P0** | S |
| A-2 | **Rename the mental model to 3 nouns: Brand · Source · Coverage** (see §3.1). Rewrite all labels/helper copy. | **P0** | S |
| A-3 | **Redesign input as a 2-step flow** (Identity → Scope & Source) with a single primary CTA and a live readiness preview (see §3.2). | **P1** | M |
| A-4 | Remove the stale "Portuguese" task; instead fix `MarketTracker.tsx:177` hardcoded title. | **P2** | XS |

### B. Brand Analysis — lifecycle (delete + cancel)

| # | Recommendation | Priority | Effort |
|---|---|---|---|
| B-1 | **Add delete to the history list** (icon + confirm dialog) wiring the existing `DELETE` endpoint. Block delete while running (offer Cancel instead). | **P0** | XS |
| B-2 | **Add Cancel** — a cooperative-cancellation contract: new status `cancelling`→`cancelled`, a `cancel_requested_at` column, a checkpoint guard in `_process`, and a `POST /{job_id}/cancel` endpoint (see §4.3). | **P1** | M |
| B-3 | **Add stuck-job recovery + GC** mirroring `recover_stuck_scheduled_report_runs`; poll `next_retry_at`; purge artifacts/`asin_offer_snapshots` on delete. | **P2** | M |

### C. Brand Pulse → Weekly Brand Intelligence

| # | Recommendation | Priority | Effort |
|---|---|---|---|
| C-1 | **Reposition completely.** New product thesis, JTBD, IA, terminology, report structure (see §5). | **P0** | — (product) |
| C-2 | **Persist it as a weekly job** modeled on `ScheduledReportRun`; generate an AI narrative digest, not a live recompute. | **P0** | L |
| C-3 | **Weekly automation** via the beat scanner pattern; one digest per account per ISO week; idempotent on `(account, iso_week)`. | **P1** | M |
| C-4 | **Differentiate hard from Performance & Market Research** (see §6 matrix); remove duplicated decline thresholds by importing from `AnalyticsService`. | **P1** | S |

### D. Cross-module IA & notifications

| # | Recommendation | Priority | Effort |
|---|---|---|---|
| D-1 | **Group the nav into a "Brand Intelligence" section** (Pulse, Strategy Deck, Market Research) separate from operational "Analytics" (Dashboard, Performance, Advertising, Forecasts). | **P1** | S |
| D-2 | **In-app notifications** by extending the `Alert` table with a `system`/`report_ready` event kind + a bell dropdown; **no email** (see §4.4). | **P1** | M |
| D-3 | **Rename for clarity:** "Brand Analysis" → **"Brand Strategy Deck"**; "Brand Pulse" → **"Weekly Brand Intelligence"** (nav + i18n only). | **P2** | XS |
| D-4 | **Shared first-run onboarding** card per module (what it is, cadence, who it's for, one CTA). | **P2** | S |

### 3.1 The minimal mental model — 3 nouns

Replace the four "brand" controls with exactly three concepts the user can hold in their head:

| Concept | What it is | UI label (EN) | Default |
|---|---|---|---|
| **Brand** | The subject of the report; the deck title. | **"Brand"** (ph: `"e.g. Zwilling"`) | — (required) |
| **Source** | Where the data comes from. | **"Data source"** → `Connected Amazon account` \| `Upload yearly exports` | Connected account if any exists; else Upload |
| **Coverage** | Which products to include. | **"Products to include"** → `Entire brand` \| `Specific ASINs` | Entire brand |

- **"Market query" disappears from the primary UI.** It becomes an optional, collapsed `Advanced` field labeled **"Market keyword override"** with helper text: *"By default we search Amazon for your brand name. Override this only if your products are sold under a different keyword."* On submit it still maps to `market_query`, defaulting to `brand_name` (no backend change).
- **"Amazon account" becomes the *value* of "Data source," not a separate field** — selecting `Connected Amazon account` reveals the account picker. This removes the "optional-but-conditionally-required" trap (P-3) because the requirement is now structural: you can't pick "Connected account" without picking an account.
- **"Scope" → "Products to include"** with plain options `Entire brand` / `Specific ASINs`. The word "ASIN list" appears exactly once (when `Specific ASINs` is chosen, the field label is "ASINs").

Exact copy table:

| Old (`en.ts`) | New |
|---|---|
| `field.brandName` "Brand name" | "Brand" |
| `field.account` "Amazon account" | (folded into Data source) "Connected Amazon account" |
| `field.mode` "Data source" *(currently unused, en.ts:929)* | "Data source" — now actually used |
| `field.marketType` "Scope" | "Products to include" |
| `marketType.brand` "Brand" | "Entire brand" |
| `marketType.asin` "ASIN list" | "Specific ASINs" |
| `field.asinList` "ASIN list" | "ASINs" |
| `field.marketQuery` "Brand or market query" | (advanced, collapsed) "Market keyword override" |
| `field.marketQueryPlaceholder` "Defaults to the brand name" | "Defaults to your brand name — override only if needed" |

### 3.2 The new input flow (2 steps, not a wall of fields)

```
STEP 1 — Identity
  • Brand                         [____________]  (required)
  • Report language               [EN ▾]
                                              → Continue

STEP 2 — Source & Coverage
  • Data source                   ( ) Connected Amazon account ▾   ( ) Upload yearly exports
        └ if connected → account picker + live readiness chips (2024 ✓ / 2025 ✓ / catalog ⚠)
        └ if upload    → 2 dropzones (2024, 2025)
  • Products to include           ( ) Entire brand   ( ) Specific ASINs → [textarea, n ASINs]
  • ▸ Advanced (collapsed)        Market keyword override [____]
                                              → Generate Strategy Deck
```

Decisions/defaults: account exists → Step 2 preselects "Connected account" + first account; zero accounts → preselects "Upload" (today's `useEffect` at `:346-353` already does this, keep it). The right-rail **Data readiness preview** (`:882-919`) stays — it's genuinely good — but moves to Step 2 so it reacts to the chosen source. One primary CTA at a time (no competing "Analyze" + "Upload external" buttons as today at `:854-878`).

> **Rebuild vs improve:** the *form* is a rebuild (2-step, folded controls); the *pipeline, readiness preview, and validation logic* are improvements/keeps.

---

## 4. Technical Implementation Plan

### 4.1 Terminology & flow (Brand Analysis frontend)
**Files:** `frontend/src/pages/BrandAnalysis.tsx`, `frontend/src/i18n/{en,it}.ts`.
- Replace the single setup `Card` (`:735-880`) with a 2-step layout. Introduce local state `step: 1 | 2`. Keep `marketType`/`asinText` state; **remove the visible `marketQuery` input** and add a collapsed `Advanced` disclosure (`<details>` or a shadcn `Collapsible`) holding the override.
- Collapse account-vs-mode into one `Data source` radio whose "Connected account" branch reveals the account `Select`. Drop `dataSource` inference-by-button; derive `mode` directly from the radio.
- i18n: add the new keys from §3.1 to both `en.ts` (`:919-1061`) and `it.ts`. Delete now-dead keys after migration. Fix `MarketTracker.tsx:177` to use `t(...)`.
- No backend change for terminology: `create` payload still sends `market_query: marketQuery.trim() || brand_name` (`:418`).

### 4.2 Delete in UI (Brand Analysis)
**Files:** `BrandAnalysis.tsx` (history `:1433-1585`), `api.ts` (`deleteJob` already at `:1108`).
- Add a `deleteMutation` (mirror Market Research's), a `Trash2` button per history row, and a confirm dialog. On success invalidate `['brand-analysis']`; if the deleted job is `selectedJobId`, clear it.
- **Disable delete when `runningStatuses.includes(status)`** (`:62-80`); show Cancel there instead (4.3).

### 4.3 Cancel (cooperative cancellation)
**Files:** `models/brand_analysis.py`, new migration, `schemas/brand_analysis.py`, `brand_analysis.py` (API), `brand_analysis_service.py` (processor), `BrandAnalysis.tsx`, `api.ts`.

What "cancel" means to the user: *"Stop this analysis. It won't finish, and it won't produce a deck. I can start a new one."* It is **not** delete (the row stays, visible as `Cancelled`, re-runnable).

- **Model:** add `cancel_requested_at: datetime|None`. Add statuses `cancelling`, `cancelled` to the literal set in `schemas/brand_analysis.py:15-38` and the `running_statuses`/`STATUS_PROGRESS` maps. *(Note: status literal is triplicated today — backend map §2 — fix that drift in the same PR.)*
- **Endpoint:** `POST /brand-analysis/{job_id}/cancel` → if status terminal, 409; else set `cancel_requested_at=now()`, `status="cancelling"`. Return the job.
- **Processor checkpoints:** in `_process` (`service.py:3219+`), after each major stage (`_resolve_adapter`, each `fetch_year`, `enriching_catalog`, before `generating_pptx`, before the final commit) call a helper:
  ```python
  async def _abort_if_cancelled(session, job_id) -> bool:
      row = await session.execute(select(BrandAnalysisJob.cancel_requested_at, BrandAnalysisJob.id)
                                  .where(BrandAnalysisJob.id == job_id))
      r = row.first()
      if r is None:          # row deleted → stop, don't resurrect (fixes P-4 resurrection bug)
          return True
      if r.cancel_requested_at is not None:
          await _set_status(session, job_id, "cancelled", "Cancelled", 100)
          return True
      return False
  ```
  This single helper also **fixes the "delete resurrects a running job" bug** by checking row existence before the final commit.
- **Frontend:** Cancel button in the job panel when `isRunning`; on click → `cancelMutation`; optimistic status → `cancelling`. Poller already running keeps it fresh until `cancelled`.

### 4.4 In-app notifications (NO email)
Reuse the `Alert` substrate rather than building a parallel system.
**Backend files:** `models/alert.py` (or a tiny new `notification.py`), `api/v1/alerts.py`, `brand_analysis_service.py`, `brand_pulse` job (4.5).
- **Decision:** extend the existing `alerts` table with two new `event_kind` values: `report_ready` and `report_failed`. The table already has `is_read`, `severity`, `details` JSONB, `dedup_key`, `triggered_at`, and a partial unread index (`models/alert.py:50-86`). `account_id`/`asin` are nullable so a system notification fits. `rule_id` is currently NOT NULL → make it nullable (migration) so system events need no `AlertRule`, OR seed a singleton `system` rule per org. *(Nullable is cleaner.)*
- On Brand Analysis completion/failure (`process_brand_analysis_job` terminal block, `service.py:3542-3586`) and on Weekly Intelligence run completion, insert an alert: `event_kind="report_ready"`, `severity="info"`, `message="Brand Strategy Deck for {brand} is ready"`, `details={"module":"brand_analysis","job_id":...,"download":true}`, `dedup_key=f"ba:{job_id}"`.
- **Frontend:** the nav already has a `Bell` at `/alerts` (`Layout.tsx:41`). Add a **bell dropdown in the top bar** backed by the existing `GET /alerts/unread-count` (`alerts.py:729`) polled every 30–60s and `GET /alerts?event_kind=report_ready,report_failed`. Clicking an item deep-links to the job and marks read via the existing bulk PATCH (`alerts.py:739`). No new transport (no SSE/websocket needed; the unread-count poll is enough and matches the codebase's polling idiom).
- **Explicitly no email** — `NotificationService.send_email` is not called; this also sidesteps the SendGrid blocker noted in MEMORY.

### 4.5 Brand Pulse → Weekly Brand Intelligence (persisted weekly job)
**New/changed files:** `models/brand_intelligence.py` (new), migration, `services/brand_intelligence_service.py` (new, replacing the thin `brand_pulse_service.py`), `services/brand_intelligence_narrative.py` (LLM), `api/v1/brand_pulse.py` → `brand_intelligence.py`, `workers/tasks/brand_intelligence.py`, beat wiring in `celery_app.py`, `frontend/src/pages/BrandPulse.tsx` → `BrandIntelligence.tsx`.

- **Model** `WeeklyBrandIntelligence` (copy the *shape* of `ScheduledReportRun`, `models/scheduled_report.py:68`):
  ```
  id, organization_id, account_id, iso_week (e.g. "2026-W23"), language,
  status (pending|generating|completed|failed), generated_at,
  metrics JSONB, narrative JSONB, sections JSONB, error_message,
  unique(account_id, iso_week)
  ```
- **Service** computes the week-over-week deltas (reuse `AnalyticsService` primitives — keep, but **import the decline thresholds from `AnalyticsService` instead of copying**, fixing the drift at `brand_pulse_service.py:25-26`), then calls the narrative LLM to produce the sections in §5.3. Persist once per week; the page reads the latest persisted run (no live recompute).
- **Automation:** beat task `scan_weekly_intelligence_due` (Monday 06:00 per org tz) mirroring `scan_scheduled_reports_due` (`scheduled_reports.py`); per account enqueue `process_weekly_intelligence`; idempotent on `(account, iso_week)`; add a `recover_stuck_weekly_intelligence` mirroring `recover_stuck_scheduled_report_runs:96`.
- **Notification:** on completion insert a `report_ready` alert (4.4) → "Your Weekly Brand Intelligence for {account} is ready."
- **API:** `GET /brand-intelligence?account_id=&iso_week=` (latest if no week), `POST /brand-intelligence/run` (manual regenerate), `GET /brand-intelligence/history`.

> **Rebuild verdict:** `brand_pulse_service.py` (190 lines) is **discarded**, not refactored. Its only salvage is the period-framing helpers and the Source/Confidence/Evidence recommendation shape (which becomes the spine of the new narrative).

### 4.6 Cross-module IA
**File:** `frontend/src/components/Layout.tsx:32-42`.
- Introduce section headers in the sidebar:
  - **Analytics:** Dashboard, Performance, Advertising, Forecasts
  - **Brand Intelligence:** Weekly Brand Intelligence, Brand Strategy Deck, Market Research
  - **Operations:** Catalog, Recommendations, Alerts, Settings
- Rename nav i18n: `nav.brandAnalysis` → "Brand Strategy Deck", `nav.brandPulse` → "Weekly Brand Intelligence". Swap the `Sparkles` icon (AI-signifier) for something neutral (`FileText`/`Presentation`).

---

## 5. Brand Pulse repositioning — the full product spec

### 5.1 Thesis
> **Weekly Brand Intelligence** is the Monday-morning AI briefing that tells a brand manager *what changed last week and what to do about it* — across their own brand, the category, and competitors — so they never have to assemble it by hand from five dashboards.

It is **not** a dashboard (that's Performance). It is a **narrative, time-boxed, push-delivered intelligence product**. The unit of value is *"this week's story + this week's actions,"* not "a number you can look up any time."

### 5.2 JTBD & differentiation
- **JTBD:** *"When I start my week, I want to know what materially changed for my brand on Amazon and what I should act on, so I can prioritize without manually diffing dashboards."*
- **Audience:** brand/account manager, weekly cadence.
- **Differentiation matrix** (this is the anti-cannibalization contract):

| | Cadence | Question | Form | AI? | Persisted? |
|---|---|---|---|---|---|
| **Performance** | live/daily | "current state?" | dashboards | no | live |
| **Weekly Brand Intelligence** | weekly | "what changed + do what?" | narrative digest + push | **yes** | **yes (per week)** |
| **Market Research** | on-demand | "vs competitors/market?" | comparative report | partial | yes |
| **Brand Strategy Deck** | quarterly/annual | "full-year strategy story?" | PPTX | yes | yes |

The hard rule that kills overlap with Performance: **Weekly Brand Intelligence never shows a raw current-state KPI without a *delta* and a *narrative*.** If the only thing to say is "revenue is €X," that belongs in Performance. Pulse's job is "revenue fell 12% w/w, driven by your top-3 ASINs losing Buy Box — here's the action."

### 5.3 Weekly report structure (sections)
Each section is **generated only if there's signal** (the same "no data → no section" rule we want in the PPTX). Every claim carries **Source · Confidence · Evidence** (reuse the existing badge concept from BrandPulse recs):

1. **This week in one line** — the headline change (the digest's subject line / notification text).
2. **Brand evolution** — revenue/units/orders/AOV **w/w deltas** with the narrative *why* (not just the numbers).
3. **Product trends** — movers: ASINs gaining/declining fast (reuse `_top_asins`/`_declining_asins` logic), with a one-line reason where derivable.
4. **Category movements** — shifts in subcategory mix / BSR drift (where catalog data supports it).
5. **Competitor activity** — new entrants, price moves, content changes on tracked ASINs (bridges to Market Research data where available; gracefully omitted otherwise).
6. **Emerging opportunities** — under-leveraged ASINs, content gaps, ad headroom.
7. **Risks** — Buy Box loss, inventory/availability, fast decliners, concentration.
8. **Recommended actions** — 3–5 prioritized, evidence-backed actions (Source/Confidence/Evidence) — the only thing the user must read if short on time.

Sections 4 and 5 degrade gracefully (omitted, not empty-stated) when data is thin — exactly the discipline the PPTX lacks today.

### 5.4 Onboarding & UX flow
- **First run (empty):** a single card — *"Weekly Brand Intelligence. Every Monday we analyze what changed for {account} and send you a briefing. Generate your first one now."* → one button → manual `POST /run`.
- **Steady state:** latest week's digest on open; a week-picker to browse history; a "Regenerate" action; a small "Delivered to your notifications" affordance.
- **No account:** the existing noAccount Alert (BrandPulse) — keep.

---

## 6. Cross-module IA — the anti-cannibalization narrative

The four surfaces map cleanly onto an **intelligence ladder by cadence** (the table in §0). The sidebar grouping (§4.6) makes that ladder visible. The one-sentence positioning each:

- **Performance** — *"Your live Amazon control room."*
- **Weekly Brand Intelligence** — *"Your Monday AI briefing on what changed."*
- **Market Research** — *"How you stack up against the market."*
- **Brand Strategy Deck** — *"The client-ready annual strategy story."*

A customer can now answer "which one do I open?" by cadence: daily→Performance, Monday→Intelligence, before a pitch→Market Research, before a QBR→Strategy Deck. That is the coherence an exec signs off on.

---

## 7. Estimated Effort (per workstream)

| Workstream | Effort | Notes |
|---|---|---|
| A. Terminology + 2-step flow (FE + i18n) | **M (3–4d)** | No backend change; mostly `BrandAnalysis.tsx` + i18n |
| B-1. Delete in UI | **XS (0.5d)** | Endpoint exists |
| B-2. Cancel (cooperative) | **M (2–3d)** | Model col + status + checkpoints + FE; also fixes resurrection bug |
| B-3. Stuck-job recovery + GC | **M (2–3d)** | Mirror scheduled_reports patterns |
| C/4.5. Brand Pulse rebuild → Weekly Intelligence (model + service + narrative + automation) | **XL (3–4w)** | Net-new product; LLM narrative is the bulk |
| D-1/4.6. Nav IA regrouping + renames | **S (1d)** | `Layout.tsx` + i18n |
| D-2/4.4. In-app notifications (extend Alert + bell dropdown) | **M (3–4d)** | Reuses alerts table + endpoints |
| D-4. First-run onboarding cards | **S (1d)** | Shared component |
| **PM-owned total** (excludes the separate PPTX-rework + capability-coverage workstreams owned by other agents) | **~6–7.5 weeks** for 1 FE + 1 BE in parallel | |

> The PPTX complete redesign and the data-coverage source integration are large workstreams owned by the PPTX/architecture and backend agents; product-side they are P0/P1 but the engineering estimate lives in those reports. Product input on PPTX: enforce **dynamic-or-omit** per section, add an **executive-summary slide** and a **methodology/limitations appendix** (the `limitations`/`metric_source_registry` data already exists), kill the canned projection slide or ground it in real trend, and surface provenance badges consistently.

---

## 8. Risks & mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| **Repositioning Brand Pulse breaks a workflow someone already relies on** | Med | Med | It has no persistence and is recomputed per request — there is no saved state to lose. Ship behind the same nav slot; redirect old `/brand-pulse` → new. Announce in-app. |
| **Weekly AI narrative hallucinates / invents numbers** | Med | High | Reuse Brand Analysis's hard guardrails: deterministic metrics + `validate_metric_provenance` gate + "forbid number invention" prompt (`service.py:998,2028`); attach Source/Confidence/Evidence to every claim; deterministic fallback when no API key. |
| **Cancel race conditions** (task finishes between request and checkpoint) | Med | Low | Cooperative checkpoints are best-effort; if the deck already completed, surface `completed` not `cancelled`; never hard-kill. The row-existence check also fixes the resurrection bug. |
| **In-app notifications add noise** | Low | Med | Scope event kinds to `report_ready`/`report_failed` only; dedup via existing `dedup_key`; mark-read on click. |
| **Stale brief erodes trust** ("Portuguese" doesn't exist) | High (already happened) | Low | Document the non-issue (done, §1.2); reallocate that effort to the real `MarketTracker.tsx:177` bug. |
| **Nav regrouping disorients existing users** | Low | Low | Keep all routes; only add section headers + renames; add a one-time "we reorganized" tip. |
| **Weekly job storms** (many accounts × weekly) overload workers | Low | Med | Reuse beat scanner's staggering + stuck-run recovery; idempotency on `(account, iso_week)` prevents duplicate runs. |

---

## 9. Rebuild-vs-improve summary

| Sub-area | Verdict | One-line justification |
|---|---|---|
| Brand Analysis input flow | **Rebuild (form)** | Four "brand" controls + opaque "Scope" can't be patched into clarity; needs the 3-noun model + 2 steps. |
| Brand Analysis pipeline / readiness / provenance | **Improve** | Genuinely good engineering — keep, add cancel checkpoints + GC. |
| Brand Analysis PPTX | **Rebuild** | Static template, dead slides, empty-table failure modes, canned projections — not consulting-grade. |
| Brand Analysis FE chrome | **Improve (de-AI)** | Strip gradients/`Sparkles`/redundant progress; logic is fine, presentation is the problem. |
| Brand Pulse (product) | **Rebuild** | As specced it has no reason to exist; reposition to weekly AI intelligence. |
| Brand Pulse (service code) | **Discard** | 190-line re-skin of `AnalyticsService`; only the rec-badge shape survives. |
| In-app notifications | **Improve/extend** | The `Alert` table + endpoints already do 90% of it. |
| Weekly automation | **Reuse** | `ScheduledReportRun` + beat scanner is the proven pattern to copy. |
| Cross-module IA | **Improve** | Keep all four products; group + rename to expose the cadence ladder. |
