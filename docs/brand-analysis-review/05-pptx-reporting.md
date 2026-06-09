# Brand Analysis — PPTX & Reporting Redesign

**Agent:** Reporting & PPTX specialist
**Scope:** Complete redesign of PPTX generation for Brand Analysis; deliverable format and block architecture for Brand Pulse weekly intelligence; LLM-narrative-per-block contract; migration path.
**Branch/anchors:** `master` (commit `156536c`). All `file:line` refer to `backend/app/services/brand_analysis_service.py` unless noted.

---

## 1. Findings (what is true today, grounded in code)

### 1.1 The deck is 100% hand-drawn rectangles — there is no chart layer at all
`BrandAnalysisPptxBuilder` (`:2413`) builds a blank `Presentation()` sized to `Inches(10) × Inches(5.625)` (`:2451-2453`) and draws every visual with three primitives only:
- `_rect` (`:2989`) → `add_shape(MSO_SHAPE.RECTANGLE, ...)`,
- `_text` (`:3000`) → `add_textbox`, single run, font hard-coded `"Nunito"` (`:2983`, `:3026`),
- `_table` (`:2933`) → `add_table`, cell-by-cell styling via `_cell_font` (`:2969`).

The only two "charts" in the deck — `_slide_revenue_yoy` (`:2530`) and `_slide_active_inactive` (`:2599`) — are literally `_rect` calls whose height/width is computed in Python from the metric value, with a denominator floored to 1 so an all-zero brand renders **degenerate/invisible bars** rather than an explicit empty state. There is no `pptx.chart`, no matplotlib, no PNG `add_picture` anywhere in `app/services/`. A grep over the service confirms zero `add_chart`/`XL_CHART_TYPE`/`matplotlib`/`plotly`. **Any donut, waterfall, trend line, treemap, or scatter would be net-new.**

### 1.2 Slide set is near-static; only 2 of 15 slides gate on data
`build()` (`:2445`) iterates a hardcoded ordered list (`:2462-2478`) of `(method, include_flag)` tuples. Cover is always slide 1. Of 15 body slides, exactly **two** carry a real gate: `_slide_channel_gap` (`_has_channel_data()` `:2441`) and `_slide_market_share` (`_has_market_share()` `:2438`). The remaining 13 always render. There is no "drop low-signal slide", no reordering by importance, no "add a slide when richer data exists" logic.

### 1.3 Tables with no empty guard render header-only "broken" tables
`_slide_top_performers` (`:2623`, table from `top_5_asins[]`), `_slide_subcategory_performance` (`:2706`), and `_slide_concentration_risk` (`:2765`) call `_table(...)` with an unguarded `rows` list. When the list is empty the deck shows a **header row over blank cells** — the single worst "looks broken in front of a client" failure mode. Content/review/channel slides *do* guard with an explicit "No source-backed …" row; the inconsistency is the bug.

### 1.4 Styling is RGB tuples copy-pasted ~40× — no theme object
There is no central theme/constants object. Brand red `(212,39,45)` is repeated inline ~15× (`:2494, 2509, 2536, 2543, 2609, 2735, 2828, 2846, 2861, 2875, …`). The 7-colour footer "rainbow" strip `[(29,78,216),(234,88,12),(22,163,74),(220,38,38),(245,158,11),(14,165,233),(100,116,139)]` is drawn on every slide (`_footer` `:2500`). Greys, semantic green/red, navy pillars — all inline literals. Typography is one family, `"Nunito"`, hard-coded and **not embedded** (`_text` `:3026`), so it silently substitutes on any viewer without the font. Sizes are inline magic numbers, many 7–9pt (table cells 7.2pt `:2967`, KPI label 7.5pt `:2923`) — dense, not deck-grade.

