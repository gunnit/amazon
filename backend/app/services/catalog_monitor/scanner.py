"""Daily catalogue scan: live content, traffic lights, content and variation anomalies (R1-R3).

For every active product of an account (Seller or Vendor) the scan reads
Catalog Items; Listings Items when a seller id or vendor code and a SKU are
known; the A+ publish-record count when the account has A+ access. Fields a
Listings or A+ call could not supply today are carried forward from the
previous version, so a failed call never looks like a change. The scan then
stores a version (a new row only when the content hash changes), today's R1
evaluation as a ``ListingQualitySnapshot``, and opens, touches or resolves:

* ``content_changed`` anomalies against the approved baseline (R3), one per
  ``FieldChange.field``;
* variation anomalies against the stored families (R2): ``child_detached``
  and ``unexpected_child`` on the child ASIN, ``family_broken`` and
  ``theme_changed`` on the parent ASIN, all with field ``parent:<parent ASIN>``.
  An ASIN whose Catalog payload came without relationships, or could not be
  read, is unknown: it neither opens nor resolves a variation anomaly.

A product that fails is counted and the scan moves on: each product's writes run
in a savepoint and are committed at once, and no Amazon call or image download
happens while a transaction is open. Only light family data is kept per ASIN
until the family pass, and baselines are read product by product, so memory does
not grow with the catalogue. ``run_catalog_scan_all`` (scheduler; only with CATALOG_SCAN_ENABLED,
for CATALOG_SCAN_ACCOUNT_IDS) and ``start_account_scan`` ("Scan now", background
thread, always available) never raise; their state lives in process memory,
keyed by account id.
"""
from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections import defaultdict
from dataclasses import asdict, dataclass, field, replace
from datetime import date, datetime, timezone
from typing import Any, Awaitable, Callable, Optional
from uuid import UUID

from sqlalchemy import select

from app.config import settings
from app.models.amazon_account import AmazonAccount
from app.services.catalog_monitor.baselines import SOURCE_LIVE
from app.services.catalog_monitor.capabilities import listing_seller_id
from app.services.catalog_monitor.clients import (
    ClientFactory,
    default_client_factory,
    load_organization,
)
from app.services.catalog_monitor.content import (
    ListingContent,
    carry_forward,
    content_from_catalog,
    content_from_dict,
    merge_listing,
    with_aplus,
)
from app.services.catalog_monitor.diff import diff_content, diff_family
from app.services.catalog_monitor.images import (
    ImageAnalysis,
    cached_image_analysis,
    download_and_analyze,
    store_image_analysis,
)
from app.services.catalog_monitor.keywords import resolve_main_keywords
from app.services.catalog_monitor.listing_health import listing_health_observation
from app.services.catalog_monitor.ptd import ProductTypeDefinitionService, fetch_definition
from app.services.catalog_monitor.repository import CatalogMonitorRepository
from app.services.catalog_monitor.rule_config import resolve_rule_configs
from app.services.catalog_monitor.rules import RuleContext, evaluate_listing
from app.services.extraction_runner import (
    _SCHEDULED_SYNC_LOCK,
    _make_local_session_factory,
    _run_per_account_job,
    list_active_account_ids,
)

logger = logging.getLogger(__name__)

MAX_RECORDED_ERRORS = 50
CONTENT_CHANGED = "content_changed"
VARIATION_KINDS = frozenset(
    {"child_detached", "family_broken", "unexpected_child", "theme_changed"}
)
_FIELD_MAX_LENGTH = 80  # catalog_anomalies.field


def family_field(parent_asin: str) -> str:
    """Anomaly ``field`` of every variation finding of one family."""
    return f"parent:{parent_asin}"


@dataclass
class ScanSummary:
    """Counts for one account scan; ``scanned`` counts products read and stored."""

    account_id: UUID
    scanned: int = 0
    new_versions: int = 0
    failed: int = 0
    anomalies_opened: int = 0
    anomalies_resolved: int = 0
    errors: list[str] = field(default_factory=list)

    def record_error(self, label: str, exc: Exception) -> None:
        if len(self.errors) < MAX_RECORDED_ERRORS:
            self.errors.append(f"{label}: {type(exc).__name__}: {exc}"[:300])

    def to_dict(self) -> dict:
        data = asdict(self)
        data["account_id"] = str(self.account_id)
        return data


