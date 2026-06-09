# Brand Analysis — PPTX / Reporting Generation: Discovery Map

All anchors are in `backend/app/services/brand_analysis_service.py` (3596 lines) unless noted.
Entry: `build_brand_analysis_pptx(metrics, narrative, language)` (L3183) → `BrandAnalysisPptxBuilder(...).build()` (L2445).
Template version constant: `PPTX_TEMPLATE_VERSION = "brand-analysis-pptx-v2"` (L30). Narrative version `NARRATIVE_TEMPLATE_VERSION = "brand-analysis-narrative-v2"` (L29).

---

## 1. How the deck is built (rendering technology)

**100% hand-drawn python-pptx primitives. No charts, no images, no matplotlib, no native pptx charts.**

- `build()` (L2445-2488): creates a blank `Presentation()`, hard-sizes it to **10 × 5.625 in** (16:9). Stashes pptx classes on `self` (`_RGBColor`, `_PP_ALIGN`, `_MSO_ANCHOR`, `_Inches`, `_Pt`). Every slide uses blank layout 6 (`_blank`, L2490).
- Every visual element is one of three primitives:
  - `_rect(...)` (L2989) — `slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, ...)` with solid fill, optional 1px line. **This is the only "chart" mechanism** — bars are rectangles whose height/width is computed in Python from the metric value.
  - `_text(...)` (L3000) — `add_textbox`, single run, font hard-coded to **"Nunito"**, word-wrap on, zero margins.
  - `_table(...)` (L2933) — `slide.shapes.add_table`, styled cell-by-cell via `_cell_font` (L2969).
- Confirmed via grep: **no `matplotlib`, `seaborn`, `add_chart`, `XL_CHART_TYPE`, `CategoryChartData`, or `plotly` anywhere in `app/services/`.** The two "charts" in the deck (`_slide_revenue_yoy` bars at L2543, `_slide_active_inactive` stacked bar at L2608-2609) are literally `_rect` calls with Python-computed dimensions. No axes, gridlines, labels-on-bar beyond a manual value textbox, no legends.

**Implication for "consulting-grade":** there is currently no real charting layer. Any donut/pie (catalog split, market share, concentration), waterfall, trend line, or treemap would have to be added either as (a) native pptx charts (`pptx.chart`, editable in PowerPoint, but limited styling) or (b) matplotlib-rendered PNGs embedded via `add_picture` (full styling control, not editable). Neither exists today.

---

## 2. Styling system (the de-facto "design tokens")

There is **no central theme/constants object** — colors are repeated as raw RGB tuples inline in every method. This is the single biggest structural weakness for a redesign.

**Color palette (scattered literals):**
- Brand red `(212, 39, 45)` — header bar, cover, 2025 bars, accent. Appears ~15× inline (e.g. L2494, 2509, 2536, 2543, 2609, 2735, 2828, 2846, 2861, 2875).
- Footer rainbow strip `[(29,78,216),(234,88,12),(22,163,74),(220,38,38),(245,158,11),(14,165,233),(100,116,139)]` (L2501) — 7-color bar at bottom of every slide (`_footer`, L2500).
- Neutral grey `(100,116,139)` for 2024 bars; greys `(248,248,248)`/`(230,230,230)` for KPI cards; `(250,250,250)`/`(230,230,230)` for body boxes; text greys `(20,20,20)/(55,55,55)/(70,70,70)/(80,80,80)/(90,90,90)/(150,150,150)`.
- Semantic green `(22,163,74)` / red `(212,39,45)` for YoY cells (`_yoy_cell_color`, L3153) and active/inactive split.
- Approach pillars dark navy `(25,35,50)` (L2827); approach banners blue/orange/green (L2832-2834); roadmap phase colors `[(212,39,45),(234,88,12),(22,163,74)]` (L2846).

**Typography:** Single font family **"Nunito"** hard-coded in `_text` (L3026) and `_cell_font` (L2983). **Risk: Nunito is not embedded** — if it's not installed on the viewer's machine, PowerPoint substitutes a default font. No font embedding logic exists. Sizes are inline magic numbers (cover 30/13pt; title 22pt + subtitle 9pt via `_title` L2917; KPI label 7.5pt + value 15pt via `_kpi` L2921; body 8.8pt via `_body_box`; table headers 7.5pt, cells 7.2pt). Many are very small (7–9pt) — dense, not deck-grade.

