# Brand Analysis & Brand Pulse — Frontend / UX Review

Author: Frontend/UX engineer-designer
Scope: `frontend/src/pages/BrandAnalysis.tsx` (1770 lines), `frontend/src/pages/BrandPulse.tsx` (321 lines), supporting i18n / API / components.
Branch: `master` (commit `156536c`). All anchors verified by reading the files, not just the discovery map.

---

## 1. Findings (what is true today)

### 1.1 The "leftover Portuguese" claim is STALE — do not hunt it
The brief and `MEMORY.md` both flag "leftover Portuguese text" in the *Upload External Yearly Market Exports* panel. **This is not reproducible.** I ran two scans:

- `grep -rnP "[ãõçáéíóúâêôà]" src --include="*.tsx" --include="*.ts"` excluding `i18n/` → **0 hits**.
- A Portuguese-function-word scan (`dados|relatório|análise|carregar|enviar|arquivo|configurações|mercado|marca|produto|vendas`) over `BrandAnalysis.tsx` → **0 hits**.

The upload panel copy is genuine English: `brandAnalysis.upload.title` = `"Upload external yearly market exports"`, `brandAnalysis.upload.description` = `"Advanced fallback for generic yearly product exports. Use CSV/XLSX with at least ASIN and revenue columns."` (`en.ts`). The IT block is genuine Italian. **The only real i18n bug in the wider area is unrelated** (`MarketTracker.tsx:177` hardcodes `Market Tracker 360`). My recommendation: mark this requirement DONE-by-verification and redirect effort. I provide a one-line replacement table in §3 in case a stray string surfaces on the user's branch, but on `master` there is nothing to remove.

### 1.2 The notification UI already exists — this is the single most important finding
There is a fully working **`NotificationBell`** component (`components/NotificationBell.tsx`, 257 lines) already mounted in `Layout.tsx:7`. It has:
- Bell trigger with unread-count badge (`NotificationBell.tsx:157-164`, `99+` cap).
- Popover dropdown with severity icons, time-ago, per-item mark-as-read, "mark all read", skeleton loader, empty state, "view all" → `/alerts` (`:166-254`).
- Optimistic cache updates via `optimisticallyMarkAlertRead` / `restoreAlertQuerySnapshot` (`lib/alertUtils`).
- Polls `alertsApi.getUnreadCount` every 60s (`:74`).

**Implication:** the "in-app notifications when analyses complete (NO email)" requirement is ~70% built on the frontend. We do NOT build a bell from scratch. We emit a notification/alert row server-side on Brand Analysis completion and let the existing bell render it, plus add a one-shot toast on the page when the polled job flips to `completed`. This collapses a feared XL into an S.

### 1.3 Brand Analysis genuinely looks AI-generated — concrete tells
Quoting the code:

| Tell | Evidence | Why it reads as "AI slop" |
|---|---|---|
| Decorative gradients with zero information | hero glyph `bg-gradient-to-br from-primary/15 to-primary/5` (`:706`); job header `from-primary/[0.08] via-transparent to-transparent` (`:927`); **every** `KpiTile` has `bg-gradient-to-br` (`:310`, `kpiTone` table `:275-292`) | Real analytics tools (Helium10, Sellerboard) use flat surfaces; gradients are pure ornament here |
| `Sparkles` as the "AI" signifier | nav icon, hero `:707`, AND "Recommended actions" header `:1167` | The literal "magic AI" cliché |
| Icon saturation | 26 lucide icons imported (`:3-30`); an icon on nearly every label, KPI, choice tile, readiness row, insight tile | Enterprise dashboards are sparing with icons |
| Tone-coded-by-lookup KPIs, not by value | `KpiTile` tone is a hardcoded prop, e.g. Inactive ASINs is **always** `tone="warning"` amber (`:1117`) even when it's 0 | Color should encode the data, not the label |
| Redundant double progress | linear `<Progress>` bar (`:972`) AND a 9-step `StepperPipeline` (`:1046`) render the **same** `progress_pct` simultaneously | Two widgets, one signal |
| Templated micro-labels | the exact class `text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground` is copy-pasted on 6 section headers (`:1043, :1168, :1203, :1215, :1284, :1310`) | The "every section gets a tiny uppercase eyebrow" pattern is an AI tell |
| Binary toggle dressed as cards | "Scope" (Brand vs ASIN list) is two large icon-chip `ChoiceTile` cards (`:803-819, :1592`) for what is a 2-option radio | Over-produced for the decision weight |
| "Recommended actions" that are nav shortcuts | 4 equal gradient-hover cards (`:1163-1197`) that are really "sync account / open settings / switch to ASIN / upload" dressed up as AI insights (`recommendedActions` array `:643-685`) | Fake intelligence |