### 1.5 Two fully-implemented slides are dead code; the LLM pays for fields nobody renders
`_slide_catalog_audit` (`:2637`) and `_slide_approach` (`:2820`) are complete methods that are **not in the build list** — they never render. `_slide_approach` even has dedicated i18n strings that are dead. Worse, the narrative contract (`:2028-2049`) makes the LLM produce `strengths[3]`, `weaknesses[3]`, and `approach_pillars[{title,body}×3]` — and **none of those three reach the deck**. Only `overview` (→ `_slide_as_is` `:2528`), `roadmap` (→ `_slide_roadmap`), and `conclusions` (→ `_slide_conclusions` `:2900`) are rendered. We pay Anthropic tokens (`max_tokens=2200`, `:2052`, model `claude-sonnet-4-6` `:2051`) for ~50% wasted output.

### 1.6 The "Growth Scenarios" slide is identical for every brand
`_slide_projection` (`:2855`) renders three scenario cards from `growth_projection_scenarios`, which are **fixed multipliers** (`projection_ranges` `:1686-1705`): conservative ×1.10–1.15 (+10–15%), realistic ×1.25–1.35, optimistic ×1.40–1.55. Every brand on the platform gets the exact same percentages. There is an honest disclaimer (`:2894`, 7pt grey), but this is the most obviously canned slide in the deck. The genuinely dynamic content on this slide is `build_priority_actions` (`:1941`) — metric-grounded, magnitude-sorted, bilingual, emits nothing when a gap is zero. That is the *one* pattern in the whole builder worth keeping and extending.

### 1.7 Formatting helpers leak technical states into client-facing cards
`format_currency` (`:2085`) returns `"EUR 1,234"` — the literal string `"EUR "`, no `€` symbol, no Italian locale grouping (`1.234,00`). `format_percent(None)` returns `"New"` (`:2093`) and `format_number/format_currency(None)` return `"N/A"` (`:2106/:2087`) — these strings land directly inside KPI value boxes. A consulting deck showing `EUR 1,234` and `N/A` in 15pt is an immediate credibility hit.

### 1.8 Fragile rendering details
- `_body_box(title_bold=True)` indexes `paragraphs[0].runs[0]` (`:2930`) → `IndexError` if the title line is empty. Conclusions/roadmap bind directly to LLM array output, so a short/empty array yields blank coloured boxes.
- `validate_pptx_bytes` (`:3187`) asserts **12–16 slides** (`:3198`); the unit test asserts exactly 15. This couples the test suite to a *count*, not to *correctness* — a dynamic deck breaks this contract by design.
- All coordinates are absolute hard-coded inches per call. Moving one element means re-tuning its neighbours by hand.

### 1.9 Badges (provenance) surface inconsistently
`_badge` (`:2431`) appends `[HIGH]`/`[ESTIMATED]`/`[PROXY]` from `metric_source_registry[...].quality`, but it is only called on `_slide_as_is` and `_slide_market_share`. Provenance is computed for *every* numeric metric (`DECK_NUMERIC_PROVENANCE_KEYS`), then surfaced on two slides. That is both under-using a real asset and inconsistent.

### 1.10 What's genuinely good (keep)
- Full EN/IT i18n in `PPTX_STATIC_STRINGS` (`:2109-2410`) with `_t` (`:2427`) — solid bilingual scaffolding.
- `build_priority_actions` (`:1941`) — the only truly data-driven prose.
- The hard provenance gate `validate_metric_provenance_for_deck` before the deck builds — prevents fabricated numbers from reaching a slide.
- Vine-mention stripping unless revenue ≥ €100k (`:2066-2067`) — disciplined honesty.

---

## 2. Problems Identified (ranked, with severity)

