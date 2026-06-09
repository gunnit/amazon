# Frontend Discovery — Brand Analysis, Brand Pulse, Market Research

Scope: deep map of the three brand-intelligence frontend surfaces. All paths relative to `frontend/src/`. Line anchors verified against the files as they stand on `master` (commit `156536c`).

Files read in full:
- `pages/BrandAnalysis.tsx` (1771 lines)
- `pages/BrandPulse.tsx` (321 lines)
- `pages/MarketResearch.tsx` (1207 lines)
- `components/market-research/MarketTracker.tsx`, `AIInsights.tsx`, `MarketOverviewStats.tsx`, `PdfExportButton.tsx`, `MarketSearchEmptyState.tsx`, `lib/market-research.ts`
- `services/api.ts` (brand endpoints), `types/index.ts` (brand types), `components/Layout.tsx`, `App.tsx`, `i18n/en.ts`, `i18n/it.ts`

---

## 0. TL;DR for downstream agents

- **Three separate pages, three separate nav entries, three separate mental models.** `Market Research`, `Brand Analysis`, `Brand Pulse` are adjacent in the sidebar (`Layout.tsx:36-38`) and overlap heavily in concept (all "brand + account + ASINs → insights") but share almost no UI and use inconsistent terminology.
- **The "leftover Portuguese text" claim in the task brief is STALE / not reproducible.** There is no Portuguese anywhere in the current frontend (`it.ts` is genuine Italian, `en.ts` genuine English, no accented PT chars, no PT function words in any page/component). See §6 for the exhaustive proof and the one genuine i18n bug found instead (a hardcoded `Market Tracker 360` literal).
- **Brand Analysis is the heaviest, most "AI-generated-looking" surface** (gradient heroes, 6-up KPI tiles, emoji-free but icon-saturated, 9-step stepper, choice tiles, capability matrix grid). Brand Pulse is the cleanest. Market Research is the most feature-dense and the most genuinely useful.
- **Job polling is identical across BrandAnalysis and MarketResearch**: react-query `refetchInterval` returning `3000` while status is running, `false` otherwise. Good reuse candidate.

---

## 1. Routing, navigation, and how a user gets here

`App.tsx`:
- `:15-17` import `MarketResearch`, `BrandAnalysis`, `BrandPulse`.
- `:93` `<Route path="market-research" .../>` — no guard wrapper.
- `:95-101` `brand-analysis` route is wrapped (the JSX wraps `<BrandAnalysis/>` in a guard/flag component — note this asymmetry: Brand Analysis and Brand Pulse are gated, Market Research is not).
- `:103-106` `brand-pulse` route, same wrapper pattern.

`Layout.tsx:36-38` — sidebar nav items, in this order:
```
{ key: 'nav.marketResearch', href: '/market-research', icon: Search },
{ key: 'nav.brandAnalysis',  href: '/brand-analysis',  icon: Sparkles },
{ key: 'nav.brandPulse',     href: '/brand-pulse',     icon: Activity },
```
- Three sibling top-level items. The `Sparkles` icon for Brand Analysis is the canonical "AI feature" icon and reappears as the page hero glyph (`BrandAnalysis.tsx:707`) and in "Recommended actions" (`:1167`) — a tell (see §7).
- Nav labels (`en.ts:880-881`): `'nav.brandAnalysis': 'Brand Analysis'`, `'nav.brandPulse': 'Brand Pulse'`.

---

## 2. Brand Analysis — full UX flow, step by step

`pages/BrandAnalysis.tsx`. This is the deck-generation flow (output = downloadable PPTX).

### 2.1 Local state (`:328-339`)
`brandName`, `selectedAccount` (default `'none'`), `language` (`'en'|'it'`), `dataSource` (`'internal'|'manual'`), `marketType` (`'brand'|'asin'`), `marketQuery`, `asinText`, `selectedJobId`, `file2024`, `file2025`, `showAdvancedUpload`, `activeTab` (`'overview'|'data'|'files'`).