@dataclass(frozen=True)
class FamilyView:
    """What the variation check needs of an ASIN's live content, and nothing more.

    Kept for every scanned ASIN until the family pass: a full ``ListingContent``
    (10-30 KB of Catalog data each) would grow with the catalogue.
    """

    parent_asins: tuple[str, ...]
    child_asins: tuple[str, ...]
    variation_theme: Optional[str]


def family_view(content: ListingContent) -> FamilyView:
    return FamilyView(
        tuple(content.parent_asins), tuple(content.child_asins), content.variation_theme
    )


def _relationships_known(payload: dict, marketplace_id: str) -> bool:
    relationships = payload.get("relationships")
    return isinstance(relationships, list) and (
        not relationships
        or any(
            isinstance(block, dict)
            and block.get("marketplaceId") == marketplace_id
            and isinstance(block.get("relationships"), list)
            for block in relationships
        )
    )


@dataclass
class _Run:
    """Per-scan state shared by the product loop and the family pass."""

    account: Any
    client: Any
    marketplace_id: str
    seller_id: Optional[str]
    aplus_ok: bool
    keywords: dict[str, str]
    overrides: list
    now: datetime
    day: date
    summary: ScanSummary
    # asin -> {(kind, field): anomaly}, loaded once per scan
    open: dict[str, dict[tuple[str, str], Any]]
    # family data used for variation decisions; None = unknown
    live: dict[str, Optional[FamilyView]] = field(default_factory=dict)
    images: dict[str, ImageAnalysis] = field(default_factory=dict)
    required: dict[str, Optional[list[str]]] = field(default_factory=dict)


@dataclass
class _Fetched:
    """One product's Amazon answers, read before any transaction is opened."""

    content: ListingContent
    relationships_known: bool
    listing_fetched: bool
    aplus_quality: dict | None
    listing_health: dict
    listing_checked_at: datetime


@dataclass
class _Lookups:
    """What the database already knows about a product, read in one short transaction."""

    baseline: Optional[ListingContent]
    image_url: Optional[str]
    image: Optional[ImageAnalysis]  # cached analysis; None = download needed (or no image)
    product_type: Optional[str]
    required: Optional[list[str]]  # fresh or stale cache; None = unknown
    required_fresh: bool


def _index_open(rows: dict[tuple[str, str, str], Any]) -> dict[str, dict[tuple[str, str], Any]]:
    index: dict[str, dict[tuple[str, str], Any]] = defaultdict(dict)
    for (asin, kind, field_name), anomaly in rows.items():
        index[asin][(kind, field_name)] = anomaly
    return index


def _aplus_ok(capability: Any) -> bool:
    results = (capability.results or {}) if capability is not None else {}
    return bool((results.get("aplus") or {}).get("ok"))


def _main_image_url(content: ListingContent) -> Optional[str]:
    if not content.images or content.images[0].variant != "MAIN":
        return None
    return content.images[0].url


