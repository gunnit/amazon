# Gara red items Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the five red items of Gioia's "Funzionalità tool x gara": listing traffic lights (R1), broken variations (R2), content protection (R3), bulk catalogue update with approval (R4), quarterly report and dashboard filters (R5).

**Architecture:** A new `catalog_monitor` service package normalises Amazon Catalog Items (+ Listings Items when available) into one `ListingContent` shape, stores content versions daily, evaluates editable quality rules, diffs against approved baselines and variation families, and routes every Amazon write through an approval queue validated with `VALIDATION_PREVIEW`. A new `quarterly_report` package builds a PPTX from existing warehouse data with the brand-analysis deck primitives.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy 2 async, Alembic, python-amazon-sp-api 1.7.1, Pillow (already installed via matplotlib), openpyxl, python-pptx; React 18 + TypeScript + Vite + Tailwind + shadcn/ui + TanStack Query.

**Spec:** `docs/superpowers/specs/2026-11-21-gara-catalog-design.md`

## Global Constraints

- Backend commands run from `backend/` with `.venv/bin/python`; tests: `ENCRYPTION_KEY=$(.venv/bin/python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())") .venv/bin/python -m pytest tests/ -q` must stay green in one process (426 passing at start).
- Frontend: `npm run build` (tsc + vite) and `npm run lint` must pass; every new i18n key exists in both `frontend/src/i18n/it.ts` and `en.ts` (CI parity check).
- No database in CI: new logic lives in pure functions or behind `CatalogMonitorRepository`; Postgres-backed tests use `@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"))`.
- No Amazon write without an approved `CatalogChangeRequest`; every write path first calls Listings Items with `mode="VALIDATION_PREVIEW"`.
- Synthetic identifiers only in code, tests and fixtures: ASINs `B0TEST0001`…, SKUs `TEST-SKU-001`…, brand `TESTBRAND`. No real client data or tokens.
- Secrets never logged. New config values go in `app/config.py` settings, not literals: `CATALOG_SCAN_HOUR_UTC=5`, `CATALOG_SCAN_MINUTE_UTC=0`, `CATALOG_SCAN_REQUEST_INTERVAL_S=0.55`, `CATALOG_FEED_THRESHOLD=50`, `PTD_CACHE_DAYS=7`.
- Italian is the primary UI language; Italian copy uses the agency's terms (semaforo, scheda prodotto, variazioni, ripristino).
- Migration revision id `034_catalog_monitor`, down_revision `033_ingestion_expansion`.
- After adding routes run `python backend/scripts/gen_tech_docs.py` (generated API docs).
- Commit after each task on branch `feature/gara-red-items`, message citing the item (R1..R5), ending with the `Co-Authored-By` trailer.

## Review Focus

1. A vendor account with no vendor code and no SKUs: scan must still produce Catalog-based content and grey (not red) for backend keywords; writes become "file only", never an exception. → tests in Task 9 and Task 13.
2. An upload that fills only `bullet_2`: the other four live bullets must be kept. → test in Task 15.
3. Amazon returns HTTP 200 with `status: "INVALID"` and issues: the request must be `invalid`, not `accepted`. → test in Task 13.
4. Content reverts to the baseline after an anomaly: the anomaly auto-resolves; a second scan with the same change does not open a duplicate. → tests in Task 9.
5. Main image URL that fails to download or is not an image: rule is grey with a reason, scan continues. → tests in Task 4 and Task 9.

---

## Phase A — Foundation

### Task 1: Data model and migration

**Files:**
- Create: `backend/app/models/catalog_monitor.py`
- Create: `backend/app/db/migrations/versions/034_catalog_monitor.py`
- Modify: `backend/app/models/__init__.py` (register and export), `backend/app/models/product.py` (two columns), `backend/app/config.py` (settings in Global Constraints)
- Test: `backend/tests/test_catalog_monitor_models.py`

**Interfaces — Produces** (SQLAlchemy models, UUID pk `id`, `created_at`/`updated_at` where noted):
- `ListingContentVersion` `listing_content_versions`: account_id FK, asin str(20), content_hash str(64), content JSONB, first_seen_at, last_seen_at; index (account_id, asin, last_seen_at).
- `ListingContentBaseline` `listing_content_baselines`: account_id, asin, content JSONB, source str(32) (`live_snapshot`|`excel_upload`), approved_by_user_id FK users nullable, approved_at; unique (account_id, asin).
- `VariationFamilyBaseline` `variation_family_baselines`: account_id, parent_asin, variation_theme nullable, child_asins JSONB list, captured_at; unique (account_id, parent_asin).
- `CatalogAnomaly` `catalog_anomalies`: account_id, asin, kind str(40) (`content_changed`|`child_detached`|`family_broken`|`unexpected_child`|`theme_changed`), field str(80), baseline_value JSONB, live_value JSONB, status str(20) (`open`|`acknowledged`|`restore_requested`|`resolved`), detected_at, last_seen_at, resolved_at nullable, change_request_id nullable; partial unique index on (account_id, asin, kind, field) where status != 'resolved'.
- `CatalogChangeRequest` `catalog_change_requests`: organization_id, account_id, batch_id UUID index, asin nullable, sku nullable, kind str(32) (`bulk_update`|`content_restore`|`variation_restore`|`new_item`), operation str(16) (`PATCH`|`PUT`), product_type nullable, payload JSONB (`{"patches": [...]} or {"attributes": {...}}`), summary JSONB (before/after per field for the UI), status str(24) (`pending`|`valid`|`invalid`|`approved`|`rejected`|`submitted`|`accepted`|`failed`|`file_only`), validation_issues JSONB, submission_result JSONB, feed_id nullable, created_by_user_id, approved_by_user_id, created_at, updated_at, approved_at, submitted_at.
- `ListingQualityRule` `listing_quality_rules`: organization_id, marketplace_id nullable, product_type nullable, rule_key str(40), enabled bool, mandatory bool, params JSONB, updated_by_user_id, updated_at; unique (organization_id, marketplace_id, product_type, rule_key) with NULLS NOT DISTINCT emulated by `coalesce` unique index.
- `ProductTypeDefinitionCache` `product_type_definitions_cache`: marketplace_id, product_type, required_attributes JSONB, property_names JSONB, fetched_at; unique (marketplace_id, product_type).
- `ImageCheck` `image_checks`: url_hash str(64) unique, url Text, white_background bool nullable, fill_ratio float nullable, width int, height int, error Text nullable, checked_at.
- `CatalogApiCapability` `catalog_api_capabilities`: account_id unique, results JSONB (`{"catalog_items": {"ok": bool, "error": str|None}, "listings_read": …, "product_type_definitions": …, "aplus": …, "feeds": …}`), vendor_code nullable str(40), checked_at.
- `Product.main_keyword` String(255) nullable, `Product.main_keyword_source` String(20) nullable (`manual`|`brand_analytics`).