### 2.2 Data queries
- `accounts` — `accountsApi.list()` (`:341-344`).
- `jobsQuery` — `brandAnalysisApi.list()`, history list (`:360-363`).
- `selectedJobQuery` — `brandAnalysisApi.get(id)`, **polls every 3000ms while status ∈ runningStatuses, else stops** (`:365-373`).
- Effect (`:346-353`): if zero accounts → force `dataSource='manual'`; else auto-select first account.

### 2.3 The setup form (left card, `:735-880`)
Header band: gradient-tinted muted header with a `Play` icon chip + "New analysis" title + description (`:736-748`).
- **Identity row** (`:751-797`): three-column grid:
  - `brand-name` Input with a leading `Search` icon (`:754-766`). Label `brandAnalysis.field.brandName` = **"Brand name"**, placeholder **"e.g. Zwilling"**.
  - Language `Select` (English / Italiano), `Languages` icon (`:768-780`).
  - Account `Select` (`:781-796`). First item is `value="none"` → **"Select account"** (`brandAnalysis.field.accountPlaceholder`). Label `brandAnalysis.field.account` = **"Amazon account"**.
- Divider (`:800`).
- **Scope choice tiles** (`:803-819`): label `brandAnalysis.field.marketType` = **"Scope"**. Two `ChoiceTile`s (custom component `:1592-1629`):
  - `brandAnalysis.marketType.brand` = **"Brand"** (icon `Search`).
  - `brandAnalysis.marketType.asin` = **"ASIN list"** (icon `ListChecks`).
- **Conditional input** (`:822-852`):
  - If scope = brand → single `market-query` Input. Label `brandAnalysis.field.marketQuery` = **"Brand or market query"**, placeholder **"Defaults to the brand name"**.
  - If scope = asin → a `<textarea>` (raw, not shadcn) for the ASIN list, monospace, with a live count badge **"{n} ASINs"** (`:840-842`). Placeholder = **"One ASIN per line; or separated by commas / spaces"**.
- **Action row** (`:854-878`): primary `Analyze brand` button (`brandAnalysis.cta.analyze`) + secondary outline `Upload external yearly exports` button (`brandAnalysis.cta.uploadExternal`).

### 2.4 Right card — "Data readiness" preview (`:882-919`)
Emerald `ShieldCheck` icon chip. Renders `readinessItems` (`:687-697`) as `ReadinessRow`s:
- `account` (account connection state), `2024`, `2025` (per-year coverage), `catalog` (enrichment).
- Each row is a left-border-accented tile colored by state (`readinessTone` `:224-229`, `ready`=emerald, `warning`=amber, `missing`=rose, `unknown`=muted) with a `ReadinessBadge`.
- "Optional fields missing" block at bottom renders missing-field badges (`:901-917`).

### 2.5 Submit behaviour — `handleAnalyze` (`:488-502`)
1. `validateForm()` (`:401-408`): brand name required; if scope=asin, ≥1 ASIN; if internal source, an account must be selected.
2. `createMutation` POSTs `/brand-analysis` (`:410-432`) → sets `selectedJobId`.
3. **Branch on mode**: if internal → immediately `startMutation` (`/brand-analysis/:id/start`). If manual → `setShowAdvancedUpload(true)` + `setActiveTab('files')` (forces the user into the upload tab).

### 2.6 Selected-job panel (`:923-1415`) — only when `selectedJobId` set
Gradient header band (`:926-1008`):
- `StatusPill` (`:252-271`) — badge with spinner/check/alert icon by status group.
- Data-source badge (Internal vs Upload), market-type badge.
- `h2` brand name + `progress_step` subtext.
- Linear `Progress` bar with `{progressPct}%` (`:962-973`).
- Right side: `Start processing` / `Re-run` button + `Download PPTX` button when `download_ready` (`:976-1006`).