**Layout primitives (reusable building blocks):**
- `_title(slide, title, subtitle)` (L2917) — title + grey subtitle top-left.
- `_kpi(slide, x,y,w,h, label, value)` (L2921) — grey card with small bold label + big value. The workhorse; used on nearly every slide.
- `_body_box(slide, ..., text, title_bold)` (L2926) — light-grey rounded-less box; if `title_bold`, bolds first paragraph's first run (L2929-2931). **Fragile**: assumes `paragraphs[0].runs[0]` exists.
- `_table(...)` (L2933) — header row grey-filled bold; optional `yoy_columns` colors cells green/red via `_yoy_cell_color`.
- `_add_header(slide, page)` (L2493) — red 0.34in top bar with brand name + page number, plus footer.
- `_footer(slide)` (L2500) — 7-color rainbow strip.

All coordinates are **absolute hard-coded inches** per call — no grid/layout helper, no responsive flow. Adding/removing a KPI means hand-retuning x/y/w/h of everything around it.

---

## 3. Slide inventory (current deck)

Build order is a static list in `build()` (L2462-2478): `[(_slide, include_flag), ...]`. Cover is always slide 1 (page numbering starts at 2). Only **2 of 15 slides are conditional**; the rest always render. Two methods exist but are **NOT in the build list**: `_slide_catalog_audit` (L2637) and `_slide_subcategory_performance`… (subcategory IS in the list; catalog_audit is the dead one). Also `_slide_approach` (L2820) is **defined but never added to the build list** — dead code.