By contrast, **Brand Pulse** (`BrandPulse.tsx`) is the *calmest* surface — plain `Card`s, no gradients, no Sparkles, a single `Activity` icon. Market Research is the most functional (real tables + recharts). Brand Analysis is the visual outlier and the one that needs the most aggressive de-AI-ing.

### 1.4 Report management is half-built
- **Delete: API exists, UI does not.** `brandAnalysisApi.delete` is defined (`api.ts`) but there is **no delete control anywhere** in `BrandAnalysis.tsx`. The history rows (`:1472-1548`) only offer select + download.
- **Cancel: nothing.** No cancel endpoint and no UI. A job stuck `running` is uncancellable from the UI (backend confirms there is no cancel endpoint and the in-process thread fallback is untracked).
- **History is a faux-grid**, not a real table: `grid-cols-[1.6fr_1fr_1fr_120px_64px]` (`:1464, :1487`), duplicated desktop + mobile renderers (`:1463-1581`).
- MarketResearch's delete uses a raw `confirm()` (`MarketResearch.tsx`), even though `components/ui/alert-dialog.tsx` exists and is unused.

### 1.5 Terminology is genuinely confusing (three "brand" inputs)
From `en.ts`:
- `field.brandName` = "Brand name" (ph "e.g. Zwilling") — the deck subject.
- `field.marketQuery` = "Brand or market query" (ph "Defaults to the brand name").
- Scope tile option `marketType.brand` = "Brand".

And `handleAnalyze` sends `market_query: marketQuery.trim() || brandName.trim()` (`:418`) — i.e. the second field silently mirrors the first if left blank. So the user types the brand once, sees a second "Brand or market query" field they don't understand, and "ASIN list" appears **twice verbatim** (Scope option `marketType.asin` and field label `field.asinList`). There is also a dead `field.mode` = "Data source" string in i18n that no JSX renders — mode is inferred from "did you pick an account + which button did you click" (`modeToDataSource`, `:161`; `handleAnalyze`, `:488-502`). That implicit-mode model is the root confusion.

### 1.6 The data layer is healthy and reusable
- **recharts ^2.10.4 is installed** and already used in `Dashboard`, `Performance`, `Forecasts`, `ProductAnalytics`, and `market-research/*`. The Brand Analysis "Metrics preview" and Brand Pulse render **zero charts** despite having chart-ready data — a wasted asset, not a missing dependency.
- Job polling is identical in BrandAnalysis (`:369-372`) and MarketResearch (`:202-206`): react-query `refetchInterval` returning `3000` while running, `false` otherwise. Clean extract candidate (`usePolledJob`).
- shadcn primitives available: `alert-dialog, dialog, table, tabs, popover, toast` (all present in `components/ui/`).

### 1.7 Brand Pulse is thin, honest, and mis-positioned
`BrandPulse.tsx` is a clean rolling-window dashboard: 4 KPI tiles with trend arrows (`:239-244`), an ads card (`:246-272`), top/declining ASIN tables (`:274-303`), and recommendation cards that **already carry Source + Confidence badges** (`RecCard`, `:119-139`) — the only place in the app matching the MEMORY "AI w/ Source/Confidence/Evidence" direction. But it is a *period-over-period performance snapshot*, which is exactly Performance Analytics re-skinned (backend confirms ~90% overlap). It is positioned as a live dashboard with no report, no narrative, no week framing, no competitor/market/risk sections. The reposition to "Weekly Brand Intelligence Report" is a near-total UX rebuild, not a tweak.

---

## 2. Problems Identified (ranked by severity)

