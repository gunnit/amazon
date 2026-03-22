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

        The background processing is triggered separately by the API endpoint.
        """
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

        title = f"Market Research: {data.source_asin}"

        report = MarketResearchReport(
            organization_id=org_id,
            created_by_id=user_id,
            account_id=account.id,
            source_asin=data.source_asin,
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


def process_report_background(report_id: str, extra_asins: Optional[List[str]] = None):
    """Process a market research report synchronously in a background thread.

    This replaces the Celery task for deployments without Redis.
    Runs: SP-API fetch + auto-discover competitors + AI analysis.
    """
    from app.db.session import AsyncSessionLocal
    from app.models.market_research import MarketResearchReport
    from app.models.amazon_account import AmazonAccount
    from app.core.amazon.sp_api_client import SPAPIClient, resolve_marketplace
    from app.core.amazon.credentials import resolve_credentials
    from app.config import settings

    async def _process():
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(MarketResearchReport).where(
                    MarketResearchReport.id == UUID(report_id)
                )
            )
            report = result.scalar_one_or_none()
            if not report:
                logger.error(f"Market research report {report_id} not found")
                return

            try:
                report.status = "processing"
                await db.flush()

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

                # Step 1: Fetch source product
                product_snapshot = _fetch_product_data(client, report.source_asin)
                report.product_snapshot = product_snapshot

                source_title = product_snapshot.get("title", "")
                source_brand = product_snapshot.get("brand")
                source_category = product_snapshot.get("category")

                if source_title:
                    report.title = f"Market Research: {source_title[:80]}"

                # Step 2: Auto-discover competitors
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
                    f"Report {report_id}: discovered {len(discovered_asins)} competitors, "
                    f"{len(extra_asins or [])} manual, {len(all_competitor_asins)} total"
                )

                # Step 3: Fetch data for each competitor
                comp_data = []
                for comp_asin in all_competitor_asins:
                    comp_snapshot = _fetch_product_data(client, comp_asin)
                    comp_data.append(comp_snapshot)
                    time.sleep(0.5)

                report.competitor_data = comp_data

                # Step 4: AI analysis
                if settings.ANTHROPIC_API_KEY:
                    from app.services.ai_analysis_service import AIAnalysisService
                    ai_service = AIAnalysisService(settings.ANTHROPIC_API_KEY)
                    analysis = ai_service.analyze(
                        product_data=product_snapshot,
                        competitor_data=comp_data,
                        category=source_category,
                        language=report.language,
                    )
                    report.ai_analysis = analysis

                report.status = "completed"
                report.completed_at = datetime.utcnow()
                await db.commit()
                logger.info(
                    f"Market research {report_id} completed: "
                    f"{len(comp_data)} competitors analyzed"
                )

            except Exception as e:
                report.status = "failed"
                report.error_message = str(e)[:500]
                await db.commit()
                logger.exception(f"Market research {report_id} failed: {e}")

    # Run async processing in a new event loop (this runs in a thread)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_process())
    finally:
        try:
            from app.db.session import engine
            loop.run_until_complete(engine.dispose())
        except Exception:
            pass
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
