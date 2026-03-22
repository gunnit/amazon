"""Reports and data endpoints."""
from typing import List, Optional
from datetime import date, timedelta
from uuid import UUID
from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select, func, Date, cast

from app.api.deps import CurrentUser, CurrentOrganization, DbSession
from app.models.amazon_account import AmazonAccount
from app.models.sales_data import SalesData
from app.services.data_extraction import DAILY_TOTAL_ASIN
from app.models.inventory import InventoryData
from app.models.advertising import AdvertisingCampaign, AdvertisingMetrics
from app.schemas.report import (
    SalesDataResponse, SalesDataAggregated,
    InventoryDataResponse, AdvertisingMetricsResponse,
    ReportScheduleCreate, ReportScheduleResponse
)

router = APIRouter()


@router.get("/sales", response_model=List[SalesDataResponse])
async def get_sales_data(
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
    start_date: date = Query(default=date.today() - timedelta(days=30)),
    end_date: date = Query(default=date.today()),
    account_ids: Optional[List[UUID]] = Query(default=None),
    asins: Optional[List[str]] = Query(default=None),
    limit: int = Query(default=1000, le=10000),
    offset: int = Query(default=0),
):
    """Get sales data for specified date range."""
    # Get organization's accounts
    accounts_query = select(AmazonAccount.id).where(
        AmazonAccount.organization_id == organization.id
    )
    if account_ids:
        accounts_query = accounts_query.where(AmazonAccount.id.in_(account_ids))

    query = (
        select(SalesData)
        .where(
            SalesData.account_id.in_(accounts_query),
            SalesData.asin != DAILY_TOTAL_ASIN,
            SalesData.date >= start_date,
            SalesData.date <= end_date,
        )
        .order_by(SalesData.date.desc(), SalesData.asin)
        .limit(limit)
        .offset(offset)
    )

    if asins:
        query = query.where(SalesData.asin.in_(asins))

    result = await db.execute(query)
    return result.scalars().all()


@router.get("/sales/aggregated", response_model=List[SalesDataAggregated])
async def get_sales_aggregated(
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
    start_date: date = Query(default=date.today() - timedelta(days=30)),
    end_date: date = Query(default=date.today()),
    account_ids: Optional[List[UUID]] = Query(default=None),
    group_by: str = Query(default="day", regex="^(day|week|month)$"),
):
    """Get aggregated sales data."""
    accounts_query = select(AmazonAccount.id).where(
        AmazonAccount.organization_id == organization.id
    )
    if account_ids:
        accounts_query = accounts_query.where(AmazonAccount.id.in_(account_ids))

    if group_by == "week":
        period_expr = cast(func.date_trunc("week", SalesData.date), Date)
    elif group_by == "month":
        period_expr = cast(func.date_trunc("month", SalesData.date), Date)
    else:
        period_expr = SalesData.date

    query = (
        select(
            period_expr.label("period_date"),
            func.sum(SalesData.units_ordered).label("total_units"),
            func.sum(SalesData.ordered_product_sales).label("total_sales"),
            func.sum(SalesData.total_order_items).label("total_orders"),
            SalesData.currency,
        )
        .where(
            SalesData.account_id.in_(accounts_query),
            SalesData.asin == DAILY_TOTAL_ASIN,
            SalesData.date >= start_date,
            SalesData.date <= end_date,
        )
        .group_by(period_expr, SalesData.currency)
        .order_by(period_expr)
    )

    result = await db.execute(query)
    rows = result.all()

    return [
        SalesDataAggregated(
            date=row.period_date,
            total_units=row.total_units or 0,
            total_sales=row.total_sales or 0,
            total_orders=row.total_orders or 0,
            currency=row.currency or "EUR",
        )
        for row in rows
    ]