| # | Problem | Severity | Evidence |
|---|---|---|---|
| P-1 | **No chart layer.** Rectangles-as-bars only; no donut/waterfall/trend/treemap/scatter. Deck cannot look consulting-grade. | Critical | `:2543`, `:2608`; grep: no chart APIs |
| P-2 | **Empty placeholders leak.** Unguarded tables render header-only; faux bars floor to invisible. Directly violates the "no empty placeholders" requirement. | Critical | `:2627`, `:2710`, `:2772`, `:2538`, `:2605` |
| P-3 | **Static slide set.** 13/15 always render in fixed order regardless of data richness. No dynamic composition. | High | `:2462-2478` |
| P-4 | **No design system.** ~40 inline RGB literals, single non-embedded font, magic-number sizes (7–9pt). | High | `:2494`+ repeats; `:2983`, `:2923` |
| P-5 | **Wasted LLM output + dead slides.** `strengths`/`weaknesses`/`approach_pillars` generated, never rendered; 2 dead slide methods. | High | `:2031-2037`, `:2637`, `:2820` |
| P-6 | **Canned projections.** Same ±multipliers for every brand. | Medium | `:1686-1705` |
| P-7 | **Formatting leaks.** `EUR 1,234`, `N/A`, `New` in KPI cards; no `€`, no IT grouping. | Medium | `:2085-2106` |
| P-8 | **Inconsistent provenance surfacing.** `_badge` on 2 slides only. | Medium | `:2431` + call sites |
| P-9 | **Fragile primitives.** `IndexError` on empty title; slide-count test couples to a magic range. | Medium | `:2930`, `:3198` |
| P-10 | **Monolith.** All slides + helpers + narrative + metrics in one 3596-line file → impossible to evolve safely. | High | whole file |
| P-11 | **No exec summary / agenda / section dividers / methodology appendix** despite rich `limitations`/`metric_source_registry` available. | Medium | build list `:2462-2478` |

---

## 3. Recommendations (priority P0–P3, effort XS–XL)

> **Verdict: rebuild the PPTX builder, do not improve it.** The current builder's core weaknesses (no chart layer, hardcoded coordinates, no theme, static slide list, dead methods) are *structural*. Patching it leaves us with a 3596-line file that still can't draw a donut. A clean `brand_analysis/deck/` package is ~3–4 weeks and unblocks everything else. Keep `calculate_brand_metrics`, the provenance spine, `build_priority_actions`, and the i18n strings — those are assets.

| ID | Recommendation | Priority | Effort |
|---|---|---|---|
| R-1 | Extract a `brand_analysis/deck/` package: `theme.py` (tokens), `charts.py` (matplotlib→PNG helper), `primitives.py`, `blocks/` (one module per block), `registry.py`, `composer.py`. | P0 | XL |
| R-2 | Introduce a **block registry**: each block declares `required_keys`, `is_available(ctx)`, `priority`, `section`, and a `render(ctx, deck)` fn. Composer renders only available blocks. **No empty placeholders, ever.** | P0 | L |
| R-3 | Add a matplotlib-rendered chart helper themed to the brand palette (donut, horizontal bar, waterfall, trend, treemap, scatter). Embed as PNG via `add_picture`. | P0 | L |
| R-4 | Build a `DeckTheme` token object (palette, type scale, spacing grid, embedded font) + a 12-col layout grid helper so blocks position relative to a grid, not absolute inches. | P0 | M |
| R-5 | Rework the narrative contract so the LLM emits **structured insight text per block** (headline + 2–4 bullets + 1 recommendation), keyed by block id. Kill `strengths`/`weaknesses`/`approach_pillars` dead fields. | P0 | M |
| R-6 | Replace canned projections: either ground scenarios in real category/trend growth, or drop the scenario cards and lead with `build_priority_actions`. | P1 | M |
| R-7 | Add Exec-Summary, Agenda, section dividers, and a Methodology/Provenance appendix (driven by `metric_source_registry` + `limitations`). | P1 | M |
| R-8 | Fix `format_currency`/`format_percent` to render `€`, locale grouping, and a single graceful empty token; remove `N/A`/`New` from value cards. | P1 | S |
| R-9 | Surface provenance consistently — every chart/table caption carries a small quality chip, not 2 slides. | P1 | S |
| R-10 | Replace the slide-count test with a **per-block contract test** (block renders iff `is_available`; golden-image snapshot per block). | P1 | M |
| R-11 | Brand Pulse deliverable = **in-app report + one-click PDF export** (not PPTX). Reuse `scheduled_report_pdf_service.py` reportlab palette. | P1 | L |
| R-12 | Reuse the document skill `pptx` patterns (HTML/CSS → thumbnail → validate loop, sanitised text, `python-pptx` server-side) as a design/QA reference for the new charts/layout — keep generation server-side. | P2 | S |

