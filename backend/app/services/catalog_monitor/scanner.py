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

A product that fails is counted and the scan moves on (each product runs in a
savepoint). ``run_catalog_scan_all`` (scheduler) and ``start_account_scan``
("Scan now", background thread) never raise; their state lives in process
memory, keyed by account id.
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
from app.services.catalog_monitor.images import ImageAnalysis, get_image_analysis
from app.services.catalog_monitor.keywords import resolve_main_keywords
from app.services.catalog_monitor.ptd import ProductTypeDefinitionService
from app.services.catalog_monitor.repository import CatalogMonitorRepository
from app.services.catalog_monitor.rule_config import resolve_rule_configs
from app.services.catalog_monitor.rules import RuleContext, evaluate_listing
from app.services.extraction_runner import _make_local_session_factory, run_for_all_accounts

logger = logging.getLogger(__name__)

COMMIT_EVERY = 25
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
    baselines: dict
    now: datetime
    day: date
    summary: ScanSummary
    # asin -> {(kind, field): anomaly}, loaded once per scan
    open: dict[str, dict[tuple[str, str], Any]]
    # content used for variation decisions; None = unknown
    live: dict[str, Optional[ListingContent]] = field(default_factory=dict)
    images: dict[str, ImageAnalysis] = field(default_factory=dict)
    required: dict[str, Optional[list[str]]] = field(default_factory=dict)


def _index_open(rows: dict[tuple[str, str, str], Any]) -> dict[str, dict[tuple[str, str], Any]]:
    index: dict[str, dict[tuple[str, str], Any]] = defaultdict(dict)
    for (asin, kind, field_name), anomaly in rows.items():
        index[asin][(kind, field_name)] = anomaly
    return index


def _aplus_ok(capability: Any) -> bool:
    results = (capability.results or {}) if capability is not None else {}
    return bool((results.get("aplus") or {}).get("ok"))


