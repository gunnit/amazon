"""Analytics and dashboard endpoints."""
from typing import List, Optional
from datetime import date, timedelta, datetime, time as dt_time, timezone
from uuid import UUID
from decimal import Decimal
import logging
import re
from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import Date, and_, cast, func, select, text

from app.api.deps import CurrentOrganization, CurrentSuperuser, CurrentUser, DbSession
from app.config import settings
from app.models.amazon_account import AmazonAccount
from app.models.order import Order, OrderItem
from app.models.returns_data import ReturnData
from app.models.sales_data import SalesData
from app.services.data_extraction import DAILY_TOTAL_ASIN
from app.models.advertising import AdvertisingCampaign, AdvertisingMetrics
from app.models.product import Product
from app.services.analytics_service import AnalyticsService
from app.services.ai_analysis_service import ProductTrendInsightsAnalysisService
from app.services.product_trends_service import ProductTrendsService, build_rule_based_insights
from app.schemas.analytics import (
    DashboardKPIs, MetricValue, TrendData, TrendDataPoint,
    ComparisonDailyPoint, ComparisonMetric, ComparisonPeriod, ComparisonResponse,
    ProductPerformance, TopPerformers,
    AdvertisingInsights, CategorySalesData, HourlyOrdersData, ProductTrendsResponse,
    ReturnAsinMetric, ReturnReasonBreakdown, ReturnsAnalyticsResponse, ReturnsSummary,
    ReturnsTrendPoint,
    AdsVsOrganicResponse,
)

router = APIRouter()
logger = logging.getLogger(__name__)

MISSING_DATA_SOURCE = "missing_data_source"
CATEGORY_FILTER_NOT_SUPPORTED = "category_filter_not_supported"
SQL_IDENTIFIER_RE = re.compile(r"^[a-z_][a-z0-9_]*$")
DATA_HEALTH_TABLES = (
    ("sales_data", "date"),
    ("inventory_data", "snapshot_date"),
    ("advertising_metrics", "date"),
    ("returns_data", "return_date"),
    ("bsr_history", "date"),
    ("competitor_history", "date"),
)


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


def _quoted_identifier(identifier: str) -> str:
    """Return a safely quoted SQL identifier from the static allowlist."""
    if not SQL_IDENTIFIER_RE.fullmatch(identifier):
        raise ValueError(f"Invalid SQL identifier: {identifier}")
    return f'"{identifier}"'


def _decimal_ratio(numerator: Decimal, denominator: Decimal, multiplier: Decimal = Decimal("1")) -> Decimal:
    """Calculate a Decimal ratio with zero protection."""
    if denominator <= 0:
        return Decimal("0")
    return (numerator * multiplier / denominator).quantize(Decimal("0.0001"))


def _validate_period(start_date: date, end_date: date, label: str) -> None:
    """Ensure a date range is valid."""
    if start_date > end_date:
        raise HTTPException(
            status_code=422,
            detail=f"{label}_start must be on or before {label}_end",
        )


def _previous_period(start_date: date, end_date: date) -> tuple[date, date]:
    """Return the immediately preceding period with matching inclusive length."""
    period_days = (end_date - start_date).days + 1
    prev_end = start_date - timedelta(days=1)
    prev_start = prev_end - timedelta(days=period_days - 1)
    return prev_start, prev_end


def _accounts_query(organization_id: UUID, account_ids: Optional[List[UUID]]) -> select:
    """Build the organization-scoped account id query."""
    query = select(AmazonAccount.id).where(AmazonAccount.organization_id == organization_id)
    if account_ids:
        query = query.where(AmazonAccount.id.in_(account_ids))
    return query


def _resolve_optional_date_range(
    date_from: Optional[date],
    date_to: Optional[date],
) -> tuple[Optional[date], Optional[date]]:
    """Default an empty date range to the last 30 days while allowing partial bounds."""
    if date_from is None and date_to is None:
        return date.today() - timedelta(days=30), date.today()
    return date_from, date_to


def _order_datetime_bounds(
    date_from: Optional[date],
    date_to: Optional[date],
) -> tuple[Optional[datetime], Optional[datetime]]:
    """Convert inclusive date filters to timestamp bounds for order queries."""
    start = None
    end = None
    if date_from:
        start = datetime.combine(date_from, dt_time.min).replace(tzinfo=timezone.utc)
    if date_to:
        end = datetime.combine(date_to + timedelta(days=1), dt_time.min).replace(tzinfo=timezone.utc)
    return start, end


