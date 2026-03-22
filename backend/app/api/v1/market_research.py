"""Market research endpoints."""
import logging
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, HTTPException, status

from app.api.deps import CurrentUser, CurrentOrganization, DbSession
from app.schemas.market_research import (
    MarketResearchCreate,
    MarketResearchResponse,
    MarketResearchListItem,
    ProductSnapshot,
    CompetitorSnapshot,
    AIAnalysis,
    AIRecommendation,
)
from app.services.market_research_service import MarketResearchService
from app.config import settings

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