class CatalogScanService:
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
        self._catalog_calls = 0

    async def scan_account(self, account, asins: Optional[list[str]] = None) -> ScanSummary:
        """Scan the account's active products (or only ``asins``); commits as it goes."""
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
            baselines=await self.repo.baselines(account.id),
            now=datetime.now(timezone.utc),
            day=self.today(),
            summary=ScanSummary(account_id=account.id),
            open=_index_open(await self.repo.open_anomalies(account.id)),
        )
        self._catalog_calls = 0

        for done, product in enumerate(products, start=1):
            await self._scan_product(run, product)
            if done % COMMIT_EVERY == 0:
                await self.db.commit()
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
            async with self.db.begin_nested():
                content, relationships_known = await self._live_content(run, product)
                configs = resolve_rule_configs(
                    run.overrides, run.marketplace_id, content.product_type
                )
                ctx = RuleContext(
                    main_keyword=run.keywords.get(asin),
                    required_attributes=await self._required_attributes(run, content.product_type),
                    main_image=await self._main_image(run, content),
                )
                evaluation = evaluate_listing(content, ctx, configs)
                writing = True
                _, is_new = await self.repo.save_version(run.account.id, asin, content, run.now)
                await self.repo.save_quality_snapshot(run.account.id, asin, evaluation, run.day)
                opened, resolved = await self._sync_content_anomalies(run, asin, content)
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
        run.live[asin] = content if relationships_known else None

    def _catalog_item(self, client, asin: str) -> dict:
        """One Catalog Items call, spaced from the previous one to respect the rate limit."""
        if self._catalog_calls:
            self.sleep(settings.CATALOG_SCAN_REQUEST_INTERVAL_S)
        self._catalog_calls += 1
        payload = client.get_catalog_item_full(asin)
        if not payload:
            raise LookupError("Catalog Items returned no item")
        return payload

    async def _live_content(self, run: _Run, product) -> tuple[ListingContent, bool]:
        """Today's content, and whether the Catalog payload included relationships."""
        asin = product.asin
        payload = self._catalog_item(run.client, asin)
        relationships_known = "relationships" in payload
        content = content_from_catalog(payload, run.marketplace_id)
        if not content.asin:
            content = replace(content, asin=asin)

        listing_fetched = False
        if run.seller_id and product.sku:
            try:
                listing = run.client.get_listing(run.seller_id, product.sku)
            except Exception as exc:  # noqa: BLE001 - keep the previous listing fields
                listing = None
                logger.info("Listings Items unavailable for %s: %s", asin, exc)
            if listing:  # an empty 200 says nothing: keep the previous listing fields
                content = merge_listing(content, listing)
                listing_fetched = True

        aplus_fetched = False
        if run.aplus_ok:
            try:
                count = run.client.get_aplus_publish_record_count(asin)
                content = with_aplus(content, count, True)
                aplus_fetched = True
            except Exception as exc:  # noqa: BLE001 - keep the previous A+ fields
                logger.info("A+ publish records unavailable for %s: %s", asin, exc)

        latest = (await self.repo.latest_versions(run.account.id, [asin])).get(asin)
        previous = content_from_dict(latest.content) if latest is not None else None
        content = carry_forward(content, previous, listing_fetched, aplus_fetched)
        if not relationships_known and previous is not None:
            # A partial payload says nothing about the family: keep the stored one.
            content = replace(
                content,
                parent_asins=list(previous.parent_asins),
                child_asins=list(previous.child_asins),
                variation_theme=previous.variation_theme,
            )
        return content, relationships_known

    async def _main_image(self, run: _Run, content: ListingContent) -> Optional[ImageAnalysis]:
        if not content.images or content.images[0].variant != "MAIN":
            return None
        url = content.images[0].url
        if url not in run.images:  # one download and one image_checks row per URL per scan
            run.images[url] = await get_image_analysis(self.db, url, fetch=self.image_fetch)
        return run.images[url]

    async def _required_attributes(
        self, run: _Run, product_type: Optional[str]
    ) -> Optional[list[str]]:
        if not product_type:
            return None
        if product_type not in run.required:
            try:
                run.required[product_type] = await ProductTypeDefinitionService(
                    self.db
                ).required_attributes(run.client, run.marketplace_id, product_type)
            except Exception as exc:  # noqa: BLE001 - attributes light turns grey
                logger.warning("Product type %s requirements unavailable: %s", product_type, exc)
                run.required[product_type] = None
        return run.required[product_type]

    async def _sync_content_anomalies(
        self, run: _Run, asin: str, content: ListingContent
    ) -> tuple[int, int]:
        baseline = run.baselines.get(asin)
        changes = diff_content(content_from_dict(baseline.content), content) if baseline else []
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

    async def _check_families(self, run: _Run, scanned: set[str], subset: bool) -> None:
        by_family: dict[str, list[tuple[str, str, Any]]] = defaultdict(list)
        for asin, rows in run.open.items():
            for (kind, name), anomaly in rows.items():
                if kind in VARIATION_KINDS:
                    by_family[name].append((asin, kind, anomaly))

        for family in await self.repo.family_baselines(run.account.id):
            parent = family.parent_asin
            children = [c for c in family.child_asins or [] if c]
            if subset and parent not in scanned and not scanned.intersection(children):
                continue
            try:
                async with self.db.begin_nested():
                    opened, resolved = await self._check_family(
                        run, parent, family.variation_theme, children,
                        by_family.get(family_field(parent), []),
                    )
            except Exception as exc:  # noqa: BLE001 - one family never stops the scan
                run.summary.record_error(f"family {parent}", exc)
                logger.warning("Variation check of %s failed: %s", parent, exc)
                continue
            run.summary.anomalies_opened += opened
            run.summary.anomalies_resolved += resolved

    def _relationships_only(self, run: _Run, asin: str) -> Optional[ListingContent]:
        """Content of an ASIN outside the scanned set, for variation decisions only."""
        try:
            payload = self._catalog_item(run.client, asin)
        except Exception as exc:  # noqa: BLE001 - unknown, not detached
            logger.info("Catalog item %s unavailable for the variation check: %s", asin, exc)
            return None
        if "relationships" not in payload:
            return None
        return content_from_catalog(payload, run.marketplace_id)

    async def _check_family(
        self,
        run: _Run,
        parent: str,
        theme: Optional[str],
        children: list[str],
        open_rows: list[tuple[str, str, Any]],
    ) -> tuple[int, int]:
        for asin in (parent, *children):
            if asin not in run.live:
                run.live[asin] = self._relationships_only(run, asin)
        live_parent = run.live.get(parent)
        findings = diff_family(
            parent, theme, children, live_parent, {c: run.live.get(c) for c in children}
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


def run_catalog_scan_all() -> dict:
    """Scheduler entry: scan every active account, Seller and Vendor. Never raises."""
    try:
        return run_for_all_accounts("Catalog monitor scan", _scheduled_scan_one)
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