- [ ] **Step 1:** Write `test_catalog_monitor_models.py`: `test_tables_registered` asserts all nine table names are in `Base.metadata.tables`; `test_open_anomaly_unique_index_is_partial` asserts the anomaly index has `postgresql_where`; `test_product_has_main_keyword` asserts `"main_keyword" in Product.__table__.c`; `test_migration_chain` imports the migration module and asserts `revision == "034_catalog_monitor"` and `down_revision == "033_ingestion_expansion"`.
- [ ] **Step 2:** Run `pytest tests/test_catalog_monitor_models.py -v` → FAIL (module missing).
- [ ] **Step 3:** Implement the models, migration (create tables, indexes, two product columns; `downgrade` drops them) and settings.
- [ ] **Step 4:** Run the test → PASS; run the full suite → green.
- [ ] **Step 5:** Commit `Add catalogue monitoring tables (R1-R4)`.

### Task 2: SP-API client methods

**Files:**
- Modify: `backend/app/core/amazon/sp_api_client.py` (imports `Feeds`, `ProductTypeDefinitions` with the same `try/except ImportError` fallback; new methods next to `get_listing`)
- Test: `backend/tests/test_sp_api_catalog_monitor.py` (stub `sp_api` modules the way `tests/test_catalog_service.py` does)

**Interfaces — Produces** (all on `SPAPIClient`, sync, `@with_throttle_retry` except where noted):
- `get_catalog_item_full(asin: str) -> dict | None` — includedData `["attributes","images","relationships","summaries","classifications","productTypes","salesRanks","identifiers"]`; returns `payload`; raises `AmazonAPIError` on non-throttle errors (unlike `get_catalog_item_details`, which swallows).
- `get_listing(seller_id, sku, included_data=None)` default includedData becomes `["summaries","attributes","issues","offers","relationships","productTypes"]`.
- `search_listings_by_asins(seller_id: str, asins: list[str]) -> list[dict]` — Listings `search_listings_items` with `identifiers=asins` (≤20 per call), `identifiersType="ASIN"`, includedData `["summaries","issues"]`; returns `items`.
- `patch_listing(seller_id, sku, product_type, patches, mode: str | None = None) -> dict` — passes `mode` when given; returns payload (`{"status": "ACCEPTED"|"INVALID"|"VALID", "issues": [...], "submissionId": ...}`).
- `put_listing(seller_id, sku, product_type, attributes: dict, mode: str | None = None, requirements: str = "LISTING") -> dict`.
- `get_product_type_definition(product_type: str, seller_id: str | None = None, locale: str = "it_IT") -> dict` — `requirements="LISTING"`, `requirementsEnforced="ENFORCED"`; returns payload.
- `fetch_json_schema(url: str) -> dict` — `httpx.get(url, timeout=30)`; no retry decorator.
- `get_aplus_publish_record_count(asin: str) -> int` — `search_content_publish_records`; number of records.
- `resolve_vendor_code() -> str | None` — vendor accounts only: purchase orders created in the last 90 days, first `orderDetails.sellingParty.partyId`.
- `submit_json_listings_feed(document: dict) -> str` — create feed document (`application/json; charset=UTF-8`), upload, create feed `JSON_LISTINGS_FEED`; returns feedId.
- `get_feed_status(feed_id: str) -> dict` — `{"processingStatus": str, "resultFeedDocumentId": str|None}`; `get_feed_result(document_id: str) -> dict` downloads and parses the JSON processing report.

- [ ] **Step 1:** Tests: `test_patch_listing_passes_validation_preview_mode` (fake ListingsItems records kwargs, assert `mode == "VALIDATION_PREVIEW"` and body unchanged); `test_patch_listing_returns_invalid_payload` (fake returns `{"status":"INVALID","issues":[{"code":"90220"}]}` → returned as is); `test_get_catalog_item_full_requests_relationships_and_images`; `test_search_listings_by_asins_chunks_by_20` (45 ASINs → 3 calls); `test_resolve_vendor_code_reads_selling_party`; `test_resolve_vendor_code_returns_none_for_seller`; `test_put_listing_sends_attributes_and_mode`.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run → PASS, full suite green.
- [ ] **Step 5:** Commit `Add catalogue read, validation-preview and feed calls to the SP-API client (R1-R4)`.

### Task 3: ListingContent normalisation

**Files:**
- Create: `backend/app/services/catalog_monitor/__init__.py`, `backend/app/services/catalog_monitor/content.py`
- Create: `backend/tests/fixtures/catalog_monitor/catalog_child.json`, `catalog_parent.json`, `catalog_vendor_minimal.json`, `listing_seller.json` (synthetic, in SP-API 2022-04-01 / 2021-08-01 shapes)
- Test: `backend/tests/test_catalog_monitor_content.py`

**Interfaces — Produces:**
```python
@dataclass(frozen=True)
class ImageRef: variant: str; url: str; width: int | None; height: int | None

@dataclass
class ListingContent:
    asin: str; marketplace_id: str
    sku: str | None = None
    title: str | None = None; brand: str | None = None
    bullets: list[str] = field(default_factory=list)
    description: str | None = None
    item_highlights: str | None = None
    backend_keywords: str | None = None
    backend_keywords_readable: bool = False
    images: list[ImageRef] = field(default_factory=list)   # MAIN first, then PT01..PT08, largest size per variant
    has_video: bool | None = None                            # None = not exposed by API
    aplus_module_count: int | None = None                    # None = unknown
    aplus_available: bool = False
    attributes: dict = field(default_factory=dict)           # raw SP-API attribute map, volatile keys removed
    product_type: str | None = None
    classification_path: list[str] = field(default_factory=list)
    browse_node_id: str | None = None
    parent_asins: list[str] = field(default_factory=list)
    child_asins: list[str] = field(default_factory=list)
    variation_theme: str | None = None
    listing_status: list[str] | None = None                  # None = no listing access
    listing_issues: list[dict] = field(default_factory=list)

VOLATILE_ATTRIBUTES: frozenset[str]  # purchasable_offer, list_price, fulfillment_availability, merchant_shipping_group, condition_type, max_order_quantity, skip_offer, merchant_release_date, supplier_declared_dg_hz_regulation, batteries_required…
def content_from_catalog(payload: dict, marketplace_id: str) -> ListingContent
def merge_listing(content: ListingContent, listing_payload: dict) -> ListingContent   # sku, backend_keywords(+readable=True), listing_status, listing_issues, attributes merged (catalog wins for shopper-visible text)
def with_aplus(content: ListingContent, module_count: int | None, available: bool) -> ListingContent
def content_hash(content: ListingContent) -> str   # sha256 of canonical JSON, excluding listing_status and listing_issues
def content_to_dict(content: ListingContent) -> dict
def content_from_dict(data: dict) -> ListingContent
def attribute_text(attributes: dict, name: str, marketplace_id: str | None = None) -> list[str]   # values for the marketplace, in order
```
Item highlights are read from the first present attribute among `item_highlights`, `item_highlight`, `highlights`.