| # | Slide method | Title (en) | Renders | Data consumed | Conditional skip? | Empty-state behavior |
|---|---|---|---|---|---|---|
| 1 | `_slide_cover` (L2507) | "{BRAND} ON AMAZON" | Full red slide, brand + subtitle | `brand_name` | Always | — |
| 2 | `_slide_as_is` (L2514) | Current Amazon Performance | 6 KPI cards + narrative overview box | `total_revenue_2025/2024`, `yoy_percent`, `weighted_average_rating`, `total_units_sold_2025`, `average_price_per_asin`; `narrative.overview` | Always | KPIs show `"N/A"`/`"New"` from `format_*` when None |
| 3 | `_slide_revenue_yoy` (L2530) | Revenue 2024 vs 2025 | 2 faux bar rects scaled to max, YoY KPI, footnote | `total_revenue_2024/2025`, `yoy_percent` | Always | If both 0, `max_value` floored to 1 → zero-height bars |
| 4 | `_slide_catalog_health` (L2555) | Catalog Health | 4 KPI cards + readiness **table** + 2 body boxes (missing fields, limitations) | `total_asins_2025`, `active/inactive_asins_2025`, `new_asins_yoy`, `data_readiness.catalog_enrichment`, `data_completeness.missing_optional_fields_2025`, `limitations.items` | Always | Table shows "N/A"; body boxes show "- None" bullet |
| 5 | `_slide_active_inactive` (L2599) | Active / Inactive ASINs | Stacked rect bar (green/red) + 3 KPI cards + footnote | `active_asins_2025`, `inactive_asins_2025`, `percentage_inactive_asins` | Always | `total` floored to 1; 100% green if no inactive |
| 6 | `_slide_top_performers` (L2623) | Top Performing ASINs | 5-col table, YoY-colored | `top_5_asins[]` | Always | **No empty guard** — empty `top_5_asins` → table with header only (1 row) |
| 7 | `_slide_content_audit` (L2659) | SEO & Content Audit | 4 KPI cards + gap table | `average_images_per_asin`, `content_health.{asins_missing_bullets, asins_missing_description, short_title_count, content_gap_asins}` | Always | If no gaps → single "N/A / No source-backed content gaps" row |
| 8 | `_slide_review_image_weaknesses` (L2683) | Image / Review Weaknesses | 3 KPI cards + weakness table | `asins_with_fewer_than_5_images`, `review_rating_weaknesses.{...}` | Always | If none → single "N/A / No review/rating weakness" row |
| 9 | `_slide_subcategory_performance` (L2706) | Subcategory Performance | 4-col table, YoY-colored | `revenue_by_subcategory[]` (top 8) | Always | **No empty guard** — empty list → header-only table |
| 10 | `_slide_operational_gap` (L2720) | Operational Performance Gap | 4 KPI cards (2×2) + 3 concentration KPIs | `percentage_inactive_asins`, `percentage_declining_asins_among_active`, `asins_with_more_than_1_seller`, `subcategory_with_largest_decline`, `top_5/10_revenue_share`, `average_revenue_per_active_asin` | Always | KPIs render "N/A" |
| 11 | `_slide_channel_gap` (L2744) | Channel Performance Gap | 3 KPI cards + reseller table | `seller_buy_box_summary.{...}`, `reseller_buy_box_distribution[]` (fallback to current snapshot) | **YES — `_has_channel_data()`** (L2441) | If included but no rows → "Not available in source data" row |
| 12 | `_slide_concentration_risk` (L2765) | Concentration Risk | 3 KPI cards + top-5 table | `top_5/10_revenue_share`, `average_revenue_per_active_asin`, `top_5_asins[]` | Always | **No empty guard** on table |
| 13 | `_slide_market_share` (L2782) | Market Share & Competition | If external market: 3 KPIs + competitor table; else 2 body boxes explaining N/A | `market_analysis.{status, market_size_2025, market_share_2024/2025, competitive_brand_distribution}` | **YES — `_has_market_share()`** (L2438) | Whole slide skipped unless `status=="calculated_from_external_market_export"`; internal else-branch never reached because skip removes it |
| 14 | `_slide_projection` (L2855) | Growth Scenarios | Current-rev band + 3 scenario cards + priority actions + disclaimer | `total_revenue_2025`, `yoy_percent`, `growth_projection_scenarios.{conservative,realistic,optimistic}`, `build_priority_actions(metrics)` | Always | Scenarios are **fixed multipliers** (see §5) |
| 15 | `_slide_roadmap` (L2842) | Operational Roadmap | 3 numbered phase rows | `narrative.roadmap[:3]` | Always | If <3 → fewer rows; if AI returns empty titles → blank rows |
| 16 | `_slide_conclusions` (L2896) | Conclusions | 4 quadrant boxes (situation/strengths/plan/urgency) | `narrative.conclusions.{current_situation,strengths,plan,urgency}` | Always | Empty lists → title-only box |

**Dead/unused slide methods:** `_slide_catalog_audit` (L2637) and `_slide_approach` (L2820) are fully implemented but **not in the build list** (L2462-2478). They're orphaned. `_slide_approach` even has its own i18n strings (L2231-2240) that never render.

**Net deck size:** 13 always-on + cover = 14, plus up to 2 conditional = **14–16** slides. `validate_pptx_bytes` (L3187) asserts **12–16** (L3198); the test asserts exactly **15** (tests L207, L217) — i.e. the test fixture happens to trigger channel data but not market share, or vice versa.

---

## 4. Narrative service: what the deck consumes from the LLM

`BrandAnalysisNarrativeService.generate(...)` (L1990) → Anthropic `claude-sonnet-4-6`, `max_tokens=2200` (L2050-2054). On any failure → `build_fallback_narrative` (L1861, deterministic). Vine mentions stripped if `rules.can_mention_vine` false (L2066, gated on revenue ≥ €100k at L1811).

**Narrative output shape (the contract the deck reads), from the prompt at L2028-2049 and `_validate` L2070:**
```
overview: str                       # → _slide_as_is body box (L2528)
strengths: [str,str,str]            # NOT rendered on any slide (only weaknesses/strengths feed conclusions separately)
weaknesses: [str,str,str]           # NOT rendered (dead — no slide reads narrative.weaknesses)
approach_pillars: [{title, body}]   # → _slide_approach ONLY, which is DEAD (never built). So pillars never render.
roadmap: [{phase,title,body}]       # → _slide_roadmap (L2847)
conclusions: {current_situation[], strengths[], plan[], urgency[]}  # → _slide_conclusions (L2900)
```