Body (`:1010-1414`):
- Loading line while `selectedJobQuery.isLoading` (`:1011-1016`).
- **Status banners** (`:1018-1039`): `waiting_for_user_action` → warning Alert with fallback banner; `error_message` → destructive Alert; `errorCode` → info Alert. Error codes are translated via `brandAnalysis.errorCode.<code>` (`:396-399`).
- **Pipeline stepper** (`:1041-1056`, component `:1662-1728`): 9 steps from `progressSteps` (`:135-145`) — capability → preflight → resolving → yearly → catalog → metrics → narrative → pptx → completed, each with a `pct` threshold. Steps render done/active/pending with emerald/primary/dashed styling.
- **Tabs** (`:1058-1412`): three tabs.
  - **overview** (`:1075-1198`): 6-up `KpiTile` grid (Revenue 2025/2024, YoY %, Revenue market share, Active ASINs, Inactive ASINs) — or `EmptyHint` if no metrics. Then 3 `InsightTile`s (Market / Content gaps / Seller-Buy Box). Then **Recommended actions** grid (`:1163-1197`) — up to 4 clickable cards from `recommendedActions` (`:643-685`): Sync Amazon, Check connection, Provide ASIN list, Upload external.
  - **data** (`:1200-1322`): repeats the `readinessItems` rows, then a **capability matrix** grid (`:1213-1260`) of up to 11 capabilities (sales_and_traffic, data_kiosk, brand_analytics, brand_registry, product_pricing, product_fees, aplus, finance_reports, settlement_reports, catalog_items, listings) each as an emerald/rose tile. Then missing-permissions Alert, "Deck limitations" list, optional-missing badges.
  - **files** (`:1324-1411`): the **upload panel** (see §2.7).

### 2.7 "Upload External Yearly Market Exports" panel (the brief's panel of interest)
Lives in the **files tab** (`:1324-1411`) and as a legacy standalone card (`:1417-1431`, only when `showUploadZone && !selectedJobId`).
- Info strip explaining it's a fallback (`brandAnalysis.upload.description` = *"Advanced fallback for generic yearly product exports. Use CSV/XLSX with at least ASIN and revenue columns."*, `en.ts:1055`).
- Two file cards, one per year `[2024, 2025]` (`:1338-1410`). Each card:
  - shows a `FileSpreadsheet` icon, **"{year} product export"** title (`brandAnalysis.upload.yearExport`), and either **"Ready ({rows} rows)"** or **"Not uploaded yet"**.
  - a `Ready`/`Missing` badge.
  - a native `<Input type="file" accept=".csv,.xlsx,.xls">` + an `Upload {year} export` button calling `handleUpload(year)` (`:504-508`) → `uploadMutation` POSTs `/brand-analysis/:id/upload/:year` as multipart (`:434-449`).
- Section title `brandAnalysis.upload.title` = **"Upload external yearly market exports"** (`en.ts:1054`). IT: **"Carica export annuali di mercato esterni"** (`it.ts:1058`).
- `canStart` (`:382`) requires either internal mode OR **both** 2024+2025 files present (`hasBothManualFiles`, `:379`).

### 2.8 History list (`:1433-1585`)
- Card with `History` icon. Empty state (`:1453-1459`): centered `Presentation` icon in a muted circle + "No analyses yet…".
- **Desktop**: a faux-table built from CSS grid `grid-cols-[1.6fr_1fr_1fr_120px_64px]` (`:1463-1551`) — columns Brand name / Data source / Automation progress / Last sync / (download). Rows are `role="button"` divs with keyboard handlers. Inline download button per row (`:1525-1543`).
- **Mobile**: stacked `<button>` list (`:1553-1581`).

### 2.9 Inline sub-components (bottom of file)
`ChoiceTile` (`:1592`), `ReadinessRow` (`:1631`), `StepperPipeline` (`:1662`), `InsightTile` (`:1730`), `EmptyHint` (`:1752`). Plus top-of-file `ReadinessBadge` (`:238`), `StatusPill` (`:252`), `KpiTile` (`:294`). **None of these are shared with the other pages** — all local to this file. This is the single biggest reuse opportunity (see §5).