---

## 4. Technical Implementation Plan

### 4.1 Target package layout

Lift the deck out of the monolith into a package. Keep `calculate_brand_metrics`, provenance, narrative-service *core*, and i18n where they are (or move them to siblings later — out of scope for the deck rebuild).

```
backend/app/services/brand_analysis/
  deck/
    __init__.py
    theme.py            # DeckTheme: palette, type scale, spacing, grid, font path
    fonts/Nunito*.ttf   # embedded (fixes §1.4 substitution)
    format.py           # currency/percent/number/share — locale-aware, € symbol, EMPTY token
    primitives.py       # rect/text/table/kpi/body_box on a 12-col grid (no absolute inches)
    charts.py           # matplotlib→PNG: donut, hbar, waterfall, trend, treemap, scatter
    context.py          # DeckContext: metrics + narrative + registry + limitations + lang
    block.py            # Block protocol + BlockResult
    registry.py         # ordered block list + section grouping
    composer.py         # DeckComposer.build() -> bytes
    blocks/
      cover.py exec_summary.py agenda.py
      revenue.py catalog_health.py active_inactive.py top_performers.py
      content_audit.py review_image.py subcategory.py operational_gap.py
      channel_gap.py concentration_risk.py market_share.py
      priority_actions.py roadmap.py conclusions.py
      methodology_appendix.py  section_divider.py
```

`build_brand_analysis_pptx(metrics, narrative, language)` (`:3183`) keeps its **exact signature** and becomes a 3-line shim that constructs `DeckContext` and calls `DeckComposer(ctx).build()`. The processor at `:3528` does not change.

### 4.2 The block interface (pseudo-code)

```python
# deck/block.py
@dataclass
class BlockResult:
    rendered: bool
    skipped_reason: str | None = None   # for the methodology appendix

class Block(Protocol):
    id: str                              # "revenue_yoy"
    section: Section                     # PERFORMANCE | CATALOG | CHANNEL | MARKET | STRATEGY
    priority: int                        # lower = earlier within its section
    required_keys: tuple[str, ...]       # metric keys that MUST be present & non-empty

    def is_available(self, ctx: DeckContext) -> bool: ...
    def render(self, ctx: DeckContext, deck: DeckBuilder, page: int) -> BlockResult: ...
```

```python
# deck/registry.py
def default_blocks() -> list[Block]:
    return [
        CoverBlock(), ExecSummaryBlock(), AgendaBlock(),
        SectionDivider(Section.PERFORMANCE),
        RevenueYoYBlock(), CatalogHealthBlock(), ActiveInactiveBlock(), TopPerformersBlock(),
        SectionDivider(Section.CATALOG),
        ContentAuditBlock(), ReviewImageBlock(), SubcategoryBlock(),
        SectionDivider(Section.CHANNEL),
        OperationalGapBlock(), ChannelGapBlock(), ConcentrationRiskBlock(),
        SectionDivider(Section.MARKET),
        MarketShareBlock(),
        SectionDivider(Section.STRATEGY),
        PriorityActionsBlock(), RoadmapBlock(), ConclusionsBlock(),
        MethodologyAppendixBlock(),
    ]
```

```python
# deck/composer.py
class DeckComposer:
    def build(self) -> bytes:
        prs = self._new_presentation()   # 13.333 x 7.5 in (true 16:9, deck-grade)
        page, rendered_ids, skipped = 1, [], []
        for block in self.blocks:
            if isinstance(block, SectionDivider):
                if not self._section_has_content(block.section): continue
            elif not (block.is_available(self.ctx) or block.always):
                skipped.append((block.id, block.skip_reason(self.ctx))); continue
            res = block.render(self.ctx, self.deck, page)
            if res.rendered: rendered_ids.append(block.id); page += 1
        self.ctx.rendered_block_ids = rendered_ids
        self.ctx.skipped_blocks = skipped         # fed to MethodologyAppendix
        return self.deck.to_bytes()
```