- [ ] **Step 1:** Tests: `test_child_payload_extracts_text_fields` (title, brand, 5 bullets in order, description); `test_images_main_first_and_largest_variant`; `test_relationships_child_has_parent`; `test_parent_payload_lists_children_and_theme`; `test_vendor_minimal_payload_has_grey_fields` (`backend_keywords_readable is False`, `listing_status is None`); `test_merge_listing_sets_backend_keywords_and_issues`; `test_hash_ignores_issues_but_tracks_bullet_order` (swap two bullets → different hash; change issues → same hash); `test_round_trip_dict`; `test_volatile_attributes_removed`.
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement. **Step 4:** Run → PASS.
- [ ] **Step 5:** Commit `Normalise Amazon catalogue and listing payloads into one content shape (R1-R3)`.

### Task 4: Main image analysis

**Files:**
- Create: `backend/app/services/catalog_monitor/images.py`
- Test: `backend/tests/test_catalog_monitor_images.py`

**Interfaces — Produces:**
```python
@dataclass(frozen=True)
class ImageAnalysis: white_background: bool; fill_ratio: float; width: int; height: int; error: str | None = None
def analyze_main_image(data: bytes, white_threshold: int = 245, border_ratio: float = 0.02) -> ImageAnalysis
async def get_image_analysis(db, url: str, fetch: Callable[[str], Awaitable[bytes]] | None = None) -> ImageAnalysis
```
Algorithm: RGB; border band of `max(1, round(border_ratio * min(w, h)))` px; white background when ≥95% of border pixels have every channel ≥ `white_threshold`; product bbox = pixels with any channel < `white_threshold`; `fill_ratio = max(bbox_w / w, bbox_h / h)` (0.0 when no product pixels). Unreadable bytes → `ImageAnalysis(False, 0.0, 0, 0, error="unreadable")`. `get_image_analysis` caches by `sha256(url)` in `ImageCheck`; download errors return an analysis with `error="download_failed"` and are cached for 1 day only.

- [ ] **Step 1:** Tests build images with Pillow in memory: `test_white_background_and_90_percent_fill` (1000×1000 white, 900×900 dark square → white True, fill≈0.9); `test_small_product_low_fill` (500×500 square → 0.5); `test_grey_background_not_white`; `test_unreadable_bytes_returns_error`; `test_download_failure_returns_error` (fetch raises) using a fake db with no cache row.
- [ ] **Step 2–4:** FAIL → implement → PASS.
- [ ] **Step 5:** Commit `Check main image background and fill (R1)`.

### Task 5: Quality rules and their overrides

**Files:**
- Create: `backend/app/services/catalog_monitor/rules.py`, `backend/app/services/catalog_monitor/rule_config.py`
- Test: `backend/tests/test_catalog_monitor_rules.py`

**Interfaces — Consumes:** `ListingContent` (Task 3), `ImageAnalysis` (Task 4). **Produces:**
```python
State = Literal["green", "yellow", "red", "grey"]
RULE_KEYS = ("title","item_highlights","bullets","description","images","main_image","video","aplus","backend_keywords","attributes","category")
@dataclass(frozen=True)
class RuleConfig: key: str; enabled: bool; mandatory: bool; params: dict
DEFAULT_RULES: dict[str, RuleConfig]   # values from the spec table
@dataclass
class RuleContext:
    main_keyword: str | None = None
    required_attributes: list[str] | None = None   # None = schema unavailable
    main_image: ImageAnalysis | None = None
@dataclass
class RuleResult: key: str; state: State; mandatory: bool; code: str; details: dict
@dataclass
class ListingEvaluation: asin: str; state: State; score: int; results: list[RuleResult]
def evaluate_listing(content: ListingContent, ctx: RuleContext, configs: dict[str, RuleConfig] | None = None) -> ListingEvaluation
def evaluation_to_dict(ev: ListingEvaluation) -> dict
def resolve_rule_configs(overrides: Iterable, marketplace_id: str, product_type: str | None) -> dict[str, RuleConfig]   # rule_config.py; overrides have marketplace_id, product_type, rule_key, enabled, mandatory, params
```
Default params: title `{max_length: 75, hard_max_length: 200}`; item_highlights `{max_length: 125}`; bullets `{target_count: 5, min_count: 3}`; description `{min_length: 200}`; images `{target_count: 8, min_count: 5}`; main_image `{min_fill: 0.85}`; aplus `{min_modules: 4}`; backend_keywords `{max_bytes: 250, min_bytes: 100}`; attributes `{recommended_attributes: ["color","size","material","item_dimensions","item_weight","age_range_description","number_of_items","included_components"]}`; category `{expected_category_keywords: []}`. Result `code` values are stable i18n keys: `ok`, `missing`, `too_long`, `too_short`, `brand_missing`, `keyword_missing`, `too_few`, `background_not_white`, `low_fill`, `not_exposed`, `unavailable`, `required_missing`, `recommended_missing`, `mismatch`, `over_limit`, `analysis_failed`. Details carry the measured value and limit (e.g. `{"length": 92, "limit": 75}`). Disabled rules are omitted from results. Overall state and score per spec ("Product-level state", "Score").

- [ ] **Step 1:** One test per row of the spec table and per state boundary, e.g. `test_title_75_is_green_76_is_yellow_201_is_red`, `test_title_without_brand_is_yellow`, `test_title_keyword_check_skipped_when_unknown` (green with `details["keyword_checked"] is False`), `test_bullets_5_green_4_yellow_2_red`, `test_images_8_green_6_yellow_4_red`, `test_main_image_grey_when_analysis_missing`, `test_main_image_red_when_background_not_white`, `test_video_always_grey`, `test_aplus_grey_when_api_unavailable`, `test_backend_keywords_251_bytes_red_counts_utf8_bytes` (use "è"), `test_backend_keywords_grey_when_not_readable`, `test_attributes_grey_without_schema`, `test_attributes_red_when_required_missing`, `test_category_mismatch_red_when_expected_configured`, `test_overall_red_only_from_mandatory`, `test_overall_grey_when_all_grey`, `test_score_weights_mandatory_double`, `test_override_most_specific_wins` (org default vs marketplace vs product type vs both), `test_override_can_disable_rule`.
- [ ] **Step 2–4:** FAIL → implement → PASS.
- [ ] **Step 5:** Commit `Evaluate listings against the client's eleven rules, editable per category and marketplace (R1)`.

### Task 6: Product type requirements

**Files:**
- Create: `backend/app/services/catalog_monitor/ptd.py`
- Test: `backend/tests/test_catalog_monitor_ptd.py`

**Interfaces — Produces:**
```python
def required_attributes_from_schema(schema: dict) -> list[str]     # top-level "required" minus volatile/offer attributes (VOLATILE_ATTRIBUTES ∪ {"externally_assigned_product_identifier","merchant_suggested_asin"}), sorted
class ProductTypeDefinitionService:
    def __init__(self, db): ...
    async def required_attributes(self, client: SPAPIClient, marketplace_id: str, product_type: str, seller_id: str | None = None) -> list[str] | None
```
Cache hit when `fetched_at` newer than `settings.PTD_CACHE_DAYS`; on API failure returns the stale cache if any, else `None` (never raises).

