# Inthezon — Development Plan

> **Updated 2026-05-28.** Aligned with `docs/planning/Avanzamento tool Niuexa new.xlsx` (last updated by product 2026-05-21).
>
> **Current state on master:** `26 🟢 / 5 🟡 / 0 🔴`. The 5 remaining 🟡 are all blocked externally — see _External blockers register_ at the bottom.

## How to read this document

The **Excel** (`docs/planning/Avanzamento tool Niuexa new.xlsx`, sheet `Foglio1`) is the **primary source of truth** for feature status. It is updated by the product owner and reflects what is delivered, what is blocked, and the rationale per item. This document is the **technical decomposition** of that backlog: it groups features into delivery waves based on dependencies (internal vs. external), and only spells out implementation prompts for items that are still open.

When updating status, update the Excel first, then sync this document.

Status legend:

- 🟢 — delivered, backend + UI integrated
- 🟡 — partially delivered; backend logic present but blocked by an external dependency (credentials, third-party config, product decision)
- 🔴 — not started

---

## Current state (2026-05-28)

| # | Feature (Excel) | Status | Note |
|---|---|---|---|
| 1 | Connessione Centralizzata degli Account | 🟢 | UI Accounts + PUT /api/v1/accounts/{id}; remember to rename after connection |
| 2 | Gestione OTP | 🟢 | Not all managed accounts connected yet — rollout ongoing |
| 3 | Dashboard dello Stato degli Account | 🟢 | New `ads_connection_state` distinguishes token/profile/key/auth issues |
| 4 | Download Pianificato dei Rapporti di Vendita | 🟢 | |
| 5 | Estrazione del Rapporto di Inventario | 🟢 | `GET_FBA_MYI_ALL_INVENTORY_DATA` + Inventory Summaries fallback |
| 6 | Estrazione dei Dati Pubblicitari/PPC | 🟡 | **Blocked**: missing Amazon Ads OAuth refresh tokens + profile_id per account |
| 7 | Monitoraggio BSR | 🟢 | |
| 8 | Raccolta Dati sui Competitori | 🟢 | Resilient discovery; per-ASIN errors preserved in `fetch_errors` |
| 9 | Estrazione Dati sugli Ordini | 🟢 | Headers + items on `orders`/`order_items`; `/reports/orders` paginated |
| 10 | Conservazione a Lungo Periodo dei Dati | 🟢 | Auto-partitioning via migration 023 + `manage_partitions` task (Wave C) |
| 11 | Confronto Periodo su Periodo | 🟢 | Uses SOT `DAILY_TOTAL_ASIN`; deterministic tests cover 2025 |
| 12 | Dashboard di Performance Unificata | 🟢 | |
| 13 | Confronto Cliente vs Competitor | 🟢 | Tolerates partial data; `overall_score=None` when uncomparable |
| 14 | Visualizzazione Analisi dei Resi | 🟡 | `/analytics/returns` returns FBA data; vendor returns expose `not_available` (API does not provide) |
| 15 | Esportazione in Excel | 🟢 | `/exports/excel-bundle` + `/exports/excel`; tests pass |
| 16 | Integrazione con Google Sheets | 🟢 | Existing endpoints + UI; needs end-to-end revalidation post-deploy |
| 17 | Generazione di Report in PowerPoint | 🟢 | Double-count bug fixed; i18n it/en; AOV/ASP/ASIN scope in deck |
| 18 | Consegna dei Rapporti Programmata | 🟡 | **Blocked**: SendGrid not configured ops-side. Errors distinguish missing key vs. empty recipients vs. SendGrid reject |
| 19 | Aggiornamenti in Massa delle Liste di Prodotti | 🟢 | `POST /catalog/bulk-update` with per-row `BulkResult` + audit log |
| 20 | Gestione dei Prezzi | 🟢 | `POST /catalog/prices` with audit log |
| 21 | Aggiornamenti sulla Disponibilità/Inventario | 🟢 | `PATCH /catalog/products/{asin}/availability` |
| 22 | Gestione delle Immagini | 🟢 | `POST /catalog/products/{asin}/images` (S3 + SP-API patch) |
| 23 | Previsione delle Vendite | 🟡 | Prophet + horizon caps + MAPE/RMSE present; forecast now labeled revenue (not units). Excel note: "non è realistico" — accuracy improvement pending |
| 24 | Previsione delle Tendenze dei Prodotti | 🟢 | 9 tests; sales/units/BSR score + deterministic fallback; `declining_fast` alert |
| 25 | Suggerimenti per l'Ottimizzazione delle Inserzioni | 🟢 | |
| 26 | Valutazione della Qualità delle Immagini | 🟢 | |
| 27 | Raccomandazioni Strategiche | 🟢 | Account + ASIN scope; XLSX export `/exports/recommendations-xlsx` |
| 28 | Sommario Quotidiano | 🟢 | |
| 29 | Correlazione dati Adv con dati organici | 🟢 | `GET /api/v1/analytics/ads-vs-organic`; `organic_sales = total − ad_attributed`, clamped ≥ 0 |
| 30 | Nomina account | 🟡 | **Blocked**: real customer names needed. UI flags placeholders; rename via PUT or `backend/scripts/rename_amazon_account.py` |
| 31 | Brand Analysis | 🟢 | 16-slide PPTX validated; `/brand-analysis/{id}/download`; e2e covered |

