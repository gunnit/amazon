"""Brand Pulse endpoint — a rolling brand-intelligence snapshot."""
from datetime import date
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from app.api.deps import CurrentOrganization, CurrentUser, DbSession
from app.models.amazon_account import AmazonAccount
from app.schemas.brand_pulse import PulseResponse
from app.services.brand_pulse_service import BrandPulseService

router = APIRouter()


@router.get("", response_model=PulseResponse)
async def get_brand_pulse(
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
    account_ids: Optional[List[UUID]] = Query(default=None),
    window_days: int = Query(default=30, ge=7, le=90),
    end_date: Optional[date] = Query(default=None),
    language: str = Query(default="en"),
):
    """Rolling brand-intelligence snapshot: sales overview, top/declining ASINs
    and advertising (ACOS/TACOS) for the last ``window_days`` vs the preceding
    period. Advertising degrades gracefully when no ad data covers the window."""
    stmt = select(AmazonAccount.id).where(
        AmazonAccount.organization_id == organization.id
    )
    if account_ids:
        stmt = stmt.where(AmazonAccount.id.in_(account_ids))
    resolved = list((await db.execute(stmt)).scalars().all())
    if account_ids and set(account_ids) - set(resolved):
        raise HTTPException(status_code=404, detail="Account not found")

    service = BrandPulseService(db)
    return await service.build_pulse(
        resolved,
        end_date=end_date or date.today(),
        window_days=window_days,
        language=language,
    )
