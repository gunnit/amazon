"""Market research service for competitive analysis."""
import logging
from typing import List, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.market_research import MarketResearchReport
from app.models.amazon_account import AmazonAccount
from app.models.competitor import Competitor
from app.schemas.market_research import MarketResearchCreate

logger = logging.getLogger(__name__)


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
        """Create a new market research report and dispatch Celery task.

        The Celery task will automatically discover competitors via SP-API
        catalog search based on the source product's title/category.
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

        # Dispatch Celery task — competitor discovery happens inside the task
        from workers.tasks.market_research import process_market_research
        process_market_research.delay(
            str(report.id),
            data.extra_competitor_asins or [],
        )

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
