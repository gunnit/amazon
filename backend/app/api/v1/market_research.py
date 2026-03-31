"""Market research endpoints."""
import logging
import time
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, HTTPException, status

from app.api.deps import CurrentUser, CurrentOrganization, DbSession
from app.schemas.market_research import (
    MarketResearchCreate,
    MarketResearchResponse,
    MarketResearchListItem,
    MarketSearchRequest,
    MarketSearchResult,
    MarketSearchResponse,
    ProductSnapshot,
    CompetitorSnapshot,
    AIAnalysis,
    AIRecommendation,
)
from app.services.market_research_service import MarketResearchService, process_report_background
from app.config import settings
from workers.tasks.market_research import process_market_research

logger = logging.getLogger(__name__)

router = APIRouter()


def _report_to_response(report) -> MarketResearchResponse:
    """Convert a MarketResearchReport model to response schema."""
    product_snapshot = None
    if report.product_snapshot:
        product_snapshot = ProductSnapshot(**report.product_snapshot)

    competitor_data = None
    if report.competitor_data:
        competitor_data = [CompetitorSnapshot(**c) for c in report.competitor_data]

    ai_analysis = None
    if report.ai_analysis:
        recs = [
            AIRecommendation(**r) for r in report.ai_analysis.get("recommendations", [])
        ]
        ai_analysis = AIAnalysis(
            strengths=report.ai_analysis.get("strengths", []),
            weaknesses=report.ai_analysis.get("weaknesses", []),
            recommendations=recs,
            overall_score=report.ai_analysis.get("overall_score", 50),
            summary=report.ai_analysis.get("summary", ""),
        )

    return MarketResearchResponse(
        id=str(report.id),
        organization_id=str(report.organization_id),
        account_id=str(report.account_id),
        source_asin=report.source_asin,
        marketplace=report.marketplace,
        language=report.language,
        title=report.title,
        status=report.status,
        progress_step=report.progress_step,
        progress_pct=report.progress_pct or 0,
        error_message=report.error_message,
        product_snapshot=product_snapshot,
        competitor_data=competitor_data,
        ai_analysis=ai_analysis,
        created_at=report.created_at.isoformat() if report.created_at else "",
        completed_at=report.completed_at.isoformat() if report.completed_at else None,
    )


@router.post("/generate", response_model=MarketResearchResponse)
async def generate_report(
    data: MarketResearchCreate,
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
):
    """Create a new market research report.

    Competitors are discovered automatically via SP-API catalog search.
    Optionally, extra_competitor_asins can be provided to include specific ASINs.
    """
    if data.extra_competitor_asins and len(data.extra_competitor_asins) > settings.MARKET_RESEARCH_MAX_COMPETITORS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Maximum {settings.MARKET_RESEARCH_MAX_COMPETITORS} extra competitors allowed",
        )

    service = MarketResearchService(db)
    try:
        report = await service.create_report(
            org_id=organization.id,
            user_id=current_user.id,
            data=data,
        )
        await db.commit()
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )

    task_kwargs = {
        "extra_asins": data.extra_competitor_asins or [],
        "market_competitor_asins": data.market_competitor_asins or [],
        "search_query": data.search_query,
        "search_type": data.search_type,
    }

    try:
        process_market_research.delay(str(report.id), **task_kwargs)
    except Exception:
        logger.exception(
            "Failed to enqueue market research %s on Celery; falling back to in-process thread",
            report.id,
        )
        import threading

        thread = threading.Thread(
            target=process_report_background,
            args=(str(report.id),),
            kwargs=task_kwargs,
            daemon=True,
        )
        thread.start()

    return _report_to_response(report)


@router.get("", response_model=List[MarketResearchListItem])
async def list_reports(
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
    limit: int = 20,
    offset: int = 0,
):
    """List market research reports for the organization."""
    service = MarketResearchService(db)
    reports = await service.list_reports(organization.id, limit, offset)

    return [
        MarketResearchListItem(
            id=str(r.id),
            title=r.title,
            source_asin=r.source_asin,
            status=r.status,
            language=r.language,
            created_at=r.created_at.isoformat() if r.created_at else "",
            competitor_count=len(r.competitor_data) if r.competitor_data else 0,
        )
        for r in reports
    ]