def _return_rate_percent(returned_units: int, ordered_units: Optional[int]) -> Optional[float]:
    """Return a percentage-based return rate when a denominator is available."""
    if not ordered_units:
        return None
    rate = _decimal_ratio(
        Decimal(returned_units),
        Decimal(ordered_units),
        multiplier=Decimal("100"),
    )
    return float(rate)


def _merge_account_ids(
    account_id: Optional[UUID],
    account_ids: Optional[List[UUID]],
) -> Optional[List[UUID]]:
    """Normalize singular/plural account query params into one list."""
    merged: list[UUID] = []
    if account_id:
        merged.append(account_id)
    if account_ids:
        merged.extend(account_ids)

    if not merged:
        return None

    return list(dict.fromkeys(merged))


def _normalize_optional_asin(asin: Optional[str]) -> Optional[str]:
    """Normalize optional ASIN filters across analytics endpoints."""
    if asin is None:
        return None
    normalized = asin.strip().upper()
    return normalized or None


async def _get_sales_period_metrics(
    db: DbSession,
    accounts_query,
    start_date: date,
    end_date: date,
    category: Optional[str] = None,
) -> dict:
    """Aggregate revenue, units, orders, and AOV for a period."""
    if category:
        query = (
            select(
                func.sum(SalesData.ordered_product_sales).label("revenue"),
                func.sum(SalesData.units_ordered).label("units"),
                func.sum(SalesData.total_order_items).label("orders"),
            )
            .select_from(SalesData)
            .join(
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
                Product.category == category,
            )
        )
    else:
        query = (
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

    row = (await db.execute(query)).one()
    revenue = float(row.revenue or 0)
    units = int(row.units or 0)
    orders = int(row.orders or 0)

    return {
        "revenue": revenue,
        "units": units,
        "orders": orders,
        "average_order_value": revenue / orders if orders > 0 else 0,
    }


async def _get_sales_daily_revenue(
    db: DbSession,
    accounts_query,
    start_date: date,
    end_date: date,
    category: Optional[str] = None,
) -> dict[date, float]:
    """Aggregate daily revenue using the same comparison filters as sales metrics."""
    if category:
        query = (
            select(
                SalesData.date.label("period_date"),
                func.sum(SalesData.ordered_product_sales).label("revenue"),
            )
            .select_from(SalesData)
            .join(
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
                Product.category == category,
            )
            .group_by(SalesData.date)
            .order_by(SalesData.date)
        )
    else:
        query = (
            select(
                SalesData.date.label("period_date"),
                func.sum(SalesData.ordered_product_sales).label("revenue"),
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

    rows = (await db.execute(query)).all()
    return {
        row.period_date: float(row.revenue or 0)
        for row in rows
    }


async def _get_returns_period_count(
    db: DbSession,
    accounts_query,
    start_date: date,
    end_date: date,
    category: Optional[str] = None,
) -> int:
    """Count return records for a comparison period."""
    if category:
        query = (
            select(func.count(ReturnData.id))
            .select_from(ReturnData)
            .join(
                Product,
                and_(
                    Product.account_id == ReturnData.account_id,
                    Product.asin == ReturnData.asin,
                ),
            )
            .where(
                ReturnData.account_id.in_(accounts_query),
                ReturnData.return_date >= start_date,
                ReturnData.return_date <= end_date,
                Product.category == category,
            )
        )
    else:
        query = (
            select(func.count(ReturnData.id))
            .where(
                ReturnData.account_id.in_(accounts_query),
                ReturnData.return_date >= start_date,
                ReturnData.return_date <= end_date,
            )
        )

    return int((await db.execute(query)).scalar() or 0)


async def _get_advertising_period_metrics(
    db: DbSession,
    accounts_query,
    start_date: date,
    end_date: date,
) -> dict:
    """Aggregate advertising metrics for a period."""
    campaigns_query = select(AdvertisingCampaign.id).where(
        AdvertisingCampaign.account_id.in_(accounts_query)
    )

    query = (
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

    row = (await db.execute(query)).one()
    spend = float(row.spend or 0)
    ad_sales = float(row.ad_sales or 0)
    impressions = int(row.impressions or 0)
    clicks = int(row.clicks or 0)

    return {
        "spend": spend,
        "ad_sales": ad_sales,
        "impressions": impressions,
        "clicks": clicks,
        "roas": ad_sales / spend if spend > 0 else 0,
        "acos": (spend / ad_sales) * 100 if ad_sales > 0 else 0,
        "ctr": (clicks / impressions) * 100 if impressions > 0 else 0,
    }


def _build_comparison_metric(
    metric_name: str,
    label: str,
    value_format: str,
    current_value: Optional[float] = None,
    previous_value: Optional[float] = None,
    *,
    is_available: bool = True,
    unavailable_reason: Optional[str] = None,
) -> ComparisonMetric:
    """Construct a metric comparison payload with trend metadata."""
    change_percent = None
    trend = "stable"

    if is_available and current_value is not None and previous_value is not None:
        change_percent, trend = calculate_change(current_value, previous_value)

    return ComparisonMetric(
        metric_name=metric_name,
        label=label,
        current_value=current_value,
        previous_value=previous_value,
        change_percent=change_percent,
        trend=trend,
        format=value_format,
        is_available=is_available,
        unavailable_reason=unavailable_reason,
    )


def _metric_value_from_comparison(metric: ComparisonMetric) -> MetricValue:
    """Adapt a comparison metric to dashboard KPI schema."""
    return MetricValue(
        value=metric.current_value or 0,
        previous_value=metric.previous_value,
        change_percent=metric.change_percent,
        trend=metric.trend,
        is_available=metric.is_available,
        unavailable_reason=metric.unavailable_reason,
    )


async def _build_period_comparison(
    db: DbSession,
    organization_id: UUID,
    period_1_start: date,
    period_1_end: date,
    period_2_start: date,
    period_2_end: date,
    account_ids: Optional[List[UUID]] = None,
    category: Optional[str] = None,
    preset: Optional[str] = None,
) -> ComparisonResponse:
    """Build a period-over-period comparison response."""
    _validate_period(period_1_start, period_1_end, "period1")
    _validate_period(period_2_start, period_2_end, "period2")

    accounts_query = _accounts_query(organization_id, account_ids)
    current_sales = await _get_sales_period_metrics(db, accounts_query, period_1_start, period_1_end, category)
    previous_sales = await _get_sales_period_metrics(db, accounts_query, period_2_start, period_2_end, category)
    current_returns = await _get_returns_period_count(db, accounts_query, period_1_start, period_1_end, category)
    previous_returns = await _get_returns_period_count(db, accounts_query, period_2_start, period_2_end, category)
    current_daily_revenue = await _get_sales_daily_revenue(
        db, accounts_query, period_1_start, period_1_end, category
    )
    previous_daily_revenue = await _get_sales_daily_revenue(
        db, accounts_query, period_2_start, period_2_end, category
    )

    period_1_days = (period_1_end - period_1_start).days + 1
    period_2_days = (period_2_end - period_2_start).days + 1
    series_length = max(period_1_days, period_2_days)
    daily_series = [
        ComparisonDailyPoint(
            day_offset=day_offset,
            period_1_date=(
                period_1_start + timedelta(days=day_offset)
                if day_offset < period_1_days
                else None
            ),
            period_1_revenue=(
                current_daily_revenue.get(period_1_start + timedelta(days=day_offset), 0.0)
                if day_offset < period_1_days
                else None
            ),
            period_2_date=(
                period_2_start + timedelta(days=day_offset)
                if day_offset < period_2_days
                else None
            ),
            period_2_revenue=(
                previous_daily_revenue.get(period_2_start + timedelta(days=day_offset), 0.0)
                if day_offset < period_2_days
                else None
            ),
        )
        for day_offset in range(series_length)
    ]

    metrics = [
        _build_comparison_metric(
            "revenue",
            "Revenue",
            "currency",
            current_sales["revenue"],
            previous_sales["revenue"],
        ),
        _build_comparison_metric(
            "units",
            "Units Sold",
            "number",
            float(current_sales["units"]),
            float(previous_sales["units"]),
        ),
        _build_comparison_metric(
            "orders",
            "Orders",
            "number",
            float(current_sales["orders"]),
            float(previous_sales["orders"]),
        ),
        _build_comparison_metric(
            "returns",
            "Returns",
            "number",
            float(current_returns),
            float(previous_returns),
        ),
    ]

    if category:
        metrics.extend([
            _build_comparison_metric(
                "roas",
                "ROAS",
                "ratio",
                is_available=False,
                unavailable_reason=CATEGORY_FILTER_NOT_SUPPORTED,
            ),
            _build_comparison_metric(
                "ctr",
                "CTR",
                "percent",
                is_available=False,
                unavailable_reason=CATEGORY_FILTER_NOT_SUPPORTED,
            ),
        ])
    else:
        current_ads = await _get_advertising_period_metrics(db, accounts_query, period_1_start, period_1_end)
        previous_ads = await _get_advertising_period_metrics(db, accounts_query, period_2_start, period_2_end)
        metrics.extend([
            _build_comparison_metric(
                "roas",
                "ROAS",
                "ratio",
                current_ads["roas"],
                previous_ads["roas"],
            ),
            _build_comparison_metric(
                "ctr",
                "CTR",
                "percent",
                current_ads["ctr"],
                previous_ads["ctr"],
            ),
        ])

    return ComparisonResponse(
        preset=preset,
        category=category,
        period_1=ComparisonPeriod(start=period_1_start, end=period_1_end),
        period_2=ComparisonPeriod(start=period_2_start, end=period_2_end),
        metrics=metrics,
        daily_series=daily_series,
    )


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
    _validate_period(start_date, end_date, "period")
    prev_start, prev_end = _previous_period(start_date, end_date)
    accounts_query = _accounts_query(organization.id, account_ids)
    sales_current = await _get_sales_period_metrics(db, accounts_query, start_date, end_date)
    sales_previous = await _get_sales_period_metrics(db, accounts_query, prev_start, prev_end)
    ads_current = await _get_advertising_period_metrics(db, accounts_query, start_date, end_date)
    ads_previous = await _get_advertising_period_metrics(db, accounts_query, prev_start, prev_end)

    revenue_metric = _build_comparison_metric(
        "revenue", "Revenue", "currency", sales_current["revenue"], sales_previous["revenue"]
    )
    units_metric = _build_comparison_metric(
        "units", "Units Sold", "number", float(sales_current["units"]), float(sales_previous["units"])
    )
    orders_metric = _build_comparison_metric(
        "orders", "Orders", "number", float(sales_current["orders"]), float(sales_previous["orders"])
    )
    aov_metric = _build_comparison_metric(
        "average_order_value",
        "Average Order Value",
        "currency",
        sales_current["average_order_value"],
        sales_previous["average_order_value"],
    )
    roas_metric = _build_comparison_metric(
        "roas", "ROAS", "ratio", ads_current["roas"], ads_previous["roas"]
    )
    acos_metric = _build_comparison_metric(
        "acos", "ACoS", "percent", ads_current["acos"], ads_previous["acos"]
    )
    ctr_metric = _build_comparison_metric(
        "ctr", "CTR", "percent", ads_current["ctr"], ads_previous["ctr"]
    )

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
        total_revenue=_metric_value_from_comparison(revenue_metric),
        total_units=_metric_value_from_comparison(units_metric),
        total_orders=_metric_value_from_comparison(orders_metric),
        average_order_value=_metric_value_from_comparison(aov_metric),
        return_rate=MetricValue(
            value=0,
            trend="stable",
            is_available=False,
            unavailable_reason=MISSING_DATA_SOURCE,
        ),
        roas=_metric_value_from_comparison(roas_metric),
        acos=_metric_value_from_comparison(acos_metric),
        ctr=_metric_value_from_comparison(ctr_metric),
        active_asins=active_asins,
        accounts_synced=accounts_synced,
        period_start=start_date,
        period_end=end_date,
    )


@router.get("/ads-vs-organic", response_model=AdsVsOrganicResponse)
async def get_ads_vs_organic(
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
    account_id: Optional[UUID] = Query(default=None),
    account_ids: Optional[List[UUID]] = Query(default=None),
    date_from: date = Query(default=date.today() - timedelta(days=30)),
    date_to: date = Query(default=date.today()),
    group_by: str = Query(default="day", pattern="^(day|week|month)$"),
    asin: Optional[str] = Query(default=None),
):
    """Get ad-attributed vs organic sales analytics."""
    _validate_period(date_from, date_to, "period")
    selected_account_ids = _merge_account_ids(account_id, account_ids)
    accounts_stmt = _accounts_query(organization.id, selected_account_ids)
    resolved_account_ids = list((await db.execute(accounts_stmt)).scalars().all())
    asin = _normalize_optional_asin(asin)

    service = AnalyticsService(db)
    return await service.get_ads_vs_organic(
        account_ids=resolved_account_ids,
        date_from=date_from,
        date_to=date_to,
        group_by=group_by,
        asin=asin,
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


@router.get("/returns", response_model=ReturnsAnalyticsResponse)
async def get_returns_analysis(
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
    account_id: Optional[UUID] = Query(default=None),
    account_ids: Optional[List[UUID]] = Query(default=None),
    date_from: Optional[date] = Query(default=None),
    date_to: Optional[date] = Query(default=None),
    asin: Optional[str] = Query(default=None, min_length=1, max_length=20),
    limit: int = Query(default=10, ge=1, le=50),
):
    """Get return trends, reasons, and ASIN-level return metrics."""
    date_from, date_to = _resolve_optional_date_range(date_from, date_to)
    asin = _normalize_optional_asin(asin)
    if date_from and date_to:
        _validate_period(date_from, date_to, "period")

    selected_account_ids = _merge_account_ids(account_id, account_ids)
    accounts_query = _accounts_query(organization.id, selected_account_ids)

    returns_filters = [ReturnData.account_id.in_(accounts_query)]
    if date_from:
        returns_filters.append(ReturnData.return_date >= date_from)
    if date_to:
        returns_filters.append(ReturnData.return_date <= date_to)
    if asin:
        returns_filters.append(ReturnData.asin == asin)

    reason_expr = func.coalesce(func.nullif(ReturnData.reason, ""), "Unknown")
    disposition_expr = func.coalesce(func.nullif(ReturnData.disposition, ""), "Unknown")

    returns_trend_rows = (
        await db.execute(
            select(
                ReturnData.return_date.label("period_date"),
                func.sum(ReturnData.quantity).label("returned_units"),
            )
            .where(*returns_filters)
            .group_by(ReturnData.return_date)
            .order_by(ReturnData.return_date)
        )
    ).all()

    reason_rows = (
        await db.execute(
            select(
                reason_expr.label("reason"),
                func.sum(ReturnData.quantity).label("quantity"),
            )
            .where(*returns_filters)
            .group_by(reason_expr)
            .order_by(func.sum(ReturnData.quantity).desc(), reason_expr)
        )
    ).all()

    returns_asin_rows = (
        await db.execute(
            select(
                ReturnData.asin,
                func.max(func.nullif(ReturnData.sku, "")).label("sku"),
                func.sum(ReturnData.quantity).label("quantity_returned"),
            )
            .where(
                *returns_filters,
                ReturnData.asin.is_not(None),
                ReturnData.asin != "",
            )
            .group_by(ReturnData.asin)
            .order_by(func.sum(ReturnData.quantity).desc(), ReturnData.asin)
        )
    ).all()

    total_returns = sum(int(row.quantity or 0) for row in reason_rows)
    unique_asins = len(returns_asin_rows)

    order_filters = [Order.account_id.in_(accounts_query)]
    order_start, order_end = _order_datetime_bounds(date_from, date_to)
    if order_start:
        order_filters.append(Order.purchase_date >= order_start)
    if order_end:
        order_filters.append(Order.purchase_date < order_end)
    if asin:
        order_filters.append(OrderItem.asin == asin)

    ordered_units_total = int(
        (
            await db.execute(
                select(func.sum(OrderItem.quantity))
                .select_from(OrderItem)
                .join(Order, Order.id == OrderItem.order_id)
                .where(*order_filters)
            )
        ).scalar()
        or 0
    )
    return_rate_available = ordered_units_total > 0

    order_day_expr = cast(func.date_trunc("day", Order.purchase_date), Date)
    ordered_trend_rows = (
        await db.execute(
            select(
                order_day_expr.label("period_date"),
                func.sum(OrderItem.quantity).label("ordered_units"),
            )
            .select_from(OrderItem)
            .join(Order, Order.id == OrderItem.order_id)
            .where(*order_filters)
            .group_by(order_day_expr)
            .order_by(order_day_expr)
        )
    ).all()
    ordered_units_by_date = {
        row.period_date: int(row.ordered_units or 0)
        for row in ordered_trend_rows
    }

    return_rate_over_time = [
        ReturnsTrendPoint(
            date=row.period_date,
            returned_units=int(row.returned_units or 0),
            ordered_units=ordered_units_by_date.get(row.period_date),
            return_rate=_return_rate_percent(
                int(row.returned_units or 0),
                ordered_units_by_date.get(row.period_date),
            ),
        )
        for row in returns_trend_rows
    ]

    return_asins = [row.asin for row in returns_asin_rows if row.asin]
    ordered_units_by_asin: dict[str, int] = {}
    if return_asins:
        ordered_asin_rows = (
            await db.execute(
                select(
                    OrderItem.asin,
                    func.sum(OrderItem.quantity).label("ordered_units"),
                )
                .select_from(OrderItem)
                .join(Order, Order.id == OrderItem.order_id)
                .where(
                    *order_filters,
                    OrderItem.asin.is_not(None),
                    OrderItem.asin != "",
                    OrderItem.asin.in_(return_asins),
                )
                .group_by(OrderItem.asin)
            )
        ).all()
        ordered_units_by_asin = {
            row.asin: int(row.ordered_units or 0)
            for row in ordered_asin_rows
            if row.asin
        }

    asin_metrics_by_asin: dict[str, ReturnAsinMetric] = {}
    for row in returns_asin_rows:
        quantity_returned = int(row.quantity_returned or 0)
        ordered_units = ordered_units_by_asin.get(row.asin)
        asin_metrics_by_asin[row.asin] = ReturnAsinMetric(
            asin=row.asin,
            sku=row.sku,
            quantity_returned=quantity_returned,
            ordered_units=ordered_units,
            return_rate=_return_rate_percent(quantity_returned, ordered_units),
        )

    top_asins_by_returns = sorted(
        asin_metrics_by_asin.values(),
        key=lambda item: (-item.quantity_returned, item.asin),
    )[:limit]
    top_asins_by_return_rate = sorted(
        [item for item in asin_metrics_by_asin.values() if item.return_rate is not None],
        key=lambda item: (-float(item.return_rate or 0), -item.quantity_returned, item.asin),
    )[:limit]

    response_asins = sorted(
        {
            item.asin
            for item in top_asins_by_returns + top_asins_by_return_rate
            if item.asin
        }
    )
    if response_asins:
        asin_detail_rows = (
            await db.execute(
                select(
                    ReturnData.asin,
                    reason_expr.label("reason"),
                    disposition_expr.label("disposition"),
                    func.sum(ReturnData.quantity).label("quantity"),
                )
                .where(*returns_filters, ReturnData.asin.in_(response_asins))
                .group_by(ReturnData.asin, reason_expr, disposition_expr)
                .order_by(ReturnData.asin, func.sum(ReturnData.quantity).desc())
            )
        ).all()

        detail_map: dict[str, tuple[str, str]] = {}
        for row in asin_detail_rows:
            if row.asin not in detail_map:
                detail_map[row.asin] = (row.reason, row.disposition)

        for asin_value, (primary_reason, disposition) in detail_map.items():
            metric = asin_metrics_by_asin.get(asin_value)
            if metric:
                metric.primary_reason = primary_reason
                metric.disposition = disposition

    summary = ReturnsSummary(
        total_returns=total_returns,
        total_ordered_units=ordered_units_total,
        return_rate=_return_rate_percent(total_returns, ordered_units_total),
        return_rate_available=return_rate_available,
        top_reason=reason_rows[0].reason if reason_rows else None,
        unique_asins=unique_asins,
    )
    reason_breakdown = [
        ReturnReasonBreakdown(
            reason=row.reason,
            quantity=int(row.quantity or 0),
            share_percent=(
                float(
                    _decimal_ratio(
                        Decimal(int(row.quantity or 0)),
                        Decimal(total_returns),
                        multiplier=Decimal("100"),
                    )
                )
                if total_returns > 0
                else 0
            ),
        )
        for row in reason_rows
    ]

    return ReturnsAnalyticsResponse(
        summary=summary,
        return_rate_over_time=return_rate_over_time,
        reason_breakdown=reason_breakdown,
        top_asins_by_returns=top_asins_by_returns,
        top_asins_by_return_rate=top_asins_by_return_rate,
    )


@router.get("/comparison", response_model=ComparisonResponse)
async def get_comparison(
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
    period1_start: date = Query(...),
    period1_end: date = Query(...),
    period2_start: date = Query(...),
    period2_end: date = Query(...),
    account_ids: Optional[List[UUID]] = Query(default=None),
    category: Optional[str] = Query(default=None),
    preset: Optional[str] = Query(default=None),
):
    """Compare metrics between two periods."""
    return await _build_period_comparison(
        db=db,
        organization_id=organization.id,
        period_1_start=period1_start,
        period_1_end=period1_end,
        period_2_start=period2_start,
        period_2_end=period2_end,
        account_ids=account_ids,
        category=category,
        preset=preset,
    )


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
    asins = [row.asin for row in rows if row.asin]
    title_map: dict[str, str] = {}

    if asins:
        product_rows = (
            await db.execute(
                select(
                    Product.asin,
                    func.max(Product.title).label("title"),
                )
                .where(
                    Product.account_id.in_(accounts_query),
                    Product.asin.in_(asins),
                )
                .group_by(Product.asin)
            )
        ).all()
        title_map = {row.asin: row.title for row in product_rows if row.title}

    by_revenue = [
        ProductPerformance(
            asin=row.asin,
            title=title_map.get(row.asin),
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


@router.get("/product-trends", response_model=ProductTrendsResponse)
async def get_product_trends(
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
    start_date: date = Query(default=date.today() - timedelta(days=30)),
    end_date: date = Query(default=date.today()),
    account_id: Optional[UUID] = Query(default=None),
    account_ids: Optional[List[UUID]] = Query(default=None),
    asin: Optional[str] = Query(default=None),
    trend_class: Optional[str] = Query(
        default=None,
        pattern="^(rising_fast|rising|stable|declining|declining_fast)$",
    ),
    language: str = Query(default="en", pattern="^(en|it)$"),
    limit: int = Query(default=50, ge=1, le=100),
):
    """Get ranked product trends and structured insights."""
    _validate_period(start_date, end_date, "trend period")
    asin = _normalize_optional_asin(asin)

    scoped_account_ids = list(account_ids or [])
    if account_id and account_id not in scoped_account_ids:
        scoped_account_ids.append(account_id)

    accounts_stmt = select(AmazonAccount.id).where(
        AmazonAccount.organization_id == organization.id
    )
    if scoped_account_ids:
        accounts_stmt = accounts_stmt.where(AmazonAccount.id.in_(scoped_account_ids))

    resolved_account_ids = list((await db.execute(accounts_stmt)).scalars().all())
    trends_service = ProductTrendsService(db)
    trend_data = await trends_service.get_product_trends(
        account_ids=resolved_account_ids,
        start_date=start_date,
        end_date=end_date,
        language=language,
        organization_id=organization.id,
        asin=asin,
        trend_class=trend_class,
        limit=limit,
    )

    insights = build_rule_based_insights(
        trend_data["summary"],
        trend_data["rising_products"],
        trend_data["declining_products"],
        language=language,
    )
    generated_with_ai = False
    ai_available = bool(settings.ANTHROPIC_API_KEY)

    if ai_available and trend_data["summary"]["eligible_products"] > 0:
        try:
            ai_service = ProductTrendInsightsAnalysisService(settings.ANTHROPIC_API_KEY)
            insights = ai_service.analyze(
                trend_data=trend_data["insights_context"],
                language=language,
            )
            generated_with_ai = True
        except Exception:
            logger.exception("Falling back to deterministic product trend insights")

    return ProductTrendsResponse(
        summary=trend_data["summary"],
        rising_products=trend_data["rising_products"],
        declining_products=trend_data["declining_products"],
        products=trend_data["products"],
        insights=insights,
        generated_with_ai=generated_with_ai,
        ai_available=ai_available,
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
    overall_query = (
        select(
            func.sum(AdvertisingMetrics.cost).label("spend"),
            func.sum(AdvertisingMetrics.attributed_sales_7d).label("sales"),
            func.sum(AdvertisingMetrics.impressions).label("impressions"),
            func.sum(AdvertisingMetrics.clicks).label("clicks"),
        )
        .select_from(AdvertisingMetrics)
        .join(AdvertisingCampaign, AdvertisingCampaign.id == AdvertisingMetrics.campaign_id)
        .where(
            AdvertisingCampaign.account_id.in_(accounts_query),
            AdvertisingMetrics.date >= start_date,
            AdvertisingMetrics.date <= end_date,
        )
    )
    overall = (await db.execute(overall_query)).one()

    total_spend = Decimal(str(overall.spend or 0))
    total_sales = Decimal(str(overall.sales or 0))
    total_impressions = int(overall.impressions or 0)
    total_clicks = int(overall.clicks or 0)
    overall_roas = _decimal_ratio(total_sales, total_spend)
    overall_acos = _decimal_ratio(total_spend, total_sales, Decimal("100"))
    overall_ctr = _decimal_ratio(Decimal(total_clicks), Decimal(total_impressions), Decimal("100"))

    campaign_query = (
        select(
            AdvertisingCampaign.campaign_id.label("campaign_id"),
            AdvertisingCampaign.campaign_name.label("campaign_name"),
            AdvertisingCampaign.campaign_type.label("campaign_type"),
            AdvertisingCampaign.state.label("state"),
            func.sum(AdvertisingMetrics.cost).label("spend"),
            func.sum(AdvertisingMetrics.attributed_sales_7d).label("sales"),
            func.sum(AdvertisingMetrics.impressions).label("impressions"),
            func.sum(AdvertisingMetrics.clicks).label("clicks"),
        )
        .select_from(AdvertisingMetrics)
        .join(AdvertisingCampaign, AdvertisingCampaign.id == AdvertisingMetrics.campaign_id)
        .where(
            AdvertisingCampaign.account_id.in_(accounts_query),
            AdvertisingMetrics.date >= start_date,
            AdvertisingMetrics.date <= end_date,
        )
        .group_by(
            AdvertisingCampaign.campaign_id,
            AdvertisingCampaign.campaign_name,
            AdvertisingCampaign.campaign_type,
            AdvertisingCampaign.state,
        )
    )
    campaign_rows = (await db.execute(campaign_query)).all()

    campaign_metrics: list[dict[str, object]] = []
    for row in campaign_rows:
        spend = Decimal(str(row.spend or 0))
        sales = Decimal(str(row.sales or 0))
        impressions = int(row.impressions or 0)
        clicks = int(row.clicks or 0)

        campaign_metrics.append(
            {
                "campaign_id": row.campaign_id,
                "campaign_name": row.campaign_name,
                "campaign_type": row.campaign_type,
                "state": row.state,
                "spend": spend,
                "sales": sales,
                "impressions": impressions,
                "clicks": clicks,
                "roas": _decimal_ratio(sales, spend),
                "acos": _decimal_ratio(spend, sales, Decimal("100")),
                "ctr": _decimal_ratio(Decimal(clicks), Decimal(impressions), Decimal("100")),
            }
        )

    top_campaigns = sorted(
        campaign_metrics,
        key=lambda item: (item["sales"], item["roas"], item["clicks"]),
        reverse=True,
    )[:5]
    underperforming_campaigns = [
        item for item in campaign_metrics
        if item["spend"] > 0 and (
            item["sales"] == 0
            or item["roas"] < Decimal("1")
            or item["acos"] > Decimal("100")
        )
    ][:5]

    recommendations: list[str] = []
    if total_spend <= 0:
        recommendations.append("No advertising spend recorded for the selected period.")
    else:
        if overall_roas >= Decimal("3"):
            recommendations.append("High overall ROAS suggests room to scale budgets on winning campaigns.")
        if overall_acos > Decimal("30"):
            recommendations.append("Overall ACoS is elevated; review bids and search terms on the highest-spend campaigns.")
        if overall_ctr < Decimal("0.35"):
            recommendations.append("CTR is low; refresh targeting or creative on campaigns with high impressions and weak click-through.")
        if total_clicks > 0 and total_sales <= 0:
            recommendations.append("Clicks are not converting into attributed sales; inspect landing products and keyword relevance.")

    if not recommendations:
        recommendations.append("Advertising performance is stable in the selected period.")

    return AdvertisingInsights(
        total_spend=total_spend,
        total_sales=total_sales,
        total_impressions=total_impressions,
        total_clicks=total_clicks,
        overall_roas=overall_roas,
        overall_acos=overall_acos,
        overall_ctr=overall_ctr,
        top_campaigns=top_campaigns,
        underperforming_campaigns=underperforming_campaigns,
        recommendations=recommendations,
    )


@router.get("/admin/data-health")
async def get_data_health(
    _current_user: CurrentSuperuser,
    db: DbSession,
):
    """Return global retention-managed table health metrics."""
    table_stats: list[dict[str, object]] = []

    for table_name, date_column in DATA_HEALTH_TABLES:
        safe_table_name = _quoted_identifier(table_name)
        safe_date_column = _quoted_identifier(date_column)
        result = await db.execute(
            text(
                f"""
                SELECT
                    COUNT(*) AS record_count,
                    MIN({safe_date_column}) AS min_date,
                    MAX({safe_date_column}) AS max_date
                FROM {safe_table_name}
                """
            )
        )
        row = result.mappings().one()
        table_stats.append(
            {
                "table": table_name,
                "min_date": row["min_date"].isoformat() if row["min_date"] else None,
                "max_date": row["max_date"].isoformat() if row["max_date"] else None,
                "record_count": int(row["record_count"] or 0),
            }
        )

    return {
        "retention_months": settings.DATA_RETENTION_MONTHS,
        "archive_enabled": settings.DATA_ARCHIVE_ENABLED,
        "tables": table_stats,
    }
