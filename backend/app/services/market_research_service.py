"""Market research service for competitive analysis."""
import asyncio
import logging
import time
from datetime import datetime
from typing import Any, Callable, List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
try:
    from sp_api.base.exceptions import (
        SellingApiBadRequestException,
        SellingApiForbiddenException,
        SellingApiGatewayTimeoutException,
        SellingApiNotFoundException,
        SellingApiRequestThrottledException,
        SellingApiServerException,
        SellingApiStateConflictException,
        SellingApiTemporarilyUnavailableException,
        SellingApiTooLargeException,
        SellingApiUnsupportedFormatException,
    )
except ImportError:  # pragma: no cover - keeps pure unit tests independent of SP-API package
    class SellingApiBadRequestException(Exception):
        pass

    class SellingApiForbiddenException(Exception):
        pass

    class SellingApiGatewayTimeoutException(Exception):
        pass

    class SellingApiNotFoundException(Exception):
        pass

    class SellingApiRequestThrottledException(Exception):
        pass

    class SellingApiServerException(Exception):
        pass

    class SellingApiStateConflictException(Exception):
        pass

    class SellingApiTemporarilyUnavailableException(Exception):
        pass

    class SellingApiTooLargeException(Exception):
        pass

    class SellingApiUnsupportedFormatException(Exception):
        pass

from app.models.market_research import MarketResearchReport
from app.models.amazon_account import AmazonAccount
from app.models.product import Product
from app.schemas.market_research import MarketResearchCreate

logger = logging.getLogger(__name__)

# How many competitors to auto-discover
AUTO_DISCOVER_COUNT = 8

# A price that repeats verbatim across several distinct listings is almost
# always a placeholder/sentinel from SP-API (a barcode or a marketplace default
# echoed onto unrelated ASINs), not a real market price. Excluding those values
# keeps averages, ranges and the comparison matrix honest.
_SENTINEL_PRICE_MIN_OCCURRENCES = 3
_SENTINEL_PRICE_MIN_SHARE = 0.3
_SENTINEL_PRICE_MIN_VALUE = 1000.0


def _detect_sentinel_prices(values: list[float]) -> set[float]:
    """Return the set of price values that look like repeated placeholders."""
    positive = [v for v in values if v is not None and v > 0]
    if len(positive) < _SENTINEL_PRICE_MIN_OCCURRENCES:
        return set()

    counts: dict[float, int] = {}
    for value in positive:
        counts[value] = counts.get(value, 0) + 1

    return {
        value
        for value, count in counts.items()
        if value >= _SENTINEL_PRICE_MIN_VALUE
        and count >= _SENTINEL_PRICE_MIN_OCCURRENCES
        and count / len(positive) >= _SENTINEL_PRICE_MIN_SHARE
    }


def _snapshot_price(snapshot: dict) -> Optional[float]:
    try:
        value = snapshot.get("price")
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _flag_sentinel_prices(snapshots: List[dict]) -> None:
    """Mark snapshots whose price is non-positive or a repeated placeholder.

    The price itself is kept (transparency for debugging) but flagged via
    ``price_unreliable`` so the API, the UI and the PDF can hide it instead
    of presenting a barcode-shaped number as a market price.
    """
    prices = [p for p in (_snapshot_price(s) for s in snapshots) if p is not None]
    sentinels = _detect_sentinel_prices(prices)

    for snapshot in snapshots:
        price = _snapshot_price(snapshot)
        if price is not None and (price <= 0 or price in sentinels):
            snapshot["price_unreliable"] = True
        else:
            snapshot.pop("price_unreliable", None)


def _backfill_missing_prices(client, snapshots: List[dict]) -> None:
    """Fill missing snapshot prices with one batched Pricing API call.

    Per-ASIN lookups regularly come back empty (throttling, no
    CompetitivePrices entry); the batch endpoint resolves many of those in
    a single round-trip. Vendors have no Pricing API access, so this is a
    no-op for them.
    """
    if getattr(client, "is_vendor", False):
        return

    missing = [
        str(s["asin"]).upper()
        for s in snapshots
        if s.get("asin") and _snapshot_price(s) is None
    ]
    if not missing:
        return

    try:
        price_map = client.get_market_prices_for_asins(missing)
    except Exception as exc:
        logger.warning("Batched price backfill failed: %s", exc)
        return

    for snapshot in snapshots:
        if _snapshot_price(snapshot) is not None:
            continue
        price = price_map.get(str(snapshot.get("asin", "")).upper())
        if price is not None:
            snapshot["price"] = float(price)


async def _backfill_missing_prices_from_catalog(
    db: AsyncSession,
    account_id: UUID,
    snapshots: List[dict],
) -> None:
    """Fill missing prices from the account's saved catalog when available."""
    missing = [
        str(s["asin"]).upper()
        for s in snapshots
        if s.get("asin") and _snapshot_price(s) is None
    ]
    if not missing:
        return

    result = await db.execute(
        select(Product.asin, Product.current_price)
        .where(
            Product.account_id == account_id,
            Product.asin.in_(list(dict.fromkeys(missing))),
            Product.current_price.is_not(None),
        )
    )
    price_map: dict[str, float] = {}
    for asin, current_price in result.all():
        price = _snapshot_price({"price": current_price})
        if price is not None and price > 0:
            price_map[str(asin).upper()] = price

    for snapshot in snapshots:
        if _snapshot_price(snapshot) is not None:
            continue
        price = price_map.get(str(snapshot.get("asin", "")).upper())
        if price is not None:
            snapshot["price"] = price