**Current Excel on master:** 26 🟢 / 5 🟡 / 0 🔴.

The 5 remaining 🟡 are externally blocked (see register below). No engineering 🔴 left.

---

## Roadmap — delivery waves

The original "Phase 1–5" structure assumed an April-to-July ramp that no longer reflects reality. The work that remains splits cleanly along **what is blocked externally** vs. **what we can ship now**.

### Wave A — Catalog bulk operations (delivered by PR #2, pending merge)

**Items:** 19, 20, 21, 22 (all 🔴 → 🟢 once merged).
**Branch:** `claude/catalog-management-validation-and-polish` (PR #2).
**Delivered:** bulk listing updates from Excel, price push to SP-API, availability toggle, image upload (S3 + listings patch), all with per-row `BulkResult` error handling, Zod + Pydantic validation, audit log table (`catalog_change_log`), confirmation dialogs in UI, i18n it/en. 19 unit tests cover schema validation + service success/failure paths.
**Pending:** live SP-API smoke test in staging (no real Amazon call covered by mocks).

### Wave B — External unblockers

These items are 🟡 because the code is ready but an external input is missing.

| Item | Blocker | Action owner |
|---|---|---|
| 6 — Advertising/PPC | Amazon Ads OAuth refresh token + `profile_id` for each managed account | Account managers + client |
| 18 — Scheduled report delivery | SendGrid API key in env | Ops |
| 30 — Account naming | Real client names to replace placeholders ("real", "second account") | Account managers |
| 2 — OTP (residual) | Onboarding remaining managed accounts | Account managers |

No engineering work blocks Wave B; once unblocked, each is validated by running an existing flow end-to-end and turning the Excel cell 🟢.

### Wave C — Internal hardening (this PR)

Items addressed by branch `claude/docs-alignment-and-internal-hardening`:

1. **Docs realignment** — this rewrite, plus `TECHNICAL_ARCHITECTURE.md` patches and `[DONE]` markers in `inthezon_user_stories.md`.
2. **Automated partitioning** — converts `sales_data`, `advertising_metrics`, `advertising_metrics_by_asin`, `bsr_history` from plain tables to monthly-partitioned tables; enhances `workers/tasks/maintenance.py::manage_partitions` to auto-create future months and drop expired partitions. This closes the operational risk under item 10 (Excel note: "ripartizionamenti rischiosi vanno eseguiti manualmente").
3. **Observability hardening** — JSON structured logging with request-ID context; Sentry SDK init that degrades gracefully without a DSN; split `/health` (liveness) + `/health/ready` (DB + Redis); `.env.example` entries for `SENTRY_DSN`, `LOG_LEVEL`, `LOG_FORMAT`.

After merge, item 10 moves to 🟢; observability + docs are not separate Excel items but are visible to engineers reading the repo.

### Wave D — Forecast realism (item 23)

**Why separate:** the Excel note on item 23 is "non è realistico" — the product owner is signaling the model output is not trustworthy, not that the pipeline is broken. This is a modelling/UX problem, not a plumbing problem.

**Direction (not committed — requires PM decision before scoping):**
- Calibrate Prophet on per-ASIN seasonality; flag insufficient-history ASINs (< 90 days) instead of generating low-confidence forecasts.
- Surface MAPE/RMSE on every forecast card so users see confidence, not just a number.
- Decide with PM whether to add a units-forecast variant alongside the existing revenue-only output.

---

## External blockers register

When an item in Wave B unblocks, update the Excel row's status and verify the existing endpoint/UI works against real data. No code is needed.

| Blocker | Affects | Owner |
|---|---|---|
| SendGrid API key in `SENDGRID_API_KEY` env | 18 | Ops |
| Amazon Ads OAuth refresh token + profile_id per account | 6 | Account managers + client |
| Real client names (replace "real", "second account") | 30 | Account managers |
| OTP enrollment for remaining managed accounts | 2 (residual) | Account managers |
| Vendor returns API access (not exposed by Amazon today) | 14 (vendor scope) | None — feature documents `not_available` |

---

## Engineering operating notes

- **Source of truth:** sales/units/orders aggregations must use `DAILY_TOTAL_ASIN` (not joins on raw `sales_data` + per-ASIN rows). The PPT and Excel export bugs that motivated this rule are fixed; do not re-introduce.
- **Partitioning:** after Wave C merges, do not write migrations that add `PRIMARY KEY` on `id` alone for tables in `PARTITION_MANAGED_TABLES`. PostgreSQL requires the partition key (`date`) in the PK; the composite is `(date, id)`.
- **External-call discipline:** Amazon API clients (`sp_api_client.py`, `advertising_client.py`) own their own retry/backoff. Do not duplicate retry logic in callers.
- **Tests:** `pytest` from `backend/` is the gate. Time-series tests should pin dates explicitly (the data reconciliation tests are the reference).