class CatalogScanService:
    """Scans an account product by product.

    Each product runs in three steps so that no SP-API call or image download
    happens while a database transaction is open: Amazon (Catalog, Listings,
    A+), then the stored data it needs (previous version, baseline, image and
    product type caches) in one short read, then the missing product type
    definition and image download, then the writes in a savepoint, committed at
    once. The family pass works the same way.
    """

    def __init__(
        self,
        db,
        repo: Optional[CatalogMonitorRepository] = None,
        client_factory: ClientFactory = default_client_factory,
        image_fetch: Optional[Callable[[str], Awaitable[bytes]]] = None,
        sleep: Callable[[float], None] = time.sleep,
        today: Callable[[], date] = date.today,
    ):
        self.db = db
        self.repo = repo or CatalogMonitorRepository(db)
        self.client_factory = client_factory
        self.image_fetch = image_fetch
        self.sleep = sleep
        self.today = today
        self.ptd = ProductTypeDefinitionService(db)
        self._catalog_calls = 0

    async def scan_account(self, account, asins: Optional[list[str]] = None) -> ScanSummary:
        """Scan the account's active products (or only ``asins``); commits product by product."""
        organization = await load_organization(self.db, account)
        client = self.client_factory(account, organization)
        capability = await self.repo.capability(account.id)
        products = [p for p in await self.repo.products_to_scan(account.id) if p.asin]
        if asins is not None:
            wanted = set(asins)
            products = [p for p in products if p.asin in wanted]

        run = _Run(
            account=account,
            client=client,
            marketplace_id=account.marketplace_id,
            seller_id=listing_seller_id(account, capability),
            aplus_ok=_aplus_ok(capability),
            keywords=await resolve_main_keywords(self.db, account.id, products),
            overrides=await self.repo.rule_overrides(account.organization_id),
            now=datetime.now(timezone.utc),
            day=self.today(),
            summary=ScanSummary(account_id=account.id),
            open=_index_open(await self.repo.open_anomalies(account.id)),
        )
        self._catalog_calls = 0

        for product in products:
            await self._scan_product(run, product)
        await self._check_families(
            run, scanned={p.asin for p in products}, subset=asins is not None
        )
        await self.db.commit()

        s = run.summary
        logger.info(
            "Catalog scan %s: %d scanned, %d failed, %d new versions, %d anomalies opened, "
            "%d resolved",
            account.id, s.scanned, s.failed, s.new_versions, s.anomalies_opened,
            s.anomalies_resolved,
        )
        return s

    # ---- one product ----

    async def _scan_product(self, run: _Run, product) -> None:
        asin = product.asin
        writing = False
        try:
            await self.db.commit()  # no transaction stays open while Amazon answers
            fetched = self._fetch_live(run, product)
            async with self.db.begin_nested():
                content = await self._with_previous(run, asin, fetched)
                lookups = await self._lookups(run, asin, content)
            await self.db.commit()
            image, required, definition = await self._fetch_missing(run, lookups)
            configs = resolve_rule_configs(run.overrides, run.marketplace_id, content.product_type)
            ctx = RuleContext(
                main_keyword=run.keywords.get(asin),
                required_attributes=required,
                main_image=image,
                aplus_breakdown=fetched.aplus_quality or {},
            )
            # Baselines from previous releases store publish records, not module counts.
            # Keep their comparison stable and score today's actual document separately.
            aplus = fetched.aplus_quality or {}
            quality_content = with_aplus(content, aplus.get("aplus_module_count"), fetched.aplus_quality is not None)
            evaluation = evaluate_listing(quality_content, ctx, configs)
            writing = True
            async with self.db.begin_nested():
                await self._store_fetched(run, lookups, definition)
                _, is_new = await self.repo.save_version(run.account.id, asin, content, run.now)
                await self.repo.save_quality_snapshot(
                    run.account.id, asin, evaluation, run.day, fetched.listing_health, fetched.listing_checked_at,
                )
                opened, resolved = await self._sync_content_anomalies(
                    run, asin, content, lookups.baseline
                )
            await self.db.commit()
        except Exception as exc:  # noqa: BLE001 - one product never stops the scan
            run.live[asin] = None
            run.summary.failed += 1
            run.summary.record_error(asin, exc)
            logger.warning(
                "Catalog scan of %s for account %s failed: %s", asin, run.account.id, exc
            )
            if writing:
                # The savepoint rollback expired the anomalies it touched; reload them.
                run.open = _index_open(await self.repo.open_anomalies(run.account.id))
            return
        run.summary.scanned += 1
        run.summary.new_versions += int(is_new)
        run.summary.anomalies_opened += opened
        run.summary.anomalies_resolved += resolved
        run.live[asin] = family_view(content) if fetched.relationships_known else None

    def _catalog_item(self, client, asin: str) -> dict:
        """One Catalog Items call, spaced from the previous one to respect the rate limit."""
        if self._catalog_calls:
            self.sleep(settings.CATALOG_SCAN_REQUEST_INTERVAL_S)
        self._catalog_calls += 1
        payload = client.get_catalog_item_full(asin)
        if not payload:
            raise LookupError("Catalog Items returned no item")
        return payload

    def _fetch_live(self, run: _Run, product) -> _Fetched:
        """Today's Amazon content: Catalog, then Listings and A+ when available. No database."""
        asin = product.asin
        payload = self._catalog_item(run.client, asin)
        relationships_known = _relationships_known(payload, run.marketplace_id)
        content = content_from_catalog(payload, run.marketplace_id)
        del payload
        if not content.asin:
            content = replace(content, asin=asin)

        listing_fetched = False
        listing = None
        if run.seller_id and product.sku:
            try:
                listing = run.client.get_listing(run.seller_id, product.sku)
            except Exception as exc:  # noqa: BLE001 - keep the previous listing fields
                listing = None
                logger.info("Listings Items unavailable for %s: %s", asin, exc)
            if listing:  # an empty 200 says nothing: keep the previous listing fields
                content = merge_listing(content, listing)
                listing_fetched = True
        health = listing_health_observation(listing, run.marketplace_id, asin, product.sku, run.account.account_type)
        checked_at = datetime.now(timezone.utc)

        aplus_quality = None
        if run.aplus_ok:
            try:
                aplus_quality = run.client.get_aplus_content_for_asin(asin)
                content = with_aplus(content, aplus_quality["publish_record_count"], True)
            except Exception as exc:  # noqa: BLE001 - keep the previous A+ fields
                logger.info("A+ publish records unavailable for %s: %s", asin, exc)
        return _Fetched(content, relationships_known, listing_fetched, aplus_quality, health, checked_at)

    async def _with_previous(self, run: _Run, asin: str, fetched: _Fetched) -> ListingContent:
        """Today's content with what a failed call could not supply taken from the last version."""
        latest = (await self.repo.latest_versions(run.account.id, [asin])).get(asin)
        previous = content_from_dict(latest.content) if latest is not None else None
        content = carry_forward(
            fetched.content, previous, fetched.listing_fetched, fetched.aplus_quality is not None
        )
        if not fetched.relationships_known and previous is not None:
            # A partial payload says nothing about the family: keep the stored one.
            content = replace(
                content,
                parent_asins=list(previous.parent_asins),
                child_asins=list(previous.child_asins),
                variation_theme=previous.variation_theme,
            )
        return content

    async def _lookups(self, run: _Run, asin: str, content: ListingContent) -> _Lookups:
        baseline_row = (await self.repo.baselines(run.account.id, [asin])).get(asin)
        url = _main_image_url(content)
        image = None
        if url is not None:
            # one download and one image_checks row per URL per scan
            image = run.images.get(url) or await cached_image_analysis(self.db, url)
        product_type = content.product_type
        required, fresh = None, True
        if product_type and product_type not in run.required:
            row = await self.ptd.cached_row(run.marketplace_id, product_type)
            fresh = self.ptd.is_fresh(row)
            required = list(row.required_attributes) if row is not None else None
        elif product_type:
            required = run.required[product_type]
        return _Lookups(
            baseline=content_from_dict(baseline_row.content) if baseline_row is not None else None,
            image_url=url,
            image=image,
            product_type=product_type,
            required=required,
            required_fresh=fresh,
        )

    async def _fetch_missing(
        self, run: _Run, lookups: _Lookups
    ) -> tuple[Optional[ImageAnalysis], Optional[list[str]], Optional[tuple[list[str], list[str]]]]:
        """Main image analysis, required attributes, and a newly fetched product type
        definition (to store), downloading only what no cache held. No database."""
        image = lookups.image
        if lookups.image_url is not None:
            if image is None:
                image = await download_and_analyze(lookups.image_url, self.image_fetch)
            run.images[lookups.image_url] = image

        definition = None
        required = lookups.required
        product_type = lookups.product_type
        if product_type and product_type not in run.required:
            if not lookups.required_fresh:
                try:
                    definition = fetch_definition(run.client, product_type)
                    required = definition[0]
                except Exception as exc:  # noqa: BLE001 - stale cache, else a grey light
                    logger.warning(
                        "Product type %s requirements unavailable: %s", product_type, exc
                    )
            run.required[product_type] = required
        return image, required, definition

    async def _store_fetched(
        self, run: _Run, lookups: _Lookups, definition: Optional[tuple[list[str], list[str]]]
    ) -> None:
        """Cache rows for what ``_fetch_missing`` downloaded for this product."""
        if lookups.image_url is not None and lookups.image is None:
            await store_image_analysis(self.db, lookups.image_url, run.images[lookups.image_url])
        if definition is not None and lookups.product_type:
            await self.ptd.store(run.marketplace_id, lookups.product_type, *definition)

    async def _sync_content_anomalies(
        self, run: _Run, asin: str, content: ListingContent, baseline: Optional[ListingContent]
    ) -> tuple[int, int]:
        changes = diff_content(baseline, content) if baseline is not None else []
        rows = run.open.setdefault(asin, {})
        opened = resolved = 0
        current: set[str] = set()
        for change in changes:
            name = change.field[:_FIELD_MAX_LENGTH]
            current.add(name)
            anomaly, is_new = await self.repo.open_or_touch_anomaly(
                run.account.id, asin, CONTENT_CHANGED, name, change.baseline, change.live, run.now
            )
            rows[(CONTENT_CHANGED, name)] = anomaly
            opened += int(is_new)
        for (kind, name), anomaly in list(rows.items()):
            if kind == CONTENT_CHANGED and name not in current:
                await self.repo.resolve_anomaly(anomaly, run.now)
                del rows[(kind, name)]
                resolved += 1
        return opened, resolved

    # ---- variation families ----

    async def _capture_missing_families(
        self, account_id: UUID, scanned: set[str], saved_parents: set[str]
    ) -> int:
        """Recover references from approved children when the parent was never scanned."""
        links = await self.repo.approved_variation_parent_links(account_id, SOURCE_LIVE)
        members: dict[str, list[str]] = defaultdict(list)
        themes: dict[str, set[str]] = defaultdict(set)
        for child, (parents, theme) in sorted(links.items()):
            for parent in dict.fromkeys(p for p in parents if isinstance(p, str) and p):
                if parent == child or parent in scanned or parent in saved_parents:
                    continue
                members[parent].append(child)
                if theme:
                    themes[parent].add(theme)

        captured = 0
        for parent, children in members.items():
            if not scanned.intersection(children):
                continue
            parent_themes = themes[parent]
            theme = next(iter(parent_themes)) if len(parent_themes) == 1 else None
            created = await self.repo.create_family_baseline_if_absent(account_id, parent, theme, children)
            captured += int(created)
        return captured

    async def _check_families(self, run: _Run, scanned: set[str], subset: bool) -> None:
        by_family: dict[str, list[tuple[str, str, Any]]] = defaultdict(list)
        for asin, rows in run.open.items():
            for (kind, name), anomaly in rows.items():
                if kind in VARIATION_KINDS:
                    by_family[name].append((asin, kind, anomaly))

        families = await self.repo.family_baselines(run.account.id)
        if not subset:
            captured = await self._capture_missing_families(
                run.account.id, scanned, {family.parent_asin for family in families}
            )
            if captured:
                logger.info("Recovered %d variation references for account %s", captured, run.account.id)
                families = await self.repo.family_baselines(run.account.id)

        for family in families:
            parent = family.parent_asin
            children = [c for c in family.child_asins or [] if c]
            theme = family.variation_theme
            if subset and parent not in scanned and not scanned.intersection(children):
                continue
            try:
                await self.db.commit()  # members outside the scan are read with no transaction open
                for asin in (parent, *children):
                    if asin not in run.live:
                        run.live[asin] = self._relationships_only(run, asin)
                async with self.db.begin_nested():
                    opened, resolved = await self._check_family(
                        run, parent, theme, children, by_family.get(family_field(parent), []),
                        is_partial=family.is_partial,
                    )
                await self.db.commit()
            except Exception as exc:  # noqa: BLE001 - one family never stops the scan
                run.summary.record_error(f"family {parent}", exc)
                logger.warning("Variation check of %s failed: %s", parent, exc)
                continue
            run.summary.anomalies_opened += opened
            run.summary.anomalies_resolved += resolved

    def _relationships_only(self, run: _Run, asin: str) -> Optional[FamilyView]:
        """Family data of an ASIN outside the scanned set, for variation decisions only."""
        try:
            payload = self._catalog_item(run.client, asin)
        except Exception as exc:  # noqa: BLE001 - unknown, not detached
            logger.info("Catalog item %s unavailable for the variation check: %s", asin, exc)
            return None
        if not _relationships_known(payload, run.marketplace_id):
            return None
        return family_view(content_from_catalog(payload, run.marketplace_id))

    async def _check_family(
        self,
        run: _Run,
        parent: str,
        theme: Optional[str],
        children: list[str],
        open_rows: list[tuple[str, str, Any]],
        *,
        is_partial: bool,
    ) -> tuple[int, int]:
        """Open, touch or resolve the family's anomalies; every member is already in run.live."""
        live_parent = run.live.get(parent)
        findings = diff_family(
            parent, theme, children, live_parent, {c: run.live.get(c) for c in children},
            is_partial=is_partial,
        )

        name = family_field(parent)
        opened = resolved = 0
        current: set[tuple[str, str]] = set()
        for finding in findings:
            asin = finding.child_asin or finding.parent_asin
            current.add((asin, finding.kind))
            _, is_new = await self.repo.open_or_touch_anomaly(
                run.account.id, asin, finding.kind, name, finding.baseline, finding.live, run.now
            )
            opened += int(is_new)
        for asin, kind, anomaly in open_rows:
            if (asin, kind) in current:
                continue
            if kind == "child_detached":
                # Back only when the child names the parent again: a broken family
                # gets no per-child findings, yet its children are still detached.
                live_child = run.live.get(asin)
                known = asin not in children or (
                    live_child is not None and parent in live_child.parent_asins
                )
            else:
                known = live_parent is not None
            if known:  # an unknown member keeps its anomaly open
                await self.repo.resolve_anomaly(anomaly, run.now)
                resolved += 1
        return opened, resolved


