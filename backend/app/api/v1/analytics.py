"""Analytics and dashboard endpoints."""
from typing import List, Optional
from datetime import date, timedelta, datetime, time as dt_time
from uuid import UUID
from decimal import Decimal
import logging
from fastapi import APIRouter, Query
from sqlalchemy import select, func, and_

from app.api.deps import CurrentUser, CurrentOrganization, DbSession
from app.models.amazon_account import AmazonAccount
from app.models.sales_data import SalesData
from app.services.data_extraction import DAILY_TOTAL_ASIN
from app.models.advertising import AdvertisingCampaign, AdvertisingMetrics
from app.models.product import Product
from app.schemas.analytics import (
    DashboardKPIs, MetricValue, TrendData, TrendDataPoint,
    ComparisonData, ProductPerformance, TopPerformers,
    AdvertisingInsights, CategorySalesData, HourlyOrdersData,
)

router = APIRouter()
logger = logging.getLogger(__name__)


def calculate_change(current: float, previous: float) -> tuple:
    """Calculate change percent and trend."""
    if previous == 0:
        change = 100 if current > 0 else 0
    else:
        change = ((current - previous) / previous) * 100

    if change > 5:
        trend = "up"
    elif change < -5:
        trend = "down"
    else:
        trend = "stable"

    return change, trend


@router.get("/dashboard", response_model=DashboardKPIs)
async def get_dashboard_kpis(
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
    start_date: date = Query(default=date.today() - timedelta(days=30)),
    end_date: date = Query(default=date.today()),
    account_ids: Optional[List[UUID]] = Query(default=None),
):
    """Get dashboard KPIs with comparisons."""
    # Calculate previous period
    period_days = (end_date - start_date).days
    prev_start = start_date - timedelta(days=period_days)
    prev_end = start_date - timedelta(days=1)

    # Get organization's accounts
    accounts_query = select(AmazonAccount.id).where(
        AmazonAccount.organization_id == organization.id
    )
    if account_ids:
        accounts_query = accounts_query.where(AmazonAccount.id.in_(account_ids))

    # Current period aggregates (use daily totals to avoid double-counting)
    current_query = (
        select(
            func.sum(SalesData.ordered_product_sales).label("revenue"),
            func.sum(SalesData.units_ordered).label("units"),
            func.sum(SalesData.total_order_items).label("orders"),
        )
        .where(
            SalesData.account_id.in_(accounts_query),
            SalesData.asin == DAILY_TOTAL_ASIN,
            SalesData.date >= start_date,
            SalesData.date <= end_date,
        )
    )
    current_result = await db.execute(current_query)
    current = current_result.one()

    # Previous period aggregates (use daily totals to avoid double-counting)
    prev_query = (
        select(
            func.sum(SalesData.ordered_product_sales).label("revenue"),
            func.sum(SalesData.units_ordered).label("units"),
            func.sum(SalesData.total_order_items).label("orders"),
        )
        .where(
            SalesData.account_id.in_(accounts_query),
            SalesData.asin == DAILY_TOTAL_ASIN,
            SalesData.date >= prev_start,
            SalesData.date <= prev_end,
        )
    )
    prev_result = await db.execute(prev_query)
    prev = prev_result.one()

    # Calculate metrics
    current_revenue = float(current.revenue or 0)
    prev_revenue = float(prev.revenue or 0)
    revenue_change, revenue_trend = calculate_change(current_revenue, prev_revenue)

    current_units = int(current.units or 0)
    prev_units = int(prev.units or 0)
    units_change, units_trend = calculate_change(current_units, prev_units)

    current_orders = int(current.orders or 0)
    prev_orders = int(prev.orders or 0)
    orders_change, orders_trend = calculate_change(current_orders, prev_orders)

    # Average order value
    current_aov = current_revenue / current_orders if current_orders > 0 else 0
    prev_aov = prev_revenue / prev_orders if prev_orders > 0 else 0
    aov_change, aov_trend = calculate_change(current_aov, prev_aov)

    # Get advertising data
    campaigns_query = select(AdvertisingCampaign.id).where(
        AdvertisingCampaign.account_id.in_(accounts_query)
    )

    ads_query = (
        select(
            func.sum(AdvertisingMetrics.cost).label("spend"),
            func.sum(AdvertisingMetrics.attributed_sales_7d).label("ad_sales"),
            func.sum(AdvertisingMetrics.impressions).label("impressions"),
            func.sum(AdvertisingMetrics.clicks).label("clicks"),
        )
        .where(
            AdvertisingMetrics.campaign_id.in_(campaigns_query),
            AdvertisingMetrics.date >= start_date,
            AdvertisingMetrics.date <= end_date,
        )
    )
    ads_result = await db.execute(ads_query)
    ads = ads_result.one()

    ad_spend = float(ads.spend or 0)
    ad_sales = float(ads.ad_sales or 0)
    impressions = int(ads.impressions or 0)
    clicks = int(ads.clicks or 0)

    roas = ad_sales / ad_spend if ad_spend > 0 else 0
    acos = (ad_spend / ad_sales) * 100 if ad_sales > 0 else 0
    ctr = (clicks / impressions) * 100 if impressions > 0 else 0

    # Count active ASINs and synced accounts (exclude sentinel)
    asin_count = await db.execute(
        select(func.count(func.distinct(SalesData.asin)))
        .where(
            SalesData.account_id.in_(accounts_query),
            SalesData.asin != DAILY_TOTAL_ASIN,
            SalesData.date >= start_date,
        )
    )
    active_asins = asin_count.scalar() or 0

    account_count = await db.execute(
        select(func.count(AmazonAccount.id))
        .where(
            AmazonAccount.organization_id == organization.id,
            AmazonAccount.is_active == True,
        )
    )
    accounts_synced = account_count.scalar() or 0

    return DashboardKPIs(
        total_revenue=MetricValue(
            value=current_revenue,
            previous_value=prev_revenue,
            change_percent=revenue_change,
            trend=revenue_trend,
        ),
        total_units=MetricValue(
            value=current_units,
            previous_value=prev_units,
            change_percent=units_change,
            trend=units_trend,
        ),
        total_orders=MetricValue(
            value=current_orders,
            previous_value=prev_orders,
            change_percent=orders_change,
            trend=orders_trend,
        ),
        average_order_value=MetricValue(
            value=current_aov,
            previous_value=prev_aov,
            change_percent=aov_change,
            trend=aov_trend,
        ),
        return_rate=MetricValue(value=0, trend="stable"),  # Would need returns data
        roas=MetricValue(value=roas, trend="stable"),
        acos=MetricValue(value=acos, trend="stable"),
        ctr=MetricValue(value=ctr, trend="stable"),
        active_asins=active_asins,
        accounts_synced=accounts_synced,
        period_start=start_date,
        period_end=end_date,
    )