**Concrete weaknesses:**
- `narrative.strengths`, `narrative.weaknesses`, and `narrative.approach_pillars` are **generated but never displayed** (approach slide is dead code; strengths/weaknesses arrays have no consumer). The LLM is paying tokens for unused output.
- Only `overview`, `roadmap`, and `conclusions` actually reach the deck. ~half the narrative payload is wasted.
- The deck is **mostly static template + deterministic metrics**; LLM contribution is 3 small text regions. "Dynamic" = numbers change; structure/wording is fixed.

---

## 5. How "dynamic" vs fixed the deck is today

- **Slide set:** near-fixed. 13/15 slides always render in a fixed order. Only channel-gap and market-share gate on data presence. There is no logic to reorder, prioritize, or drop low-signal slides, nor to add slides when richer data exists.
- **Projections (`_slide_projection`):** **fixed multipliers, identical for every brand** — conservative ×1.10–1.15, realistic ×1.25–1.35, optimistic ×1.40–1.55 (`projection_ranges`, L1686-1705). Labeled "illustrative, not a forecast" (disclaimer L2251/L2894) — honest, but not analyst-grade. This is the most obviously "canned" slide.
- **Priority actions (`build_priority_actions`, L1941):** genuinely dynamic — derived from real metric gaps, sorted by magnitude, bilingual, only emits non-zero items. Good pattern; the only truly data-driven prose on the deck.
- **Badges:** `_badge(metric_key)` (L2431) appends `[HIGH]/[ESTIMATED]/...` quality tags from `metric_source_registry`. Applied only on `_slide_as_is` and `_slide_market_share` — inconsistent (provenance is computed for all metrics but surfaced on 2 slides).
- **i18n:** full EN/IT via `PPTX_STATIC_STRINGS` (L2109-2410) + `_t()` (L2427). Solid.

---

## 6. Where empty placeholders / weak states can appear

1. **Tables with no empty guard** — `_slide_top_performers` (L2627), `_slide_subcategory_performance` (L2710), `_slide_concentration_risk` (L2772) build rows directly from possibly-empty lists with **no `if not rows` fallback** → renders a header-only table (looks broken). Contrast with content/review/channel slides which DO guard.
2. **Zero-value faux bars** — `_slide_revenue_yoy` (L2538) and `_slide_active_inactive` (L2605) floor denominators to 1, so all-zero data renders invisible/degenerate bars rather than an explicit "no data" state.
3. **`format_currency` returns `"EUR 1,234"`** (L2085-2088) — plain `"EUR "` prefix, not the `€` symbol, no locale grouping for IT. `format_percent(None)` returns `"New"` (L2093) which leaks into KPI cards as a literal value.
4. **`_body_box(title_bold=True)`** (L2929) indexes `paragraphs[0].runs[0]` — if the title line is empty (e.g. empty narrative section), this throws `IndexError`. Brittle.
5. **Nunito not embedded** — font silently substitutes on viewers without it installed.
6. **Conclusions/roadmap** bind directly to LLM output; if the model returns short/empty arrays, boxes render blank with just a colored bar/marker.

---

## 7. Reusable patterns elsewhere in the codebase

- **`scheduled_report_pdf_service.py`** — uses **reportlab** (`SimpleDocTemplate`, `Paragraph`, `Table`, `TableStyle`, `ParagraphStyle`) with a **real palette of HexColors** (`#1F4E79`, `#5D6D7E`, `#D5DBDB`, alternating `ROWBACKGROUNDS`) and named paragraph styles (title/subtitle/section/body at L42-76) — a much more disciplined styling approach than the inline RGB tuples in the pptx builder. **No charts though** (tables + text only). Good source for: a centralized style/token object, alternating-row tables, section hierarchy.
- **`strategic_recommendations_export.py`** — **openpyxl `Workbook`** (xlsx), not slides. `build_recommendations_workbook_bytes` (L146). Not directly reusable for pptx, but shows the export-bytes-from-service pattern.
- **`export_service.py`** — multiple `io.BytesIO()` exporters (csv/xlsx/zip). Same bytes-return pattern.
- **Neither reusable module draws charts.** There is **no existing chart-rendering helper anywhere** to borrow — a consulting-grade redesign must introduce one (recommend matplotlib→PNG→`add_picture`, or native `pptx.chart`).

