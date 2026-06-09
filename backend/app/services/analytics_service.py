"""Analytics service for computing KPIs and trends."""
from datetime import date, datetime, timedelta
from typing import List, Dict, Any, Optional
from uuid import UUID
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, cast, Date, and_

from app.models.amazon_account import AccountType, AmazonAccount
from app.models.sales_data import SalesData
from app.models.advertising import AdvertisingMetrics, AdvertisingCampaign, AdvertisingMetricsByAsin
from app.models.product import Product, BSRHistory
from app.services.data_extraction import DAILY_TOTAL_ASIN
from app.services.granularity import Granularity, granularity_for_account_types
from app.services.sales_metrics import display_revenue_expr, display_units_expr


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
        """Get metrics for a specific period.

        Totals (revenue/units/orders) come from the DAILY_TOTAL_ASIN sentinel
        rows so they match what salesAndTrafficByDate reports. Active ASIN
        counts come from real per-ASIN rows, otherwise the sentinel itself
        would be counted as a product.
        """
        totals_query = (
            select(
                func.sum(display_revenue_expr()).label("revenue"),
                func.sum(display_units_expr()).label("units"),
                func.sum(SalesData.total_order_items).label("orders"),
            )
            .where(
                SalesData.account_id.in_(account_ids),
                SalesData.asin == DAILY_TOTAL_ASIN,
                SalesData.date >= start_date,
                SalesData.date <= end_date,
            )
        )

        totals_row = (await self.db.execute(totals_query)).one()

        active_asins_query = (
            select(func.count(func.distinct(SalesData.asin)))
            .where(
                SalesData.account_id.in_(account_ids),
                SalesData.asin != DAILY_TOTAL_ASIN,
                SalesData.date >= start_date,
                SalesData.date <= end_date,
            )
        )
        active_asins = int((await self.db.execute(active_asins_query)).scalar() or 0)

        revenue = float(totals_row.revenue or 0)
        units = int(totals_row.units or 0)
        orders = int(totals_row.orders or 0)

        return {
            "revenue": revenue,
            "units": units,
            "orders": orders,
            "average_order_value": revenue / orders if orders > 0 else 0,
            "active_asins": active_asins,
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
            value_expr = func.sum(display_revenue_expr())
        elif metric == "units":
            value_expr = func.sum(display_units_expr())
        elif metric == "orders":
            value_expr = func.sum(SalesData.total_order_items)
        else:
            raise ValueError(f"Unknown metric: {metric}")

        query = (
            select(SalesData.date, value_expr.label("value"))
            .where(
                SalesData.account_id.in_(account_ids),
                SalesData.asin == DAILY_TOTAL_ASIN,
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
            order_expr = func.sum(display_revenue_expr()).desc()
        elif sort_by == "units":
            order_expr = func.sum(display_units_expr()).desc()
        else:
            order_expr = func.sum(display_revenue_expr()).desc()

        query = (
            select(
                SalesData.asin,
                func.sum(display_revenue_expr()).label("revenue"),
                func.sum(display_units_expr()).label("units"),
                func.sum(SalesData.total_order_items).label("orders"),
            )
            .where(
                SalesData.account_id.in_(account_ids),
                SalesData.asin != DAILY_TOTAL_ASIN,
                SalesData.date >= start_date,
                SalesData.date <= end_date,
            )
            .group_by(SalesData.asin)
            .order_by(order_expr)
            .limit(limit)
        )

        result = await self.db.execute(query)
        rows = result.all()

        asins = [row.asin for row in rows]

        ad_query = (
            select(
                AdvertisingMetricsByAsin.asin,
                func.sum(AdvertisingMetricsByAsin.cost).label("ad_spend"),
                func.sum(AdvertisingMetricsByAsin.attributed_sales_7d).label("ad_sales"),
            )
            .where(
                AdvertisingMetricsByAsin.account_id.in_(account_ids),
                AdvertisingMetricsByAsin.asin.in_(asins),
                AdvertisingMetricsByAsin.date >= start_date,
                AdvertisingMetricsByAsin.date <= end_date,
            )
            .group_by(AdvertisingMetricsByAsin.asin)
        )
        ad_result = await self.db.execute(ad_query)
        ad_by_asin = {r.asin: r for r in ad_result.all()}

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

            ad = ad_by_asin.get(row.asin)
            ad_spend = float(ad.ad_spend) if ad and ad.ad_spend else 0.0
            ad_sales = float(ad.ad_sales) if ad and ad.ad_sales else 0.0
            ad_acos = (ad_spend / ad_sales * 100) if ad_sales > 0 else None
            ad_roas = (ad_sales / ad_spend) if ad_spend > 0 else None

            products.append({
                "asin": row.asin,
                "title": product.title if product else None,
                "revenue": float(row.revenue),
                "units": int(row.units),
                "orders": int(row.orders),
                "ad_spend": ad_spend,
                "ad_sales": ad_sales,
                "acos": round(ad_acos, 1) if ad_acos is not None else None,
                "roas": round(ad_roas, 2) if ad_roas is not None else None,
            })

        return products

    async def asin_sales_breakdown(
        self,
        account_ids: List[UUID],
        date_from: date,
        date_to: date,
    ) -> Dict[str, float]:
        """Snapshot-aware per-ASIN sales for a period, as an ``{asin: sales}`` map.

        Vendor per-ASIN rows are settled monthly figures and can be summed.
        Seller per-ASIN rows are trailing-window snapshots re-stamped on every
        sync, so summing them across dates multiplies a product's sales; for
        sellers we take the single most complete snapshot date instead. This is
        the same handling as :meth:`_fetch_asin_breakdown` but returns the full
        map (no top-N truncation) so callers can compute period-over-period
        deltas.
        """
        if not account_ids:
            return {}

        types_rows = (
            await self.db.execute(
                select(AmazonAccount.id, AmazonAccount.account_type).where(
                    AmazonAccount.id.in_(account_ids)
                )
            )
        ).all()
        vendor_ids = [r.id for r in types_rows if r.account_type == AccountType.VENDOR]
        seller_ids = [r.id for r in types_rows if r.account_type == AccountType.SELLER]

        contributions: Dict[str, float] = {}

        if vendor_ids:
            for row in await self._sum_asin_sales(vendor_ids, date_from, date_to):
                contributions[row.asin] = contributions.get(row.asin, 0.0) + self._as_float(
                    row.total_sales
                )

        for seller_id in seller_ids:
            snapshot_date = await self._latest_full_snapshot_date(
                seller_id, date_from, date_to
            )
            if snapshot_date is None:
                continue
            for row in await self._sum_asin_sales([seller_id], snapshot_date, snapshot_date):
                contributions[row.asin] = contributions.get(row.asin, 0.0) + self._as_float(
                    row.total_sales
                )

        return contributions

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

    async def _resolve_granularity(self, account_ids: List[UUID]) -> Granularity:
        """Resolve granularity from the resolved in-scope account ids."""
        if not account_ids:
            return Granularity.UNKNOWN
        account_types = (
            await self.db.execute(
                select(AmazonAccount.account_type).where(AmazonAccount.id.in_(account_ids))
            )
        ).scalars().all()
        return granularity_for_account_types(account_types)

    async def get_ads_vs_organic(
        self,
        account_ids: List[UUID],
        date_from: date,
        date_to: date,
        group_by: str = "day",
        asin: Optional[str] = None,
        language: str = "en",
    ) -> Dict[str, Any]:
        """Compare total sales with ad-attributed sales for the selected period."""
        self._validate_group_by(group_by)
        asin = self._normalize_optional_asin(asin)

        granularity = await self._resolve_granularity(account_ids)
        # Monthly (vendor-only) data cannot be split into coherent daily/weekly
        # buckets, so force a monthly cadence regardless of the requested group.
        if granularity == Granularity.MONTHLY and group_by != "month":
            group_by = "month"

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
                "Il filtro per ASIN restringe solo i dati di vendita; le metriche pubblicitarie restano a livello account perché i dati ad memorizzati sono basati sulle campagne."
                if language == "it"
                else "ASIN filtering narrows sales data only; advertising metrics remain account-level because stored ad data is campaign-based."
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
            "breakdown_notes": [],
            "group_by": group_by,
            "granularity": granularity.value,
            "asin": asin,
            "attribution_notes": attribution_notes,
        }

        if asin is None:
            breakdown, breakdown_notes = await self._fetch_asin_breakdown(
                account_ids=account_ids,
                date_from=date_from,
                date_to=date_to,
                language=language,
            )
            response["asin_breakdown"] = breakdown
            response["breakdown_notes"] = breakdown_notes

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
                func.sum(display_revenue_expr()).label("total_sales"),
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
        language: str = "en",
    ) -> tuple[List[Dict[str, Any]], List[str]]:
        """Return a sales breakdown by ASIN for the current period.

        Vendor per-ASIN rows are settled monthly figures, so summing them over a
        period is correct and reconciles with the account sentinel. Seller
        per-ASIN rows are a trailing-window snapshot re-stamped on every sync,
        so summing the same ASIN across dates multiplies its sales many times
        over. We therefore aggregate vendor and seller accounts separately: sum
        the vendor rows and, for each seller account, take the single most
        complete snapshot date. Shares are computed against the breakdown's own
        total so they always stay coherent (no ASIN above 100%)."""
        if not account_ids:
            return [], []

        types_rows = (
            await self.db.execute(
                select(AmazonAccount.id, AmazonAccount.account_type).where(
                    AmazonAccount.id.in_(account_ids)
                )
            )
        ).all()
        vendor_ids = [r.id for r in types_rows if r.account_type == AccountType.VENDOR]
        seller_ids = [r.id for r in types_rows if r.account_type == AccountType.SELLER]

        contributions: Dict[str, float] = {}
        has_seller_snapshot = False

        if vendor_ids:
            for row in await self._sum_asin_sales(vendor_ids, date_from, date_to):
                contributions[row.asin] = contributions.get(row.asin, 0.0) + self._as_float(
                    row.total_sales
                )

        for seller_id in seller_ids:
            snapshot_date = await self._latest_full_snapshot_date(
                seller_id, date_from, date_to
            )
            if snapshot_date is None:
                continue
            has_seller_snapshot = True
            for row in await self._sum_asin_sales(
                [seller_id], snapshot_date, snapshot_date
            ):
                contributions[row.asin] = contributions.get(row.asin, 0.0) + self._as_float(
                    row.total_sales
                )

        if not contributions:
            return [], []

        titles = await self._asin_titles(account_ids, list(contributions.keys()))
        breakdown_total = sum(contributions.values())

        ranked = sorted(contributions.items(), key=lambda kv: (-kv[1], kv[0]))[:25]
        breakdown = [
            {
                "asin": asin,
                "title": titles.get(asin),
                "total_sales": self._round_money(value),
                "sales_share_pct": self._round_percent(self._share(value, breakdown_total)),
            }
            for asin, value in ranked
        ]

        notes: List[str] = []
        if has_seller_snapshot:
            notes.append(
                "Per gli account Seller la ripartizione per ASIN usa lo snapshot più completo del periodo (i report per-ASIN di Amazon sono cumulativi e non si possono sommare per giorno). Il totale dell'account resta basato sulle vendite confermate."
                if language == "it"
                else "For Seller accounts the per-ASIN breakdown uses the period's most complete snapshot (Amazon's by-ASIN reports are cumulative and cannot be summed per day). The account total stays based on confirmed sales."
            )

        return breakdown, notes

    async def _sum_asin_sales(self, account_ids, date_from: date, date_to: date):
        """Sum per-ASIN sales for the given accounts and date range."""
        query = (
            select(
                SalesData.asin.label("asin"),
                func.sum(display_revenue_expr()).label("total_sales"),
            )
            .where(
                SalesData.account_id.in_(account_ids),
                SalesData.asin != DAILY_TOTAL_ASIN,
                SalesData.date >= date_from,
                SalesData.date <= date_to,
            )
            .group_by(SalesData.asin)
        )
        return (await self.db.execute(query)).all()

    async def _latest_full_snapshot_date(
        self, account_id: UUID, date_from: date, date_to: date
    ) -> Optional[date]:
        """Return the snapshot date with the most per-ASIN sales for a seller.

        Seller per-ASIN rows are trailing-window snapshots, so we pick the date
        whose snapshot carries the most sales to best approximate the account's
        product mix without double-counting overlapping windows."""
        query = (
            select(
                SalesData.date.label("date"),
                func.sum(display_revenue_expr()).label("total_sales"),
            )
            .where(
                SalesData.account_id == account_id,
                SalesData.asin != DAILY_TOTAL_ASIN,
                SalesData.date >= date_from,
                SalesData.date <= date_to,
            )
            .group_by(SalesData.date)
            .order_by(func.sum(display_revenue_expr()).desc(), SalesData.date.desc())
            .limit(1)
        )
        row = (await self.db.execute(query)).first()
        if row is None or self._as_float(row.total_sales) <= 0:
            return None
        return row.date

    async def _asin_titles(self, account_ids, asins) -> Dict[str, Optional[str]]:
        """Resolve product titles for a set of ASINs in scope."""
        if not asins:
            return {}
        rows = (
            await self.db.execute(
                select(Product.asin, func.max(Product.title).label("title"))
                .where(
                    Product.account_id.in_(account_ids),
                    Product.asin.in_(asins),
                )
                .group_by(Product.asin)
            )
        ).all()
        return {row.asin: row.title for row in rows}

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