class MarketResearchService:
    """Service for creating and managing market research reports."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_report(
        self,
        org_id: UUID,
        user_id: UUID,
        data: MarketResearchCreate,
    ) -> MarketResearchReport:
        """Create a new market research report.

        Supports two modes:
        - Product Analysis: source_asin is provided (existing flow)
        - Market Search: search_query + search_type provided (Market Tracker 360)
        """
        # Validate that we have either source_asin or search_query
        if not data.source_asin and not data.search_query:
            raise ValueError("Either source_asin or search_query must be provided")
        if data.search_query and not data.search_type:
            raise ValueError("search_type is required when search_query is provided")

        # Verify account belongs to org
        result = await self.db.execute(
            select(AmazonAccount).where(
                AmazonAccount.id == UUID(data.account_id),
                AmazonAccount.organization_id == org_id,
            )
        )
        account = result.scalar_one_or_none()
        if not account:
            raise ValueError("Account not found or does not belong to organization")

        # For Market Tracker 360, use the query as a placeholder source_asin
        source_asin = data.source_asin or data.search_query[:20]
        if data.search_query:
            title = f"Market Search: {data.search_query[:80]}"
        else:
            title = f"Market Research: {data.source_asin}"

        report = MarketResearchReport(
            organization_id=org_id,
            created_by_id=user_id,
            account_id=account.id,
            source_asin=source_asin,
            marketplace=account.marketplace_country,
            language=data.language,
            title=title,
            status="pending",
        )
        self.db.add(report)
        await self.db.flush()
        await self.db.refresh(report)

        return report

    async def get_report(self, report_id: UUID, org_id: UUID) -> Optional[MarketResearchReport]:
        """Get a single report by ID, scoped to org."""
        result = await self.db.execute(
            select(MarketResearchReport).where(
                MarketResearchReport.id == report_id,
                MarketResearchReport.organization_id == org_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_reports(
        self, org_id: UUID, limit: int = 20, offset: int = 0,
    ) -> List[MarketResearchReport]:
        """List reports for an organization."""
        result = await self.db.execute(
            select(MarketResearchReport)
            .where(MarketResearchReport.organization_id == org_id)
            .order_by(MarketResearchReport.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def delete_report(self, report_id: UUID, org_id: UUID) -> bool:
        """Delete a report."""
        report = await self.get_report(report_id, org_id)
        if not report:
            return False
        await self.db.delete(report)
        await self.db.flush()
        return True

    def get_comparison_matrix(self, report: MarketResearchReport) -> dict[str, Any]:
        """Build a dimension-by-dimension comparison matrix for a completed report.

        Tolerant of partial data: each dimension reports how many competitors
        contributed a value (``competitors_with_data``). Dimensions that lack
        enough comparable data are still returned (so the UI can label them
        N/A) but do not contribute to ``overall_score``. When no dimension is
        scoreable, ``overall_score`` is ``None`` rather than a misleading 0.
        """
        product_snapshot = report.product_snapshot or {}
        competitor_data = report.competitor_data or []

        if not product_snapshot or not competitor_data:
            raise ValueError("Comparison matrix requires product and competitor data")

        dimensions_config = [
            {"name": "price", "field": "price", "weight": 0.3, "lower_is_better": True},
            {"name": "bsr", "field": "bsr", "weight": 0.3, "lower_is_better": True},
            {"name": "reviews", "field": "review_count", "weight": 0.2, "lower_is_better": False},
            {"name": "rating", "field": "rating", "weight": 0.2, "lower_is_better": False},
        ]

        all_prices = [
            self._coerce_numeric(snapshot.get("price"))
            for snapshot in [product_snapshot, *competitor_data]
        ]
        sentinel_prices = _detect_sentinel_prices([p for p in all_prices if p is not None])

        dimensions: list[dict[str, Any]] = []
        overall_score = 0.0
        total_weight = 0.0
        opportunities: list[str] = []

        for config in dimensions_config:
            dimension = self._build_comparison_dimension(
                product_snapshot=product_snapshot,
                competitor_data=competitor_data,
                name=config["name"],
                field=config["field"],
                lower_is_better=config["lower_is_better"],
                invalid_values=sentinel_prices if config["field"] == "price" else None,
            )

            dimensions.append(dimension)

            # Only score dimensions where we have the client value plus at
            # least one comparable competitor value. This prevents a single
            # data point from anchoring an overall_score.
            if (
                dimension["client_rank"] is not None
                and dimension.get("competitors_with_data", 0) >= 1
            ):
                normalized_rank = self._normalize_rank(
                    rank=dimension["client_rank"],
                    total=dimension["total_competitors"],
                )
                overall_score += normalized_rank * config["weight"]
                total_weight += config["weight"]

            if dimension.pop("is_worse_than_average", False):
                opportunities.append(config["name"])

        return {
            "dimensions": dimensions,
            "overall_score": round(overall_score / total_weight, 1) if total_weight else None,
            "opportunities": opportunities,
        }

    @staticmethod
    def _coerce_numeric(value: Any) -> Optional[float]:
        """Convert numeric JSON values to float and ignore non-numeric values."""
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @classmethod
    def _build_comparison_dimension(
        cls,
        product_snapshot: dict[str, Any],
        competitor_data: list[dict[str, Any]],
        name: str,
        field: str,
        lower_is_better: bool,
        invalid_values: Optional[set[float]] = None,
    ) -> dict[str, Any]:
        """Compute comparison stats for a single metric dimension.

        ``invalid_values`` (e.g. detected sentinel prices) and non-positive
        prices are treated as missing so they never pollute averages, ranges
        or the rank used for scoring.
        """
        invalid = invalid_values or set()
        is_price = field == "price"

        def _clean(raw: Any) -> Optional[float]:
            numeric = cls._coerce_numeric(raw)
            if numeric is None:
                return None
            if is_price and numeric <= 0:
                return None
            if numeric in invalid:
                return None
            return numeric

        client_value = _clean(product_snapshot.get(field))

        competitor_values: list[tuple[dict[str, Any], float]] = []
        for competitor in competitor_data:
            numeric_value = _clean(competitor.get(field))
            if numeric_value is not None:
                competitor_values.append((competitor, numeric_value))

        raw_competitor_values = [value for _, value in competitor_values]
        competitor_avg_raw = (
            sum(raw_competitor_values) / len(raw_competitor_values)
            if raw_competitor_values
            else None
        )
        competitor_avg = round(competitor_avg_raw, 2) if competitor_avg_raw is not None else None
        competitor_min = min(raw_competitor_values) if raw_competitor_values else None
        competitor_max = max(raw_competitor_values) if raw_competitor_values else None

        competitor_best = None
        competitor_best_name = None
        if competitor_values:
            best_competitor, competitor_best = min(
                competitor_values,
                key=lambda item: item[1],
            ) if lower_is_better else max(
                competitor_values,
                key=lambda item: item[1],
            )
            competitor_best_name = (
                best_competitor.get("title")
                or best_competitor.get("asin")
                or None
            )

        ranked_values = list(raw_competitor_values)
        if client_value is not None:
            ranked_values.append(client_value)

        client_rank = None
        if client_value is not None and ranked_values:
            better_count = sum(
                1
                for value in raw_competitor_values
                if ((value < client_value) if lower_is_better else (value > client_value))
            )
            client_rank = better_count + 1

        gap_percent = None
        if client_value is not None and competitor_avg_raw not in (None, 0):
            gap_percent = round(((client_value - competitor_avg_raw) / competitor_avg_raw) * 100, 1)

        is_worse_than_average = False
        if client_value is not None and competitor_avg_raw is not None:
            is_worse_than_average = (
                client_value > competitor_avg_raw
                if lower_is_better
                else client_value < competitor_avg_raw
            )

        return {
            "name": name,
            "client_value": client_value,
            "competitor_avg": competitor_avg,
            "competitor_min": competitor_min,
            "competitor_max": competitor_max,
            "competitor_best": competitor_best,
            "competitor_best_name": competitor_best_name,
            "client_rank": client_rank,
            "total_competitors": len(ranked_values),
            "competitors_with_data": len(raw_competitor_values),
            "gap_percent": gap_percent,
            "is_worse_than_average": is_worse_than_average,
        }

    @staticmethod
    def _normalize_rank(rank: int, total: int) -> float:
        """Normalize rank to a 0-100 competitive score."""
        if total <= 1:
            return 100.0
        return ((total - rank) / (total - 1)) * 100


def process_report_background(
    report_id: str,
    extra_asins: Optional[List[str]] = None,
    market_competitor_asins: Optional[List[str]] = None,
    search_query: Optional[str] = None,
    search_type: Optional[str] = None,
):
    """Process a market research report synchronously in a background thread.

    This replaces the Celery task for deployments without Redis.
    Supports two modes:
    - Product Analysis (default): source ASIN → discover competitors → AI analysis
    - Market Search (search_query provided): keyword/brand search → AI analysis
    """
    from sqlalchemy import text as sa_text
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
    from app.models.market_research import MarketResearchReport
    from app.models.amazon_account import AmazonAccount
    from app.core.amazon.sp_api_client import SPAPIClient, resolve_marketplace
    from app.core.amazon.credentials import resolve_credentials
    from app.config import settings

    # Build a private engine + session factory for this invocation.
    # The shared engine (app.db.session.engine) uses an asyncpg connection pool
    # that is bound to the event loop where connections were first created.
    # Since each call here runs in its own asyncio.new_event_loop(), reusing
    # the shared pool causes "another operation is in progress" errors.
    from app.db.session import db_url as _db_url
    _local_engine = create_async_engine(
        _db_url,
        echo=settings.APP_DEBUG,
        pool_size=2,
        max_overflow=1,
    )
    _LocalSession = async_sessionmaker(
        bind=_local_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )

    async def _process():
        async with _LocalSession() as db:
            result = await db.execute(
                select(MarketResearchReport).where(
                    MarketResearchReport.id == UUID(report_id)
                )
            )
            report = result.scalar_one_or_none()
            if not report:
                logger.error(f"Market research report {report_id} not found")
                return

            async def _set_progress(step: str, pct: int):
                """Update progress via a separate session so it's immediately
                visible to polling GET requests regardless of main tx state."""
                try:
                    async with _LocalSession() as pdb:
                        await pdb.execute(
                            sa_text(
                                "UPDATE market_research_reports "
                                "SET progress_step = :step, progress_pct = :pct "
                                "WHERE id = :rid"
                            ),
                            {"step": step, "pct": pct, "rid": report_id},
                        )
                        await pdb.commit()
                except Exception as exc:
                    logger.warning(f"Progress update failed for {report_id}: {exc}")

            try:
                report.status = "processing"
                await db.commit()
                await _set_progress("Initializing analysis...", 5)

                # Load account
                acc_result = await db.execute(
                    select(AmazonAccount).where(AmazonAccount.id == report.account_id)
                )
                account = acc_result.scalar_one_or_none()
                if not account:
                    raise ValueError(f"Account {report.account_id} not found")

                from app.models.user import Organization
                org_result = await db.execute(
                    select(Organization).where(Organization.id == report.organization_id)
                )
                organization = org_result.scalar_one_or_none()

                # Build SP-API client
                credentials = resolve_credentials(account, organization)
                marketplace = resolve_marketplace(account.marketplace_country)
                client = SPAPIClient(
                    credentials, marketplace,
                    account_type=account.account_type.value,
                )

                if search_query:
                    # ── Market Tracker 360 mode ──
                    logger.info(
                        f"Report {report_id}: Market Search mode "
                        f"({search_type}): '{search_query}'"
                    )
                    await _set_progress("Searching Amazon catalog...", 10)

                    selected_reference_asin = (
                        report.source_asin.upper() if report.source_asin else None
                    )
                    seeded_competitor_asins = list(
                        dict.fromkeys(
                            [
                                asin.upper()
                                for asin in (market_competitor_asins or [])
                                if asin
                            ]
                        )
                    )
                    discovery_errors: list[str] = []

                    def _safe_catalog_search(query: str, max_results: int) -> list[dict]:
                        try:
                            return client.search_catalog_by_keyword(
                                query, max_results=max_results
                            )
                        except Exception as exc:
                            logger.warning(
                                "Catalog search failed for %r on report %s: %s",
                                query,
                                report_id,
                                exc,
                            )
                            discovery_errors.append(f"catalog_search:{exc}"[:300])
                            return []

                    if search_type == "asin":
                        # Fetch the specific ASIN as reference product
                        await _set_progress("Fetching product data...", 15)
                        reference_asin = selected_reference_asin or search_query.upper()
                        product_snapshot = _fetch_product_data(
                            client, reference_asin
                        )
                        report.product_snapshot = product_snapshot
                        report.source_asin = reference_asin
                        source_title = product_snapshot.get("title", "")
                        source_category = product_snapshot.get("category")
                        if source_title:
                            report.title = f"Market Search: {source_title[:80]}"

                        if seeded_competitor_asins:
                            comp_asins = [
                                asin for asin in seeded_competitor_asins
                                if asin != reference_asin
                            ][:10]
                        else:
                            # Discover related products
                            await _set_progress("Discovering related products...", 25)
                            search_kw = source_title[:80] if source_title else search_query
                            raw = _safe_catalog_search(search_kw, max_results=15)
                            comp_asins = [
                                r["asin"] for r in raw
                                if r["asin"] != reference_asin
                            ][:10]
                    else:
                        if seeded_competitor_asins and selected_reference_asin:
                            await _set_progress("Fetching reference product...", 20)
                            reference_asin = selected_reference_asin
                            product_snapshot = _fetch_product_data(
                                client, reference_asin
                            )
                            sample_size = len(seeded_competitor_asins) + 1
                            comp_asins = [
                                asin for asin in seeded_competitor_asins
                                if asin != reference_asin
                            ][:10]
                        else:
                            # keyword or brand search
                            await _set_progress("Searching market...", 15)
                            raw = _safe_catalog_search(search_query, max_results=15)
                            if not raw:
                                raise ValueError(
                                    f"No products found for '{search_query}'. "
                                    "Try a different search term."
                                    + (
                                        f" Catalog search errors: {discovery_errors[0]}"
                                        if discovery_errors else ""
                                    )
                                )

                            reference_asin = selected_reference_asin
                            if not reference_asin:
                                reference_asin = raw[0]["asin"]

                            await _set_progress("Fetching reference product...", 20)
                            product_snapshot = _fetch_product_data(
                                client, reference_asin
                            )
                            sample_size = len(raw)
                            comp_asins = [
                                r["asin"] for r in raw
                                if r["asin"] != reference_asin
                            ][:10]

                        report.product_snapshot = product_snapshot
                        report.source_asin = reference_asin
                        source_category = product_snapshot.get("category")
                        report.title = (
                            f"Market Search: {search_query[:60]} "
                            f"({sample_size} products)"
                        )

                    # Fetch competitor data. _fetch_product_data already
                    # captures per-ASIN errors via the ``fetch_errors`` field
                    # on the snapshot, so one bad ASIN doesn't sink the report.
                    comp_data = []
                    total_comps = len(comp_asins)
                    for i, asin in enumerate(comp_asins):
                        pct = 30 + int((i / max(total_comps, 1)) * 40)
                        await _set_progress(
                            f"Analyzing competitor {i + 1}/{total_comps}...", pct
                        )
                        comp_data.append(_fetch_product_data(client, asin))
                        time.sleep(0.5)
                    report.competitor_data = comp_data
                    if discovery_errors and isinstance(report.product_snapshot, dict):
                        snapshot_copy = dict(report.product_snapshot)
                        existing = list(snapshot_copy.get("fetch_errors") or [])
                        existing.extend(discovery_errors)
                        snapshot_copy["fetch_errors"] = list(dict.fromkeys(existing))
                        report.product_snapshot = snapshot_copy

                else:
                    # ── Classic Product Analysis mode ──
                    # Step 1: Fetch source product
                    await _set_progress("Fetching product data...", 10)
                    product_snapshot = _fetch_product_data(
                        client, report.source_asin
                    )
                    report.product_snapshot = product_snapshot

                    source_title = product_snapshot.get("title", "")
                    source_brand = product_snapshot.get("brand")
                    source_category = product_snapshot.get("category")

                    if source_title:
                        report.title = f"Market Research: {source_title[:80]}"

                    if not source_title:
                        logger.warning(
                            f"Report {report_id}: SP-API returned no data for "
                            f"{report.source_asin}. Check ASIN and credentials."
                        )

                    # Step 2: Auto-discover competitors
                    await _set_progress("Discovering competitors...", 20)
                    discovered_asins = _discover_competitors(
                        client,
                        source_asin=report.source_asin,
                        source_title=source_title,
                        source_brand=source_brand,
                        max_results=AUTO_DISCOVER_COUNT,
                    )

                    # Merge with manual ASINs
                    all_competitor_asins = list(dict.fromkeys(
                        discovered_asins + (extra_asins or [])
                    ))
                    all_competitor_asins = [
                        a for a in all_competitor_asins
                        if a != report.source_asin
                    ][:10]

                    logger.info(
                        f"Report {report_id}: "
                        f"{len(discovered_asins)} discovered, "
                        f"{len(extra_asins or [])} manual, "
                        f"{len(all_competitor_asins)} total"
                    )

                    if not source_title and not all_competitor_asins:
                        raise ValueError(
                            "Could not retrieve product data from Amazon "
                            "SP-API. Please verify the ASIN is correct and "
                            "the account credentials are configured."
                        )

                    # Step 3: Fetch data for each competitor
                    comp_data = []
                    total_comps = len(all_competitor_asins)
                    for i, comp_asin in enumerate(all_competitor_asins):
                        pct = 30 + int((i / max(total_comps, 1)) * 40)
                        await _set_progress(
                            f"Analyzing competitor {i + 1}/{total_comps}...", pct
                        )
                        comp_data.append(
                            _fetch_product_data(client, comp_asin)
                        )
                        time.sleep(0.5)
                    report.competitor_data = comp_data

                # Consolidate snapshots: one batched pricing call fills any
                # prices the per-ASIN lookups missed, then repeated
                # placeholder prices are flagged before anything is
                # persisted or fed to the AI.
                product_snapshot = dict(report.product_snapshot or {})
                comp_data = [dict(c) for c in (report.competitor_data or [])]
                _backfill_missing_prices(client, [product_snapshot, *comp_data])
                await _backfill_missing_prices_from_catalog(
                    db,
                    report.account_id,
                    [product_snapshot, *comp_data],
                )
                _flag_sentinel_prices([product_snapshot, *comp_data])
                report.product_snapshot = product_snapshot
                report.competitor_data = comp_data

                # Step 4: AI analysis (best-effort: market data is already
                # complete at this point, so an AI failure must not turn a
                # valid report into status=failed).
                if settings.ANTHROPIC_API_KEY:
                    await _set_progress("Generating AI insights...", 75)
                    from app.services.ai_analysis_service import AIAnalysisService
                    try:
                        ai_service = AIAnalysisService(settings.ANTHROPIC_API_KEY)
                        analysis = ai_service.analyze(
                            product_data=product_snapshot,
                            competitor_data=comp_data,
                            category=source_category,
                            language=report.language,
                        )
                        report.ai_analysis = analysis
                    except Exception:
                        logger.exception(
                            "AI analysis failed for report %s; completing without AI narrative",
                            report_id,
                        )

                await _set_progress("Finalizing report...", 95)
                report.status = "completed"
                report.progress_step = "Complete"
                report.progress_pct = 100
                report.completed_at = datetime.utcnow()
                await db.commit()
                logger.info(
                    f"Market research {report_id} completed: "
                    f"{len(comp_data)} competitors analyzed"
                )

            except Exception as e:
                logger.exception(f"Market research {report_id} failed: {e}")
                try:
                    await db.rollback()
                    report.status = "failed"
                    report.error_message = str(e)[:500]
                    await db.commit()
                except Exception:
                    # Last resort: try a separate session to mark as failed
                    try:
                        async with _LocalSession() as fdb:
                            await fdb.execute(
                                sa_text(
                                    "UPDATE market_research_reports "
                                    "SET status = 'failed', error_message = :msg "
                                    "WHERE id = :rid"
                                ),
                                {"msg": str(e)[:500], "rid": report_id},
                            )
                            await fdb.commit()
                    except Exception:
                        logger.error(f"Could not mark report {report_id} as failed")

    # Run async processing in a new event loop (this runs in a thread).
    # Dispose the private engine afterwards to release connections.
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_process())
    finally:
        loop.run_until_complete(_local_engine.dispose())
        loop.close()


def _discover_competitors(
    client,
    source_asin: str,
    source_title: str,
    source_brand: Optional[str],
    max_results: int = 8,
) -> List[str]:
    """Auto-discover competitor ASINs via SP-API catalog search.

    Returns an empty list (with a logged warning) on transient catalog
    search failures rather than letting the exception propagate; the
    caller can still complete the report with the source product alone.
    """
    if not source_title:
        logger.warning(f"No title for {source_asin}, cannot discover competitors")
        return []

    noise_words = {
        "the", "a", "an", "for", "and", "or", "with", "in", "of", "to",
        "per", "con", "e", "di", "da", "il", "la", "le", "un", "una",
        "-", "&", "|", "/", ",", ".", "(", ")", "[", "]",
    }
    words = source_title.split()
    keywords = []
    for w in words:
        clean = w.strip("()[].,;:-\u2013\u2014\"'").lower()
        if len(clean) < 2:
            continue
        if clean in noise_words:
            continue
        if source_brand and clean == source_brand.lower():
            continue
        keywords.append(w.strip("()[].,;:-\u2013\u2014\"'"))
        if len(keywords) >= 5:
            break

    if not keywords:
        logger.warning(f"Could not extract keywords from title: {source_title}")
        return []

    search_query = " ".join(keywords)
    logger.info(f"Competitor search query: '{search_query}' (from: {source_title[:60]})")

    try:
        results = client.search_competitor_asins(
            keywords=search_query,
            source_asin=source_asin,
            source_brand=source_brand,
            max_results=max_results,
        )
    except Exception as exc:
        logger.warning(
            "Competitor discovery via SP-API catalog search failed for %s: %s",
            source_asin,
            exc,
        )
        return []

    return [r["asin"] for r in results]


def _retry_delay_from_headers(exc: Exception, default_delay: float = 2.0) -> float:
    """Read Retry-After from SP-API exceptions without assuming headers shape."""
    headers = getattr(exc, "headers", None) or {}
    if hasattr(headers, "get"):
        retry_after = headers.get("Retry-After") or headers.get("retry-after")
    else:
        retry_after = None

    try:
        return max(default_delay, float(retry_after))
    except (TypeError, ValueError):
        return default_delay


def _classify_fetch_exception(exc: Exception) -> str:
    """Collapse SP-API and transport failures into stable error labels."""
    if isinstance(
        exc,
        (
            SellingApiBadRequestException,
            SellingApiNotFoundException,
            SellingApiStateConflictException,
            SellingApiTooLargeException,
            SellingApiUnsupportedFormatException,
        ),
    ):
        return "invalid"

    if isinstance(
        exc,
        (
            SellingApiGatewayTimeoutException,
            SellingApiServerException,
            SellingApiTemporarilyUnavailableException,
        ),
    ):
        return "network"

    if type(exc).__name__ in {
        "ConnectTimeout",
        "ConnectionError",
        "ReadTimeout",
        "RequestException",
        "Timeout",
    }:
        return "network"

    return "error"


def _call_sp_api_with_single_retry(
    fetcher: Callable[[], Any],
    asin: str,
    operation: str,
) -> tuple[Any, Optional[str]]:
    """Execute one SP-API request, retrying a throttled response once."""
    try:
        return fetcher(), None
    except SellingApiRequestThrottledException as exc:
        delay = _retry_delay_from_headers(exc, default_delay=2.0)
        logger.warning(
            "SP-API throttled during %s lookup for %s; retrying once in %.1fs",
            operation,
            asin,
            delay,
        )
        time.sleep(delay)
        try:
            return fetcher(), None
        except SellingApiRequestThrottledException as retry_exc:
            logger.warning(
                "SP-API remained throttled during %s lookup for %s after retry: %s",
                operation,
                asin,
                retry_exc,
            )
            return None, "throttled"
        except SellingApiForbiddenException as retry_exc:
            logger.warning(
                "SP-API denied %s lookup for %s after throttle retry: %s",
                operation,
                asin,
                retry_exc,
            )
            return None, "forbidden"
        except Exception as retry_exc:
            logger.warning(
                "SP-API %s lookup failed for %s after throttle retry: %s",
                operation,
                asin,
                retry_exc,
            )
            return None, _classify_fetch_exception(retry_exc)
    except SellingApiForbiddenException as exc:
        logger.warning(
            "SP-API denied %s lookup for %s: %s",
            operation,
            asin,
            exc,
        )
        return None, "forbidden"
    except Exception as exc:
        logger.warning(
            "SP-API %s lookup failed for %s: %s",
            operation,
            asin,
            exc,
        )
        return None, _classify_fetch_exception(exc)


def _extract_rating_and_reviews(attributes: dict) -> tuple[Optional[float], Optional[int]]:
    """Pull average rating and review count from a catalog attributes payload.

    SP-API exposes these under shapes that vary by marketplace. We probe a
    few well-known paths and return ``(None, None)`` if nothing is found.
    Never invent or default a value.
    """
    rating: Optional[float] = None
    reviews: Optional[int] = None

    def _read_number(value):
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return value
        if isinstance(value, dict):
            for key in ("value", "average", "Value"):
                if key in value:
                    return _read_number(value[key])
        if isinstance(value, list) and value:
            return _read_number(value[0])
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    customer_reviews = attributes.get("customer_reviews") or attributes.get("customerReviews") or {}
    if isinstance(customer_reviews, dict):
        rating_value = _read_number(customer_reviews.get("average_rating") or customer_reviews.get("averageRating"))
        reviews_value = _read_number(customer_reviews.get("review_count") or customer_reviews.get("reviewCount"))
        if rating_value is not None:
            rating = float(rating_value)
        if reviews_value is not None:
            reviews = int(reviews_value)

    return rating, reviews


def _extract_text_attribute_values(attributes: dict, *keys: str) -> list[str]:
    """Extract text values from SP-API catalog attribute shapes.

    Attribute payloads vary by marketplace and may be a scalar, a dict with a
    ``value`` field, or a list of marketplace-specific dicts. Missing values
    return an empty list so downstream code can report N/A instead of guessing.
    """
    values: list[str] = []

    def walk(node: Any) -> None:
        if node is None:
            return
        if isinstance(node, str):
            text = node.strip()
            if text:
                values.append(text)
            return
        if isinstance(node, (int, float)):
            values.append(str(node))
            return
        if isinstance(node, list):
            for item in node:
                walk(item)
            return
        if isinstance(node, dict):
            if "value" in node:
                walk(node.get("value"))
                return
            for nested_key in ("display_value", "displayValue", "name"):
                if nested_key in node:
                    walk(node.get(nested_key))
                    return

    for key in keys:
        walk(attributes.get(key))
    # Preserve order while deduping repeated marketplace values.
    return list(dict.fromkeys(values))


def _extract_offers_metadata(payload: Any) -> tuple[Optional[int], Optional[str]]:
    """Best-effort extraction of (sellers_count, buy_box_owner) from offers payloads.

    Returns ``(None, None)`` when the payload doesn't expose this data.
    """
    if not payload:
        return None, None

    offers = None
    if isinstance(payload, dict):
        offers = payload.get("Offers") or payload.get("offers")
        if offers is None:
            summary = payload.get("Summary") or payload.get("summary") or {}
            total_offer = summary.get("TotalOfferCount") or summary.get("totalOfferCount")
            if total_offer is not None:
                return int(total_offer), None
    if not offers:
        return None, None

    sellers_count = len(offers)
    buy_box_owner = None
    for offer in offers:
        if not isinstance(offer, dict):
            continue
        is_buy_box = offer.get("IsBuyBoxWinner") or offer.get("isBuyBoxWinner")
        if is_buy_box:
            buy_box_owner = (
                offer.get("SellerId")
                or offer.get("sellerId")
                or offer.get("seller_name")
                or offer.get("sellerName")
            )
            if buy_box_owner:
                break
    return sellers_count, buy_box_owner


def _fetch_product_data(client, asin: str) -> dict:
    """Fetch product catalog details and competitive pricing for an ASIN."""
    snapshot = {"asin": asin}
    fetch_errors: list[str] = []

    def _fetch_catalog():
        api = client._catalog_api()
        response = api.get_catalog_item(
            asin=asin,
            marketplaceIds=client.marketplace.marketplace_id,
            includedData=["summaries", "salesRanks", "classifications", "attributes", "images"],
        )
        return response.payload

    catalog, catalog_error = _call_sp_api_with_single_retry(
        _fetch_catalog,
        asin=asin,
        operation="catalog",
    )
    if catalog_error:
        fetch_errors.append(f"catalog:{catalog_error}")
        if catalog_error == "forbidden":
            snapshot["catalog_unavailable_reason"] = "forbidden"
    if catalog:
        summaries = catalog.get("summaries", [])
        if summaries:
            summary = summaries[0]
            snapshot["title"] = summary.get("itemName")
            snapshot["brand"] = summary.get("brand")

        classifications = catalog.get("classifications", [])
        if classifications:
            classification = classifications[0]
            snapshot["category"] = (
                classification.get("displayName")
                or classification.get("classification", {}).get("displayName")
            )
            # Subcategory = last (most specific) node in the classification path.
            display_name = (
                classification.get("classification", {}).get("displayName")
                or classification.get("displayName")
            )
            snapshot["subcategory"] = display_name or snapshot.get("category")

        sales_ranks = catalog.get("salesRanks", [])
        if sales_ranks:
            for rank_list in sales_ranks:
                ranks = rank_list.get("ranks", [])
                for rank in ranks:
                    if rank.get("link") is None:
                        snapshot["bsr"] = rank.get("value")
                        break
                if "bsr" in snapshot:
                    break

        # Customer reviews (rating + review_count) live under attributes when
        # SP-API exposes them. Failure to find them must not invent a value.
        attributes = catalog.get("attributes") or {}
        rating, review_count = _extract_rating_and_reviews(attributes)
        if rating is not None:
            snapshot["rating"] = rating
        if review_count is not None:
            snapshot["review_count"] = review_count

        bullet_values = _extract_text_attribute_values(
            attributes,
            "bullet_point",
            "bulletPoints",
            "feature_bullets",
        )
        if bullet_values:
            snapshot["bullets"] = bullet_values
            snapshot["bullet_count"] = len(bullet_values)

        description_values = _extract_text_attribute_values(
            attributes,
            "product_description",
            "productDescription",
            "description",
        )
        if description_values:
            snapshot["description"] = "\n".join(description_values)

        generic_keywords = _extract_text_attribute_values(
            attributes,
            "generic_keyword",
            "genericKeywords",
            "search_terms",
        )
        if generic_keywords:
            snapshot["generic_keywords"] = generic_keywords

        # Image count from the images array (catalog may return marketplace-
        # specific image lists). Count distinct image entries across all
        # variants. ``images`` key shape: list of {"marketplaceId": ..., "images": [{"link": ...}, ...]}.
        images_payload = catalog.get("images") or []
        image_count = 0
        for entry in images_payload:
            if isinstance(entry, dict):
                items = entry.get("images") or []
                image_count = max(image_count, len(items))
        if image_count:
            snapshot["images_count"] = image_count

    price = None
    offers_meta = None
    if client.is_vendor:
        logger.debug(
            "Skipping pricing lookup for %s because Product Pricing API is seller-only",
            asin,
        )
    else:
        def _fetch_competitive_price():
            api = client._products_api()
            response = api.get_competitive_pricing_for_asins([asin])
            return client._extract_price_amount(response.payload)

        def _fetch_offers():
            api = client._products_api()
            response = api.get_item_offers(asin=asin, item_condition="New")
            return getattr(response, "payload", None)

        price, pricing_error = _call_sp_api_with_single_retry(
            _fetch_competitive_price,
            asin=asin,
            operation="pricing",
        )
        if pricing_error:
            fetch_errors.append(f"pricing:{pricing_error}")
            if pricing_error == "forbidden":
                snapshot["pricing_unavailable_reason"] = "forbidden"

        # Offers are fetched separately so a failure here (404, throttle)
        # cannot discard a price the competitive-pricing call already found.
        offers_payload, offers_error = _call_sp_api_with_single_retry(
            _fetch_offers,
            asin=asin,
            operation="offers",
        )
        if offers_error:
            fetch_errors.append(f"offers:{offers_error}")
        elif offers_payload:
            sellers_count, buy_box_owner = _extract_offers_metadata(offers_payload)
            offers_meta = {
                "sellers_count": sellers_count,
                "buy_box_owner": buy_box_owner,
                "offer_snapshot": client._extract_offer_snapshot(offers_payload),
            }
            if price is None:
                price = client._extract_price_amount(offers_payload)

    if price is None and catalog:
        price = client._extract_catalog_price_amount(catalog)
    if price is not None:
        snapshot["price"] = float(price)
    if offers_meta:
        if offers_meta.get("sellers_count") is not None:
            snapshot["sellers_count"] = int(offers_meta["sellers_count"])
            snapshot["offer_count"] = int(offers_meta["sellers_count"])
        if offers_meta.get("buy_box_owner"):
            snapshot["buy_box_owner"] = str(offers_meta["buy_box_owner"])
        if offers_meta.get("offer_snapshot"):
            snapshot["offer_snapshot"] = offers_meta["offer_snapshot"]

    # Status: prefer "active" if a price/offer was found, "inactive" if the
    # catalog returned data with no offers, otherwise "unknown".
    if snapshot.get("price") is not None or snapshot.get("sellers_count"):
        snapshot["status"] = "active"
    elif catalog and not snapshot.get("price"):
        snapshot["status"] = "inactive"
    else:
        snapshot["status"] = "unknown"

    if fetch_errors:
        snapshot["fetch_errors"] = fetch_errors

    return snapshot
