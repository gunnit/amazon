"""Market research service for competitive analysis."""
import asyncio
import logging
import time
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

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


def _fetch_product_data(client, asin: str) -> dict:
    """Fetch product catalog details and competitive pricing for an ASIN."""
    snapshot = {"asin": asin}

    catalog = client.get_catalog_item_details(asin)
    if catalog:
        summaries = catalog.get("summaries", [])
        if summaries:
            summary = summaries[0]
            snapshot["title"] = summary.get("itemName")
            snapshot["brand"] = summary.get("brand")

        classifications = catalog.get("classifications", [])
        if classifications:
            snapshot["category"] = classifications[0].get("displayName")

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

    price = client.get_competitive_pricing(asin)
    if price is not None:
        snapshot["price"] = float(price)

    return snapshot