# ---- runners and in-process scan state ----

_STATE_LOCK = threading.Lock()
_STATE: dict[UUID, dict] = {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _idle_state() -> dict:
    return {"running": False, "started_at": None, "finished_at": None, "summary": None}


def _claim(account_id: UUID) -> bool:
    """Mark a scan of the account as running; False if one already is."""
    with _STATE_LOCK:
        state = _STATE.get(account_id)
        if state is not None and state["running"]:
            return False
        _STATE[account_id] = {
            "running": True,
            "started_at": _now_iso(),
            "finished_at": None,
            "summary": None,
        }
        return True


def _release(account_id: UUID, summary: Optional[dict]) -> None:
    with _STATE_LOCK:
        state = _STATE.setdefault(account_id, _idle_state())
        state.update(running=False, finished_at=_now_iso(), summary=summary)


def scan_state(account_id: UUID) -> dict:
    """``{"running", "started_at", "finished_at", "summary"}`` of the account's last scan."""
    with _STATE_LOCK:
        return dict(_STATE.get(account_id) or _idle_state())


def _failure_summary(account_id: UUID, exc: Exception) -> dict:
    errors = [f"scan failed: {type(exc).__name__}"]
    return ScanSummary(account_id=account_id, errors=errors).to_dict()


async def _scan_account_by_id(
    account_id: UUID, session_factory, asins: Optional[list[str]] = None
) -> Optional[ScanSummary]:
    async with session_factory() as db:
        result = await db.execute(select(AmazonAccount).where(AmazonAccount.id == account_id))
        account = result.scalar_one_or_none()
        if account is None:
            return None
        try:
            return await CatalogScanService(db).scan_account(account, asins)
        except Exception:
            try:
                await db.rollback()
            except Exception:  # noqa: BLE001
                pass
            raise


async def _scan_and_record(account_id: UUID, session_factory) -> Optional[ScanSummary]:
    """Scan an account already claimed and record the outcome; never raises."""
    summary: Optional[ScanSummary] = None
    record: Optional[dict] = None
    try:
        summary = await _scan_account_by_id(account_id, session_factory)
        record = summary.to_dict() if summary is not None else None
    except Exception as exc:  # noqa: BLE001
        logger.exception("Catalog scan failed for account %s", account_id)
        record = _failure_summary(account_id, exc)
    finally:
        _release(account_id, record)
    return summary


async def _scheduled_scan_one(account_id: UUID, session_factory) -> int:
    if not _claim(account_id):
        logger.info("Catalog scan of %s skipped: a scan is already running", account_id)
        return 0
    summary = await _scan_and_record(account_id, session_factory)
    return summary.scanned if summary is not None else 0


def scan_account_allowlist(raw: str) -> Optional[set[UUID]]:
    """Accounts the daily scan may cover: None (every active account) when ``raw`` is empty.

    Entries that are not UUIDs are logged and ignored; a list with no valid entry
    scans nothing rather than everything.
    """
    entries = [e.strip() for e in (raw or "").split(",") if e.strip()]
    if not entries:
        return None
    allowed: set[UUID] = set()
    for entry in entries:
        try:
            allowed.add(UUID(entry))
        except ValueError:
            logger.warning("CATALOG_SCAN_ACCOUNT_IDS: %r is not an account id, ignored", entry)
    return allowed


async def _scheduled_account_ids(db) -> list[UUID]:
    """Active accounts, narrowed to CATALOG_SCAN_ACCOUNT_IDS when it is set."""
    ids = await list_active_account_ids(db)
    allowed = scan_account_allowlist(settings.CATALOG_SCAN_ACCOUNT_IDS)
    return ids if allowed is None else [i for i in ids if i in allowed]


def run_catalog_scan_all() -> dict:
    """Scheduler entry (and its Celery twin): the daily scan; never raises.

    Does nothing unless CATALOG_SCAN_ENABLED; then scans the active accounts of
    CATALOG_SCAN_ACCOUNT_IDS (all when empty), and skips the day when another
    scheduled sync holds the shared lock. "Scan now" (``start_account_scan``)
    does not depend on either setting.
    """
    if not settings.CATALOG_SCAN_ENABLED:
        logger.info("Catalog monitor scan skipped: CATALOG_SCAN_ENABLED is off")
        return {"status": "disabled", "accounts": 0, "records": 0}
    try:
        return _run_per_account_job(
            "Catalog monitor scan",
            _scheduled_scan_one,
            _scheduled_account_ids,
            lock=_SCHEDULED_SYNC_LOCK,
        )
    except Exception:  # noqa: BLE001
        logger.exception("Catalog monitor scan failed")
        return {"status": "error", "accounts": 0, "records": 0}


def _scan_in_thread(account_id: UUID) -> None:
    engine = None
    loop = None
    try:
        engine, session_factory = _make_local_session_factory()
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(_scan_and_record(account_id, session_factory))
    except Exception as exc:  # noqa: BLE001 - setup failed before the scan recorded itself
        logger.exception("Catalog scan thread failed for account %s", account_id)
        _release(account_id, _failure_summary(account_id, exc))
    finally:
        try:
            if loop is not None and engine is not None:
                loop.run_until_complete(engine.dispose())
        except Exception:  # noqa: BLE001
            logger.exception("Catalog scan engine cleanup failed")
        finally:
            if loop is not None:
                loop.close()


def start_account_scan(account_id: UUID) -> bool:
    """Start a background scan of one account; False if one is already running."""
    if not _claim(account_id):
        return False
    try:
        threading.Thread(
            target=_scan_in_thread,
            args=(account_id,),
            name=f"catalog-scan-{account_id}",
            daemon=True,
        ).start()
    except Exception as exc:  # noqa: BLE001
        logger.exception("Could not start the catalog scan of %s", account_id)
        _release(account_id, _failure_summary(account_id, exc))
        return False
    return True
