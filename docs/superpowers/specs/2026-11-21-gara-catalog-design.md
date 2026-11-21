# Gara red items: catalogue monitoring, bulk update v2, quarterly report

Date: 2026-11-21. Source: Gioia Mormile's "Funzionalità tool x gara" (18 Nov 2026),
the items marked red. Deadline set by Roberto Botto: 30 Nov 2026, for a tender demo.
Decisions below were made by the builder (the user delegated the how); each is
marked **[call]** where it is ours, not the client's.

## Intent

Inthezon must show a prospect, in a demo, that the tool keeps thousands of Amazon
product pages compliant and protected, can change them in bulk with an operator's
approval, and produces a quarterly business review. The tool today scores the wrong
listing fields, has no content baseline, no variation monitoring, a seller-only bulk
editor that can delete bullets, and no quarterly report.

## Goals (the five red items)

1. **R1 Listing quality traffic lights.** Per ASIN and per element, one of
   green (compliant, optimised), yellow (compliant, improvable), red (non-compliant
   or missing), grey (cannot be verified). Elements and the client's thresholds:
   - Title: max 75 characters, contains brand, main keyword, distinctive features.
   - Item Highlights: max 125 characters.
   - Bullet points: 5, with keywords, features, benefits, usage.
   - Description: complete, keywords, SEO.
   - Images: target 8 per product (main, detail, lifestyle, infographic).
   - Main image: white background, no promotional text, product fills at least 85%.
   - Video: at least one.
   - A+ Content: present, quality (images, text, comparison tables).
   - Backend keywords: present, under 250 bytes.
   - Attributes: complete (dimensions, materials, composition, colour, size, age range).
   - Category: correct placement in categories and subcategories.
   Mandatory requirements are separated from best practice. Rules are editable and
   differ per product category and marketplace. The current traffic-light graphics
   are improved.
2. **R2 Broken variations.** Store each family's original structure (parent and
   children), scan daily, flag detached children, broken families and wrong
   associations, show original vs live, allow bulk restore.
3. **R3 Content protection.** Store the brand-approved content and compare it daily
   with what is live: title, bullets, description, images (replaced, missing,
   reordered), A+ (missing or changed), attributes. Flag anomalies, show original and
   changed side by side, allow restore, keep a history.
4. **R4 Bulk catalogue update.** Excel/CSV import and export; update texts, images,
   attributes; restore original content; create and restore variations; fill and
   validate NIS files; generate Vendor Central compatible files; update via Amazon
   API where allowed, or via bulk files, always after operator approval.
5. **R5 Dashboard and reporting.** Periodic data collection with history; automatic
   quarterly report with data, charts, period comparisons, AI insights and
   suggestions; combine Vendor Central, Brand Analytics, Ads and market intelligence,
   marking actual vs estimated; analysis by brand, category, ASIN, keyword,
   competitor and country.

## Non-goals

- Yellow and green items of the doc (catalogue health beyond listing issues,
  competitive scenario, keyword traffic, retail/ADV integration, new products).
- Amazon Notifications (needs AWS SQS/EventBridge); the daily scan replaces it.
- Restoring A+ content through the API (we detect and show; restore is manual).
- Filling Amazon's official NIS .xlsm templates: blocked until Gioia sends them.
  We validate new items against Amazon's product type schema instead.

## Anti-goals

- Never write to a live Amazon listing without an explicit operator approval in
  the tool. Every write is first checked with Amazon's `VALIDATION_PREVIEW` mode.
- Never lose content: a partial upload must not erase fields it does not mention.
- Never show a green light for something we could not check (that is grey).

## Constraints

- Stack stays as is: FastAPI + SQLAlchemy 2 async + Alembic, React + Vite +
  Tailwind + shadcn/ui, in-process APScheduler, single Render instance.
- CI has no database: tests are pure-logic or use the FakeAsyncSession pattern;
  Postgres-backed tests are skipped unless `TEST_DATABASE_URL` is set.
- Vendor and seller accounts must both work. Catalog Items works for any ASIN;
  Listings Items accepts a vendor code as `sellerId`.
