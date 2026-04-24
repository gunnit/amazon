"""Reports and data endpoints."""
from typing import List, Optional
from datetime import date, datetime, time as dt_time, timedelta, timezone
from uuid import UUID
from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select, func, Date, cast
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUser, CurrentOrganization, DbSession
from app.models.amazon_account import AmazonAccount
from app.models.order import Order, OrderItem
from app.models.scheduled_report import ScheduledReport
from app.models.sales_data import SalesData
from app.services.data_extraction import DAILY_TOTAL_ASIN
from app.models.inventory import InventoryData
from app.models.advertising import AdvertisingCampaign, AdvertisingMetrics
from app.schemas.report import (
    SalesDataResponse, SalesDataAggregated,
    OrderListResponse, OrderResponse,
    InventoryDataResponse, AdvertisingMetricsResponse,
    ScheduledReportCreate, ScheduledReportResponse,
    ScheduledReportRunResponse, ScheduledReportUpdate,
)
from app.services.scheduled_report_service import (
    ScheduledReportService,
    enqueue_scheduled_run_processing,
    scheduled_report_run_to_response,
    scheduled_report_to_response,
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
    group_by: str = Query(default="day", pattern="^(day|week|month)$"),
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


@router.get("/orders", response_model=OrderListResponse)
async def get_orders_report(
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
    start_date: date = Query(default=date.today() - timedelta(days=30)),
    end_date: date = Query(default=date.today()),
    account_id: Optional[UUID] = Query(default=None),
    order_status: Optional[str] = Query(default=None),
    asin: Optional[str] = Query(default=None, min_length=1, max_length=20),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    """Get persisted order-level data with filters and pagination."""
    if start_date > end_date:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="start_date must be on or before end_date",
        )

    accounts_query = select(AmazonAccount.id).where(
        AmazonAccount.organization_id == organization.id
    )
    if account_id:
        accounts_query = accounts_query.where(AmazonAccount.id == account_id)

    start_datetime = datetime.combine(start_date, dt_time.min).replace(tzinfo=timezone.utc)
    end_datetime = datetime.combine(end_date + timedelta(days=1), dt_time.min).replace(tzinfo=timezone.utc)

    filters = [
        Order.account_id.in_(accounts_query),
        Order.purchase_date >= start_datetime,
        Order.purchase_date < end_datetime,
    ]
    if order_status:
        filters.append(Order.order_status == order_status)

    items_query = select(Order).options(selectinload(Order.items)).where(*filters)
    count_query = select(func.count(Order.id)).where(*filters)

    if asin:
        items_query = items_query.join(OrderItem).where(OrderItem.asin == asin).distinct()
        count_query = (
            select(func.count(func.distinct(Order.id)))
            .select_from(Order)
            .join(OrderItem)
            .where(*filters, OrderItem.asin == asin)
        )

    items_query = (
        items_query
        .order_by(Order.purchase_date.desc(), Order.id.desc())
        .offset(offset)
        .limit(limit)
    )

    result = await db.execute(items_query)
    total = (await db.execute(count_query)).scalar_one()
    orders = result.scalars().unique().all()

    return OrderListResponse(
        items=[OrderResponse.model_validate(order) for order in orders],
        total=total,
        limit=limit,
        offset=offset,
        has_more=offset + len(orders) < total,
    )


@router.get("/inventory", response_model=List[InventoryDataResponse])
async def get_inventory_data(
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
    snapshot_date: Optional[date] = Query(default=None),
    start_date: Optional[date] = Query(default=None),
    end_date: Optional[date] = Query(default=None),
    account_id: Optional[UUID] = Query(default=None),
    account_ids: Optional[List[UUID]] = Query(default=None),
    asin: Optional[str] = Query(default=None),
    asins: Optional[List[str]] = Query(default=None),
    low_stock_only: bool = Query(default=False),
    limit: int = Query(default=1000, le=10000),
):
    """Get inventory data."""
    if start_date and end_date and start_date > end_date:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="start_date cannot be after end_date",
        )

    selected_account_ids = []
    if account_id:
        selected_account_ids.append(account_id)
    if account_ids:
        selected_account_ids.extend(account_ids)

    selected_asins = []
    if asin:
        selected_asins.append(asin)
    if asins:
        selected_asins.extend(asins)

    accounts_query = select(AmazonAccount.id).where(
        AmazonAccount.organization_id == organization.id
    )
    if selected_account_ids:
        accounts_query = accounts_query.where(
            AmazonAccount.id.in_(list(dict.fromkeys(selected_account_ids)))
        )

    query = select(InventoryData).where(InventoryData.account_id.in_(accounts_query))

    if snapshot_date:
        query = query.where(InventoryData.snapshot_date == snapshot_date)
    elif start_date or end_date:
        if start_date:
            query = query.where(InventoryData.snapshot_date >= start_date)
        if end_date:
            query = query.where(InventoryData.snapshot_date <= end_date)
    else:
        max_date_query = select(func.max(InventoryData.snapshot_date)).where(
            InventoryData.account_id.in_(accounts_query)
        )
        result = await db.execute(max_date_query)
        latest_snapshot = result.scalar() or date.today()
        query = query.where(InventoryData.snapshot_date == latest_snapshot)

    if selected_asins:
        query = query.where(InventoryData.asin.in_(list(dict.fromkeys(selected_asins))))

    if low_stock_only:
        query = query.where(InventoryData.afn_fulfillable_quantity < 10)

    query = query.order_by(InventoryData.snapshot_date.desc(), InventoryData.asin).limit(limit)

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
    offset: int = Query(default=0, ge=0),
):
    """Get advertising performance data."""
    if start_date > end_date:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="start_date must be on or before end_date",
        )

    accounts_query = select(AmazonAccount.id).where(
        AmazonAccount.organization_id == organization.id
    )
    if account_ids:
        accounts_query = accounts_query.where(AmazonAccount.id.in_(account_ids))

    query = (
        select(
            AdvertisingMetrics,
            AdvertisingCampaign.campaign_id.label("external_campaign_id"),
            AdvertisingCampaign.campaign_name,
            AdvertisingCampaign.campaign_type,
        )
        .join(AdvertisingCampaign, AdvertisingCampaign.id == AdvertisingMetrics.campaign_id)
        .where(
            AdvertisingCampaign.account_id.in_(accounts_query),
            AdvertisingMetrics.date >= start_date,
            AdvertisingMetrics.date <= end_date,
        )
        .order_by(AdvertisingMetrics.date.desc(), AdvertisingMetrics.id.desc())
        .offset(offset)
        .limit(limit)
    )
    if campaign_types:
        query = query.where(
            AdvertisingCampaign.campaign_type.in_(list(dict.fromkeys(campaign_types)))
        )

    result = await db.execute(query)
    rows = result.all()

    return [
        AdvertisingMetricsResponse(
            id=row.AdvertisingMetrics.id,
            campaign_id=row.external_campaign_id,
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


@router.get("/schedules", response_model=List[ScheduledReportResponse])
async def list_report_schedules(
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
):
    """List scheduled reports for the organization."""
    service = ScheduledReportService(db)
    schedules = await service.list_schedules(organization.id)
    return [scheduled_report_to_response(schedule) for schedule in schedules]


@router.post("/schedules", response_model=ScheduledReportResponse, status_code=status.HTTP_201_CREATED)
async def create_report_schedule(
    schedule_in: ScheduledReportCreate,
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
):
    """Create a new scheduled report."""
    service = ScheduledReportService(db)
    try:
        schedule = await service.create_schedule(organization, current_user.id, schedule_in)
        await db.commit()
        await db.refresh(schedule)
        return scheduled_report_to_response(schedule)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))