- [ ] **Step 1:** Tests: `test_required_from_schema_drops_offer_attributes`; `test_cache_hit_skips_api` (fake db returns fresh row, client not called); `test_api_failure_returns_none_without_cache`; `test_api_failure_returns_stale_cache`.
- [ ] **Step 2–4:** FAIL → implement → PASS. **Step 5:** Commit `Read required attributes from Amazon product type definitions (R1, R4)`.

### Task 7: Content and variation diff

**Files:**
- Create: `backend/app/services/catalog_monitor/diff.py`
- Test: `backend/tests/test_catalog_monitor_diff.py`

**Interfaces — Produces:**
```python
@dataclass
class FieldChange: field: str; change: Literal["modified","missing","added","reordered"]; baseline: Any; live: Any
# field ∈ "title" | "bullets" | "description" | "images" | "aplus" | "attribute:<name>"
def diff_content(baseline: ListingContent, live: ListingContent) -> list[FieldChange]
@dataclass
class VariationFinding: kind: Literal["child_detached","family_broken","unexpected_child","theme_changed"]; parent_asin: str; child_asin: str | None; baseline: Any; live: Any
def diff_family(parent_asin: str, baseline_theme: str | None, baseline_children: list[str], live_parent: ListingContent | None, live_children: dict[str, ListingContent | None]) -> list[VariationFinding]
```
Rules: text compared after whitespace normalisation; bullets: same set different order → `reordered`, otherwise `modified` (or `missing` when live has none); images: compare by URL list — same set different order → `reordered`, any URL replaced or removed → `modified`/`missing`; aplus: baseline >0 modules and live 0 → `missing`, different count → `modified`, unknown on either side → no change; attributes: only names present in the baseline, volatile ones excluded, compare normalised values for the marketplace. Family: child whose live `parent_asins` lacks the parent → `child_detached`; live parent with no children while baseline had some → `family_broken` (one finding, no per-child duplicates); live child of the parent not in baseline → `unexpected_child`; theme differs → `theme_changed`. A child whose live content is `None` (not fetched) produces no finding.

- [ ] **Step 1:** Tests for each rule above, including `test_whitespace_only_change_is_not_a_change`, `test_volatile_attribute_change_ignored`, `test_family_broken_suppresses_child_findings`, `test_unfetched_child_is_not_detached`.
- [ ] **Step 2–4:** FAIL → implement → PASS. **Step 5:** Commit `Diff live content and variation families against the baseline (R2, R3)`.

### Task 8: Repository and Amazon access check

**Files:**
- Create: `backend/app/services/catalog_monitor/repository.py`, `backend/app/services/catalog_monitor/capabilities.py`, `backend/app/services/catalog_monitor/clients.py`
- Test: `backend/tests/test_catalog_monitor_capabilities.py`, `backend/tests/test_catalog_monitor_repository_pg.py` (Postgres, skipped without `TEST_DATABASE_URL`)

**Interfaces — Produces:**
```python
# clients.py
ClientFactory = Callable[[AmazonAccount, Any], SPAPIClient]
def default_client_factory(account, organization) -> SPAPIClient   # resolve_credentials + resolve_marketplace + SPAPIClient(account_type=account.account_type.value)
async def load_organization(db, account) -> Organization | None

# repository.py — all async, no commit (callers commit)
class CatalogMonitorRepository:
    def __init__(self, db): ...
    async def products_to_scan(self, account_id) -> list[Product]                 # is_active, ordered by asin
    async def latest_versions(self, account_id, asins: list[str] | None = None) -> dict[str, ListingContentVersion]
    async def save_version(self, account_id, asin, content: ListingContent, seen_at: datetime) -> tuple[ListingContentVersion, bool]   # bool = new version
    async def versions(self, account_id, asin, limit: int = 50) -> list[ListingContentVersion]
    async def baselines(self, account_id) -> dict[str, ListingContentBaseline]
    async def upsert_baseline(self, account_id, asin, content: ListingContent, source: str, user_id) -> ListingContentBaseline
    async def family_baselines(self, account_id) -> list[VariationFamilyBaseline]
    async def upsert_family_baseline(self, account_id, parent_asin, theme, children: list[str]) -> VariationFamilyBaseline
    async def open_anomalies(self, account_id) -> dict[tuple[str, str, str], CatalogAnomaly]   # key (asin, kind, field)
    async def open_or_touch_anomaly(self, account_id, asin, kind, field, baseline_value, live_value, now) -> tuple[CatalogAnomaly, bool]   # bool = newly opened
    async def resolve_anomaly(self, anomaly: CatalogAnomaly, now) -> None
    async def save_quality_snapshot(self, account_id, asin, evaluation: ListingEvaluation, day: date) -> None   # upsert ListingQualitySnapshot (score, components=evaluation_to_dict)
    async def rule_overrides(self, organization_id) -> list[ListingQualityRule]
    async def capability(self, account_id) -> CatalogApiCapability | None
    async def save_capability(self, account_id, results: dict, vendor_code: str | None, now) -> CatalogApiCapability

# capabilities.py
CAPABILITY_KEYS = ("catalog_items","listings_read","product_type_definitions","aplus","feeds")
def probe_capabilities(client: SPAPIClient, account, sample_asin: str | None, sample_sku: str | None) -> tuple[dict, str | None]   # (results, vendor_code); each check try/except → {"ok": bool, "error": str | None}; never raises
async def check_account_capabilities(db, account, client_factory: ClientFactory = default_client_factory) -> CatalogApiCapability
def listing_seller_id(account, capability: CatalogApiCapability | None) -> str | None   # seller: account.seller_id; vendor: capability.vendor_code
```

- [ ] **Step 1:** `test_probe_marks_each_failure_without_raising` (fake client raising `AmazonAPIError` on listings and feeds → those `ok: False`, others `ok: True`); `test_probe_resolves_vendor_code_for_vendor`; `test_listing_seller_id_for_seller_and_vendor`; Postgres tests: `test_save_version_dedupes_by_hash`, `test_open_or_touch_anomaly_no_duplicate`, `test_resolve_then_reopen_creates_new_row`.
- [ ] **Step 2–4:** FAIL → implement → PASS (Postgres tests run in Task 21 locally).
- [ ] **Step 5:** Commit `Add the catalogue monitor repository and per-account Amazon access check (R1-R4)`.

### Task 9: Daily scan

**Files:**
- Create: `backend/app/services/catalog_monitor/scanner.py`, `backend/app/services/catalog_monitor/keywords.py`
- Modify: `backend/app/main.py` (job `catalog-monitor-scan`, `CronTrigger(hour=settings.CATALOG_SCAN_HOUR_UTC, minute=settings.CATALOG_SCAN_MINUTE_UTC)`), `backend/app/services/extraction_runner.py` (add `list_active_account_ids`-based runner for all account types if a generic one is missing)
- Test: `backend/tests/test_catalog_monitor_scanner.py`