@router.get("/trends", response_model=List[TrendData])
async def get_trends(
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
    metrics: List[str] = Query(default=["revenue", "units"]),
    start_date: date = Query(default=date.today() - timedelta(days=30)),
    end_date: date = Query(default=date.today()),
    account_ids: Optional[List[UUID]] = Query(default=None),
):
    """Get trend data for specified metrics."""
    accounts_query = select(AmazonAccount.id).where(
        AmazonAccount.organization_id == organization.id
    )
    if account_ids:
        accounts_query = accounts_query.where(AmazonAccount.id.in_(account_ids))

    trends = []

    for metric in metrics:
        if metric == "revenue":
            query = (
                select(
                    SalesData.date,
                    func.sum(SalesData.ordered_product_sales).label("value"),
                )
                .where(
                    SalesData.account_id.in_(accounts_query),
                    SalesData.asin == DAILY_TOTAL_ASIN,
                    SalesData.date >= start_date,
                    SalesData.date <= end_date,
                )
                .group_by(SalesData.date)
                .order_by(SalesData.date)
            )
        elif metric == "units":
            query = (
                select(
                    SalesData.date,
                    func.sum(SalesData.units_ordered).label("value"),
                )
                .where(
                    SalesData.account_id.in_(accounts_query),
                    SalesData.asin == DAILY_TOTAL_ASIN,
                    SalesData.date >= start_date,
                    SalesData.date <= end_date,
                )
                .group_by(SalesData.date)
                .order_by(SalesData.date)
            )
        else:
            continue

        result = await db.execute(query)
        rows = result.all()

        data_points = [
            TrendDataPoint(date=row.date, value=float(row.value or 0))
            for row in rows
        ]

        values = [dp.value for dp in data_points]
        trends.append(TrendData(
            metric_name=metric,
            data_points=data_points,
            total=sum(values),
            average=sum(values) / len(values) if values else 0,
            min_value=min(values) if values else 0,
            max_value=max(values) if values else 0,
        ))

    return trends