@router.get("/inventory", response_model=List[InventoryDataResponse])
async def get_inventory_data(
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
    snapshot_date: Optional[date] = Query(default=None),
    account_ids: Optional[List[UUID]] = Query(default=None),
    asins: Optional[List[str]] = Query(default=None),
    low_stock_only: bool = Query(default=False),
    limit: int = Query(default=1000, le=10000),
):
    """Get inventory data."""
    accounts_query = select(AmazonAccount.id).where(
        AmazonAccount.organization_id == organization.id
    )
    if account_ids:
        accounts_query = accounts_query.where(AmazonAccount.id.in_(account_ids))

    # Default to latest snapshot
    if not snapshot_date:
        max_date_query = select(func.max(InventoryData.snapshot_date)).where(
            InventoryData.account_id.in_(accounts_query)
        )
        result = await db.execute(max_date_query)
        snapshot_date = result.scalar() or date.today()

    query = (
        select(InventoryData)
        .where(
            InventoryData.account_id.in_(accounts_query),
            InventoryData.snapshot_date == snapshot_date,
        )
        .limit(limit)
    )

    if asins:
        query = query.where(InventoryData.asin.in_(asins))

    if low_stock_only:
        query = query.where(InventoryData.afn_fulfillable_quantity < 10)

    result = await db.execute(query)
    return result.scalars().all()


@router.get("/advertising", response_model=List[AdvertisingMetricsResponse])
async def get_advertising_data(
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
    start_date: date = Query(default=date.today() - timedelta(days=30)),
    end_date: date = Query(default=date.today()),
    account_ids: Optional[List[UUID]] = Query(default=None),
    campaign_types: Optional[List[str]] = Query(default=None),
    limit: int = Query(default=1000, le=10000),
):
    """Get advertising performance data."""
    accounts_query = select(AmazonAccount.id).where(
        AmazonAccount.organization_id == organization.id
    )
    if account_ids:
        accounts_query = accounts_query.where(AmazonAccount.id.in_(account_ids))

    campaigns_query = select(AdvertisingCampaign.id).where(
        AdvertisingCampaign.account_id.in_(accounts_query)
    )
    if campaign_types:
        campaigns_query = campaigns_query.where(
            AdvertisingCampaign.campaign_type.in_(campaign_types)
        )

    query = (
        select(
            AdvertisingMetrics,
            AdvertisingCampaign.campaign_name,
            AdvertisingCampaign.campaign_type,
        )
        .join(AdvertisingCampaign)
        .where(
            AdvertisingMetrics.campaign_id.in_(campaigns_query),
            AdvertisingMetrics.date >= start_date,
            AdvertisingMetrics.date <= end_date,
        )
        .order_by(AdvertisingMetrics.date.desc())
        .limit(limit)
    )

    result = await db.execute(query)
    rows = result.all()

    return [
        AdvertisingMetricsResponse(
            id=row.AdvertisingMetrics.id,
            campaign_id=row.AdvertisingMetrics.campaign_id,
            campaign_name=row.campaign_name or "",
            campaign_type=row.campaign_type or "",
            date=row.AdvertisingMetrics.date,
            impressions=row.AdvertisingMetrics.impressions,
            clicks=row.AdvertisingMetrics.clicks,
            cost=row.AdvertisingMetrics.cost,
            attributed_sales_7d=row.AdvertisingMetrics.attributed_sales_7d,
            attributed_units_ordered_7d=row.AdvertisingMetrics.attributed_units_ordered_7d,
            ctr=row.AdvertisingMetrics.ctr,
            cpc=row.AdvertisingMetrics.cpc,
            acos=row.AdvertisingMetrics.acos,
            roas=row.AdvertisingMetrics.roas,
        )
        for row in rows
    ]


@router.post("/schedule", response_model=ReportScheduleResponse)
async def create_report_schedule(
    schedule_in: ReportScheduleCreate,
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
):
    """Create a scheduled report."""
    # Verify accounts belong to organization
    result = await db.execute(
        select(AmazonAccount)
        .where(
            AmazonAccount.id.in_(schedule_in.account_ids),
            AmazonAccount.organization_id == organization.id
        )
    )
    accounts = result.scalars().all()

    if len(accounts) != len(schedule_in.account_ids):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="One or more account IDs are invalid"
        )

    # Create sync jobs for each account
    from app.models.sync_job import SyncJob

    jobs = []
    for account in accounts:
        job = SyncJob(
            account_id=account.id,
            job_type=schedule_in.report_type,
            schedule_cron=schedule_in.schedule_cron,
            is_enabled=True,
        )
        db.add(job)
        jobs.append(job)

    await db.flush()

    if jobs:
        await db.refresh(jobs[0])
        return jobs[0]

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Failed to create report schedule"
    )