@router.get("/{report_id}", response_model=MarketResearchResponse)
async def get_report(
    report_id: UUID,
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
):
    """Get a market research report by ID."""
    service = MarketResearchService(db)
    report = await service.get_report(report_id, organization.id)

    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report not found",
        )

    return _report_to_response(report)


@router.delete("/{report_id}")
async def delete_report(
    report_id: UUID,
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
):
    """Delete a market research report."""
    service = MarketResearchService(db)
    deleted = await service.delete_report(report_id, organization.id)

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report not found",
        )

    await db.commit()
    return {"status": "deleted"}


@router.post("/market-search", response_model=MarketSearchResponse)
async def market_search(
    data: MarketSearchRequest,
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
):
    """Search the market by keyword, brand, or ASIN (Market Tracker 360).

    Returns a list of products found on Amazon matching the search query,
    with their metrics (price, BSR, reviews, rating).
    """
    from sqlalchemy import select as sa_select
    from app.models.amazon_account import AmazonAccount
    from app.core.amazon.sp_api_client import SPAPIClient, resolve_marketplace
    from app.core.amazon.credentials import resolve_credentials
    from app.models.user import Organization

    # Verify account belongs to org
    result = await db.execute(
        sa_select(AmazonAccount).where(
            AmazonAccount.id == UUID(data.account_id),
            AmazonAccount.organization_id == organization.id,
        )
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account not found or does not belong to organization",
        )

    # Load org for credential resolution
    org_result = await db.execute(
        sa_select(Organization).where(Organization.id == organization.id)
    )
    org = org_result.scalar_one_or_none()

    try:
        credentials = resolve_credentials(account, org)
        marketplace = resolve_marketplace(account.marketplace_country)
        client = SPAPIClient(
            credentials, marketplace,
            account_type=account.account_type.value,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to connect to Amazon SP-API: {e}",
        )

    # Perform the search based on type
    from app.core.exceptions import AmazonAPIError

    try:
        if data.search_type == "asin":
            # For ASIN search: get the specific product + discover competitors
            from app.services.market_research_service import _fetch_product_data
            product = _fetch_product_data(client, data.query.upper())
            results = [product]

            # Also discover related products using the product title
            title = product.get("title", "")
            if title:
                related = client.search_catalog_by_keyword(title[:80], max_results=19)
                for item in related:
                    if item["asin"] != data.query.upper():
                        # Enrich with pricing
                        price = client.get_competitive_pricing(item["asin"])
                        if price is not None:
                            item["price"] = float(price)
                        results.append(item)
                        time.sleep(0.3)
                        if len(results) >= 20:
                            break
        else:
            # keyword or brand search
            raw_results = client.search_catalog_by_keyword(data.query, max_results=20)

            # Enrich each result with pricing
            results = []
            for item in raw_results:
                price = client.get_competitive_pricing(item["asin"])
                if price is not None:
                    item["price"] = float(price)
                results.append(item)
                time.sleep(0.3)
    except AmazonAPIError as e:
        error_code = getattr(e, "error_code", "UNKNOWN")
        if error_code == "THROTTLED":
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Amazon API rate limited. Please try again in a few seconds.",
            )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Amazon API error: {e}",
        )
    except Exception as e:
        logger.exception(f"Unexpected error in market search: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search failed: {str(e)[:200]}",
        )

    search_results = [
        MarketSearchResult(
            asin=r.get("asin", ""),
            title=r.get("title"),
            brand=r.get("brand"),
            category=r.get("category"),
            price=r.get("price"),
            bsr=r.get("bsr"),
            review_count=r.get("review_count"),
            rating=r.get("rating"),
        )
        for r in results
    ]

    return MarketSearchResponse(
        results=search_results,
        total_found=len(search_results),
        query=data.query,
        search_type=data.search_type,
    )


@router.get("/competitors/suggest")
async def suggest_competitors(
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
    category: Optional[str] = None,
    marketplace: Optional[str] = None,
):
    """Suggest competitors from the tracked competitors table."""
    service = MarketResearchService(db)
    competitors = await service.suggest_competitors(
        organization.id, category, marketplace,
    )

    return [
        {
            "asin": c.asin,
            "title": c.title,
            "brand": c.brand,
            "marketplace": c.marketplace,
            "current_price": float(c.current_price) if c.current_price else None,
            "current_bsr": c.current_bsr,
            "review_count": c.review_count,
            "rating": float(c.rating) if c.rating else None,
        }
        for c in competitors
    ]