**Interfaces — Consumes:** Tasks 2–8. **Produces:**
```python
@dataclass
class ScanSummary: account_id: UUID; scanned: int = 0; new_versions: int = 0; failed: int = 0; anomalies_opened: int = 0; anomalies_resolved: int = 0; errors: list[str] = field(default_factory=list)
class CatalogScanService:
    def __init__(self, db, repo: CatalogMonitorRepository | None = None, client_factory: ClientFactory = default_client_factory,
                 image_fetch=None, sleep: Callable[[float], None] = time.sleep, today: Callable[[], date] = date.today): ...
    async def scan_account(self, account, asins: list[str] | None = None) -> ScanSummary
def run_catalog_scan_all() -> dict                      # scheduler entry, every active account (seller and vendor), engine/loop lifecycle like _run_seller_job
def start_account_scan(account_id: UUID) -> bool         # background thread; False if one is already running for that account
def scan_state(account_id: UUID) -> dict                 # {"running": bool, "started_at": iso|None, "finished_at": iso|None, "summary": dict|None}
# keywords.py
async def resolve_main_keywords(db, account_id, products: list[Product]) -> dict[str, str]   # manual Product.main_keyword first, else top BrandSearchTerm (latest week, best click share) whose top-3 includes the ASIN
```
Per product: `get_catalog_item_full` (sleep `CATALOG_SCAN_REQUEST_INTERVAL_S` between calls) → `content_from_catalog`; if `listing_seller_id` and SKU: `get_listing` → `merge_listing`; A+ count when capability `aplus.ok`; image analysis for `images[0]`; required attributes via `ProductTypeDefinitionService`; `evaluate_listing` with `resolve_rule_configs`; `save_version`; `save_quality_snapshot`; diff with baseline → open/touch anomalies `content_changed` per field, resolve open `content_changed` anomalies of that ASIN no longer present. After the loop: family diff per family baseline with the contents fetched (children not in the scanned set are fetched on demand) → anomalies; resolve stale family anomalies. A failing product increments `failed`, records the error, and the loop continues. Commit every 25 products. Remove the old weekly `listing-quality-snapshot` job and `run_listing_quality_snapshot_all` (the daily scan now writes `ListingQualitySnapshot`); check every reader of `ListingQualitySnapshot.components` (e.g. `strategic_recommendations_service.py`) still works with the new `evaluation_to_dict` shape, adapting it and its tests.

- [ ] **Step 1:** Tests with an in-memory fake repository (subclass with dict storage) and a fake client built from Task 3 fixtures: `test_scan_vendor_without_listing_access_uses_catalog_only` (backend keywords grey, no exception); `test_scan_opens_anomaly_on_title_change_and_does_not_duplicate`; `test_scan_resolves_anomaly_when_content_reverts`; `test_scan_continues_after_one_failed_asin`; `test_image_download_failure_gives_grey_main_image`; `test_detached_child_opens_variation_anomaly`; `test_quality_snapshot_saved_per_asin`; `test_main_keyword_manual_beats_brand_analytics`.
- [ ] **Step 2–4:** FAIL → implement → PASS.
- [ ] **Step 5:** Commit `Scan every account's catalogue daily, score it and flag content and variation changes (R1-R3)`.

### Task 10: Baselines

**Files:**
- Create: `backend/app/services/catalog_monitor/baselines.py`
- Test: `backend/tests/test_catalog_monitor_baselines.py`

**Interfaces — Produces:**
```python
async def approve_live_as_baseline(repo, account_id, asins: list[str] | None, user_id) -> int   # from latest versions; also upserts family baselines for parents among them (children from parent's child_asins)
async def accept_anomaly(repo, anomaly: CatalogAnomaly, user_id, now) -> None                  # copy live field value into the baseline, resolve the anomaly
async def import_baseline_rows(repo, account_id, rows: list[tuple[str, dict]], user_id) -> tuple[int, list[str]]   # (asin, cells) pairs; Task 16 builds them from bulk_io.ParsedRow; starts from latest version, overrides given cells (same column names as EXPORT_COLUMNS); source "excel_upload"
```
- [ ] **Step 1:** `test_approve_all_creates_baselines_and_families`; `test_accept_anomaly_updates_only_that_field`; `test_import_overrides_only_given_cells` (cells dict built inline).
- [ ] **Step 2–4:** FAIL → implement → PASS. **Step 5:** Commit `Approve live or uploaded content as the protected baseline (R2, R3)`.

## Phase B — R1 API and screens

### Task 11: Catalogue monitor API (quality, rules, keywords, scan, capabilities)

**Files:**
- Create: `backend/app/api/v1/catalog_monitor.py`, `backend/app/schemas/catalog_monitor.py`
- Modify: `backend/app/api/v1/router.py` (`prefix="/catalog-monitor"`, tag "Catalog Monitor"), generated docs via `gen_tech_docs.py`
- Test: `backend/tests/test_catalog_monitor_api.py` (pure helpers + FastAPI `TestClient` with dependency overrides and a fake repository)

**Interfaces — Produces** (all require `CurrentUser` + `CurrentOrganization`; account must belong to the org, else 404; writes to rules require `AdminOrganization`):
- `GET /catalog-monitor/quality?account_id&state&rule&mandatory_only&search&page&page_size` → `{"summary": {"green": n, "yellow": n, "red": n, "grey": n, "per_rule": {rule: {state: n}}}, "items": [{"asin","sku","title","main_image_url","state","score","results":[RuleResult]}], "total", "last_scan_at"}` from the latest `ListingQualitySnapshot` per ASIN joined to `Product`.
- `GET /catalog-monitor/quality/{asin}?account_id` → item + `content` (latest version dict) + `main_keyword`.
- `GET /catalog-monitor/quality/export?account_id` → xlsx (one row per ASIN, one column per rule state + code).
- `GET /catalog-monitor/rules` → `{"defaults": {key: RuleConfig}, "overrides": [ListingQualityRule]}`; `PUT /catalog-monitor/rules` body `{"overrides": [...]}` replaces the org's overrides (admin).
- `PUT /catalog-monitor/keywords` body `{"account_id", "items": [{"asin", "keyword"}]}` sets `Product.main_keyword` (`source="manual"`; empty string clears).
- `POST /catalog-monitor/scan` body `{"account_id"}` → `{"started": bool}`; `GET /catalog-monitor/scan?account_id` → `scan_state`.
- `GET /catalog-monitor/capabilities?account_id` → stored capability or `null`; `POST /catalog-monitor/capabilities/check` body `{"account_id"}` → fresh result.

- [ ] **Step 1:** Tests: `test_quality_summary_counts_states`, `test_quality_filter_by_rule_and_state`, `test_rules_put_requires_admin` (403 for member), `test_keywords_put_sets_manual_source`, `test_account_from_other_org_is_404`.
- [ ] **Step 2–4:** FAIL → implement → PASS; regenerate tech docs.
- [ ] **Step 5:** Commit `Expose listing quality, rules, keywords, scan and access check over the API (R1)`.

### Task 12: Quality screens