---

## 3. Brand Pulse — full UX flow

`pages/BrandPulse.tsx` (321 lines). Output = an on-screen "last N days vs previous period" dashboard. No PPTX/PDF, no job lifecycle, no polling — it's a plain read query.

### 3.1 State + query
- `accountId` (defaults to first account), `windowDays` (30/60/90, `WINDOW_OPTIONS` `:21`).
- Vendor accounts default to 90d, sellers to 30d on first load (`defaultedAccountRef` effect `:153-159`) — because vendors report monthly.
- `brandPulseApi.get({ account_ids, window_days, language })` (`:161-170`), enabled only when an account exists. **Single GET, no polling.**

### 3.2 Layout (`:178-320`)
- Header: `Activity` icon + **"Brand Pulse"** title + subtitle **"How your brand performed in the last {n} days vs the previous period."** (`brandPulse.subtitle`, `en.ts:885`). Account `Select` + window `Select` on the right.
- States: `noAccount` Alert (`:215-219`), `isLoading` spinner line (`:220-224`), `isError` destructive Alert (`:225-229`).
- `awaitingData` Alert (`:233-238`) when the period has no posted data yet (monthly-reporting accounts).
- **KPI row** (`:239-244`): 4 `KpiTile`s (local component `:41-69`) — Revenue, Units, Orders, Avg order value — each with a trend arrow + % change vs previous.
- **Advertising card** (`:246-272`): if `ads.is_available` → 4 `Metric`s (Ad spend, ACOS, TACOS, ROAS) + attribution-window note; else "Ads not connected".
- **Top / Declining ASINs** (`:274-303`): two cards each with an `AsinTable` (local `:80-117`). Seller accounts show a "snapshot" caveat note (`brandPulse.snapshotNote`).
- **Recommendations** (`:305-316`): list of `RecCard`s (local `:119-139`). Each shows title, evidence, and **Source** + **Confidence** badges — this matches the "AI w/ Source/Confidence/Evidence" direction in MEMORY. Empty → "Nothing needs attention in this period."

### 3.3 Overlap with Performance Analytics (confirmed)
Brand Pulse surfaces revenue/units/orders/AOV deltas, top/declining ASINs, and ads ACOS/TACOS — the same primitives Performance Analytics already computes. The frontend has **no shared component** with the analytics pages; the duplication is conceptual + backend (`brand_pulse_service.py`), but the page itself is thin and self-contained, so it is cheap to re-skin or fold in.

---

## 4. Market Research — full UX flow

`pages/MarketResearch.tsx` (1207 lines). The most feature-complete surface. Output = on-screen report + PDF export.

### 4.1 Structure
- Shared **Account + Analysis-language** selector card (`:415-450`).
- **Two tabs** (`:452-581`):
  - **"Analyze My Product"** (`product-analysis`, `:466-557`): pick a catalog product (ASIN) → optionally add up to 5 extra competitor ASINs via `AsinInput` (advanced, collapsible `:524-539`) → `Generate`. Calls `marketResearchApi.generate`.
  - **"Explore Similar Market"** (`market-search`, `:560-580`): renders `<MarketTracker>` (search keyword/brand/ASIN → live results → pick reference → generate report).
- **Selected-report display** (`:584-1120`): polled via `selectedReportQuery` (`:198-208`, **3000ms while pending/processing**). Branches: loading → processing (progress bar) → failed → completed.
- Completed report renders: PDF export button, market snapshot (for market-search reports), report context, comparison table (`CompetitorTable`), radar (`RadarComparison`) with competitor multi-select checkboxes, `MarketPositionSummary`, a detailed comparison **matrix** table (`comparison-matrix` endpoint), opportunities cards, AI summary + `AIInsights`.
- **Previous Reports** list (`:1122-1195`): status badge + type badge + title; per-row `Eye` (open) + `Trash2` (delete, with `confirm()`).

