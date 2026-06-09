# Brand Analysis & Brand Pulse — Amazon Data Coverage Review

**Author:** Amazon Data Specialist Agent (SP-API / Vendor / Ads / Data Kiosk / Brand Analytics)
**Scope:** Own DATA COVERAGE. Evaluate the 10 unfetched sources, cross-check probe-vs-fetch, and recommend a prioritized integration order — with explicit seller-vs-vendor differences and which sources unlock Brand Pulse competitor/market intelligence.
**Date:** 2026-06-09 · branch `master` @ `156536c`

---

## 0. The one-sentence verdict

The capability probe **detects 11 sources but the pipeline only consumes 4** (Catalog Items, Product Pricing, Product Fees, A+ Content). Data Kiosk, Brand Analytics, Finance Reports, Settlement Reports, and Listings are probed, persisted, and then **ignored** — and the report's headline "market share / search share" numbers are hardcoded to `None` unless a human uploads an external Excel. The good news: the **hard plumbing already exists** (`request_and_download_report` async poller, vendor report support, an Ads report poller), so most of the missing value is *wiring*, not *building*.

---

## 1. Findings (grounded in code)

### 1.1 What the probe checks vs what the pipeline fetches

The probe (`brand_analysis_capabilities.py:124-332`) runs 11 small read calls and persists booleans. But the **only data that reaches `calculate_brand_metrics`** comes from `AmazonAccountDataSource._fetch_catalog_via_market_research` (`brand_analysis_sources.py:574-613`), which calls exactly three things per ASIN:

- `_fetch_product_data(client, asin)` → Catalog Items + competitive pricing (`market_research_service.py:1030`)
- `client.estimate_fba_fee_for_asin(asin, price)` → Product Fees (`sp_api_client.py:1286`)
- `client.get_aplus_content_for_asin(asin)` → A+ Content (`sp_api_client.py:1382`)

Plus brand discovery via `client.search_catalog_by_keyword(brand, max_results=80)` (`brand_analysis_sources.py:399`). **That is the entire SP-API surface Brand Analysis actually uses.**

| Capability key (`capabilities.py:23-35`) | Probed? | Probe call | **Fetched into metrics?** |
|---|---|---|---|
| `sales_and_traffic_available` | yes (`:228-242`) | `get_reports(GET_SALES_AND_TRAFFIC_REPORT)` | **Yes** — but via the warehouse `sales_data` table, not a fresh probe pull |
| `data_kiosk_available` | yes (`:259`) | `_data_kiosk_api().get_queries(pageSize=1)` | **No** |
| `brand_analytics_available` | yes (`:244`) | `get_reports(GET_BRAND_ANALYTICS_SEARCH_TERMS_REPORT)` | **No** |
| `brand_registry_available_or_inferred` | inferred (`:312`) | = `aplus_available` result | **No** (only the inference, never used) |
| `product_pricing_available` | yes, seller-only (`:275-285`) | `get_item_offers(asin, New)` | **Yes** (price/offers via `_fetch_product_data`) |
| `product_fees_available` | yes, seller-only (`:287-302`) | `get_product_fees_estimate_for_asin` | **Yes** |
| `aplus_available` | yes (`:304-311`) | `search_content_documents(pageSize=1)` | **Yes** |
| `finance_reports_available` | yes (`:254-258`) | `list_financial_event_groups(MaxResultsPerPage=1)` | **No** |
| `settlement_reports_available` | yes (`:249-253`) | `get_reports(GET_V2_SETTLEMENT_REPORT_DATA_FLAT_FILE)` | **No** |
| `catalog_items_available` | yes (`:265-274`) | `get_catalog_item(asin, [summaries])` | **Yes** |
| `listings_available` | yes, seller-only (`:316-328`) | `get_listings_item(sellerId, sku)` | **No** |

**5 of 11 capabilities are pure dead weight** (probe-only): Data Kiosk, Brand Analytics, Finance, Settlement, Listings. The brand-registry inference is computed but never read.

### 1.2 The "market share / search share" numbers are fake-or-absent

`calculate_brand_metrics` only produces market size/share **when a broad external competitor export was manually uploaded** (`broad_market_available`, `brand_analysis_service.py:1646-1666`). With internal SP-API data only:

- `market_size_status = "not_available"` (`:1657`)
- `search_purchase_share` / `search_click_share` / `search_cart_add_share` → all `None`, quality `"unavailable"` (`:845-865`)
- The PPTX `_slide_market_share` is **entirely skipped** unless that external export exists.

So the single most valuable competitive output of the deck — *"here is your share of search and the market"* — is dark for every internal-only run. **Brand Analytics is the source that lights it up, and it is probed but never fetched.**

### 1.3 The plumbing is already there