| # | Problem | Severity | Evidence |
|---|---|---|---|
| P-1 | **Brand Pulse is mis-positioned** as a perf dashboard duplicating Performance Analytics; no report, no week framing, no market/competitor/risk content | Critical | §1.7; whole `BrandPulse.tsx` |
| P-2 | **No delete / no cancel in Brand Analysis UI**; delete API exists unused, cancel doesn't exist | High | §1.4 |
| P-3 | **Terminology confusion** — three overlapping "brand" inputs, implicit mode, "ASIN list" duplicated | High | §1.5 |
| P-4 | **Brand Analysis reads as AI-generated** — gradients, Sparkles, fake "recommended actions", redundant progress, tone-by-lookup | High | §1.3 |
| P-5 | **No charts** in either surface despite recharts being installed and the data being chart-ready | Medium | §1.6 |
| P-6 | **Notification-on-completion** not wired, even though the bell + toast infra exists | Medium | §1.2 |
| P-7 | **Report management is a faux-grid** with duplicated desktop/mobile renderers and no real table/sort/filter | Medium | §1.4 |
| P-8 | **Redundant/duplicated components** — `KpiTile` reimplemented 3× (BrandAnalysis `:294`, BrandPulse `:41`, MarketOverviewStats); `downloadBlob` re-defined (`:213`) instead of `@/lib/utils`; polling logic copy-pasted | Medium | §1.6 |
| P-9 | **Progress %/step mismatch** — 9 frontend `progressSteps` (`:135-145`) hardcode pcts that the backend `_set_status` calls disagree with (backend double-source-of-truth) → stepper can show a step "active" that's already past | Low | §1.3 / backend §2 |
| P-10 | "Leftover Portuguese" requirement is based on stale info | Low (effort sink risk) | §1.1 |

---

## 3. Recommendations (priority P0–P3, effort XS–XL)

### Brand Analysis

| ID | Recommendation | Priority | Effort |
|---|---|---|---|
| R-1 | **Collapse the three "brand" inputs into ONE explicit flow.** One "Brand name" field + an explicit **Data source** segmented control (Connected Amazon account / Upload exports) + an optional, collapsed-by-default "Advanced: scope" disclosure (Brand vs ASIN list). Kill the implicit mode. | P0 | M |
| R-2 | **Wire delete with an `AlertDialog` confirm** in history rows + the job header. Use existing `brandAnalysisApi.delete` and `components/ui/alert-dialog.tsx`. | P0 | S |
| R-3 | **Add Cancel for in-progress jobs** (needs new backend `POST /brand-analysis/{id}/cancel`; FE adds a Cancel button + `cancelling`/`cancelled` states). | P0 | S (FE) |
| R-4 | **De-AI the visual language** (see §4.2): strip decorative gradients, remove Sparkles-as-AI, drop fake "Recommended actions" cards (move sync/settings into a quiet "Fix data" inline strip), collapse double progress into ONE component, make KPI color encode value not label. | P0 | M |
| R-5 | **Add real charts to the metrics preview** (revenue YoY bar, active/inactive donut, top-ASIN bars) using recharts. | P1 | M |
| R-6 | **Rebuild history as a real sortable report table** with status, source, created/completed, progress, and a row action menu (open / download / re-run / delete). One responsive component, not duplicated desktop+mobile. | P1 | M |
| R-7 | **Notification on completion**: toast on the page when the polled job flips to `completed`/`failed`; rely on the existing bell for the global signal (backend emits an alert row). | P1 | S |
| R-8 | **Onboarding empty state**: a proper first-run "what is a Brand Analysis + the 3 inputs" panel instead of the current bare form. | P2 | S |
| R-9 | Mark "remove Portuguese" DONE-by-verification; if a stray surfaces, replace per the table below. | P3 | XS |