### 4.2 Honesty guards (notably good, worth preserving)
- `hasUsableMarketData` (`:347-353`) — hides AI narrative when no competitor carries a real metric.
- `competitiveMetricsAvailable` via `hasCompetitiveMetrics` (`:358-361`) — hides the radar when only price exists (a single axis would look fabricated). Shows an explicit "competitive metrics unavailable" card instead.
- `lib/market-research.ts` sentinel-price detection (`:24-50`) strips placeholder/EAN prices from aggregates. These guards are a model for how Brand Analysis should treat thin data.

### 4.3 Report management UI
Market Research is the only one of the three with **delete** + per-row open/delete actions and a typed report list. Brand Analysis history has open + download but **no delete in the UI** (the API exists: `brandAnalysisApi.delete`, `api.ts:1108`). Brand Pulse has no list at all.

---

## 5. Component reuse opportunities (concrete)

| Concept | BrandAnalysis | BrandPulse | MarketResearch | Note |
|---|---|---|---|---|
| **KpiTile** | local `:294-321` (gradient surface, icon chip, tone) | local `:41-69` (trend arrow) | `MarketOverviewStats` builds its own stat tiles | **Three independent KPI-tile implementations.** Unify into one `<KpiTile>` with optional `change`/`tone`/`icon`. |
| **Job polling** | `selectedJobQuery` 3000ms `:369-372` | n/a | `selectedReportQuery` 3000ms `:202-206` | Identical pattern → extract a `usePolledJob(queryKey, fetcher, isRunning)` hook. |
| **Progress / processing card** | header bar + 9-step `StepperPipeline` | n/a | spinner + `Progress` + `progress_step` `:598-621` | Both show `progress_pct` + `progress_step`. A shared `<JobProgress>` would cover both. |
| **Status badge** | `StatusPill` `:252-271` | n/a | `statusVariant` map `:54-59` + inline badge | Different visual languages for the same idea. |
| **Empty state** | `EmptyHint` `:1752-1769` + `Presentation`-circle empty `:1453-1459` | inline `—` / text | `MarketSearchEmptyState.tsx` (icon cluster) | At least 3 distinct empty-state visual styles. |
| **Report/history list** | faux-grid table `:1463-1551` | none | bordered rows w/ open+delete `:1137-1192` | A shared `<ReportList>` could serve BrandAnalysis + MarketResearch. |
| **Recommendations w/ Source/Confidence/Evidence** | "Recommended actions" are *navigational* (not AI evidence) | `RecCard` `:119-139` (Source+Confidence) | `AIInsights` recommendations (priority+area+action+impact) | Three different recommendation shapes. The MEMORY direction (Source/Confidence/Evidence) only exists in BrandPulse today. |
| **`downloadBlob`** | local copy `:213-222` | n/a | imported from `@/lib/utils` (used by `PdfExportButton`) | BrandAnalysis re-defines `downloadBlob` instead of importing the lib one. Dead-simple dedupe. |
| **PDF/PPTX export button** | inline `Download PPTX` buttons | n/a | `PdfExportButton.tsx` (captures charts, calls `/exports/...`) | Export-button pattern could be generalized. |

---

## 6. Terminology audit — Brand Name vs Amazon Account vs Brand-or-Market Query

### 6.1 Exact strings (EN, from `en.ts`)
- `brandAnalysis.field.brandName` = **"Brand name"** (placeholder **"e.g. Zwilling"**, `:924-925`).
- `brandAnalysis.field.account` = **"Amazon account"** (placeholder **"Select account"**, `:927-928`).
- `brandAnalysis.field.marketType` = **"Scope"** (`:930`), with options `brandAnalysis.marketType.brand` = **"Brand"** and `brandAnalysis.marketType.asin` = **"ASIN list"** (`:939-940`).
- `brandAnalysis.field.marketQuery` = **"Brand or market query"** (placeholder **"Defaults to the brand name"**, `:931-932`).
- `brandAnalysis.field.asinList` = **"ASIN list"** (`:933`) — **collides verbatim with the "ASIN list" Scope option label**.
- `brandAnalysis.mode.internal` = **"Internal Amazon data"**, `brandAnalysis.mode.manual` = **"Upload external yearly exports"** (`:935-937`).