**Key rule:** a block that fails `is_available` is *never drawn*. A `SectionDivider` is suppressed when its section has no rendered content. This is the mechanism that guarantees "if data missing → section not generated."

### 4.3 `is_available` per block (replaces the unguarded tables of §1.3)

| Block | `is_available` truth condition |
|---|---|
| `revenue_yoy` | `total_revenue_2025 > 0 or total_revenue_2024 > 0` |
| `top_performers` | `len(top_5_asins) >= 3` (header-only is impossible) |
| `subcategory` | `len(revenue_by_subcategory) >= 2` |
| `concentration_risk` | `top_5_share is not None and len(top_5_asins) >= 3` |
| `channel_gap` | `_has_channel_data()` (kept; reuse `:2441`) |
| `market_share` | `_has_market_share()` (kept; reuse `:2438`) |
| `content_audit` | `content_health` has ≥1 non-null gap metric |
| `review_image` | `review_rating_weaknesses` non-empty OR `asins_with_fewer_than_5_images > 0` |
| `roadmap` | `len(narrative.roadmap) >= 1` |
| `conclusions` | any of 4 conclusion arrays non-empty |
| `priority_actions` | `len(build_priority_actions(...)) >= 1` |
| `exec_summary`, `cover`, `agenda`, `methodology` | `always=True` |

### 4.4 Charting approach — decision

| Option | Editable in PPT | Styling control | Effort | Verdict |
|---|---|---|---|---|
| `pptx.chart` native | Yes | Limited (theme XML hell; no rounded donuts, no real waterfall) | M | ❌ can't hit consulting polish |
| **matplotlib → PNG → `add_picture`** | No | **Full** (any chart, exact brand palette, antialiased) | L | ✅ **Recommended** |
| HTML/CSS → headless screenshot | No | Full | XL (browser dep) | ❌ heavy infra |

**Decision: matplotlib → PNG.** Clients receive a *finished* deck, not an editable spreadsheet; rendering control matters more than post-hoc editability. `charts.py` renders to an in-memory PNG at 2× DPI, themed from `DeckTheme`, and the block inserts it via `slide.shapes.add_picture(BytesIO(png), ...)`. matplotlib is already an indirect transitive dep in most data stacks; pin it explicitly. Chart catalogue:

| Chart | Block | Replaces |
|---|---|---|
| Donut (active vs inactive) | `active_inactive` | floored faux bar `:2605` |
| Revenue waterfall / paired bar + YoY callout | `revenue_yoy` | floored faux bars `:2543` |
| Horizontal bar (top performers, sorted) | `top_performers` | header-only table |
| Treemap (subcategory revenue mix) | `subcategory` | YoY table |
| Donut + competitor bars | `market_share` | explanatory boxes |
| Lollipop / hbar (content & review gaps) | `content_audit`, `review_image` | dense tables |
| Bullet/gauge (concentration: top-5 share vs benchmark) | `concentration_risk` | KPI text |

### 4.5 Theme tokens (replaces ~40 inline RGB literals)

```python
# deck/theme.py
class DeckTheme:
    BRAND_PRIMARY   = (212, 39, 45)       # keep current brand red, single source
    INK             = (23, 23, 27)
    MUTED           = (110, 116, 124)
    POSITIVE        = (22, 163, 74)
    NEGATIVE        = (212, 39, 45)
    SURFACE         = (248, 249, 250)
    HAIRLINE        = (228, 230, 233)
    FONT = "Nunito"; FONT_PATH = ".../fonts/Nunito-Regular.ttf"   # embedded
    TYPE = {"h1": 30, "h2": 22, "kpi_value": 24, "kpi_label": 9,
            "body": 11, "caption": 8, "table": 9}                 # min 8pt floor
    GRID_COLS = 12; MARGIN = 0.55; GUTTER = 0.18
```

Drop the 7-colour rainbow footer; replace with a single hairline + brand mark + page number. Embed the font (`prs` core part) so it stops substituting.

