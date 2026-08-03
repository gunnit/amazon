"""Competitor tracking endpoints (US-2.5 / US-4.2)."""
import logging
import re
from datetime import date, timedelta
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import delete, func, select

from app.api.deps import CurrentUser, CurrentOrganization, DbSession
from app.models.amazon_account import AmazonAccount
from app.models.competitor import Competitor, CompetitorHistory
from app.schemas.competitor import (
    CompetitorCreate,
    CompetitorHistoryPoint,
    CompetitorHistoryResponse,
    CompetitorResponse,
)
from app.services.competitor_tracking_service import CompetitorTrackingService

logger = logging.getLogger(__name__)

router = APIRouter()

ASIN_RE = re.compile(r"^[A-Z0-9]{10}$")


def _to_response(competitor: Competitor, last_snapshot_date=None) -> CompetitorResponse:
    return CompetitorResponse(
        id=str(competitor.id),
        asin=competitor.asin,
        marketplace=competitor.marketplace,
        title=competitor.title,
        brand=competitor.brand,
        current_price=float(competitor.current_price) if competitor.current_price is not None else None,
        current_bsr=competitor.current_bsr,
        review_count=competitor.review_count,
        rating=float(competitor.rating) if competitor.rating is not None else None,
        is_tracking=bool(competitor.is_tracking),
        created_at=competitor.created_at.isoformat() if competitor.created_at else "",
        last_snapshot_date=last_snapshot_date.isoformat() if last_snapshot_date else None,
    )


async def _get_account(db, organization_id: UUID, account_id: str) -> AmazonAccount:
    try:
        account_uuid = UUID(account_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid account_id",
        )
    result = await db.execute(
        select(AmazonAccount).where(
            AmazonAccount.id == account_uuid,
            AmazonAccount.organization_id == organization_id,
        )
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account not found or does not belong to organization",
        )
    return account


@router.get("", response_model=List[CompetitorResponse])
async def list_competitors(
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
):
    """List all tracked competitors with their latest known metrics."""
    last_dates = (
        select(
            CompetitorHistory.competitor_id,
            func.max(CompetitorHistory.date).label("last_date"),
        )
        .group_by(CompetitorHistory.competitor_id)
        .subquery()
    )
    result = await db.execute(
        select(Competitor, last_dates.c.last_date)
        .outerjoin(last_dates, last_dates.c.competitor_id == Competitor.id)
        .where(
            Competitor.organization_id == organization.id,
            Competitor.is_tracking.is_(True),
        )
        .order_by(Competitor.created_at)
    )
    return [_to_response(competitor, last_date) for competitor, last_date in result.all()]


@router.post("", response_model=CompetitorResponse, status_code=status.HTTP_201_CREATED)
async def add_competitor(
    data: CompetitorCreate,
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
):
    """Track a new competitor ASIN and fetch its first snapshot immediately."""
    asin = data.asin.strip().upper()
    if not ASIN_RE.match(asin):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid ASIN format",
        )

    account = await _get_account(db, organization.id, data.account_id)
    marketplace = (account.marketplace_country or "IT").upper()

    existing = await db.execute(
        select(Competitor).where(
            Competitor.organization_id == organization.id,
            Competitor.asin == asin,
            Competitor.marketplace == marketplace,
        )
    )
    competitor = existing.scalar_one_or_none()
    if competitor is not None:
        if competitor.is_tracking:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Competitor is already tracked",
            )
        competitor.is_tracking = True
    else:
        competitor = Competitor(
            organization_id=organization.id,
            asin=asin,
            marketplace=marketplace,
        )
        db.add(competitor)
        await db.flush()

    # First snapshot inline so the user sees data right away. A fetch failure
    # still keeps the competitor tracked — the daily job retries tomorrow.
    service = CompetitorTrackingService(db)
    try:
        from app.services.data_extraction import DataExtractionService

        org = await DataExtractionService(db)._load_organization(account)
        client = service._create_sp_api_client(account, org)
        await service.snapshot_competitor(client, competitor, emit_alerts=False)
        last_snapshot_date = date.today()
    except Exception as exc:
        logger.warning("Initial competitor snapshot failed for %s: %s", asin, exc)
        last_snapshot_date = None

    await db.commit()
    await db.refresh(competitor)
    return _to_response(competitor, last_snapshot_date)


@router.delete("/{competitor_id}")
async def delete_competitor(
    competitor_id: UUID,
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
):
    """Stop tracking a competitor and remove its history."""
    result = await db.execute(
        select(Competitor).where(
            Competitor.id == competitor_id,
            Competitor.organization_id == organization.id,
        )
    )
    competitor = result.scalar_one_or_none()
    if not competitor:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Competitor not found")
    # Core delete: the FK cascade removes history without the ORM lazy-loading
    # the collection (which would raise MissingGreenlet on an async session).
    await db.execute(delete(Competitor).where(Competitor.id == competitor.id))
    await db.commit()
    return {"status": "deleted"}


@router.get("/{competitor_id}/history", response_model=CompetitorHistoryResponse)
async def get_competitor_history(
    competitor_id: UUID,
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
    days: int = Query(default=90, ge=1, le=365),
):
    """Daily price/BSR/reviews/rating history for one tracked competitor."""
    result = await db.execute(
        select(Competitor).where(
            Competitor.id == competitor_id,
            Competitor.organization_id == organization.id,
        )
    )
    competitor = result.scalar_one_or_none()
    if not competitor:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Competitor not found")

    rows = await db.execute(
        select(CompetitorHistory)
        .where(
            CompetitorHistory.competitor_id == competitor.id,
            CompetitorHistory.date >= date.today() - timedelta(days=days),
        )
        .order_by(CompetitorHistory.date)
    )
    points = [
        CompetitorHistoryPoint(
            date=row.date.isoformat(),
            price=float(row.price) if row.price is not None else None,
            bsr=row.bsr,
            review_count=row.review_count,
            rating=float(row.rating) if row.rating is not None else None,
        )
        for row in rows.scalars().all()
    ]
    return CompetitorHistoryResponse(
        competitor_id=str(competitor.id),
        asin=competitor.asin,
        points=points,
    )