---

## 8. Gap to consulting-grade (Helium10-style) — concrete

1. **No real charts.** Bars are rectangles; no pies/donuts, no trend lines, no waterfall (revenue bridge), no treemap (catalog/subcategory mix), no scatter (price vs rating). This is the #1 gap. Need a chart helper (matplotlib PNGs for full control, brand-themed).
2. **No design system.** RGB literals are copy-pasted ~40×; one palette object + spacing/size scale + a layout grid would make the deck consistent and editable. Mirror the reportlab style-dict approach.
3. **Dead/wasted content.** `_slide_approach` and `_slide_catalog_audit` orphaned; `narrative.strengths/weaknesses/approach_pillars` generated but never rendered. Either wire them in or stop generating them.
4. **Canned projections.** Fixed ±multipliers for every brand undermine credibility. Could ground in actual YoY trend / category growth, or drop in favor of the (already-good) data-driven priority actions.
5. **Inconsistent provenance surfacing.** `_badge` only on 2 slides though provenance is computed for all metrics.
6. **Dense, tiny type** (7–9pt) and 16:9 over-packed KPI grids — not the "one idea per slide, big visual" cadence of consulting decks.
7. **Fragile empty states** (header-only tables, `paragraphs[0].runs[0]` index, zero-height bars) — a redesign should route every slide through a guarded "no data → explicit empty card" path.
8. **No cover/section dividers / agenda / executive-summary** slide beyond the single red cover; no per-section transitions; no appendix/methodology slide despite heavy provenance/limitations data being available in `metrics.limitations` / `metric_source_registry`.
9. **Font not embedded** → rendering drift off the author's machine.
10. **Monolith.** All 16 `_slide_*` + helpers live in one 3596-line service file. Extracting a `pptx/` package (theme, primitives, charts, one module per slide) would be a precondition for any serious redesign.

---

## 9. Key file:line anchor index

- `BrandAnalysisPptxBuilder` class: L2413; `build()` (slide list): L2445-2488
- Conditionals: `_has_market_share` L2438, `_has_channel_data` L2441, `_badge` L2431
- Chrome: `_add_header` L2493, `_footer` L2500 (rainbow strip), `_blank` L2490
- Slides: cover L2507, as_is L2514, revenue_yoy L2530, catalog_health L2555, active_inactive L2599, top_performers L2623, **catalog_audit L2637 (DEAD)**, content_audit L2659, review_image L2683, subcategory L2706, operational_gap L2720, channel_gap L2744, concentration_risk L2765, market_share L2782, **approach L2820 (DEAD)**, roadmap L2842, projection L2855, conclusions L2896
- Primitives/helpers: `_title` L2917, `_kpi` L2921, `_body_box` L2926, `_table` L2933, `_cell_font` L2969, `_rect` L2989, `_text` L3000
- Color helpers: `_yoy_cell_color` L3153
- Entry/validation: `build_brand_analysis_pptx` L3183, `validate_pptx_bytes` L3187 (asserts 12–16 slides, L3198)
- Data feeding deck: `calculate_brand_metrics` L1300 (full metrics dict L1707-1829); `growth_projection_scenarios` fixed multipliers L1686-1705
- Narrative: `BrandAnalysisNarrativeService.generate` L1990 (prompt L2010-2049, model `claude-sonnet-4-6` L2051); `_validate` L2070; `build_fallback_narrative` L1861; `_remove_vine_mentions` L1853; `build_priority_actions` L1941 (the only truly data-driven prose)
- i18n strings: `PPTX_STATIC_STRINGS` L2109-2410; `_t` L2427
- format_* helpers: L2085-2106 (`"EUR "` prefix, `format_percent(None)→"New"`)
- Orchestration: `process_brand_analysis_job` L3219; metric/narrative/pptx wiring L3483-3541
- Reusable styling refs: `scheduled_report_pdf_service.py` (reportlab styles L40-121); `strategic_recommendations_export.py` (openpyxl L146-167)