**Files:**
- Create: `frontend/src/components/catalog-monitor/TrafficLight.tsx`, `QualityPanel.tsx`, `QualityDetailDialog.tsx`, `RulesPanel.tsx`, `AccessCheck.tsx`, `ScanButton.tsx`
- Modify: `frontend/src/services/api.ts` (`catalogMonitorApi`), `frontend/src/types/index.ts`, `frontend/src/pages/Catalog.tsx` (tab `quality` replaces `health`; new tab `rules`, visible to all, editable for admins), `frontend/src/i18n/it.ts`, `en.ts` (keys under `cm.`; one label per rule key and per result `code`)
- Delete: `frontend/src/components/catalog/ListingHealthCard.tsx` and its now-unused i18n keys

**Behaviour:** summary strip with four counts (click filters); matrix table: one row per ASIN (thumbnail, ASIN, title, overall light, score) and one column per enabled rule showing a `TrafficLight` (filled circle with an icon and accessible label: check, minus, cross, question mark; colours green-600, amber-500, red-600, slate-400; tooltip with the translated code and details); mandatory rules marked with a small "obbligatorio" tag in the header; filters: state, rule, mandatory only, search; export button; row click opens the detail dialog (main image preview, each rule with message and measured value, main keyword inline edit). `AccessCheck` shows the five capability chips and a "Verifica accesso Amazon" button. `ScanButton` starts a scan and polls `GET /scan` every 5 s while running. `RulesPanel`: table of rules × (enabled, mandatory, params) with optional marketplace and product type scope; save (admin).

- [ ] **Step 1:** Implement components and wiring.
- [ ] **Step 2:** Run `npm run build` and `npm run lint` → PASS; run the CI parity check command from `.github/workflows/ci.yml` → PASS.
- [ ] **Step 3:** Commit `Show the new listing traffic lights, rules and Amazon access check in Catalogo (R1)`.

## Phase C — R3, R2 and approvals

### Task 13: Change requests and approval queue

**Files:**
- Create: `backend/app/services/catalog_monitor/changes.py`
- Test: `backend/tests/test_catalog_monitor_changes.py`

**Interfaces — Consumes:** Tasks 2, 3, 8. **Produces:**
```python
LANGUAGE_TAG_BY_MARKETPLACE: dict[str, str]  # IT APJ6JRA9NG5V4 it_IT, DE A1PA6795UKMFR9 de_DE, FR A13V1IB3VIYZZH fr_FR, ES A1RKKUPIHCS9HS es_ES, UK A1F83G8C2ARO7P en_GB, NL A1805IZSGTT6HS nl_NL, SE A2NODRKZP88ZB9 sv_SE, PL A1C3SOZRARQ6R3 pl_PL, BE AMEN7PMS3EDWL fr_BE, US ATVPDKIKX0DER en_US
@dataclass
class ChangeItem: asin: str | None; sku: str | None; product_type: str | None; kind: str; operation: Literal["PATCH","PUT"] = "PATCH"
                  patches: list[dict] = field(default_factory=list); attributes: dict | None = None; summary: dict = field(default_factory=dict)
def text_value(value: str, marketplace_id: str) -> list[dict]          # [{"value", "language_tag", "marketplace_id"}]
def patches_from_content(fields: dict[str, Any], marketplace_id: str) -> list[dict]   # fields: title, bullets(list), description, backend_keywords, item_highlights, images(list of URLs, main first), attribute:<name> raw → "replace" ops on item_name, bullet_point, product_description, generic_keyword, item_highlights, main_product_image_locator, other_product_image_locator_1..8 (missing slots → "delete" op), attributes
def restore_patches(baseline: ListingContent, fields: list[str]) -> list[dict]
def variation_patches(parent_sku: str, theme: str, marketplace_id: str) -> list[dict]  # parentage_level child, child_parent_sku_relationship, variation_theme
class ChangeRequestService:
    def __init__(self, db, client_factory: ClientFactory = default_client_factory, repo: CatalogMonitorRepository | None = None): ...
    async def create(self, account, items: list[ChangeItem], user_id, batch_id: UUID | None = None) -> list[CatalogChangeRequest]   # status pending, or file_only when no listing seller id or no sku
    async def validate(self, account, requests) -> None      # VALIDATION_PREVIEW; status valid / invalid (issues with severity ERROR) ; WARNING issues kept but valid
    async def approve(self, requests, user_id, is_admin: bool) -> None   # only valid → approved; non-admin → PermissionError
    async def reject(self, requests, user_id) -> None
    async def submit(self, account, requests) -> None         # approved only; < CATALOG_FEED_THRESHOLD → patch/put each (ACCEPTED → accepted, INVALID → failed with issues); else one JSON_LISTINGS_FEED → submitted with feed_id
    async def refresh_feed(self, account, feed_id) -> None    # DONE → per-message accepted/failed from the processing report
def build_listings_feed(requests, seller_id: str, marketplace_id: str) -> dict   # {"header": {"sellerId","version":"2.0","issueLocale":"it_IT"}, "messages": [{"messageId", "sku", "operationType", "productType", "patches"|"attributes"}]}
```
Anomaly linkage: when a request created from an anomaly is accepted, set the anomaly `status="restore_requested"` on create and leave resolution to the next scan.

- [ ] **Step 1:** Tests: `test_text_value_carries_language_and_marketplace`; `test_images_patch_deletes_missing_slots`; `test_validate_marks_invalid_on_error_issue_even_with_http_200` (Review Focus 3); `test_validate_keeps_warning_as_valid`; `test_create_without_sku_is_file_only` (Review Focus 1); `test_approve_requires_admin`; `test_submit_small_batch_patches_each`; `test_submit_large_batch_uses_feed`; `test_feed_document_shape`; `test_variation_patches_shape`.
- [ ] **Step 2–4:** FAIL → implement → PASS.
- [ ] **Step 5:** Commit `Route every catalogue write through validation and operator approval (R2-R4)`.

### Task 14: Protection, variations and approvals API

**Files:**
- Modify: `backend/app/api/v1/catalog_monitor.py`, `backend/app/schemas/catalog_monitor.py`
- Test: extend `backend/tests/test_catalog_monitor_api.py`

**Interfaces — Produces:**
- `GET /catalog-monitor/anomalies?account_id&kind&status&search` (default status open+acknowledged+restore_requested) → `[{"id","asin","title","kind","field","status","baseline_value","live_value","detected_at","last_seen_at"}]`.
- `POST /catalog-monitor/anomalies/{id}/accept` → accept_anomaly. `POST /catalog-monitor/anomalies/restore` body `{"anomaly_ids": [...]}` → creates and validates change requests (fields grouped per ASIN) → `{"batch_id", "requests": [...]}`.
- `GET /catalog-monitor/history/{asin}?account_id` → versions (newest first) with per-version `FieldChange` list against the previous version.
- `GET /catalog-monitor/baselines/status?account_id` → `{"asins_with_baseline", "asins_total", "families"}`; `POST /catalog-monitor/baselines` body `{"account_id", "asins": null|[...]}` → count.
- `GET /catalog-monitor/variations?account_id` → `[{"parent_asin","variation_theme","status": "ok"|"broken"|"partial","children":[{"asin","state": "ok"|"detached"|"unexpected"|"unknown"}], "anomaly_ids": [...]}]`; `POST /catalog-monitor/variations/restore` body `{"account_id","parent_asin","child_asins": null|[...]}` → batch.
- `GET /catalog-monitor/changes?account_id&batch_id&status` → requests; `POST /catalog-monitor/changes/approve|reject|submit` body `{"ids": [...]}` (approve/submit admin-only); `GET /catalog-monitor/changes/feed-file?batch_id` → JSON download of `build_listings_feed` for file_only/approved requests.