### 6.2 Where it's redundant / confusing
1. **"Brand name" vs "Brand or market query" vs "Brand" (Scope)** — three fields/options all containing the word "brand", with overlapping meaning:
   - `brandName` is the deck subject (required).
   - `marketQuery` defaults to `brandName` (`handleAnalyze`/`createMutation` `:418`: `market_query: marketQuery.trim() || brandName.trim()`). So in the common path the user types the brand name twice, or leaves the second blank and it silently mirrors the first. The label "Brand or market query" does not explain why a second brand field exists.
   - The Scope tile "Brand" (vs "ASIN list") is a *third* use of the word, meaning "discover by brand-name search" — unrelated to the `marketQuery` field.
2. **"ASIN list" appears twice** — once as a Scope tile (`marketType.asin`, `:940`) and once as the field label (`field.asinList`, `:933`). Identical text, two different roles.
3. **"Amazon account" is optional-but-required-conditionally** — the account `Select` defaults to `"none"`/"Select account", yet internal mode *requires* it (`validateForm` `:404-406`). The form doesn't communicate that selecting "internal" makes the account mandatory; the failure only surfaces as a toast.
4. **"Scope" is an opaque label** — it actually means "how to define the ASIN universe" (by brand discovery vs explicit ASIN list). "Scope" gives no hint of that.
5. **Mode label drift**: the type literal is `mode: 'internal' | 'manual'`, the UI never shows a "mode" picker (the field key `brandAnalysis.field.mode` = "Data source" exists in i18n `:929` but is **unused** in the JSX — mode is inferred from account presence + which button is clicked). So "Data source" copy exists with no control.

### 6.3 Brand Pulse / Market Research terminology
- Market Research uses **"Analyze My Product"** / **"Explore Similar Market"** for its tabs (`marketResearch.productAnalysisTab/marketTrackerTab`, `en.ts:1066-1067`) — friendlier, task-oriented copy. The selectors say **"Account"** (reuses `forecasts.account` key, `:419`) and **"Analysis language"**.
- This means **the same "pick an Amazon account" control is labelled "Amazon account" in Brand Analysis but "Account" in Market Research** — minor inconsistency across the three pages.

---

## 7. The "leftover Portuguese text" — finding

**Not reproducible. There is no Portuguese in the current frontend.** Exhaustive checks run:
- `grep -rnP "[ãõçáéíóúâêôà]"` across all `.tsx/.ts` excluding `i18n/{it,en}.ts` → **0 matches**.
- PT function-word scan (`você/voce/não/nao/exportações/mercado/faturamento/pesquisar/baixar/concorrentes/anuais/carregar/relatorio`, with and without diacritics) across pages + components + i18n → **0 matches** outside legitimate English/Italian.
- `it.ts` brandAnalysis block (`:924-1061`) is genuine **Italian** ("Genera la presentazione annuale…", "Carica export annuali esterni…", "Scarica PPTX", "Riesegui"). `en.ts` block is genuine **English**. Neither contains PT.
- git history for `BrandAnalysis.tsx` shows the file was introduced/polished in `ea1918e` → `b908324` → `156536c`; no PT survives in HEAD.

**Conclusion:** the brief's "HAS leftover Portuguese text" is stale (likely fixed in a prior pass, or a mis-recollection). Downstream agents should **not** spend effort hunting PT in `BrandAnalysis.tsx`.

