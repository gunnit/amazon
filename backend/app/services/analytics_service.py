"""Analytics service for computing KPIs and trends."""
from datetime import date, datetime, timedelta
from typing import List, Dict, Any, Optional
from uuid import UUID
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, cast, Date, and_

from app.models.sales_data import SalesData
from app.models.advertising import AdvertisingMetrics, AdvertisingCampaign
from app.models.product import Product, BSRHistory
from app.services.data_extraction import DAILY_TOTAL_ASIN


class AnalyticsService:
    """Service for analytics computations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def compute_dashboard_kpis(
        self,
        account_ids: List[UUID],
        start_date: date,
        end_date: date,
    ) -> Dict[str, Any]:
        """Compute dashboard KPIs for specified accounts and date range."""
        # Calculate previous period for comparison
        period_days = (end_date - start_date).days
        prev_start = start_date - timedelta(days=period_days + 1)
        prev_end = start_date - timedelta(days=1)

        # Current period metrics
        current = await self._get_period_metrics(account_ids, start_date, end_date)
        previous = await self._get_period_metrics(account_ids, prev_start, prev_end)

        return {
            "current": current,
            "previous": previous,
            "changes": self._calculate_changes(current, previous),
        }

    async def _get_period_metrics(
        self,
        account_ids: List[UUID],
        start_date: date,
        end_date: date,
    ) -> Dict[str, Any]:
        """Get metrics for a specific period."""
        query = (
            select(
                func.sum(SalesData.ordered_product_sales).label("revenue"),
                func.sum(SalesData.units_ordered).label("units"),
                func.sum(SalesData.total_order_items).label("orders"),
                func.count(func.distinct(SalesData.asin)).label("active_asins"),
            )
            .where(
                SalesData.account_id.in_(account_ids),
                SalesData.date >= start_date,
                SalesData.date <= end_date,
            )
        )

        result = await self.db.execute(query)
        row = result.one()

        revenue = float(row.revenue or 0)
        units = int(row.units or 0)
        orders = int(row.orders or 0)

        return {
            "revenue": revenue,
            "units": units,
            "orders": orders,
            "average_order_value": revenue / orders if orders > 0 else 0,
            "active_asins": row.active_asins or 0,
        }

    def _calculate_changes(
        self,
        current: Dict[str, Any],
        previous: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Calculate percentage changes between periods."""
        changes = {}
        for key in ["revenue", "units", "orders", "average_order_value"]:
            curr_val = current.get(key, 0)
            prev_val = previous.get(key, 0)

            if prev_val > 0:
                change = ((curr_val - prev_val) / prev_val) * 100
            elif curr_val > 0:
                change = 100
            else:
                change = 0

            changes[key] = {
                "absolute": curr_val - prev_val,
                "percent": round(change, 2),
                "trend": "up" if change > 5 else ("down" if change < -5 else "stable"),
            }

        return changes

    async def compute_trends(
        self,
        account_ids: List[UUID],
        metric: str,
        start_date: date,
        end_date: date,
        group_by: str = "day",
    ) -> List[Dict[str, Any]]:
        """Compute trend data for a metric."""
        if metric == "revenue":
            value_expr = func.sum(SalesData.ordered_product_sales)
        elif metric == "units":
            value_expr = func.sum(SalesData.units_ordered)
        elif metric == "orders":
            value_expr = func.sum(SalesData.total_order_items)
        else:
            raise ValueError(f"Unknown metric: {metric}")

        query = (
            select(SalesData.date, value_expr.label("value"))
            .where(
                SalesData.account_id.in_(account_ids),
                SalesData.date >= start_date,
                SalesData.date <= end_date,
            )
            .group_by(SalesData.date)
            .order_by(SalesData.date)
        )

        result = await self.db.execute(query)
        rows = result.all()

        return [
            {"date": row.date.isoformat(), "value": float(row.value or 0)}
            for row in rows
        ]

    async def get_top_products(
        self,
        account_ids: List[UUID],
        start_date: date,
        end_date: date,
        sort_by: str = "revenue",
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Get top performing products."""
        if sort_by == "revenue":
            order_expr = func.sum(SalesData.ordered_product_sales).desc()
        elif sort_by == "units":
            order_expr = func.sum(SalesData.units_ordered).desc()
        else:
            order_expr = func.sum(SalesData.ordered_product_sales).desc()

        query = (
            select(
                SalesData.asin,
                func.sum(SalesData.ordered_product_sales).label("revenue"),
                func.sum(SalesData.units_ordered).label("units"),
                func.sum(SalesData.total_order_items).label("orders"),
            )
            .where(
                SalesData.account_id.in_(account_ids),
                SalesData.date >= start_date,
                SalesData.date <= end_date,
            )
            .group_by(SalesData.asin)
            .order_by(order_expr)
            .limit(limit)
        )

        result = await self.db.execute(query)
        rows = result.all()

        # Get product details
        products = []
        for row in rows:
            product_result = await self.db.execute(
                select(Product)
                .where(
                    Product.asin == row.asin,
                    Product.account_id.in_(account_ids),
                )
                .limit(1)
            )
            product = product_result.scalar_one_or_none()

            products.append({
                "asin": row.asin,
                "title": product.title if product else None,
                "revenue": float(row.revenue),
                "units": int(row.units),
                "orders": int(row.orders),
            })

        return products

    async def compute_advertising_metrics(
        self,
        account_ids: List[UUID],
        start_date: date,
        end_date: date,
    ) -> Dict[str, Any]:
        """Compute advertising performance metrics."""
        campaigns_query = select(AdvertisingCampaign.id).where(
            AdvertisingCampaign.account_id.in_(account_ids)
        )

        query = (
            select(
                func.sum(AdvertisingMetrics.impressions).label("impressions"),
                func.sum(AdvertisingMetrics.clicks).label("clicks"),
                func.sum(AdvertisingMetrics.cost).label("cost"),
                func.sum(AdvertisingMetrics.attributed_sales_7d).label("sales"),
            )
            .where(
                AdvertisingMetrics.campaign_id.in_(campaigns_query),
                AdvertisingMetrics.date >= start_date,
                AdvertisingMetrics.date <= end_date,
            )
        )

        result = await self.db.execute(query)
        row = result.one()

        impressions = int(row.impressions or 0)
        clicks = int(row.clicks or 0)
        cost = float(row.cost or 0)
        sales = float(row.sales or 0)

        return {
            "impressions": impressions,
            "clicks": clicks,
            "cost": cost,
            "sales": sales,
            "ctr": (clicks / impressions * 100) if impressions > 0 else 0,
            "cpc": cost / clicks if clicks > 0 else 0,
            "acos": (cost / sales * 100) if sales > 0 else 0,
            "roas": sales / cost if cost > 0 else 0,
        }

    async def get_ads_vs_organic(
        self,
        account_ids: List[UUID],
        date_from: date,
        date_to: date,
        group_by: str = "day",
        asin: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Compare total sales with ad-attributed sales for the selected period."""
        self._validate_group_by(group_by)
        asin = self._normalize_optional_asin(asin)

        current_series = await self._fetch_ads_vs_organic_series(
            account_ids=account_ids,
            date_from=date_from,
            date_to=date_to,
            group_by=group_by,
            asin=asin,
        )

        prev_start, prev_end = self._previous_period(date_from, date_to)
        previous_series = await self._fetch_ads_vs_organic_series(
            account_ids=account_ids,
            date_from=prev_start,
            date_to=prev_end,
            group_by=group_by,
            asin=asin,
        )

        current_totals = self._summarize_ads_vs_organic(current_series)
        previous_totals = self._summarize_ads_vs_organic(previous_series)
        attribution_notes: list[str] = []
        if asin:
            attribution_notes.append(
                "ASIN filtering narrows sales data only; advertising metrics remain account-level because stored ad data is campaign-based."
            )

        response: Dict[str, Any] = {
            "summary": {
                "total_sales": self._build_metric_value(
                    current_totals["total_sales"], previous_totals["total_sales"]
                ),
                "ad_sales": self._build_metric_value(
                    current_totals["ad_sales"], previous_totals["ad_sales"]
                ),
                "organic_sales": self._build_metric_value(
                    current_totals["organic_sales"], previous_totals["organic_sales"]
                ),
                "ad_share_pct": self._build_metric_value(
                    current_totals["ad_share_pct"], previous_totals["ad_share_pct"]
                ),
                "organic_share_pct": self._build_metric_value(
                    current_totals["organic_share_pct"], previous_totals["organic_share_pct"]
                ),
                "period_start": date_from,
                "period_end": date_to,
                "previous_period_start": prev_start,
                "previous_period_end": prev_end,
            },
            "time_series": current_series,
            "asin_breakdown": None,
            "group_by": group_by,
            "asin": asin,
            "attribution_notes": attribution_notes,
        }

        if asin is None:
            response["asin_breakdown"] = await self._fetch_asin_breakdown(
                account_ids=account_ids,
                date_from=date_from,
                date_to=date_to,
                total_sales=current_totals["total_sales"],
            )

        return response

    async def _fetch_ads_vs_organic_series(
        self,
        account_ids: List[UUID],
        date_from: date,
        date_to: date,
        group_by: str,
        asin: Optional[str],
    ) -> List[Dict[str, Any]]:
        """Fetch aligned sales and ad sales for each account/date bucket."""
        if date_from > date_to:
            raise ValueError("date_from must be on or before date_to")

        bucket_dates = list(self._iter_bucket_dates(date_from, date_to, group_by))
        if not account_ids:
            return [self._empty_time_series_point(bucket_date) for bucket_date in bucket_dates]

        sales_bucket = self._bucket_expression(SalesData.date, group_by).label("bucket_date")
        sales_filters = [
            SalesData.account_id.in_(account_ids),
            SalesData.date >= date_from,
            SalesData.date <= date_to,
        ]
        if asin:
            sales_filters.append(SalesData.asin == asin)
        else:
            sales_filters.append(SalesData.asin == DAILY_TOTAL_ASIN)

        sales_query = (
            select(
                SalesData.account_id.label("account_id"),
                sales_bucket,
                func.sum(SalesData.ordered_product_sales).label("total_sales"),
            )
            .where(*sales_filters)
            .group_by(SalesData.account_id, sales_bucket)
            .order_by(sales_bucket, SalesData.account_id)
        )

        campaign_accounts = (
            select(
                AdvertisingCampaign.id.label("campaign_id"),
                AdvertisingCampaign.account_id.label("account_id"),
            )
            .where(AdvertisingCampaign.account_id.in_(account_ids))
            .subquery()
        )
        ads_bucket = self._bucket_expression(AdvertisingMetrics.date, group_by).label("bucket_date")
        ads_query = (
            select(
                campaign_accounts.c.account_id.label("account_id"),
                ads_bucket,
                func.sum(AdvertisingMetrics.attributed_sales_7d).label("ad_sales"),
            )
            .select_from(AdvertisingMetrics)
            .join(
                campaign_accounts,
                campaign_accounts.c.campaign_id == AdvertisingMetrics.campaign_id,
            )
            .where(
                AdvertisingMetrics.date >= date_from,
                AdvertisingMetrics.date <= date_to,
            )
            .group_by(campaign_accounts.c.account_id, ads_bucket)
            .order_by(ads_bucket, campaign_accounts.c.account_id)
        )

        sales_rows = (await self.db.execute(sales_query)).all()
        ads_rows = (await self.db.execute(ads_query)).all()

        aligned: Dict[tuple[UUID, date], Dict[str, float]] = {}
        for row in sales_rows:
            key = (row.account_id, self._normalize_bucket_date(row.bucket_date))
            aligned[key] = {
                "total_sales": self._as_float(row.total_sales),
                "ad_sales": aligned.get(key, {}).get("ad_sales", 0.0),
            }

        for row in ads_rows:
            key = (row.account_id, self._normalize_bucket_date(row.bucket_date))
            slot = aligned.setdefault(key, {"total_sales": 0.0, "ad_sales": 0.0})
            slot["ad_sales"] = self._as_float(row.ad_sales)

        totals_by_bucket: Dict[date, Dict[str, float]] = {}
        for (_account_id, bucket_date), values in aligned.items():
            bucket_totals = totals_by_bucket.setdefault(
                bucket_date,
                {"total_sales": 0.0, "ad_sales": 0.0},
            )
            bucket_totals["total_sales"] += values["total_sales"]
            bucket_totals["ad_sales"] += values["ad_sales"]

        series: list[Dict[str, Any]] = []
        for bucket_date in bucket_dates:
            bucket_totals = totals_by_bucket.get(bucket_date, {"total_sales": 0.0, "ad_sales": 0.0})
            total_sales = self._round_money(bucket_totals["total_sales"])
            ad_sales = self._round_money(bucket_totals["ad_sales"])
            organic_sales = self._round_money(max(total_sales - ad_sales, 0.0))
            series.append(
                {
                    "date": bucket_date,
                    "total_sales": total_sales,
                    "ad_sales": ad_sales,
                    "organic_sales": organic_sales,
                    "ad_share_pct": self._round_percent(self._share(ad_sales, total_sales)),
                    "organic_share_pct": self._round_percent(self._share(organic_sales, total_sales)),
                }
            )

        return series

    async def _fetch_asin_breakdown(
        self,
        account_ids: List[UUID],
        date_from: date,
        date_to: date,
        total_sales: float,
    ) -> List[Dict[str, Any]]:
        """Return a sales breakdown by ASIN for the current period."""
        if not account_ids:
            return []

        breakdown_query = (
            select(
                SalesData.asin.label("asin"),
                func.max(Product.title).label("title"),
                func.sum(SalesData.ordered_product_sales).label("total_sales"),
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
                SalesData.account_id.in_(account_ids),
                SalesData.asin != DAILY_TOTAL_ASIN,
                SalesData.date >= date_from,
                SalesData.date <= date_to,
            )
            .group_by(SalesData.asin)
            .order_by(func.sum(SalesData.ordered_product_sales).desc(), SalesData.asin)
            .limit(25)
        )
        rows = (await self.db.execute(breakdown_query)).all()

        return [
            {
                "asin": row.asin,
                "title": row.title,
                "total_sales": self._round_money(self._as_float(row.total_sales)),
                "sales_share_pct": self._round_percent(
                    self._share(self._as_float(row.total_sales), total_sales)
                ),
            }
            for row in rows
        ]

    def _bucket_expression(self, column, group_by: str):
        """Return a normalized SQL expression for the requested time bucket."""
        if group_by == "day":
            return column
        return cast(func.date_trunc(group_by, column), Date)

    def _iter_bucket_dates(self, date_from: date, date_to: date, group_by: str):
        """Yield bucket start dates for the selected period."""
        current = self._bucket_floor(date_from, group_by)
        end = self._bucket_floor(date_to, group_by)
        while current <= end:
            yield current
            current = self._next_bucket_date(current, group_by)

    def _bucket_floor(self, value: date, group_by: str) -> date:
        """Floor a date to the start of its bucket."""
        if group_by == "day":
            return value
        if group_by == "week":
            return value - timedelta(days=value.weekday())
        if group_by == "month":
            return value.replace(day=1)
        raise ValueError(f"Unsupported group_by: {group_by}")

    def _next_bucket_date(self, value: date, group_by: str) -> date:
        """Advance to the next bucket date."""
        if group_by == "day":
            return value + timedelta(days=1)
        if group_by == "week":
            return value + timedelta(days=7)
        if group_by == "month":
            return (value.replace(day=28) + timedelta(days=4)).replace(day=1)
        raise ValueError(f"Unsupported group_by: {group_by}")

    def _previous_period(self, date_from: date, date_to: date) -> tuple[date, date]:
        """Return the preceding inclusive period."""
        period_days = (date_to - date_from).days + 1
        previous_end = date_from - timedelta(days=1)
        previous_start = previous_end - timedelta(days=period_days - 1)
        return previous_start, previous_end

    def _summarize_ads_vs_organic(self, time_series: List[Dict[str, Any]]) -> Dict[str, float]:
        """Roll time-series rows into period totals."""
        total_sales = sum(self._as_float(point["total_sales"]) for point in time_series)
        ad_sales = sum(self._as_float(point["ad_sales"]) for point in time_series)
        organic_sales = max(total_sales - ad_sales, 0.0)

        total_sales = self._round_money(total_sales)
        ad_sales = self._round_money(ad_sales)
        organic_sales = self._round_money(organic_sales)

        return {
            "total_sales": total_sales,
            "ad_sales": ad_sales,
            "organic_sales": organic_sales,
            "ad_share_pct": self._round_percent(self._share(ad_sales, total_sales)),
            "organic_share_pct": self._round_percent(self._share(organic_sales, total_sales)),
        }

    def _build_metric_value(self, current: float, previous: float) -> Dict[str, Any]:
        """Build a dashboard-style metric payload."""
        change_percent, trend = self._change_and_trend(current, previous)
        return {
            "value": current,
            "previous_value": previous,
            "change_percent": change_percent,
            "trend": trend,
        }

    def _change_and_trend(self, current: float, previous: float) -> tuple[float, str]:
        """Calculate percent change and trend direction."""
        if previous > 0:
            change = ((current - previous) / previous) * 100
        elif current > 0:
            change = 100.0
        else:
            change = 0.0

        change = round(change, 2)
        trend = "up" if change > 5 else ("down" if change < -5 else "stable")
        return change, trend

    def _share(self, numerator: float, denominator: float) -> float:
        """Return the share percentage for two values."""
        if denominator <= 0:
            return 0.0
        return (numerator / denominator) * 100

    def _empty_time_series_point(self, bucket_date: date) -> Dict[str, Any]:
        """Return an empty time-series row."""
        return {
            "date": bucket_date,
            "total_sales": 0.0,
            "ad_sales": 0.0,
            "organic_sales": 0.0,
            "ad_share_pct": 0.0,
            "organic_share_pct": 0.0,
        }

    def _normalize_bucket_date(self, value: Any) -> date:
        """Normalize SQL bucket results to date values."""
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        if isinstance(value, str):
            return date.fromisoformat(value[:10])
        raise TypeError(f"Unsupported bucket value: {value!r}")

    def _validate_group_by(self, group_by: str) -> None:
        """Validate time grouping values."""
        if group_by not in {"day", "week", "month"}:
            raise ValueError(f"Unsupported group_by: {group_by}")

    def _round_money(self, value: float) -> float:
        """Round a monetary value for API responses."""
        return round(value, 2)

    def _round_percent(self, value: float) -> float:
        """Round percentage values for API responses."""
        return round(value, 2)

    def _as_float(self, value: Any) -> float:
        """Convert query values to floats safely."""
        return float(value or 0)

    def _normalize_optional_asin(self, asin: Optional[str]) -> Optional[str]:
        """Normalize optional ASIN filters for consistent lookups."""
        if asin is None:
            return None
        normalized = asin.strip().upper()
        return normalized or None