@router.get("/comparison", response_model=List[ComparisonData])
async def get_comparison(
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
    period1_start: date = Query(...),
    period1_end: date = Query(...),
    period2_start: date = Query(...),
    period2_end: date = Query(...),
    account_ids: Optional[List[UUID]] = Query(default=None),
):
    """Compare metrics between two periods."""
    accounts_query = select(AmazonAccount.id).where(
        AmazonAccount.organization_id == organization.id
    )
    if account_ids:
        accounts_query = accounts_query.where(AmazonAccount.id.in_(account_ids))

    async def get_period_data(start: date, end: date) -> dict:
        query = (
            select(
                func.sum(SalesData.ordered_product_sales).label("revenue"),
                func.sum(SalesData.units_ordered).label("units"),
                func.sum(SalesData.total_order_items).label("orders"),
            )
            .where(
                SalesData.account_id.in_(accounts_query),
                SalesData.asin == DAILY_TOTAL_ASIN,
                SalesData.date >= start,
                SalesData.date <= end,
            )
        )
        result = await db.execute(query)
        row = result.one()
        return {
            "revenue": float(row.revenue or 0),
            "units": int(row.units or 0),
            "orders": int(row.orders or 0),
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
        }

    period1_data = await get_period_data(period1_start, period1_end)
    period2_data = await get_period_data(period2_start, period2_end)

    comparisons = []
    for metric in ["revenue", "units", "orders"]:
        current = period1_data[metric]
        previous = period2_data[metric]
        change_abs = current - previous
        change_pct = ((current - previous) / previous * 100) if previous > 0 else 0

        comparisons.append(ComparisonData(
            metric_name=metric,
            current_period=period1_data,
            previous_period=period2_data,
            change_absolute=change_abs,
            change_percent=change_pct,
        ))

    return comparisons


@router.get("/top-performers", response_model=TopPerformers)
async def get_top_performers(
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
    start_date: date = Query(default=date.today() - timedelta(days=30)),
    end_date: date = Query(default=date.today()),
    account_ids: Optional[List[UUID]] = Query(default=None),
    limit: int = Query(default=10, le=50),
):
    """Get top performing products."""
    accounts_query = select(AmazonAccount.id).where(
        AmazonAccount.organization_id == organization.id
    )
    if account_ids:
        accounts_query = accounts_query.where(AmazonAccount.id.in_(account_ids))

    # Top by revenue (real ASINs only)
    revenue_query = (
        select(
            SalesData.asin,
            func.sum(SalesData.units_ordered).label("total_units"),
            func.sum(SalesData.ordered_product_sales).label("total_revenue"),
            func.sum(SalesData.total_order_items).label("total_orders"),
        )
        .where(
            SalesData.account_id.in_(accounts_query),
            SalesData.asin != DAILY_TOTAL_ASIN,
            SalesData.date >= start_date,
            SalesData.date <= end_date,
        )
        .group_by(SalesData.asin)
        .order_by(func.sum(SalesData.ordered_product_sales).desc())
        .limit(limit)
    )

    result = await db.execute(revenue_query)
    rows = result.all()

    # Calculate total revenue for share calculation
    total_revenue = sum(float(row.total_revenue or 0) for row in rows)

    by_revenue = [
        ProductPerformance(
            asin=row.asin,
            title=None,
            sku=None,
            total_units=row.total_units or 0,
            total_revenue=row.total_revenue or Decimal(0),
            total_orders=row.total_orders or 0,
            avg_price=None,
            current_bsr=None,
            bsr_change=None,
            revenue_share=(float(row.total_revenue or 0) / total_revenue * 100) if total_revenue > 0 else 0,
        )
        for row in rows
    ]

    return TopPerformers(
        by_revenue=by_revenue,
        by_units=by_revenue,  # Same for now
        by_growth=[],  # Would require historical comparison
    )