- [ ] **Step 1:** Tests: `test_restore_groups_fields_per_asin`, `test_variations_status_from_anomalies`, `test_submit_requires_admin`, `test_feed_file_contains_only_batch_requests`.
- [ ] **Step 2–4:** FAIL → implement → PASS; regenerate tech docs. **Step 5:** Commit `Expose content protection, variations and the approval queue over the API (R2, R3)`.

### Task 15: Bulk import/export logic

**Files:**
- Create: `backend/app/services/catalog_monitor/bulk_io.py`
- Test: `backend/tests/test_catalog_monitor_bulk_io.py`

**Interfaces — Produces:**
```python
EXPORT_COLUMNS = ["asin","sku","product_type","title","bullet_1","bullet_2","bullet_3","bullet_4","bullet_5","description","backend_keywords","item_highlights","main_keyword","main_image_url","image_1",…,"image_8","parent_asin","parent_sku","variation_theme"]  # + dynamic "attr:<name>" columns
LIMITS = {"title": 200, "bullet": 500, "description": 2000, "item_highlights": 125, "backend_keywords_bytes": 250}
def build_export_workbook(rows: list[tuple[Product, ListingContent | None]]) -> bytes   # sheet "Catalogo" + sheet "Istruzioni" (Italian)
@dataclass
class ParsedRow: row_number: int; asin: str | None; sku: str | None; product_type: str | None; cells: dict[str, Any]; errors: list[str]
def parse_upload(file_bytes: bytes, filename: str) -> list[ParsedRow]   # xlsx or csv (utf-8, ; or , sniffed); empty cells omitted from cells; limit errors per row
def row_to_change_item(row: ParsedRow, live: ListingContent | None, marketplace_id: str) -> ChangeItem | None   # only cells that differ from live; bullets merged per position with live bullets; images merged per slot; None when nothing changes
@dataclass
class NewItemRow: row_number: int; sku: str; product_type: str; attributes: dict; errors: list[str]
def parse_new_items(file_bytes: bytes, filename: str) -> list[NewItemRow]   # columns sku, product_type, then attribute columns (dotted names allowed, e.g. "item_dimensions.length")
def validate_new_item(row: NewItemRow, required: list[str] | None) -> list[str]   # missing required attributes
```
- [ ] **Step 1:** Tests: `test_export_then_parse_round_trip_has_no_changes` (export from fixture content, parse, `row_to_change_item` → None); `test_only_bullet_2_keeps_other_live_bullets` (Review Focus 2: patch `bullet_point` has 5 values, positions 1,3,4,5 equal live); `test_backend_keywords_over_250_bytes_is_row_error`; `test_title_over_200_is_row_error`; `test_csv_semicolon_sniffed`; `test_new_item_missing_required_attribute_reported`.
- [ ] **Step 2–4:** FAIL → implement → PASS. **Step 5:** Commit `Export the catalogue as an editable file and turn uploads into minimal changes (R4)`.

### Task 16: Bulk API and retire the direct-write editor

**Files:**
- Modify: `backend/app/api/v1/catalog_monitor.py` (+schemas), `backend/app/api/v1/catalog.py` (old `POST /catalog/bulk-update` and `GET /catalog/bulk-update/template` return 410 with a message pointing to the new tab), `backend/app/services/catalog_service.py` (remove `bulk_update_from_excel` and its helpers now unused)
- Modify tests that covered the removed function (`backend/tests/test_catalog_service.py`)
- Test: extend `backend/tests/test_catalog_monitor_api.py`

**Interfaces — Produces:**
- `GET /catalog-monitor/export?account_id` → xlsx.
- `POST /catalog-monitor/bulk/upload` multipart (`account_id`, `file`, `mode`=`update`|`baseline`) → `update`: creates + validates change requests, returns `{"batch_id","rows": n,"changes": n,"unchanged": n,"row_errors":[...],"requests":[...]}`; `baseline`: `import_baseline_rows` → `{"updated": n, "row_errors": [...]}`.
- `GET /catalog-monitor/new-items/template?account_id&product_type` → xlsx whose columns are sku, product_type and the required attributes from Task 6 (plus recommended).
- `POST /catalog-monitor/new-items/upload` multipart → `PUT` change requests validated with `put_listing(mode="VALIDATION_PREVIEW")` plus required-attribute check.

- [ ] **Step 1:** Tests: `test_upload_returns_row_errors_and_creates_only_changed`, `test_baseline_mode_does_not_create_requests`, `test_old_bulk_endpoint_is_gone_410`.
- [ ] **Step 2–4:** FAIL → implement → PASS (full suite). **Step 5:** Commit `Replace the direct-write bulk editor with export, upload, preview and approval (R4)`.

### Task 17: Protection, variations, bulk and approvals screens

**Files:**
- Create: `frontend/src/components/catalog-monitor/ProtectionPanel.tsx`, `DiffView.tsx`, `HistoryDialog.tsx`, `VariationsPanel.tsx`, `BulkPanel.tsx`, `ApprovalsPanel.tsx`, `ChangePreview.tsx`
- Modify: `frontend/src/services/api.ts`, `frontend/src/types/index.ts`, `frontend/src/pages/Catalog.tsx` (tabs in this order: Prodotti, Qualità listing, Protezione contenuti, Variazioni, Aggiornamento massivo, Approvazioni (badge with pending count), Importa, Prezzi, Disponibilità, Regole), i18n `it.ts`/`en.ts`
- Delete: `frontend/src/components/catalog/BulkUpdateCard.tsx` and unused keys

**Behaviour:** Protection: baseline status bar ("142 di 150 prodotti protetti" + "Approva contenuti attuali come riferimento"); anomalies table (ASIN, field label, change type, detected, status) with select-all and "Ripristina selezionati"; row opens `DiffView` side by side: baseline left, live right, word-level highlights for text, numbered image strips with changed slots outlined, actions Accetta come nuovo riferimento / Ripristina; "Storico" opens `HistoryDialog` timeline. Variations: one card per family with status badge, children chips coloured by state, "Ripristina famiglia". Bulk: step 1 Esporta catalogo; step 2 Carica file (mode update/baseline); step 3 preview table per request (before → after per field, Amazon issues, status) with links to Approvals; new-items sub-section (template download by product type, upload, validation result). Approvals: requests grouped by batch, filters by status, select → Approva / Rifiuta / Invia ad Amazon (admin only; members see the buttons disabled with a tooltip), "Scarica file per Vendor Central" for file_only, confirmation dialog stating the number of listings that will change on Amazon.

- [ ] **Step 1:** Implement. **Step 2:** `npm run build`, `npm run lint`, parity check → PASS. **Step 3:** Commit `Add content protection, variations, bulk update and approval screens (R2-R4)`.

