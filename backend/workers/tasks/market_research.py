"""Market research Celery tasks — automated competitor discovery + AI analysis."""
import logging
import time
from datetime import datetime
from uuid import UUID
from typing import List, Optional

from workers.celery_app import celery_app
from workers.tasks.extraction import run_async

logger = logging.getLogger(__name__)

# How many competitors to auto-discover
AUTO_DISCOVER_COUNT = 8


@celery_app.task(bind=True, max_retries=2)
def process_market_research(self, report_id: str, extra_asins: Optional[List[str]] = None):
    """Process a market research report.

    1. Fetch source product details from SP-API
    2. Auto-discover competitors via catalog search (keywords from title)
    3. Merge with any manually provided ASINs
    4. Fetch pricing/details for each competitor
    5. Run AI analysis via Claude API
    """
    from app.db.session import AsyncSessionLocal
    from app.models.market_research import MarketResearchReport
    from app.models.amazon_account import AmazonAccount
    from app.core.amazon.sp_api_client import SPAPIClient, resolve_marketplace
    from app.core.amazon.credentials import resolve_credentials
    from app.config import settings
    from sqlalchemy import select

    async def _process():
        async with AsyncSessionLocal() as db:
            # Load report
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
                # Set processing
                report.status = "processing"
                await db.flush()

                # Load account + org for credentials
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

                # ── Step 1: Fetch source product ──
                product_snapshot = _fetch_product_data(client, report.source_asin)
                report.product_snapshot = product_snapshot

                source_title = product_snapshot.get("title", "")
                source_brand = product_snapshot.get("brand")
                source_category = product_snapshot.get("category")

                # Update report title now that we know the product name
                if source_title:
                    report.title = f"Market Research: {source_title[:80]}"

                # ── Step 2: Auto-discover competitors ──
                discovered_asins = _discover_competitors(
                    client,
                    source_asin=report.source_asin,
                    source_title=source_title,
                    source_brand=source_brand,
                    max_results=AUTO_DISCOVER_COUNT,
                )

                # Merge with manually provided ASINs (dedup, exclude source)
                all_competitor_asins = list(dict.fromkeys(
                    discovered_asins + (extra_asins or [])
                ))
                all_competitor_asins = [
                    a for a in all_competitor_asins
                    if a != report.source_asin
                ][:10]  # cap at 10

                logger.info(
                    f"Report {report_id}: discovered {len(discovered_asins)} competitors, "
                    f"{len(extra_asins or [])} manual, {len(all_competitor_asins)} total"
                )

                # ── Step 3: Fetch data for each competitor ──
                comp_data = []
                for comp_asin in all_competitor_asins:
                    comp_snapshot = _fetch_product_data(client, comp_asin)
                    comp_data.append(comp_snapshot)
                    time.sleep(0.5)  # gentle throttle between calls

                report.competitor_data = comp_data

                # ── Step 4: AI analysis ──
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
                raise

    try:
        run_async(_process())
    except Exception as e:
        logger.error(f"Market research task failed for {report_id}: {e}")
        raise self.retry(exc=e, countdown=60)


def _discover_competitors(
    client,
    source_asin: str,
    source_title: str,
    source_brand: Optional[str],
    max_results: int = 8,
) -> List[str]:
    """Auto-discover competitor ASINs via SP-API catalog search.

    Strategy:
    1. Extract meaningful keywords from the product title
    2. Search the catalog excluding the source product and same brand
    3. Return up to max_results competitor ASINs
    """
    if not source_title:
        logger.warning(f"No title for {source_asin}, cannot discover competitors")
        return []

    # Extract search keywords: take first ~5 meaningful words from title
    # Strip common noise words and brand name
    noise_words = {
        "the", "a", "an", "for", "and", "or", "with", "in", "of", "to",
        "per", "con", "e", "di", "da", "il", "la", "le", "un", "una",
        "-", "&", "|", "/", ",", ".", "(", ")", "[", "]",
    }
    words = source_title.split()
    keywords = []
    for w in words:
        clean = w.strip("()[].,;:-–—\"'").lower()
        if len(clean) < 2:
            continue
        if clean in noise_words:
            continue
        # Skip brand name in keywords to find competitors, not own products
        if source_brand and clean == source_brand.lower():
            continue
        keywords.append(w.strip("()[].,;:-–—\"'"))
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

    # Catalog details
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

    # Competitive pricing
    price = client.get_competitive_pricing(asin)
    if price is not None:
        snapshot["price"] = float(price)

    return snapshot