@router.get("/sales-by-category", response_model=List[CategorySalesData])
async def get_sales_by_category(
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
    start_date: date = Query(default=date.today() - timedelta(days=30)),
    end_date: date = Query(default=date.today()),
    account_ids: Optional[List[UUID]] = Query(default=None),
    category: Optional[str] = Query(default=None),
    limit: int = Query(default=20, le=100),
):
    """Get sales aggregates grouped by product category."""
    accounts_query = select(AmazonAccount.id).where(
        AmazonAccount.organization_id == organization.id
    )
    if account_ids:
        accounts_query = accounts_query.where(AmazonAccount.id.in_(account_ids))

    category_expr = func.coalesce(Product.category, "Uncategorized")
    query = (
        select(
            category_expr.label("category"),
            func.sum(SalesData.ordered_product_sales).label("total_revenue"),
            func.sum(SalesData.units_ordered).label("total_units"),
            func.sum(SalesData.total_order_items).label("total_orders"),
        )
        .select_from(SalesData)
        .outerjoin(
            Product,
            and_(
                Product.account_id == SalesData.account_id,
                Product.asin == SalesData.asin,
            ),
        )
        .where(
            SalesData.account_id.in_(accounts_query),
            SalesData.asin != DAILY_TOTAL_ASIN,
            SalesData.date >= start_date,
            SalesData.date <= end_date,
        )
    )

    if category:
        query = query.where(Product.category == category)

    query = (
        query.group_by(category_expr)
        .order_by(func.sum(SalesData.ordered_product_sales).desc())
        .limit(limit)
    )

    rows = (await db.execute(query)).all()
    return [
        CategorySalesData(
            category=row.category or "Uncategorized",
            total_revenue=float(row.total_revenue or 0),
            total_units=int(row.total_units or 0),
            total_orders=int(row.total_orders or 0),
        )
        for row in rows
    ]