### 4.6 LLM narrative → structured insight per block

Today the narrative is one flat blob (`:2028-2049`) and half is unused. New contract: the LLM returns a **dict keyed by block id**, each with a tight structure the block consumes verbatim. The prompt only requests insights for blocks that *will render* (composer pre-computes `available_block_ids` and injects them), so we never pay for unrendered text.

```jsonc
// New narrative contract (replaces :2028-2049)
{
  "exec_summary": {
    "headline": "Zwilling grew +18% YoY but 34% of the catalog is dormant.",
    "bullets": ["...", "...", "..."],          // 3, metric-grounded
    "so_what": "One actionable sentence."
  },
  "blocks": {
    "revenue_yoy":      {"insight": "1–2 sentences", "recommendation": "1 sentence"},
    "catalog_health":   {"insight": "...", "recommendation": "..."},
    "active_inactive":  {"insight": "...", "recommendation": "..."},
    "...": {}                                   // only for available_block_ids
  },
  "roadmap": [{"phase":"01","title":"...","body":"..."}],   // kept
  "conclusions": {"current_situation":[], "strengths":[], "plan":[], "urgency":[]}
}
```

Validation tightens: `_validate` requires `exec_summary.headline` + `blocks[id].insight` for each available id; missing → deterministic per-block fallback built from the metric itself (e.g. "Revenue moved from {a} to {b} ({yoy}% YoY)."). The "never invent numbers / Vine gate / never convert proxy to revenue share" guardrails (`:2024-2026`, `:2066`) are preserved verbatim. Model can move to a current Claude id; keep `max_tokens` similar but expect **smaller** output since we stop generating dead fields.

### 4.7 Files to change / add

| Action | Path | Note |
|---|---|---|
| ADD | `backend/app/services/brand_analysis/deck/**` | new package (§4.1) |
| EDIT | `brand_analysis_service.py:3183` | `build_brand_analysis_pptx` → shim to `DeckComposer` |
| EDIT | `brand_analysis_service.py:2070` | `_validate` → per-block contract |
| EDIT | `brand_analysis_service.py:2010` | narrative prompt → keyed-by-block, available-ids only |
| DELETE | `_slide_catalog_audit` (`:2637`), `_slide_approach` (`:2820`) | dead; migrate any wording into blocks |
| EDIT | `brand_analysis_service.py:3187` | `validate_pptx_bytes` → assert rendered blocks ⊆ available, not a count |
| EDIT | `requirements.txt` | pin `matplotlib`, `squarify` (treemap) |
| EDIT | `tests/test_brand_analysis_service.py` | replace `==15` assertion with per-block tests |
| KEEP | `calculate_brand_metrics`, provenance, `build_priority_actions`, `PPTX_STATIC_STRINGS` | assets |

### 4.8 In-app completion notifications (no email)

Add a lightweight notification on job completion (the processor already knows the terminal state at `:3542-3572`):
- Table `notifications(id, organization_id, user_id, type, payload JSONB, read_at, created_at)` (migration `022_*`).
- On terminal status in `process_brand_analysis_job`, insert one row (`type="brand_analysis.completed"`, payload = job_id/brand/status/download_url).
- `GET /notifications?unread=1` + `POST /notifications/{id}/read`; FE polls every 30s (reuse the react-query interval pattern) and shows a bell badge in `Layout.tsx`. SSE/websocket is overkill given the existing poll architecture.

---

## 5. Brand Pulse — Weekly Brand Intelligence deliverable

**Deliverable: in-app report (primary) + one-click PDF export (secondary). Not PPTX.** Rationale: Brand Pulse is a *recurring weekly read*, consumed on screen and forwarded as a one-pager — a long, editable slide deck is the wrong shape. The Brand Analysis PPTX stays the heavyweight quarterly artifact; Pulse is the lightweight weekly. Reuse `scheduled_report_pdf_service.py`'s reportlab palette (`#1F4E79` etc.) and `ScheduledReportRun` shape for generation/delivery state.