## Phase D — R5

### Task 18: Quarterly report data, insights and deck

**Files:**
- Create: `backend/app/services/quarterly_report/__init__.py`, `data.py`, `insights.py`, `deck.py`
- Test: `backend/tests/test_quarterly_report.py`

**Interfaces — Produces:**
```python
@dataclass
class QuarterScope: organization_id: UUID; account_ids: list[UUID]; year: int; quarter: int; brand: str | None = None; category: str | None = None; asins: list[str] | None = None; language: Literal["it","en"] = "it"
def quarter_bounds(year: int, quarter: int) -> tuple[date, date]
def previous_quarter(year: int, quarter: int) -> tuple[int, int]
@dataclass
class Metric: key: str; value: float | None; previous: float | None; last_year: float | None; provenance: Literal["actual","estimated"]; unit: str
@dataclass
class QuarterData: scope: QuarterScope; kpis: list[Metric]; monthly: list[dict]; top_asins: list[dict]; bottom_asins: list[dict]; catalogue: dict; search_terms: list[dict]; competitors: list[dict]; data_gaps: list[str]
async def collect_quarter_data(db, scope: QuarterScope) -> QuarterData   # revenue (display revenue rule of sales_metrics), units, ad_spend, ad_sales, roas, acos, tacos = ad_spend / revenue, return_rate; brand/category/asins filter via products
@dataclass
class Insight: title: str; body: str; action: str; source: Literal["ai","rules"]
def rule_insights(data: QuarterData) -> list[Insight]        # deterministic: growth/decline vs previous and last year, TACOS trend, top decliners, catalogue red share, open anomalies
def build_insights(data: QuarterData) -> list[Insight]       # Anthropic when ANTHROPIC_API_KEY works (model as in strategic_recommendations_service), any failure → rule_insights
def build_quarterly_deck(data: QuarterData, insights: list[Insight]) -> bytes   # DeckBuilder primitives + charts from brand_analysis.deck; slides: cover, KPI table (value, Δ vs prev, Δ vs LY, provenance tag), monthly trend chart, top/bottom ASINs, catalogue health, search terms, competitors, insights & actions, data notes
```
- [ ] **Step 1:** Tests: `test_quarter_bounds_q1_and_q4`, `test_previous_quarter_wraps_year`, `test_tacos_from_spend_and_revenue`, `test_rule_insights_flags_decline`, `test_build_insights_falls_back_without_key`, `test_deck_is_valid_pptx_with_expected_slide_count` (python-pptx opens the bytes; slide count ≥ 8), `test_metric_without_data_is_none_and_reported_in_gaps`.
- [ ] **Step 2–4:** FAIL → implement → PASS. **Step 5:** Commit `Build the quarterly business review deck with comparisons and insights (R5)`.

### Task 19: Quarterly report API, schedule and dashboard filters

**Files:**
- Modify: `backend/app/api/v1/reports.py` (`POST /reports/quarterly` → PPTX download), `backend/app/schemas/report.py` (`ScheduledReportFrequency` adds `"quarterly"`, `ScheduledReportType` adds `"quarterly_review"`), `backend/app/services/scheduled_report_utils.py` (quarterly next-run = first day of next quarter at hour/minute; period = previous full quarter), `backend/app/services/scheduled_report_service.py` (generate the deck for `quarterly_review`), analytics dashboard endpoints used by `Dashboard.tsx` (add optional `brand` and `category` query params filtering through `products`)
- Modify frontend: `frontend/src/components/ScheduledReportsPanel.tsx` (quarterly option), new `frontend/src/components/QuarterlyReportCard.tsx` on the Performance page (quarter picker, accounts, brand, category, ASINs, language, "Genera report trimestrale"), `frontend/src/pages/Dashboard.tsx` (mount `CategoryFilter` and a new `BrandFilter` from distinct product brands, `GET /catalog/brands`), i18n
- Test: `backend/tests/test_quarterly_report_api.py`, extend `backend/tests/test_scheduled_report_service.py`

**Interfaces — Produces:** `POST /reports/quarterly` body `{"account_ids", "year", "quarter", "brand"?, "category"?, "asins"?, "language"}` → `application/vnd.openxmlformats-officedocument.presentationml.presentation`; `GET /catalog/brands?account_ids` → `list[str]`.

- [ ] **Step 1:** Tests: `test_quarterly_next_run_is_first_day_of_next_quarter`, `test_quarterly_period_is_previous_full_quarter`, `test_quarterly_endpoint_rejects_quarter_5`, `test_dashboard_brand_filter_applied` (helper that builds the filtered query).
- [ ] **Step 2–4:** FAIL → implement → PASS; frontend build/lint/parity; regenerate tech docs.
- [ ] **Step 5:** Commit `Generate and schedule the quarterly report, and filter the dashboard by brand and category (R5)`.

## Phase E — Verification and docs

### Task 20: In-app documentation

**Files:**
- Modify/Create: `frontend/src/content/docs/it/*.md` and `en/*.md` pages for: Qualità listing e regole, Protezione contenuti, Variazioni, Aggiornamento massivo e approvazioni, Report trimestrale (follow the existing docs index/registration pattern); remove statements about image management being available.
- [ ] **Step 1:** Write the pages. **Step 2:** `npm run build` → PASS. **Step 3:** Commit `Document the new catalogue monitoring and reporting features (R1-R5)`.

### Task 21: Local end-to-end run

**Files:**
- Create: `backend/scripts/dev_seed_catalog_monitor.py` (local only: refuses to run unless `DATABASE_URL` host is localhost; creates org, admin user, a seller account `TEST Seller IT` and a vendor account `TEST Vendor IT`, 12 products `B0TEST0001`…, a variation family, 120 days of sales/ads rows; runs `CatalogScanService` with a `FixtureClient` built from `tests/fixtures/catalog_monitor`, approves baselines, mutates fixtures (title change, bullet removed, image reordered, child detached), scans again)

- [ ] **Step 1:** Start a throwaway Postgres (`initdb` in the scratchpad, port 5455), `alembic upgrade head`, run the Postgres-backed tests with `TEST_DATABASE_URL`, run the seed.
- [ ] **Step 2:** Start the API (`uvicorn`) and the frontend (`npm run dev`) against it; in the browser: log in, Catalogo → each new tab shows the seeded data; open a diff; restore → request appears in Approvazioni as `valid` or `file_only` (fixture client answers `VALIDATION_PREVIEW`); approve; generate a quarterly report and open it (slide count, KPI table). Capture screenshots.
- [ ] **Step 3:** Full backend suite, `npm run build`, `npm run lint`, parity → PASS.
- [ ] **Step 4:** Commit `Add a local seed for the catalogue monitor and fix what the end-to-end run found`.

### Task 22: Whole-branch review

- [ ] **Step 1:** Fresh reviewer reads spec, plan and `git diff master...feature/gara-red-items`; fix confirmed findings with tests.
- [ ] **Step 2:** Full verification again; commit fixes.