Stray-string replacement table (only if found on the user's working branch — none on `master`):

| If you find (PT) | file:line | Replace with (EN) |
|---|---|---|
| "Carregar exportações anuais" | n/a on master | "Upload external yearly exports" |
| "Exportação de produtos {year}" | n/a on master | "{year} product export" |
| "Arraste um CSV ou XLSX" | n/a on master | "Drop a CSV or XLSX, or click to browse" |

### Brand Pulse

| ID | Recommendation | Priority | Effort |
|---|---|---|---|
| R-10 | **Rebuild as "Weekly Brand Intelligence" report reader** (see §4.4): week selector, exec summary, sectioned narrative (Market / Brand evolution / Competitors / Opportunities / Risks / Trends / Recommendations), WoW deltas, generate + history. | P0 | XL |
| R-11 | **Rename + re-IA**: nav "Brand Pulse" → "Brand Intelligence" (`Radar`/`Telescope` icon, not `Activity`). Move out of the performance neighborhood. | P0 | XS |
| R-12 | **Keep the honest bits**: Source/Confidence/Evidence rec badges (`RecCard`), vendor/seller window defaulting, "awaiting data" gate — port them into the new reader. | P1 | XS |
| R-13 | **Weekly automation surface**: a "subscribe to weekly report for this brand" toggle that drives the backend scheduler; show "next report: Mon 9am" + last-generated. | P1 | S (FE) |

### Cross-cutting

| ID | Recommendation | Priority | Effort |
|---|---|---|---|
| R-14 | **Shared component library**: `usePolledJob` hook, one `KpiStat`, one `JobProgress`, one `StatusBadge`, one `ReportTable`, one `ConfirmDelete`. Replace the 3 KpiTiles and 2 status-badge dialects. | P1 | M |
| R-15 | Replace `confirm()` in MarketResearch delete with the shared `ConfirmDelete` (consistency dividend). | P3 | XS |

---

## 4. Technical Implementation Plan

### 4.0 Design tokens (shared) — kill the inline ad-hoc styling
Add `frontend/src/lib/brand-ui.ts`:
```ts
// Enterprise-analytics palette. No decorative gradients.
export const stat = {
  pos: 'text-emerald-600 dark:text-emerald-400',
  neg: 'text-rose-600 dark:text-rose-400',
  flat: 'text-muted-foreground',
}
// value-driven tone: pass the number, not a label
export function deltaTone(n?: number) {
  if (n == null) return stat.flat
  return n > 0 ? stat.pos : n < 0 ? stat.neg : stat.flat
}
export const eyebrow = 'text-[11px] font-medium uppercase tracking-wide text-muted-foreground'
```
Replace the 6 copy-pasted eyebrow class strings and the `kpiTone` lookup with these. **Rule: surfaces are flat `bg-card`; color is reserved for data state.**

### 4.1 New shared components (`frontend/src/components/shared/`)
| File | Replaces | Notes |
|---|---|---|
| `usePolledJob.ts` | BrandAnalysis `:369`, MarketResearch `:202` | `usePolledJob(id, fetchFn, isRunning, { onComplete })` — fires `onComplete` once on terminal transition (drives the completion toast in R-7). |
| `KpiStat.tsx` | BrandAnalysis `KpiTile:294`, BrandPulse `KpiTile:41` | `{ label, value, delta?, deltaSuffix? }`; flat card; delta colored by value via `deltaTone`. |
| `JobProgress.tsx` | the double progress (`:972` + `:1046`) | ONE component: compact = thin bar + current step label; detailed = horizontal stepper. Default to compact; show stepper only in the job detail. |
| `StatusBadge.tsx` | `StatusPill:252` + MR `statusVariant` | one status→variant map. |
| `ReportTable.tsx` | history faux-grid `:1463-1581` | responsive `<table>` (real `components/ui/table.tsx`), row action menu, empty + loading states. |
| `ConfirmDelete.tsx` | MR `confirm()` + new BA delete | wraps `alert-dialog.tsx`. |

### 4.2 Brand Analysis rebuild — component tree
`BrandAnalysis.tsx` is a 1770-line god-component. **Rebuild the page shell; reuse the data hooks.** Verdict per area in §7.

```
<BrandAnalysisPage>
  <PageHeader title="Brand Analysis" />                 // no Sparkles, no gradient
  <Tabs defaultValue="create">                          // top-level IA: Create | Reports
    <TabsContent value="create">
      <AnalysisSetupCard>                                // R-1 simplified flow
        <Field label="Brand name" />                     // the ONLY brand input
        <SourceSelect>                                   // segmented: Connected account | Upload exports
          [account] -> <AccountPicker/> + <ReadinessInline/>
          [upload]  -> <YearlyExportUpload/>             // redesigned (4.3)
        </SourceSelect>
        <Disclosure label="Advanced: scope (optional)">  // collapsed by default
          <ScopeRadio> Brand | ASIN list </ScopeRadio>   // plain radio, not ChoiceTile cards
          {scope==='asin' && <AsinTextarea count={n}/>}
        </Disclosure>
        <Button>Generate analysis</Button>
      </AnalysisSetupCard>
    </TabsContent>
    <TabsContent value="reports">
      <ReportTable rows={jobs}
        onOpen onDownload onRerun onDelete={ConfirmDelete}/>  // R-2, R-6
    </TabsContent>
  </Tabs>

  {selectedJob && <JobDetailPanel job>                   // appears when a report is opened
    <JobHeader>
      <StatusBadge/> <SourceBadge/>
      {running && <CancelButton/>}                       // R-3
      {ready && <DownloadButton/>}
      <RerunButton/> <DeleteButton confirm/>
    </JobHeader>
    <JobProgress detailed/>                               // single stepper, real % (4.6)
    <Tabs> Overview | Data & coverage | Files
      Overview -> <KpiStat/>×N + <RevenueYoYChart/> + <ActiveInactiveDonut/> + <TopAsinBar/>  // R-5
      Data     -> <CoverageGrid/> + <CapabilityMatrix/> + <LimitationsList/>
      Files    -> <YearlyExportUpload/>
    </Tabs>
  </JobDetailPanel>}
</BrandAnalysisPage>
```

`AnalysisSetupCard` — the explicit-source flow (pseudo-JSX):
```tsx
<div className="space-y-5">
  <Field id="brand" label="Brand name" placeholder="e.g. Zwilling"
         value={brand} onChange={setBrand} />

  <fieldset>
    <legend className={eyebrow}>Data source</legend>
    <SegmentedControl value={source} onChange={setSource}
      options={[
        { value:'internal', label:'Connected Amazon account', icon:Database },
        { value:'manual',   label:'Upload yearly exports',    icon:Upload },
      ]}/>
    {source === 'internal'
      ? <AccountPicker value={accountId} onChange={setAccountId} accounts={accounts}/>
      : <YearlyExportUpload jobId={jobId}/>}
  </fieldset>

  <Disclosure label="Advanced: scope (optional)" hint="By default we discover ASINs from the brand name.">
    <RadioGroup value={scope} onChange={setScope}>
      <Radio value="brand">Discover from brand name</Radio>
      <Radio value="asin">Specific ASIN list</Radio>
    </RadioGroup>
    {scope === 'asin' && <AsinTextarea value={asinText} onChange={setAsinText} count={asinList.length}/>}
  </Disclosure>

  <Button onClick={handleAnalyze} disabled={!brand || (source==='internal' && !accountId)}>
    Generate analysis
  </Button>
</div>
```
This removes `marketQuery` entirely (it just mirrored `brandName`); the create call sends `market_query: brand` server-side. It makes mode **explicit** (the segmented control) instead of inferred from button choice. "Scope" moves into an Advanced disclosure so 90% of users never see ASIN-vs-Brand.

i18n changes (`en.ts` / `it.ts`):
- Add `brandAnalysis.field.source` = "Data source", `brandAnalysis.source.internal` = "Connected Amazon account", `brandAnalysis.source.manual` = "Upload yearly exports".
- Add `brandAnalysis.scope.advanced` = "Advanced: scope (optional)", `brandAnalysis.scope.fromBrand` = "Discover from brand name", `brandAnalysis.scope.asin` = "Specific ASIN list".
- **Remove from JSX** the `field.marketQuery` / `field.marketQueryPlaceholder` usage (keep keys for migration safety, drop the input). Rename Scope choice strings so "ASIN list" appears once.

### 4.3 Yearly-export upload redesign (`YearlyExportUpload.tsx`)
Replace the two native `<input type=file>` cards (`:1338-1410`) with a single drag-and-drop zone per year, each showing: state (empty / uploaded with row count / error), a real dropzone (`onDragOver`/`onDrop` + hidden input), and a "replace" affordance. Copy from `brandAnalysis.upload.dropHere` ("Drop a CSV or XLSX, or click to browse"). Add a compact "what we need" hint (ASIN + revenue columns, optional rating/reviews/images). No new deps — native DnD. The panel header stays "Upload external yearly market exports" (already English).

### 4.4 Brand Pulse → Weekly Brand Intelligence (full rebuild)
New page `frontend/src/pages/BrandIntelligence.tsx` (keep route `brand-pulse` for back-compat, relabel nav). This is a **report reader**, not a live dashboard.

```
<BrandIntelligencePage>
  <PageHeader title="Brand Intelligence"
              subtitle="AI weekly report: market shifts, competitors, opportunities, risks." />
  <Toolbar>
    <BrandPicker/>                          // account/brand
    <WeekPicker/>                           // ISO week selector (this week / pick)
    <WeeklySubscribeToggle/>                // R-13 -> scheduler
    <GenerateButton/>                       // on-demand generate for the selected week
  </Toolbar>

  {report
    ? <ReportReader>
        <ExecSummary headline kpis={[rev,units,ads]} wowDeltas/>   // KpiStat row w/ WoW
        <Section icon={Globe}    title="Market & category">  <Narrative/> </Section>
        <Section icon={TrendUp}  title="Brand evolution">    <Narrative/> <MiniTrend/> </Section>
        <Section icon={Swords}   title="Competitor activity"><CompetitorDeltaTable/></Section>
        <Section icon={Sparkle?} title="Opportunities">      <OppCards/> </Section>
        <Section icon={Shield}   title="Risks">              <RiskCards/> </Section>
        <Section icon={Activity} title="Product & trend movements"><AsinMoversTable/></Section>
        <Section icon={Target}   title="Strategic recommendations">
          <RecCard source confidence evidence/>             // PORTED from BrandPulse:119
        </Section>
        <ReportFooter generatedAt model coverageNote/>
      </ReportReader>
    : <EmptyOrGeneratingState/>}            // uses usePolledJob during generation

  <PreviousReports>                          // ReportTable: week, status, generated, open/download/delete
</BrandIntelligencePage>
```
Data: backend (Architect's domain) produces a weekly report job with sections; FE polls via `usePolledJob` exactly like Brand Analysis. WoW deltas reuse `KpiStat` with `delta`. The reader layout follows SimilarWeb/SEMrush "insight report" conventions (big headline, scannable sections with one chart each), not a KPI-grid dashboard. Keep `awaitingData` gate and `RecCard` verbatim.

### 4.5 Notifications on completion (frontend side of R-7)
The bell is done. Two FE touchpoints:
1. **Page toast** — in `usePolledJob`, fire `onComplete(job)` on terminal transition; the page does `toast({ title: t('brandAnalysis.toast.done'), description: brand, action: <DownloadAction/> })`. No new infra (`useToast` already imported).
2. **Bell** — when the backend emits an alert/notification row on completion, the existing `NotificationBell` renders it automatically (it polls `getUnreadCount` every 60s and lists unread on open). If the Architect adds a dedicated `notifications` resource instead of reusing `alerts`, the only FE change is pointing `NotificationBell`'s two queries at the new endpoints and adding an `analysis_complete` type to `alertTypeLabel` (`NotificationBell.tsx:43-49`). Either way this is S, not XL.

Add `brandAnalysis.toast.done` = "Brand analysis ready — {brand}", `brandAnalysis.toast.failed` = "Brand analysis failed — {brand}".

### 4.6 Progress integrity (P-9)
Drive the stepper from the **backend's `progress_step` string** (active step) rather than re-deriving from hardcoded pcts. Map `status → step index` in ONE place that mirrors `STATUS_PROGRESS`; show the linear bar only as a thin sub-element of `JobProgress`. This removes the double-source-of-truth on the FE and the "step shows active when already past" glitch.

### 4.7 Files to add / change (summary)
- **Add:** `lib/brand-ui.ts`; `components/shared/{usePolledJob,KpiStat,JobProgress,StatusBadge,ReportTable,ConfirmDelete}.tsx`; `components/brand-analysis/{AnalysisSetupCard,SourceSelect,YearlyExportUpload,JobDetailPanel,MetricsCharts}.tsx`; `pages/BrandIntelligence.tsx`; `components/brand-intelligence/{ReportReader,Section,CompetitorDeltaTable,RiskCards,OppCards,WeekPicker,WeeklySubscribeToggle}.tsx`.
- **Change:** `pages/BrandAnalysis.tsx` (reduce to shell using new components); `components/Layout.tsx` (nav relabel + icon); `App.tsx` (point `brand-pulse` route at new page or add `/brand-intelligence`); `services/api.ts` (`brandAnalysisApi.cancel`, weekly-report endpoints); `i18n/{en,it}.ts`; `NotificationBell.tsx` (new alert type, if new endpoint); `pages/MarketResearch.tsx` (swap `confirm()` for `ConfirmDelete`).
- **New API methods:** `brandAnalysisApi.cancel(id)` → `POST /brand-analysis/{id}/cancel`; `brandIntelligenceApi.{generate,list,get,subscribe,unsubscribe}`.

---

## 5. Estimated Effort (per workstream)

| Workstream | Effort | Notes |
|---|---|---|
| W1 — Shared component library (tokens, hooks, KpiStat, JobProgress, StatusBadge, ReportTable, ConfirmDelete) | M (~3–4 d) | Unblocks everything; pure FE |
| W2 — Brand Analysis flow redesign (R-1, R-4, R-8) | M (~3–4 d) | Simplified inputs + de-AI |
| W3 — Brand Analysis report mgmt (R-2 delete, R-3 cancel, R-6 table) | S–M (~2–3 d) | FE; needs cancel endpoint from backend |
| W4 — Brand Analysis charts (R-5) | S–M (~2 d) | recharts already in repo |
| W5 — Completion notifications FE (R-7) | S (~1 d) | bell exists; just toast + type |
| W6 — Yearly export upload redesign (R-3 upload) | S (~1 d) | native DnD |
| W7 — Brand Intelligence reader rebuild (R-10/11/12/13) | XL (~6–8 d) | Largest; depends on backend report pipeline |
| W8 — MarketResearch confirm() swap + cleanup (R-15) | XS (~0.5 d) | consistency |
| **Total** | **~20–26 dev-days (≈4–5 weeks, 1 FE engineer)** | W7 is the long pole and gated on backend |

If parallelized: Brand Analysis track (W1–W6) ≈ 2.5 weeks; Brand Intelligence track (W7) ≈ 1.5–2 weeks, can start once backend report schema is agreed.

---

## 6. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| **Effort wasted hunting non-existent Portuguese** | Settled in §1.1 — mark DONE-by-verification, ship the replacement table only as a safety net. |
| **Brand Intelligence FE blocked on backend report pipeline** | Define the section JSON contract first (FE + Backend agree on a typed `WeeklyReport` shape); FE builds against a fixture so the reader is done before the pipeline lands. |
| **Cancel has no backend today** → button that does nothing | Gate the Cancel UI behind a feature flag / capability until `POST /cancel` exists; until then show "Cancel unavailable" disabled with tooltip rather than a dead button. |
| **Notification double-channel** (alerts vs new notifications resource) | Decide with Backend Architect: reuse `alerts` (zero FE bell work) vs new `notifications` (small FE repoint). Recommend reusing the alerts pipeline to avoid building a parallel inbox. |
| **God-component refactor regressions** | Extract incrementally behind the same routes; keep `useQuery` keys (`['brand-analysis']`) stable so cache/polling behavior is preserved; snapshot the existing happy path before refactor. |
| **Progress-step mismatch persists if backend not aligned** | FE drives the stepper from `progress_step` string and treats pct as cosmetic; coordinate the single status map with backend (P-9) but don't block on it. |
| **Over-charting a thin dataset** | Only render a chart when the metric is present and has ≥2 points (mirror MarketResearch's `hasUsableMarketData` honesty guards); otherwise an explicit empty card, never a degenerate bar. |

---

## 7. Rebuild vs Improve (verdict per screen)

| Area | Verdict | Justification |
|---|---|---|
| Brand Analysis **page shell / IA** | **Rebuild** | 1770-line god-component; flow confusion is structural, not cosmetic. Reuse the data hooks, replace the shell. |
| Brand Analysis **data hooks / queries / polling** | **Improve (extract)** | The react-query + polling logic is sound; lift into `usePolledJob`. |
| Brand Analysis **setup form** | **Rebuild** | Three-brand-input + implicit-mode model can't be patched into clarity. |
| Brand Analysis **history** | **Rebuild** | Faux-grid + duplicated renderers; replace with `ReportTable` (gains delete it's missing). |
| Brand Analysis **readiness/capability/limitations panels** | **Improve** | Genuinely useful and honest; just de-gradient and re-token. |
| Brand Pulse | **Rebuild** | Wrong product (perf dashboard); reposition to weekly intelligence reader. Salvage `RecCard`, window-defaulting, awaiting-data gate. |
| Notification bell | **Reuse as-is** | Already complete; wire completion events, add one alert type. |
| Shared primitives (KpiTile/status/empty) | **Rebuild once, reuse everywhere** | Currently triplicated; consolidate. |

**Bottom line:** Brand Analysis is an *improve-the-data, rebuild-the-shell* job — the intelligence underneath is honest; the chrome is AI-slop. Brand Pulse is a *rebuild-the-product* job — it's solving the wrong problem and overlaps Performance Analytics. The notification requirement is mostly already done and was the cheapest win on the list.