@router.get("/orders-by-hour", response_model=List[HourlyOrdersData])
async def get_orders_by_hour(
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
    start_date: date = Query(default=date.today() - timedelta(days=30)),
    end_date: date = Query(default=date.today()),
    account_ids: Optional[List[UUID]] = Query(default=None),
    max_pages_per_account: int = Query(default=10, ge=1, le=50),
):
    """Get order counts by hour (UTC) from SP-API Orders endpoint."""
    accounts_stmt = select(AmazonAccount).where(
        AmazonAccount.organization_id == organization.id,
        AmazonAccount.is_active == True,
    )
    if account_ids:
        accounts_stmt = accounts_stmt.where(AmazonAccount.id.in_(account_ids))

    accounts = (await db.execute(accounts_stmt)).scalars().all()
    hourly_counts = {h: 0 for h in range(24)}

    if not accounts:
        return [HourlyOrdersData(hour=h, orders=0) for h in range(24)]

    # Include the full end day by default, but keep the upper bound at least
    # 2 minutes behind current UTC time to satisfy Orders API constraints.
    lower_bound = datetime.combine(start_date, dt_time.min)
    upper_bound = datetime.combine(end_date + timedelta(days=1), dt_time.min)
    safe_now = datetime.utcnow() - timedelta(minutes=2)
    if upper_bound > safe_now:
        upper_bound = safe_now
    if upper_bound <= lower_bound:
        upper_bound = lower_bound + timedelta(minutes=1)

    created_after = lower_bound.isoformat()
    created_before = upper_bound.isoformat()

    from app.core.amazon.credentials import resolve_credentials
    from app.core.amazon.sp_api_client import SPAPIClient, resolve_marketplace

    from app.models.amazon_account import AccountType

    for account in accounts:
        try:
            credentials = resolve_credentials(account, organization)
            marketplace = resolve_marketplace(account.marketplace_country)
            client = SPAPIClient(credentials, marketplace, account_type=account.account_type.value)

            if account.account_type == AccountType.VENDOR:
                # Vendor accounts use VendorOrders (purchase orders) API
                api = client._vendor_orders_api()
                page_count = 0
                next_token = None

                while True:
                    kwargs = {
                        "createdAfter": created_after,
                        "createdBefore": created_before,
                    }
                    if next_token:
                        kwargs["nextToken"] = next_token

                    response = api.get_purchase_orders(**kwargs)
                    payload = response.payload or {}
                    orders = payload.get("orders", [])

                    for order in orders:
                        po_date = (
                            order.get("orderDetails", {}).get("purchaseOrderDate")
                            or order.get("purchaseOrderDate")
                        )
                        if not po_date:
                            continue
                        try:
                            ts = str(po_date).replace("Z", "+00:00")
                            hour = datetime.fromisoformat(ts).hour
                            hourly_counts[hour] = hourly_counts.get(hour, 0) + 1
                        except Exception:
                            continue

                    page_count += 1
                    pagination = payload.get("pagination", {})
                    next_token = pagination.get("nextToken")
                    if not next_token or page_count >= max_pages_per_account:
                        break
            else:
                # Seller accounts use the Orders API
                api = client._orders_api()

                page_count = 0
                response = api.get_orders(
                    CreatedAfter=created_after,
                    CreatedBefore=created_before,
                )

                while True:
                    payload = response.payload or {}
                    orders = payload.get("Orders") or payload.get("orders") or []

                    for order in orders:
                        purchase_date = (
                            order.get("PurchaseDate")
                            or order.get("purchaseDate")
                            or order.get("LastUpdateDate")
                            or order.get("lastUpdateDate")
                        )
                        if not purchase_date:
                            continue

                        try:
                            ts = str(purchase_date).replace("Z", "+00:00")
                            hour = datetime.fromisoformat(ts).hour
                            hourly_counts[hour] = hourly_counts.get(hour, 0) + 1
                        except Exception:
                            continue

                    page_count += 1
                    next_token = payload.get("NextToken") or payload.get("nextToken")
                    if not next_token or page_count >= max_pages_per_account:
                        break
                    response = api.get_orders(NextToken=next_token)
        except Exception as exc:
            logger.warning(
                "Failed hourly orders extraction for account %s (%s): %s",
                account.account_name,
                account.id,
                exc,
            )

    return [HourlyOrdersData(hour=h, orders=hourly_counts[h]) for h in range(24)]


@router.get("/advertising", response_model=AdvertisingInsights)
async def get_advertising_insights(
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
    start_date: date = Query(default=date.today() - timedelta(days=30)),
    end_date: date = Query(default=date.today()),
):
    """Get advertising performance insights."""
    accounts_query = select(AmazonAccount.id).where(
        AmazonAccount.organization_id == organization.id
    )
    campaigns_query = select(AdvertisingCampaign.id).where(
        AdvertisingCampaign.account_id.in_(accounts_query)
    )

    # Overall metrics
    overall_query = (
        select(
            func.sum(AdvertisingMetrics.cost).label("spend"),
            func.sum(AdvertisingMetrics.attributed_sales_7d).label("sales"),
        )
        .where(
            AdvertisingMetrics.campaign_id.in_(campaigns_query),
            AdvertisingMetrics.date >= start_date,
            AdvertisingMetrics.date <= end_date,
        )
    )
    overall = (await db.execute(overall_query)).one()

    total_spend = Decimal(str(overall.spend or 0))
    total_sales = Decimal(str(overall.sales or 0))
    overall_roas = total_sales / total_spend if total_spend > 0 else Decimal(0)
    overall_acos = (total_spend / total_sales * 100) if total_sales > 0 else Decimal(0)

    return AdvertisingInsights(
        total_spend=total_spend,
        total_sales=total_sales,
        overall_roas=overall_roas,
        overall_acos=overall_acos,
        top_campaigns=[],
        underperforming_campaigns=[],
        recommendations=[
            "Consider increasing budget for campaigns with ROAS > 3",
            "Review and optimize keywords with high ACoS",
            "Test new ad creative for underperforming campaigns",
        ],
    )
