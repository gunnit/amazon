"""Market research service for competitive analysis."""
import asyncio
import logging
import time
from datetime import datetime
from typing import Any, Callable, List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
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

from app.models.market_research import MarketResearchReport
from app.models.amazon_account import AmazonAccount
from app.models.competitor import Competitor
from app.schemas.market_research import MarketResearchCreate

logger = logging.getLogger(__name__)

# How many competitors to auto-discover
AUTO_DISCOVER_COUNT = 8


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

    async def suggest_competitors(
        self, org_id: UUID, category: Optional[str] = None, marketplace: Optional[str] = None,
    ) -> List[Competitor]:
        """Suggest competitors from the existing competitors table."""
        query = select(Competitor).where(
            Competitor.organization_id == org_id,
            Competitor.is_tracking == True,
        )
        if marketplace:
            query = query.where(Competitor.marketplace == marketplace)
        query = query.limit(20)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    def get_comparison_matrix(self, report: MarketResearchReport) -> dict[str, Any]:
        """Build a dimension-by-dimension comparison matrix for a completed report."""
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
            )

            dimensions.append(dimension)

            if dimension["client_rank"] is not None and dimension["total_competitors"] > 1:
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
            "overall_score": round(overall_score / total_weight, 1) if total_weight else 0.0,
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
    ) -> dict[str, Any]:
        """Compute comparison stats for a single metric dimension."""
        client_value = cls._coerce_numeric(product_snapshot.get(field))

        competitor_values: list[tuple[dict[str, Any], float]] = []
        for competitor in competitor_data:
            numeric_value = cls._coerce_numeric(competitor.get(field))
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
                            raw = client.search_catalog_by_keyword(
                                search_kw, max_results=15
                            )
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
                            raw = client.search_catalog_by_keyword(
                                search_query, max_results=15
                            )
                            if not raw:
                                raise ValueError(
                                    f"No products found for '{search_query}'. "
                                    "Try a different search term."
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

                    # Fetch competitor data
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

                # Step 4: AI analysis
                if settings.ANTHROPIC_API_KEY:
                    await _set_progress("Generating AI insights...", 75)
                    from app.services.ai_analysis_service import AIAnalysisService
                    ai_service = AIAnalysisService(settings.ANTHROPIC_API_KEY)
                    analysis = ai_service.analyze(
                        product_data=product_snapshot,
                        competitor_data=comp_data,
                        category=source_category,
                        language=report.language,
                    )
                    report.ai_analysis = analysis

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
    """Auto-discover competitor ASINs via SP-API catalog search."""
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

    results = client.search_competitor_asins(
        keywords=search_query,
        source_asin=source_asin,
        source_brand=source_brand,
        max_results=max_results,
    )

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


def _fetch_product_data(client, asin: str) -> dict:
    """Fetch product catalog details and competitive pricing for an ASIN."""
    snapshot = {"asin": asin}
    fetch_errors: list[str] = []

    def _fetch_catalog():
        api = client._catalog_api()
        response = api.get_catalog_item(
            asin=asin,
            marketplaceIds=client.marketplace.marketplace_id,
            includedData=["summaries", "salesRanks", "classifications", "attributes"],
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

    def _fetch_price():
        if client.is_vendor:
            logger.debug(
                "Skipping pricing lookup for %s because Product Pricing API is seller-only",
                asin,
            )
            return None

        api = client._products_api()
        response = api.get_competitive_pricing_for_asins([asin])
        price_value = client._extract_price_amount(response.payload)
        if price_value is not None:
            return price_value

        offers_response = api.get_item_offers(asin=asin, item_condition="New")
        return client._extract_price_amount(offers_response.payload)

    price, pricing_error = _call_sp_api_with_single_retry(
        _fetch_price,
        asin=asin,
        operation="pricing",
    )
    if pricing_error:
        fetch_errors.append(f"pricing:{pricing_error}")
        if pricing_error == "forbidden":
            snapshot["pricing_unavailable_reason"] = "forbidden"
    if price is None and catalog:
        price = client._extract_catalog_price_amount(catalog)
    if price is not None:
        snapshot["price"] = float(price)

    if fetch_errors:
        snapshot["fetch_errors"] = fetch_errors

    return snapshot