This is the most important finding for effort estimation. The hard parts of SP-API integration **already exist**:

- **Async report poller**: `request_and_download_report(report_type, start, end, report_options)` (`sp_api_client.py:489-555`) — creates a report, polls `processingStatus` until `DONE`/`FATAL`, downloads the document, surfaces failure reasons. Reused by `get_sales_report` (`:558`), `get_vendor_sales_report` (`:1672`), inventory/returns. **Adding Brand Analytics or Settlement is one new method that calls this with a different `reportType`.**
- **Vendor reports work**: `get_vendor_sales_report(..., distributorView="MANUFACTURING"|"SOURCING")` (`:1672-1711`) already handles month-aligned vendor windows, settlement lag, sell-in vs sell-through.
- **Ads report poller**: `AdvertisingAPIClient.request_report / _poll_report_location / download_report` (`advertising_client.py:513-606`) with `AdvertisingReportConfig` (`:130`). Adding a search-term report = one new `AdvertisingReportConfig` entry.
- **All SP-API sub-clients are already instantiated**: `_data_kiosk_api`, `_finances_api`, `_product_fees_api`, `_listings_api`, `_aplus_content_api` (`sp_api_client.py:241-264`). The `sp_api` package is installed with `DataKiosk`, `Finances`, `ProductFees`, `ListingsItems`, `AplusContent` (`:70`).

### 1.4 Seller vs vendor is already gated (but incompletely)

The probe correctly treats Product Pricing and Product Fees as **seller-only** (`capabilities.py:275-302`): vendors get `"product_pricing_available": "seller-only SP-API endpoint"`. This is correct — Product Pricing (`getItemOffers`) and the FBA fee estimator require a seller offer. **But the inverse is missing**: vendor-only sources (vendor analytics in Data Kiosk, vendor forecasting/inventory reports) are never probed, so a vendor account's richest first-party data is invisible to Brand Analysis.

### 1.5 Brand Pulse has zero dedicated Amazon data — it re-reads dashboard primitives

`BrandPulseService.build_pulse` (`brand_pulse_service.py:36-96`) calls `compute_dashboard_kpis`, `asin_sales_breakdown`, `_asin_titles`, `compute_advertising_metrics` — **the exact same AnalyticsService calls the Performance dashboard uses**. It pulls **no market data, no competitor data, no search data, no category data**. The Ads client it leans on only has **campaign-level** reports (`advertising_client.py:168-228`) — there is **no search-term report** (`spSearchTerm`) and **no purchased-product report**, so Pulse literally cannot see competitor keywords, category share, or what shoppers searched. This is the root cause of the "Brand Pulse = Performance Analytics reskin" overlap.

---

## 2. The 10 sources — detailed coverage table

Columns: **Availability** (seller/vendor + marketplace/role), **API source** (exact endpoint + existing client method), **Permissions/Roles**, **Limitations**, **Effort** (XS–XL + person-days), **Value** (Brand Analysis deck / Brand Pulse weekly).

### 2.1 Data Kiosk

| Field | Detail |
|---|---|
| **Availability** | Seller **and** Vendor, all EU/NA/FE marketplaces. Different GraphQL schemas per program: `analytics_salesAndTraffic_2024_04_24` (seller), `vendor` economics/sales schemas, `analytics_economics` (seller FBA/fee economics). |
| **API source** | Data Kiosk GraphQL: `POST /dataKiosk/2023-11-15/queries` (create), poll `GET /queries/{id}`, fetch document. Client: `client._data_kiosk_api()` (`sp_api_client.py:261`); probe uses `get_queries(pageSize=1)` (`capabilities.py:261`). **No query-submission helper exists yet** — must be built. |
| **Permissions/Roles** | Same OAuth roles as the underlying data (Brand Analytics role for traffic/economics schemas; vendor role for vendor schemas). **No PII**. App must be authorized for the relevant Data Kiosk dataset. |
| **Limitations** | Async GraphQL: submit → poll (minutes) → download JSONL via documents API. Schema-versioned (breaks on Amazon schema bumps). Vendor economics has multi-day settlement lag. Daily granularity available. Rate-limited (low create QPS). |
| **Effort** | **L (5–7 pd)**: build a `submit_data_kiosk_query()` + reuse the polling pattern, write GraphQL queries per program, JSONL parser, seller/vendor schema branching. |
| **Value** | **Deck: HIGH** (replaces per-ASIN catalog loops with one bulk traffic+conversion+economics pull; gives sessions, page views, conversion rate, buy-box %). **Pulse: HIGH** (weekly traffic/conversion deltas, economics trend). The single best *bulk* source — but it overlaps what `sales_data` already gives, so it is a *quality/economics* upgrade, not net-new revenue. |