**Section/block architecture (PDF + in-app, same content model):**

| Block | Purpose | Source | Gate |
|---|---|---|---|
| Header / week band | Brand, account, ISO week, period vs prior | request | always |
| Executive headline | 1 LLM sentence: the week in one line | LLM over deltas | always |
| Brand evolution | Revenue/units/orders/AOV WoW deltas + sparklines | AnalyticsService deltas | totals present |
| Movers | Top risers / top decliners (ASIN) | `_top_asins`/`_declining_asins` | ≥1 mover |
| Advertising pulse | Spend/ACOS/TACOS/ROAS WoW | `compute_advertising_metrics` | ads connected |
| Category / market movement | Category rank/share shifts | Brand Analytics / Data Kiosk (when integrated) | data present |
| Competitor activity | New entrants, price/BuyBox moves | offer snapshots / market research | data present |
| Emerging opportunities & risks | LLM-synthesised, evidence-tagged | LLM over all blocks | always |
| Strategic recommendations | Source + Confidence + Evidence chips (already the Pulse pattern) | `build_pulse_recommendations` | ≥1 rec |

**Weekly automation:** a beat task `scan_brand_pulse_due` (mirror `scan_scheduled_reports_due`, `workers/tasks/scheduled_reports.py`) enqueues one Pulse run per opted-in brand each Monday; the run computes deltas, calls the LLM for headline/opportunities/risks, persists a `brand_pulse_reports` row, renders the PDF, and fires the in-app notification. No email.

---

## 6. Proposed Slide Architecture (consulting-grade)

| # | Block | Purpose | Data inputs | Chart | Insight text it carries | Availability gate |
|---|---|---|---|---|---|---|
| 1 | Cover | Brand identity | `brand_name` | — | title only | always |
| 2 | **Exec Summary** | The whole story on one slide | rev, yoy, active/inactive, top-5 share | mini KPI strip | LLM `exec_summary.headline` + 3 bullets + so-what | always |
| 3 | Agenda | Sections present in *this* deck | composer `rendered_block_ids` | — | section list | always |
| — | *Divider: Performance* | | | band | | section non-empty |
| 4 | Revenue YoY | Growth magnitude | rev 24/25, yoy | waterfall/paired bar | "Revenue moved €X→€Y (+Z%)" + rec | rev present |
| 5 | Catalog Health | Coverage & enrichment | asins, active, new, completeness | donut | LLM insight + rec | always |
| 6 | Active/Inactive | Dormant-asset risk | active/inactive, %inactive | donut | "N inactive = €X latent" + rec | active>0 |
| 7 | Top Performers | Revenue concentration | `top_5_asins[]` | horizontal bar | "Top 5 = X% of revenue" + rec | ≥3 ASINs |
| — | *Divider: Catalog & Content* | | | band | | section non-empty |
| 8 | Content/SEO Audit | Listing quality gaps | `content_health.*`, images | lollipop | gap counts + rec | ≥1 gap metric |
| 9 | Review/Image Weakness | Trust gaps | review/rating weaknesses | hbar | weakest ASINs + rec | weakness present |
| 10 | Subcategory Mix | Where revenue lives | `revenue_by_subcategory[]` | treemap | top/bottom subcats + rec | ≥2 subcats |
| — | *Divider: Channel & Risk* | | | band | | section non-empty |
| 11 | Operational Gap | Execution shortfalls | %inactive, %declining, multi-seller | 2×2 KPI + bullet | gap synthesis + rec | always |
| 12 | Channel Gap | Buy Box / reseller control | `seller_buy_box_summary.*` | reseller bar | control insight + rec | `_has_channel_data` |
| 13 | Concentration Risk | Dependence | top-5/10 share | bullet/gauge | risk read + rec | share present, ≥3 ASINs |
| — | *Divider: Market* | | | band | | section non-empty |
| 14 | Market Share | Competitive position | `market_analysis.*` | donut + competitor bars | share + rec | `_has_market_share` |
| — | *Divider: Strategy* | | | band | | section non-empty |
| 15 | Priority Actions | Ranked, metric-grounded to-dos | `build_priority_actions` | numbered list | already dynamic | ≥1 action |
| 16 | Roadmap | 12-month phasing | `narrative.roadmap` | 3-phase timeline | LLM phases | ≥1 phase |
| 17 | Conclusions | Exec wrap | `narrative.conclusions` | 4-quadrant | LLM bullets | ≥1 array non-empty |
| 18 | **Methodology / Provenance** | Trust & limitations | `metric_source_registry`, `limitations`, `skipped_blocks` | quality table | what's exact/proxy/estimated, what was skipped & why | always |

