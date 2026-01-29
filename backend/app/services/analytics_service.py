"""Analytics service for computing KPIs and trends."""
from datetime import date, timedelta
from typing import List, Dict, Any, Optional
from uuid import UUID
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.models.sales_data import SalesData
from app.models.advertising import AdvertisingMetrics, AdvertisingCampaign
from app.models.product import Product, BSRHistory


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