@router.get("/schedules/{schedule_id}", response_model=ScheduledReportResponse)
async def get_report_schedule(
    schedule_id: UUID,
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
):
    """Get a single scheduled report."""
    service = ScheduledReportService(db)
    schedule = await service.get_schedule(schedule_id, organization.id)
    if not schedule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scheduled report not found")
    return scheduled_report_to_response(schedule)


@router.put("/schedules/{schedule_id}", response_model=ScheduledReportResponse)
async def update_report_schedule(
    schedule_id: UUID,
    schedule_in: ScheduledReportUpdate,
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
):
    """Update a scheduled report."""
    service = ScheduledReportService(db)
    schedule = await service.get_schedule(schedule_id, organization.id)
    if not schedule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scheduled report not found")
    try:
        updated = await service.update_schedule(schedule, organization, schedule_in)
        await db.commit()
        await db.refresh(updated)
        return scheduled_report_to_response(updated)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))


@router.post("/schedules/{schedule_id}/toggle", response_model=ScheduledReportResponse)
async def toggle_report_schedule(
    schedule_id: UUID,
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
    enabled: bool = Query(...),
):
    """Enable or disable a scheduled report."""
    service = ScheduledReportService(db)
    schedule = await service.get_schedule(schedule_id, organization.id)
    if not schedule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scheduled report not found")
    updated = await service.toggle_schedule(schedule, enabled)
    await db.commit()
    await db.refresh(updated)
    return scheduled_report_to_response(updated)


@router.get("/schedules/{schedule_id}/runs", response_model=List[ScheduledReportRunResponse])
async def list_report_schedule_runs(
    schedule_id: UUID,
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
    limit: int = Query(default=20, ge=1, le=100),
):
    """List execution history for a scheduled report."""
    service = ScheduledReportService(db)
    schedule = await service.get_schedule(schedule_id, organization.id)
    if not schedule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scheduled report not found")
    runs = await service.list_runs(schedule_id, organization.id, limit=limit)
    return [scheduled_report_run_to_response(run) for run in runs]


@router.post("/schedules/{schedule_id}/run-now", response_model=ScheduledReportRunResponse)
async def run_report_schedule_now(
    schedule_id: UUID,
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
):
    """Create and enqueue an immediate scheduled report run."""
    service = ScheduledReportService(db)
    schedule = await service.get_schedule(schedule_id, organization.id)
    if not schedule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scheduled report not found")
    run = await service.create_run(schedule)
    await db.commit()
    enqueue_scheduled_run_processing(str(run.id))
    await db.refresh(run)
    return scheduled_report_run_to_response(run)


@router.get("/schedules/runs/{run_id}/download")
async def download_report_schedule_run(
    run_id: UUID,
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
):
    """Download the artifact produced by a scheduled report run."""
    service = ScheduledReportService(db)
    run = await service.get_run(run_id, organization.id)
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scheduled report run not found")
    if not run.artifact_data:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Report artifact is not ready")
    filename = run.artifact_filename or f"scheduled-report-{run.id}"
    return StreamingResponse(
        iter([run.artifact_data]),
        media_type=run.artifact_content_type or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