Deck size becomes genuinely variable (≈10–18 slides). The slide-count assertion (`:3198`) is retired in favour of the per-block contract test. The Methodology appendix turns the "missing data" story into a *feature* (transparency) instead of an empty slide.

---

## 7. Estimated Effort

| Workstream | Effort | Notes |
|---|---|---|
| Deck package scaffold (theme, primitives, grid, format, context) | M (3–4 d) | foundation for everything |
| `charts.py` matplotlib helper + 7 chart types | L (4–5 d) | the long pole |
| Block registry + composer + `is_available` per block | L (4–5 d) | the dynamic core |
| Port 16–18 blocks to new primitives + charts | L (5–6 d) | mechanical once charts/grid land |
| Narrative contract rework (keyed-by-block) + `_validate` + fallbacks | M (2–3 d) | |
| Format/locale fixes + provenance chips | S (1 d) | |
| Per-block contract tests + golden images | M (2–3 d) | replaces brittle count test |
| In-app notifications (table, endpoints, FE bell) | M (2–3 d) | shared with Brand Pulse |
| Brand Pulse weekly PDF + automation + persistence | L (5–6 d) | reuses scheduled-report infra |
| **Total (Brand Analysis deck)** | **~3.5–4 weeks** | one engineer |
| **Total (incl. Pulse weekly + notifications)** | **~5.5–6 weeks** | |

---

## 8. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| matplotlib adds a heavy/native dependency to the worker image | Pin versions; render with the `Agg` backend (no display); cache the themed style; chart render is ~50–150ms each, negligible vs SP-API calls |
| Variable slide count breaks the existing `==15` test and any downstream expectations | Replace with per-block contract + golden-image snapshots; communicate that count is now data-driven by design |
| Font embedding bloats the PPTX / licensing | Embed a subset; confirm Nunito (OFL) license permits embedding (it does); fallback to a system sans if embed fails |
| LLM keyed-by-block output drifts from the available-ids list | Composer computes `available_block_ids` and the prompt is constrained to them; any missing key → deterministic per-block fallback (no blank slide) |
| Big-bang rebuild stalls delivery | Migrate incrementally behind a flag: ship `DeckComposer` rendering the *current* 15 slides first (parity), then swap blocks to charts one section at a time; keep the old builder importable until parity is signed off |
| Removing canned projections may disappoint stakeholders who expect "growth numbers" | Keep one honest scenario block but label it illustrative and lead with metric-grounded priority actions; gate it behind data when trend signal is too thin |
| Provenance appendix exposes how much data is proxy/estimated | This is a feature, not a bug — it is the honest differentiator vs a Helium10 export; frame it as methodology transparency |

---

## 9. Bottom line

The current builder is a **dead end for a consulting-grade deck**: no charts, hardcoded everything, half its LLM output thrown away, and empty placeholders that look broken in front of a client. **Rebuild it** as a small `deck/` package built on a block registry where every block declares its own `is_available` gate — that single architectural move delivers the headline requirement (no empty placeholders, dynamic composition) for free. Add a matplotlib chart layer and a real theme, rework the narrative to feed structured insight *per rendered block*, and turn the "missing data" problem into a methodology-transparency feature. Keep the genuine assets — metrics, provenance gate, `build_priority_actions`, i18n. For Brand Pulse, ship an in-app weekly report with PDF export on the scheduled-report rails, not another PPTX.