- SP-API rates: Catalog Items `getCatalogItem` 2 req/s; Listings Items 5 req/s.
- No new paid services. Anthropic credit is at zero: AI text must fall back to
  deterministic text.
- Italian and English UI strings must stay in parity (CI checks it).

## Approaches considered

1. **Monitor from Catalog Items, write through Listings Items** **[call, chosen]**.
   Catalog Items returns what shoppers see for any ASIN (vendor or seller):
   attributes, images, relationships, product type, classification. Listings Items
   adds issues/status and backend keywords when we know the SKU and seller/vendor
   code, and is the write channel (`patchListingsItem`, with `VALIDATION_PREVIEW`).
   Bulk writes over ~50 rows go through `JSON_LISTINGS_FEED`.
2. Monitor from Listings Items only. Rejected: it shows what this partner
   submitted, not what Amazon publishes after other contributors overwrite it,
   which is exactly what content protection must catch; and it needs a SKU.
3. Helium 10 Listing Analyzer for quality. Rejected for the client's own catalogue:
   1,000 calls/month cannot cover thousands of ASINs daily.

## Design

### Data

New tables (migration `034_catalog_monitor`):

- `listing_content_versions`: one row per distinct content of an ASIN
  (account, asin, content_hash, content JSONB, first_seen_at, last_seen_at).
  A new row only when the hash changes; otherwise `last_seen_at` moves. This is
  the history.
- `listing_content_baselines`: the approved content per (account, asin), with
  source (`live_snapshot` or `excel_upload`), approved_by, approved_at.
- `variation_family_baselines`: per (account, parent_asin): variation theme and
  child ASIN list.
- `catalog_anomalies`: open/acknowledged/restored/resolved findings per
  (account, asin, kind, field), with baseline and live values. At most one open
  anomaly per key; auto-resolved when live matches baseline again.
- `catalog_change_requests`: the approval queue for every write (bulk rows,
  restores, variation restores, new items): payload (product type + patches),
  status lifecycle, validation issues, submission result, who created and approved.
- `listing_quality_rules`: per-organization overrides of the rule defaults, scoped
  by optional marketplace and optional product type.
- `product_type_definitions_cache`: required and known attributes per
  (marketplace, product_type), refreshed weekly.
- `image_checks`: main-image analysis keyed by image URL.
- `catalog_api_capabilities`: per account, the result of trying each Amazon API.
- `products.main_keyword` (+ source) column.

Existing `listing_quality_snapshots` keeps the daily per-ASIN evaluation (score and
per-rule results) for trends.

### Daily scan (05:00 UTC, all active accounts, seller and vendor)

For each active product of the account: fetch Catalog Items (attributes, images,
relationships, summaries, classifications, productTypes); when SKU and
seller/vendor code are known, fetch Listings Items (attributes, issues, summaries);
fetch A+ publish records. Normalise into `ListingContent`, store a version,
evaluate R1, compare with the baseline (R3) and the family baseline (R2), upsert
anomalies. A "Scan now" button runs the same for one account in a background
thread.

### R1 rules **[call on thresholds and mandatory split]**

| Rule | Mandatory by default | Green | Yellow | Red | Grey |
|---|---|---|---|---|---|
| title | yes | present, ≤75 chars, has brand and main keyword | ≤200 but >75, or brand/keyword missing | missing or >200 | — |
| item_highlights | no | present, ≤125 | >125 | — | attribute not exposed by Amazon |
| bullets | yes | 5 (and keyword in one, if known) | 3–4, or no keyword | 0–2 | — |
| description | no | ≥200 chars, keyword present | shorter or no keyword | missing | — |
| images | no | ≥8 | 5–7 | <5 | — |
| main_image | yes | white background and fill ≥85% | fill <85% | missing or background not white | image could not be analysed |
| video | no | — | — | — | always grey: not exposed by SP-API |
| aplus | no | ≥4 modules | 1–3 modules | none | A+ API not available for account |
| backend_keywords | no | 100–250 bytes | <100 bytes | missing or >250 bytes | not readable (no listing access) |
| attributes | yes | all required + recommended present | required complete, recommended missing | required missing | product type schema unavailable |
| category | yes | classification present and matches expected (if configured) | — | missing or mismatch | — |