**Genuine i18n bug found instead** (worth flagging in its place):
- `components/market-research/MarketTracker.tsx:177` hardcodes the literal **`Market Tracker 360`** as the `CardTitle` (not wrapped in `t(...)`). It is untranslatable and inconsistent with the tab label "Explore Similar Market". This is the only non-`t()` user-facing string of note in the three surfaces (the only other raw literals are `English`/`Italiano` select items and `e.g. …` placeholders in `MarketTracker.tsx:216-219`, which are language-neutral by design).

---

## 8. Loading / progress / empty / error state inventory

### Brand Analysis
- **Loading**: page-level `selectedJobQuery.isLoading` line (`:1011-1016`); history `Loader2` (`:1449-1452`); button spinners on create/start/upload/download (e.g. `:860-864`, `:983-987`, `:1399-1405`).
- **Progress**: dual representation — linear `Progress` in the job header (`:962-973`) **and** the 9-step `StepperPipeline` (`:1041-1056`). Both driven by `progress_pct`.
- **Empty**: `EmptyHint` for missing metrics (`:1121-1126`); `Presentation`-icon empty for no jobs (`:1453-1459`).
- **Error**: three-way banner block (`:1018-1039`): waiting-for-user warning, destructive error, info error-code. Error codes translated via `brandAnalysis.errorCode.*`. Mutations surface failures as toasts (`:425-431`, `:442-448`, `:458-464`).
- **Partial/degraded**: "Deck limitations" list (`:1282-1306`), "Missing permissions" Alert (`:1262-1280`), "Optional fields missing" badges, `completed_with_limitations` status + amber badge variant.

### Brand Pulse
- **Loading**: spinner line (`:220-224`). **Error**: destructive Alert (`:225-229`). **Empty**: `noAccount` Alert (`:215-219`); per-table `—` (`:81-83`); "No declining ASINs" / "Nothing needs attention". **Degraded**: `awaitingData` Alert + KPI changes suppressed (`:233-243`).

### Market Research
- **Loading**: report-load spinner card (`:586-597`); processing card with `Progress` + `progress_step` (`:598-621`); `comparisonMatrixQuery.isLoading` card (`:889-902`); `MarketTracker` has an **animated skeleton** (`:242-255`) — the only true skeleton in the three surfaces.
- **Error**: failed-report card with `AlertCircle` (`:622-633`); matrix-failed text (`:1059-1066`); search errors via toast.
- **Empty**: `MarketSearchEmptyState` (icon cluster), no-results blocks (`:262-271`, `:712-758`), no-reports text (`:1132-1135`), insufficient-data card (`:1070-1077`).

---

## 9. How the frontend polls job status (exact mechanism)

Both job-bearing pages use react-query `refetchInterval` as a function of the latest data:

- **BrandAnalysis** (`:369-372`):
  ```ts
  refetchInterval: (query) => {
    const status = query.state.data?.status
    return status && runningStatuses.includes(status) ? 3000 : false
  }
  ```
  `runningStatuses` is the explicit list at `:62-80` (pending, capability_checking, preflight_checking, …, exporting_2024). When status leaves that set, polling stops automatically.
- **MarketResearch** (`:202-206`): same shape, `status === 'pending' || 'processing' → 3000 else false`. Plus a side-effect (`:364-368`) invalidating the list query when a report reaches `completed`/`failed` so the list badge updates.
- **BrandPulse**: **no polling** — single read query keyed on `[account, window, language]`.

No websockets/SSE anywhere. Mutations manually `invalidateQueries` to refresh lists.

---

## 10. Why the Brand Analysis UI "feels AI-generated" — honest critique (concrete tells)

These are the strongest signals, with anchors:

1. **Gradient overuse.** Multiple decorative `bg-gradient-to-br` layers used purely as background tint: the page-hero glyph (`:706`), the selected-job header band (`:927`), every `KpiTile` surface (`:275-292` tone map → `:310`). Gradients carry no information; they're applied uniformly as "polish."
2. **Icon saturation / `Sparkles` as the AI signifier.** `Sparkles` appears as nav icon, page hero (`:707`), and "Recommended actions" header (`:1167`). Nearly every label, badge, tile, and section header has a leading lucide icon (the import block alone pulls ~26 icons, `:3-30`). Dense icon-per-element is a classic generated-UI tell.
3. **Generic "card-in-card-in-card" density.** The selected-job panel nests: Card → gradient header band → Tabs → TabsContent → grid of bordered tiles → inner icon-chip + text. Everything is a rounded-border surface; visual hierarchy comes from borders, not from typographic restraint.
4. **6-up KPI grid + tone-coded everything.** Six KPI tiles in a row (`:1077-1119`), each color-toned (primary/success/warning/neutral) by a lookup table. Color is decorative rather than meaningful (e.g. "Inactive ASINs" is `warning`-amber by default regardless of value).
5. **Redundant progress visualizations.** Both a linear bar **and** a 9-step stepper render the same `progress_pct` simultaneously (`:962-973` + `:1041-1056`). Showing the same state two ways is a hallmark of "more components = better."
6. **Copy patterns.** Section headers are uppercase, letter-spaced, muted micro-labels (`text-[11px] font-semibold uppercase tracking-[0.08em]`, repeated at `:1043`, `:1168`, `:1203`, `:1215`, `:1284`, `:1310`). Help text is uniformly hedged/templated ("Run the analysis to verify this source.", "Fallback for missing 2024 or 2025 internal history."). Reads like generated boilerplate rather than a product voice.
7. **Choice-tile pattern for a binary toggle.** "Scope" is a 2-option toggle rendered as two large `ChoiceTile` cards with icon chips + ring states (`:803-819`, component `:1592-1629`) — heavier than the decision warrants.
8. **"Recommended actions" as decorative cards.** Four equally-weighted gradient-hover cards (`:1163-1197`) that are really just nav shortcuts (sync / settings / switch scope / upload). Presenting navigation as AI "recommendations" inflates perceived intelligence.
9. **Inconsistent visual language vs siblings.** Brand Pulse (plain bordered cards, no gradients) and Market Research (functional tables/charts) look like a different, calmer product. Brand Analysis is the outlier that "looks AI-made" — the inconsistency itself is a tell.

**What reads as genuinely human/considered (keep):** the data-honesty guards in Market Research (§4.2), the vendor-vs-seller window defaulting in Brand Pulse (`:153-159`), the sentinel-price filtering (`lib/market-research.ts`), and the explicit error-code → translated-message mapping. The problem is concentrated in `BrandAnalysis.tsx` presentation, not in the logic.

---

## 11. Quick file:line index for specialists

- Setup form: `BrandAnalysis.tsx:735-880` · Readiness preview: `:882-919` · Job panel: `:923-1415` · Upload panel: `:1324-1411` (+ legacy `:1417-1431`) · History: `:1433-1585` · Local components: `:1592-1769`.
- Job create/start/upload/download mutations: `:410-486`. Polling: `:369-372`. runningStatuses: `:62-80`. progressSteps: `:135-145`. capability keys: `:624-636`.
- Brand Pulse: query `:161-170`, KPI row `:239-244`, ads `:246-272`, ASIN tables `:274-303`, recs `:305-316`.
- Market Research: tabs `:452-581`, report render `:584-1120`, comparison matrix `:903-1058`, previous reports `:1122-1195`, honesty guards `:347-361`. MarketTracker hardcoded title: `MarketTracker.tsx:177`.
- API: `services/api.ts:1011-1123` (`marketResearchApi`, `brandAnalysisApi`, `brandPulseApi`).
- Types: `types/index.ts:30-90` (Pulse), `:757-805` (MarketResearch/Comparison), `:840-955` (BrandAnalysis).
- i18n EN: `en.ts:884-916` (brandPulse), `:919-1061` (brandAnalysis), `:1063-1211` (marketResearch/marketTracker). IT mirror: `it.ts:924-1061`.
- Routing: `App.tsx:93-106`. Nav: `Layout.tsx:36-38`.