### 2.2 Brand Analytics

| Field | Detail |
|---|---|
| **Availability** | **Brand Owner only** (Brand Registry enrolled). Seller and Vendor both, if brand-enrolled. EU/NA/FE. This is the crown-jewel competitive source. |
| **API source** | Reports API report types: `GET_BRAND_ANALYTICS_SEARCH_TERMS_REPORT`, `GET_BRAND_ANALYTICS_MARKET_BASKET_REPORT`, `GET_BRAND_ANALYTICS_REPEAT_PURCHASE_REPORT`, `GET_BRAND_ANALYTICS_ITEM_COMPARISON_REPORT`, `GET_BRAND_ANALYTICS_ALTERNATE_PURCHASE_REPORT`. Also surfaced via Data Kiosk schemas. Probe: `get_reports(GET_BRAND_ANALYTICS_SEARCH_TERMS_REPORT)` (`capabilities.py:244-248`). **Fetch via existing `request_and_download_report(...)`** (`sp_api_client.py:489`) with a `reportOptions={"reportPeriod": "WEEK"/"MONTH"}`. |
| **Permissions/Roles** | "Brand Analytics" / Brand Registry role. **No PII**. The account must be the brand owner. Inthezon's probe already maps the failure to `missing_roles`. |
| **Limitations** | Async report (create→poll→download). Granularity DAY/WEEK/MONTH/QUARTER. Search Terms returns top-3 click/conversion-share ASINs per search term (so you see **competitors** ranking on your terms). Market Basket = "bought together" cross-brand. Repeat Purchase = retention. Data lags ~2–3 days. Quarterly reports have the deepest history. |
| **Effort** | **M (3–4 pd)**: 2–3 thin fetch methods on the SP-API client, a parser, and wiring `search_purchase_share`/`search_click_share` into `calculate_brand_metrics` (the metric keys already exist at `service.py:845-865`, currently always `None`). |
| **Value** | **Deck: VERY HIGH** — finally fills the dark `_slide_market_share` with *real* search-query share, top competitor ASINs per term, and market-basket cross-sell. **Pulse: VERY HIGH** — this is THE source that makes "Weekly Brand Intelligence" real: week-over-week search-term share shifts, new competitor entrants on your terms, basket changes. **#1 strategic source.** |

### 2.3 Brand Registry Available

| Field | Detail |
|---|---|
| **Availability** | Seller and Vendor. It is a **status/eligibility flag**, not a data feed. There is no dedicated "Brand Registry API" returning catalog data; brand-owner status is *inferred* from access to brand-gated endpoints (A+ create, Brand Analytics). |
| **API source** | No first-class endpoint. Inthezon currently infers it from A+ Content access (`capabilities.py:312`: `brand_registry_available_or_inferred = aplus_available`). A stronger signal: success on `GET_BRAND_ANALYTICS_SEARCH_TERMS_REPORT` (only brand owners can run it). |
| **Permissions/Roles** | N/A — derived. |
| **Limitations** | Inference only. A+ access can exist via agency relationships without full brand ownership, so the current inference can false-positive. Brand Analytics success is the more reliable gate. |
| **Effort** | **XS (0.5 pd)**: improve the inference to `aplus OR brand_analytics`, and use it as a *router* (if brand owner → run Brand Analytics path). |
| **Value** | **Deck: LOW directly, HIGH as a router** — it decides whether the high-value Brand Analytics slides can be generated. **Pulse: same** — gates the competitive intelligence section. Keep it as a capability flag, not a data source. |

### 2.4 Product Pricing

| Field | Detail |
|---|---|
| **Availability** | **Seller only** (vendors have no offer, so `getItemOffers` is N/A — correctly gated at `capabilities.py:275-285`). All marketplaces. |
| **API source** | Product Pricing API: `getItemOffers`, `getItemOffersBatch`, `getCompetitivePricing`. Client methods **already exist and are used**: `get_competitive_pricing` (`sp_api_client.py:933`), `get_item_offer_snapshot` (`:1274`), `get_market_prices_for_asins` (`:1055`, batched). Probe: `get_item_offers(asin, New)` (`capabilities.py:278`). |
| **Permissions/Roles** | "Pricing" role. **No PII**. Seller offer required. |
| **Limitations** | Per-ASIN or batched (≤20 ASINs/`getItemOffersBatch`). Buy-Box *ownership* visible; Buy-Box **win-% history is NOT** (hardcoded unavailable, `service.py:1748-1759`). Real-time but rate-limited. |
| **Effort** | **XS (0.5 pd)** — already integrated. The improvement is to **persist and read** `AsinOfferSnapshot` (currently write-only, `brand_analysis_sources.py:615`; no read path) so Pulse can show week-over-week Buy-Box / seller-count shifts. |
| **Value** | **Deck: MEDIUM** (channel/reseller slide, Buy-Box ownership). **Pulse: HIGH** (week-over-week new sellers, Buy-Box loss, price war detection — *if* snapshots are read). Currently fetched but the snapshots rot. |