Promotional text on the main image is grey ("not verifiable") unless an AI vision
check is available. Product-level state: red if any mandatory rule is red;
yellow if any rule is red or yellow; green otherwise; grey only if every rule is
grey. Score 0–100: green 1, yellow 0.5, red 0, grey excluded, mandatory weight 2.

Overrides (`listing_quality_rules`) may change `enabled`, `mandatory` and params
(`max_length`, `target_count`, `min_count`, `min_fill`, `max_bytes`,
`expected_category_keywords`, `recommended_attributes`). Resolution: most specific
(marketplace + product type) wins over product type, over marketplace, over
organization default, over code defaults.

Main keyword per ASIN: operator-set (UI or Excel column); otherwise the top Brand
Analytics term that ASIN wins; otherwise unknown (keyword checks are skipped, noted).

### R2 and R3

Baselines are created from the latest live version ("approve current content", per
ASIN or all) or from an uploaded Excel in the export format. Families are captured
at the same time from relationships. Diffed fields: title, bullets (text and order),
description, images (set and order), A+ (presence, module count), attributes (all
baseline attributes except volatile ones such as prices, offers, stock).
Anomaly actions: accept live as new baseline; restore (creates a change request
with patches built from the baseline, validated with `VALIDATION_PREVIEW`).
Variation restore patches each child's `parentage_level`,
`child_parent_sku_relationship` and `variation_theme`; it needs child and parent
SKUs, otherwise the request is marked "file only" and goes into a JSON listings
feed file for manual upload.

### R4

The export is the import template (round trip): asin, sku, product_type, title,
bullet_1..5, description, backend_keywords, main_keyword, main_image_url,
image_1..8, parent_asin, parent_sku, variation_theme, and `attr:<name>` columns.
Upload builds a batch of change requests: only changed, non-empty cells become
patches; bullets are merged position by position with the live bullets; values
carry `language_tag` and `marketplace_id`; product type comes from the row or the
latest version. Each request is validated (`VALIDATION_PREVIEW`), shown with a
before/after diff and Amazon's issues, then approved (admin role) and submitted
(per-SKU patch, or one `JSON_LISTINGS_FEED` for large batches). Accounts without
listing write access (no vendor code/SKU) get a downloadable feed file instead.
New items ("NIS"): Excel with product_type + attributes, validated against the
product type schema's required attributes and with `putListingsItem` in
`VALIDATION_PREVIEW`, then submitted like any other request.

### R5

New report `quarterly_review` (PPTX, reusing the brand-analysis deck primitives and
charts) for a quarter and a scope (accounts = countries, optional brand, category,
ASIN list). Sections: KPIs vs previous quarter and same quarter last year (revenue,
units, ad spend, ROAS, ACoS, TACOS, return rate); monthly trend chart; top and
bottom ASINs; catalogue health (R1 distribution, open R2/R3 anomalies); search terms
(Brand Analytics, where available); tracked competitors; AI insights and actions
(deterministic fallback). Every figure carries a provenance tag: actual (Amazon
reports) or estimated (Helium 10, forecasts). Scheduled reports gain the `quarterly`
frequency. The dashboard gains brand and category filters.

### Amazon access check

`POST /catalog-monitor/capabilities/check` tries, per account: Catalog Items,
Listings Items read, Product Type Definitions, A+ Content, Feeds list, vendor code
resolution. Results are stored and shown; features use them to choose grey/file-only
paths instead of failing.

## Left to the builder

Component layout and copy of the new screens (in Italian and English), chart
styling, batch sizes, retry details, and the exact slide layout of the quarterly
report, within the existing design language.

## Open with the client (do not block the build)

Gara date and demo account; source of approved content; NIS templates; main
keyword list; an ASIN with Item Highlights; a model quarterly report; who approves;
category-specific rule values. Drafted to Gioia on 21 Nov (unsent).