### 2.5 Product Fees

| Field | Detail |
|---|---|
| **Availability** | **Seller only** (FBA fee estimate needs a seller offer/price; gated at `capabilities.py:287-302`). All marketplaces. |
| **API source** | Product Fees API: `getMyFeesEstimateForASIN`. Client: `estimate_fba_fee_for_asin(asin, price)` (`sp_api_client.py:1286`), **used** at `brand_analysis_sources.py:587`. |
| **Permissions/Roles** | "Product Listing" / fees role. **No PII**. |
| **Limitations** | Needs a price input (uses current price; if price unknown → unavailable, `sources.py:601-604`). Estimate, not actuals (actuals live in Finance/Settlement). Per-ASIN call, no batch. |
| **Effort** | **XS (already done)**. Upgrade path: cross-check estimate vs **actual** FBA fees from Finance/Settlement (§2.7/2.8) to produce a real margin figure. |
| **Value** | **Deck: MEDIUM** (margin/profitability framing). **Pulse: LOW-MEDIUM** (fee changes are slow). Best value comes when paired with actual fees from Finance for a true unit-economics view. |

### 2.6 A+ Content

| Field | Detail |
|---|---|
| **Availability** | Brand-owner seller and vendor. All marketplaces. |
| **API source** | A+ Content API: `searchContentDocuments`, `getContentDocument`. Client: `get_aplus_content_for_asin(asin)` (`sp_api_client.py:1382`), **used** at `sources.py:606`. Probe: `search_content_documents(pageSize=1)` (`capabilities.py:306`). |
| **Permissions/Roles** | Brand Registry / A+ role. **No PII**. |
| **Limitations** | Returns content *modules* (text/image counts, has-A+). ASIN→content mapping requires resolving which content doc applies to which ASIN; current helper summarizes module presence (`_summarize_aplus_payload`, `:1338`). Per-ASIN, no batch. |
| **Effort** | **XS (already done)**. |
| **Value** | **Deck: MEDIUM** (content-audit slide: which ASINs lack A+, module counts). **Pulse: LOW** (content changes slowly). Solid as-is; not a priority to extend. |

### 2.7 Finance Reports

| Field | Detail |
|---|---|
| **Availability** | **Seller** primarily (`listFinancialEventGroups`/`listFinancialEvents`). Vendors use a different invoice/remittance path (vendor payments via vendor APIs). All marketplaces. |
| **API source** | Finances API: `listFinancialEventGroups`, `listFinancialEvents`. Client: `client._finances_api()` (`sp_api_client.py:256`); probe: `list_financial_event_groups(MaxResultsPerPage=1)` (`capabilities.py:256`). **No fetch/aggregation helper exists yet.** |
| **Permissions/Roles** | "Finance and Accounting" role. **Contains financial detail but not customer PII**. |
| **Limitations** | Event-stream pagination (heavy for a year of data). Many event types (shipment, refund, fee, service fee, adjustment). Needs careful aggregation to ASIN-level net proceeds. Latency: near real-time but voluminous. |
| **Effort** | **L (5–6 pd)**: paginating fetcher + event-type aggregation to per-ASIN actual fees/refunds/net. |
| **Value** | **Deck: MEDIUM-HIGH** (real margin: actual fees, refund rate, net proceeds vs the *estimated* fees we show today). **Pulse: MEDIUM** (weekly refund-rate spikes, fee changes). High value but high effort; depends on real profitability being a product goal. |

### 2.8 Settlement Reports

| Field | Detail |
|---|---|
| **Availability** | **Seller only.** Vendors settle via vendor remittance, not these reports. All marketplaces. |
| **API source** | Reports API: `GET_V2_SETTLEMENT_REPORT_DATA_FLAT_FILE` (and `_FLAT_FILE_V2`). Probe: `get_reports(GET_V2_SETTLEMENT_REPORT_DATA_FLAT_FILE)` (`capabilities.py:251`). **Special: settlement reports are auto-generated by Amazon on a schedule — you can only `getReports` to list and download existing ones, NOT `createReport` to request on demand.** Fetch via `_reports_api().get_reports(...)` then download. |
| **Permissions/Roles** | Finance role. **No customer PII** (settlement IDs, amounts). |
| **Limitations** | **Cannot request ad hoc** — must list Amazon's bi-weekly settlement periods and download. Flat-file TSV parsing. Aligns to settlement periods, not calendar months → reconciliation needed. |
| **Effort** | **M (3–4 pd)**: list + download + TSV parse + period reconciliation. Slightly easier than Finance (it's a flat file, not an event stream) but the bi-weekly-period model is awkward. |
| **Value** | **Deck: MEDIUM** (definitive net deposits/actuals). **Pulse: LOW** (bi-weekly cadence doesn't fit weekly). Overlaps Finance; pick **one** of Finance/Settlement, not both. I'd pick Finance for ASIN granularity. |

### 2.9 Catalog Items

| Field | Detail |
|---|---|
| **Availability** | Seller and Vendor. All marketplaces. The backbone of enrichment. |
| **API source** | Catalog Items API v2022-04-01: `getCatalogItem`, `searchCatalogItems`. Client: `_catalog_api()` (`sp_api_client.py:221`), `get_catalog_item_details` (`:918`), `search_catalog_by_keyword` (`:1533`). **Used** for title/brand/category/images/BSR/bullets/rating via `_fetch_product_data` (`market_research_service.py:1030`). Probe: `get_catalog_item(asin, [summaries])` (`capabilities.py:268`). |
| **Permissions/Roles** | No special role (broadly available). **No PII**. |
| **Limitations** | `includedData` controls payload (summaries, images, salesRanks, attributes). Rating/review counts are **not** always in catalog summaries (often need a separate source). Per-ASIN calls dominate today's latency — **N sequential calls, no thread pool** (`sources.py:581-583`). `searchCatalogItems` caps results and isn't a full competitor census. |
| **Effort** | **XS (already done)**; the win is **batching/parallelism** (see Risks) — **S (1–2 pd)** to add a bounded thread pool. |
| **Value** | **Deck: HIGH** (every catalog-audit, content, and top-performers slide depends on it). **Pulse: MEDIUM** (catalog changes weekly: new variations, image/title changes). Foundational; keep and optimize. |

### 2.10 Listings

| Field | Detail |
|---|---|
| **Availability** | **Seller only** (needs `sellerId` + `sku`; gated at `capabilities.py:316-328`). Vendors don't have seller SKUs. All marketplaces. |
| **API source** | Listings Items API: `getListingsItem`. Client: `_listings_api()` (`sp_api_client.py:241`); probe `get_listings_item(sellerId, sku, [summaries])` (`capabilities.py:319`). **No fetch into metrics.** |
| **Permissions/Roles** | "Product Listing" role. **No PII**. |
| **Limitations** | Per-SKU. Returns *your own* listing's attributes, fulfillment, issues — **not competitor data**. Requires SKU mapping (Inthezon has SKUs only for synced seller products). |
| **Effort** | **S-M (2–3 pd)** to fetch listing issues/quality per SKU and surface in a listing-health slide. |
| **Value** | **Deck: LOW-MEDIUM** (listing-quality/issues audit — overlaps content audit). **Pulse: LOW** (slow-changing). Lowest priority of the seller sources. |

---

## 3. Problems Identified (ranked)

| # | Problem | Severity | Evidence |
|---|---|---|---|
| **P-1** | **Brand Analytics is probed but never fetched** → the deck's market/search-share story is permanently dark for internal runs. The metric keys exist and are hardcoded `None`. | **Critical** | `service.py:845-865`, `:1804`; `capabilities.py:244` |
| **P-2** | **Brand Pulse has no competitive/market data at all** — it re-reads dashboard primitives, so the "Weekly Brand Intelligence" reposition is impossible without new sources. | **Critical** | `brand_pulse_service.py:36-96` |
| **P-3** | **No search-term / purchased-product Ads report** — Ads client is campaign-only, so no competitor keyword or category intelligence from Ads either. | **High** | `advertising_client.py:168-228` (only spCampaigns/sbCampaigns/sdCampaigns/spAdvertisedProduct) |
| **P-4** | **5 capabilities probed + persisted then ignored** (Data Kiosk, Brand Analytics, Finance, Settlement, Listings) — the probe gives a false impression of coverage; UI shows green cells for data nobody uses. | **High** | `capabilities.py:23-35` vs `sources.py:574-613` |
| **P-5** | **`AsinOfferSnapshot` is write-only** — Buy-Box/seller-count snapshots are written every run and never read, so no competitive trend is possible despite paying for the pricing calls. | **High** | write `sources.py:615`; no read path anywhere |
| **P-6** | **Vendor first-party data is invisible** — no vendor Data Kiosk / vendor traffic / vendor forecasting probe or fetch; vendors get the thinnest possible analysis. | **Medium-High** | probe has no vendor branch beyond disabling seller-only calls (`capabilities.py:275-302`) |
| **P-7** | **Per-ASIN sequential enrichment** — Catalog + Fees + A+ run inline, serially, no thread pool; this caps the practical ASIN count and makes large brands slow/timeout-prone. | **Medium** | `sources.py:581-583` |
| **P-8** | **Estimated fees presented as economics** — no actual fees from Finance/Settlement, so "margin" framing rests on estimates only. | **Medium** | `sources.py:587-604` |

---

## 4. Recommendations (prioritized; value/effort)

### Integration order (the opinionated ranking)

I rank by **(strategic value × reuse of existing plumbing) ÷ effort**. Brand Analytics wins decisively: highest value, the report poller already exists, and the metric sink keys are already coded.

| Priority | Source / Action | Effort | Why this order |
|---|---|---|---|
| **P0** | **Brand Analytics — Search Terms + Market Basket** via `request_and_download_report` | **M (3–4 pd)** | Unlocks the deck's dead market-share slide AND is the single source that makes Brand Pulse competitive intelligence real. Plumbing exists; sink keys exist (`service.py:845-865`). Gate on `brand_registry_available_or_inferred`. |
| **P0** | **Ads Search-Term + Purchased-Product reports** — add `AdvertisingReportConfig` entries | **S (1–2 pd)** | Cheapest competitive-keyword unlock; reuses `request_report`/`download_report` (`advertising_client.py:513-606`). Feeds Pulse "competitors on your terms" without Brand Registry gating. |
| **P1** | **Read `AsinOfferSnapshot` for week-over-week competitive deltas** (Pulse) | **S (1–2 pd)** | We already *write* these every run; add a unique constraint + read path. Instant "new seller / Buy-Box loss / price war" signal for Pulse. |
| **P1** | **Data Kiosk bulk traffic + economics** (seller schema first) | **L (5–7 pd)** | Replaces the N-call catalog loop with one bulk pull (sessions, conversion, buy-box, economics). Big quality + performance win; reuse the polling pattern. |
| **P1** | **Parallelize per-ASIN enrichment** (bounded thread pool) | **S (1–2 pd)** | Removes the practical ASIN ceiling; prerequisite for analyzing large brands. |
| **P2** | **Finance Reports → actual fees/refunds/net per ASIN** | **L (5–6 pd)** | True margin. Do only if profitability is a product goal; otherwise estimated fees suffice. |
| **P2** | **Vendor Data Kiosk / vendor traffic** (vendor parity) | **M-L (4–6 pd)** | Inthezon serves vendors; give them first-party traffic/sourcing analytics. Depends on Data Kiosk groundwork (P1). |
| **P3** | **Listings health per SKU** | **S-M (2–3 pd)** | Marginal; overlaps content audit. |
| **P3** | **Settlement reports** | **M (3–4 pd)** | Skip if Finance is built — redundant, worse cadence. |
| **XS** | **Stop showing green for probe-only capabilities** until fetched; relabel "detected vs integrated" | **XS (0.5 pd)** | Honesty fix; matches the MEMORY "Source/Confidence/Evidence" direction. |

### Which sources unlock Brand Pulse's competitor/market/category intelligence (explicit)

- **Brand Analytics Search Terms** → *competitor ASINs ranking on your branded + category search terms*, your search-conversion share, week-over-week share shifts. **THE source for "competitor activity" + "category movements".**
- **Brand Analytics Market Basket** → *what shoppers buy alongside your products* (cross-brand) → "emerging opportunities" + "product trends".
- **Brand Analytics Repeat Purchase** → retention/loyalty trend → "brand evolution".
- **Ads Search-Term report** → real shopper queries triggering your ads + competitor pressure (cheaper, no Brand Registry gate) → "market changes / emerging opportunities".
- **Data Kiosk economics + traffic** → category-level conversion/traffic context → "category movements / risks".
- **`AsinOfferSnapshot` (Product Pricing) read path** → new sellers, Buy-Box loss, price wars → "competitor activity / risks".

Without at least Brand Analytics **or** the Ads search-term report, "Weekly Brand Intelligence" is just the Performance dashboard with a weekly label.

### Seller vs vendor (explicit, since Inthezon serves both)

| Source | Seller | Vendor |
|---|---|---|
| Product Pricing / Fees | **Yes** | **No** (no offer) — correctly gated `capabilities.py:275-302` |
| Settlement / Listings | **Yes** | **No** |
| Brand Analytics | Yes (if brand owner) | **Yes** (if brand owner) — vendors are usually brand owners, so this is *more* reliable for vendors |
| Catalog Items / A+ | Yes | Yes |
| Finance | Yes | Vendor uses vendor remittance, not these events |
| Data Kiosk | Seller schemas | **Vendor schemas** (sales/economics/forecasting) — currently unprobed |
| Ads search-term | Yes (Sponsored Products) | Yes (vendors run ads too) |

**Implication:** For **vendors**, the highest-value path is **Brand Analytics + vendor Data Kiosk**, not pricing/fees. The current pipeline gives vendors almost nothing beyond `sales_data` + catalog. This is the biggest vendor gap.

---

## 5. Technical Implementation Plan

### 5.1 P0 — Brand Analytics fetch (Search Terms + Market Basket)

**New SP-API client methods** (`app/core/amazon/sp_api_client.py`, next to `get_vendor_sales_report`):

```python
def get_brand_analytics_search_terms(
    self, start_date: date, end_date: date, *, report_period: str = "WEEK"
) -> list[dict]:
    """GET_BRAND_ANALYTICS_SEARCH_TERMS_REPORT → top search terms with
    top-3 click/conversion-share ASINs (competitors) per term."""
    raw = self.request_and_download_report(
        report_type="GET_BRAND_ANALYTICS_SEARCH_TERMS_REPORT",
        start_date=start_date, end_date=end_date,
        report_options={"reportPeriod": report_period},
    )
    return self._parse_brand_analytics_search_terms(raw)

def get_brand_analytics_market_basket(self, start_date, end_date, *, report_period="MONTH") -> list[dict]:
    raw = self.request_and_download_report(
        report_type="GET_BRAND_ANALYTICS_MARKET_BASKET_REPORT",
        start_date=start_date, end_date=end_date,
        report_options={"reportPeriod": report_period},
    )
    return self._parse_brand_analytics_market_basket(raw)
```

**Wire into metrics** (`brand_analysis_service.py`): in `calculate_brand_metrics`, when a `brand_analytics` payload is present, populate the *already-existing* keys `search_purchase_share`, `search_click_share`, `search_cart_add_share` (`:845-865`) and add a `top_competitor_asins_by_term` block. Change the `market_analysis.status` from `"not_available"` to `"calculated_from_brand_analytics"`.

**Wire into the data source** (`brand_analysis_sources.py`): add `AmazonAccountDataSource._fetch_brand_analytics()` guarded by the persisted `brand_analytics_available` flag; attach result to the `ParsedBrandExport` (new optional field `brand_analytics: dict | None`). Run **once per analysis**, not per ASIN.

**PPTX**: `_slide_market_share` (`service.py:2782`) already renders the external-export path; point it at the new `market_analysis` source so it stops being skipped.

### 5.2 P0 — Ads Search-Term + Purchased-Product reports

**`app/core/amazon/advertising_client.py`** — add to `DEFAULT_REPORT_CONFIGS` (`:168`):

```python
"sp_search_term": AdvertisingReportConfig(
    report_type_id="spSearchTerm", ad_product="SPONSORED_PRODUCTS",
    group_by=["searchTerm"],
    columns=["date","campaignId","searchTerm","keywordId","matchType",
             "impressions","clicks","cost","sales7d","purchases7d"],
),
"sp_purchased_product": AdvertisingReportConfig(
    report_type_id="spPurchasedProduct", ad_product="SPONSORED_PRODUCTS",
    group_by=["asin"],
    columns=["date","campaignId","advertisedAsin","purchasedAsin",
             "sales7d","unitsSoldClicks7d"],  # purchasedAsin reveals cross-brand baskets
),
```

No new poller needed — `request_report`/`_poll_report_location`/`download_report` (`:513-606`) already handle these. Add a `BrandPulseService` method that fetches the last-7-day search-term report and computes competitor pressure.

### 5.3 P1 — Read AsinOfferSnapshot for Pulse deltas

- Migration: add `uq_asin_offer_snapshots_org_account_asin_observed` (currently no unique constraint, `models/brand_analysis.py:122`).
- New method `BrandPulseService._offer_deltas(account_ids, window_days)` reading the two latest snapshots per ASIN → emit "new sellers", "buy-box lost", "price moved" signals.

### 5.4 P1 — Data Kiosk bulk pull

- New `app/services/amazon_data_kiosk.py`: `submit_query(graphql) → poll → download_jsonl`. Reuse the create/poll/download shape of `request_and_download_report`.
- Seller schema first (`analytics_salesAndTraffic_2024_04_24`, `analytics_economics`); vendor schemas in P2.
- Feed into a new bulk path that replaces the per-ASIN catalog loop where Data Kiosk is available.

### 5.5 P1 — Parallelize enrichment

In `brand_analysis_sources.py:574-613`, wrap the per-ASIN `_fetch_catalog_via_market_research` in a bounded `ThreadPoolExecutor` (the helper is already synchronous; run via `asyncio.get_event_loop().run_in_executor`). Cap concurrency (e.g. 5) to respect SP-API rate limits.

### 5.6 Capability honesty

- `capabilities.py`: split the boolean into `{detected, integrated}` per key (or add an `INTEGRATED_CAPABILITIES` set) so the frontend matrix shows "detected ✓ / integrated ✗" — directly supports the brief's "Source/Confidence/Evidence" direction.

---

## 6. Estimated Effort (per workstream + total)

| Workstream | Effort | Person-days |
|---|---|---|
| P0 Brand Analytics (search terms + market basket → metrics + slide) | M | 3–4 |
| P0 Ads search-term + purchased-product reports | S | 1–2 |
| P1 AsinOfferSnapshot read path + Pulse deltas | S | 1–2 |
| P1 Data Kiosk bulk pull (seller) | L | 5–7 |
| P1 Parallelize enrichment | S | 1–2 |
| P2 Finance actual fees/net | L | 5–6 |
| P2 Vendor Data Kiosk parity | M-L | 4–6 |
| P3 Listings health | S-M | 2–3 |
| XS Capability detected-vs-integrated honesty | XS | 0.5 |
| **Total (P0+P1, the high-value core)** | — | **11–17 pd (~2–3.5 weeks)** |
| **Total (everything)** | — | **23–32 pd (~5–6.5 weeks)** |

**Recommendation:** ship **P0 + the two cheap P1s** (snapshot read + parallelize) first — ~13–17 pd — and you transform both the deck (live market share) and Brand Pulse (real competitive intelligence) before touching the expensive Data Kiosk/Finance work.

---

## 7. Risks (and mitigations)

| Risk | Mitigation |
|---|---|
| **Brand Analytics requires Brand Registry** — many managed accounts may not be brand owners, so the high-value path is dark for them. | Gate on `brand_registry_available_or_inferred`; **fall back to the Ads search-term report** (no Brand Registry gate) for non-brand-owner accounts. Surface "Brand Analytics not available — connect a brand-owner account" as an explicit limitation, not a blank slide. |
| **Async report latency** — Brand Analytics/Settlement reports can take minutes; the synchronous `request_and_download_report` blocks. | These already run inside the Celery/background processor, not the request thread. Keep them there; never call from the API request path. Respect `SP_API_REPORT_POLL_MAX_ATTEMPTS`. |
| **Data Kiosk schema versioning** — Amazon bumps GraphQL schema versions and breaks queries. | Pin schema version per query; wrap in try/except → degrade to the existing `sales_data` path; log schema errors as a capability limitation. |
| **Rate limits on parallel enrichment** — a thread pool can trip SP-API throttling. | Bound concurrency (≤5), reuse the existing `with_throttle_retry` decorator (`sp_api_client.py:136`), respect `x-amzn-RateLimit-Limit`. |
| **PII / data residency** — none of these 10 sources return customer PII (Finance/Settlement are amounts, not buyer data). | No PII handling needed; document this explicitly. The Restricted Data Token flow is *not* required for any of these. |
| **Vendor vs seller mis-gating** — calling seller-only endpoints on vendor accounts wastes calls and logs noise. | The probe already gates Pricing/Fees/Listings as seller-only; mirror that gating in the fetch layer, and add an explicit `is_vendor` branch for Data Kiosk schemas. |
| **Probe says available but fetch fails differently** — probe is a tiny `pageSize=1` read; a full-year report can still FATAL ("data not yet available"). | Treat probe as *necessary-not-sufficient*; the `request_and_download_report` FATAL path already downloads and surfaces the reason (`sp_api_client.py:294-316`) — map it to a job limitation, not a hard failure. |
| **Double-counting with existing `sales_data`** — Data Kiosk traffic overlaps the warehouse sales path. | Use Data Kiosk for *traffic/conversion/economics* (new dimensions), keep `sales_data` as the revenue source of truth; don't sum both. |

---

## 8. Rebuild vs Improve (per sub-area)

- **Capability probe** — **Improve.** It's well-structured (`capabilities.py`); it just needs a `detected` vs `integrated` distinction and a vendor branch.
- **SP-API client report layer** — **Improve / extend.** `request_and_download_report` is solid; add report types, don't rebuild.
- **Per-ASIN enrichment loop** — **Improve** (parallelize), with a **partial rebuild** toward a bulk Data Kiosk path for large brands.
- **Brand Analytics integration** — **Build new** (doesn't exist), but on top of existing plumbing — low rebuild cost.
- **Brand Pulse data layer** — **Rebuild.** It is currently a re-presentation of dashboard primitives (`brand_pulse_service.py:36-96`) with zero competitive data. To become "Weekly Brand Intelligence" it needs a new data spine (Brand Analytics + Ads search-term + offer-snapshot deltas), not a tweak.
- **AsinOfferSnapshot** — **Improve** (add constraint + read path); the write side is fine.
