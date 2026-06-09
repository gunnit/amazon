"""Brand Pulse — a rolling brand-intelligence snapshot.

Assembles existing analytics primitives into one payload: a sales overview
(current period vs the immediately preceding one), top ASINs, declining ASINs,
and an advertising block with ACOS/TACOS that degrades gracefully when no ad
data covers the window. Recommendations are attached by the recommendation
layer; this service leaves the list empty.

All numbers are computed deterministically from synced Amazon data — nothing
here is inferred or AI-generated.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.analytics_service import AnalyticsService
from app.services.granularity import Granularity
from app.services.strategic_recommendations_service import build_pulse_recommendations

# Mirror AnalyticsService's trend thresholds so Pulse and the dashboards agree.
DECLINE_THRESHOLD_PCT = -5.0
DECLINE_FAST_THRESHOLD_PCT = -20.0


class BrandPulseService:
    """Compose analytics primitives into a Brand Pulse payload."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.analytics = AnalyticsService(db)

    async def build_pulse(
        self,
        account_ids: List[UUID],
        *,
        end_date: date,
        window_days: int = 30,
        top_limit: int = 10,
        language: str = "en",
    ) -> Dict[str, Any]:
        start_date = end_date - timedelta(days=window_days - 1)
        prev_end = start_date - timedelta(days=1)
        prev_start = prev_end - timedelta(days=window_days - 1)

        overview = await self.analytics.compute_dashboard_kpis(
            account_ids, start_date, end_date
        )

        # Monthly-cadence (vendor) accounts report one settled row per month and
        # trail by weeks, so a rolling window with no posted data yet is a
        # reporting-lag artifact, not a real collapse. Flag it so the UI and the
        # recommendation rules don't raise a false "-100%" alarm.
        granularity = await self.analytics._resolve_granularity(account_ids)
        awaiting_data = (
            granularity == Granularity.MONTHLY
            and float(overview["current"]["revenue"]) == 0.0
        )

        current_map = await self.analytics.asin_sales_breakdown(
            account_ids, start_date, end_date
        )
        previous_map = await self.analytics.asin_sales_breakdown(
            account_ids, prev_start, prev_end
        )
        titles = await self._titles(account_ids, current_map, previous_map)

        ads = await self._ads_block(
            account_ids,
            start_date,
            end_date,
            total_revenue=float(overview["current"]["revenue"]),
        )
        payload = {
            "period": {
                "start": start_date,
                "end": end_date,
                "previous_start": prev_start,
                "previous_end": prev_end,
                "window_days": window_days,
                "cadence": granularity.value,
                "awaiting_data": awaiting_data,
            },
            "overview": overview,
            "top_asins": self._top_asins(current_map, previous_map, titles, top_limit),
            "declining_asins": self._declining_asins(
                current_map, previous_map, titles, top_limit
            ),
            "ads": ads,
            "recommendations": [],
        }
        payload["recommendations"] = build_pulse_recommendations(payload, language=language)
        return payload

    async def _titles(
        self, account_ids: List[UUID], current_map: Dict[str, float], previous_map: Dict[str, float]
    ) -> Dict[str, Optional[str]]:
        asins = sorted(set(current_map) | set(previous_map))
        if not asins:
            return {}
        return await self.analytics._asin_titles(account_ids, asins)

    def _top_asins(
        self,
        current_map: Dict[str, float],
        previous_map: Dict[str, float],
        titles: Dict[str, Optional[str]],
        limit: int,
    ) -> List[Dict[str, Any]]:
        ranked = sorted(current_map.items(), key=lambda kv: (-kv[1], kv[0]))[:limit]
        return [
            {
                "asin": asin,
                "title": titles.get(asin),
                "revenue": round(sales, 2),
                "previous_revenue": round(previous_map.get(asin, 0.0), 2),
                "change_percent": self._change_percent(sales, previous_map.get(asin, 0.0)),
            }
            for asin, sales in ranked
        ]

    def _declining_asins(
        self,
        current_map: Dict[str, float],
        previous_map: Dict[str, float],
        titles: Dict[str, Optional[str]],
        limit: int,
    ) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for asin, previous in previous_map.items():
            if previous <= 0:
                continue
            current = current_map.get(asin, 0.0)
            change = (current - previous) / previous * 100
            if change > DECLINE_THRESHOLD_PCT:
                continue
            rows.append(
                {
                    "asin": asin,
                    "title": titles.get(asin),
                    "revenue": round(current, 2),
                    "previous_revenue": round(previous, 2),
                    "change_percent": round(change, 1),
                    "trend_class": (
                        "declining_fast"
                        if change < DECLINE_FAST_THRESHOLD_PCT
                        else "declining"
                    ),
                }
            )
        rows.sort(key=lambda row: row["change_percent"])
        return rows[:limit]

    async def _ads_block(
        self,
        account_ids: List[UUID],
        start_date: date,
        end_date: date,
        *,
        total_revenue: float,
    ) -> Dict[str, Any]:
        ads = await self.analytics.compute_advertising_metrics(
            account_ids, start_date, end_date
        )
        # Same coverage gate the dashboard uses: no impressions/clicks/spend in
        # the window means advertising is not connected for this period.
        available = bool(ads.get("impressions") or ads.get("clicks") or ads.get("cost"))
        if not available:
            return {"is_available": False, "unavailable_reason": "ads_not_connected"}

        spend = float(ads.get("cost") or 0.0)
        return {
            "is_available": True,
            "spend": round(spend, 2),
            "ad_sales": round(float(ads.get("sales") or 0.0), 2),
            "acos": round(float(ads.get("acos") or 0.0), 1),
            "tacos": round(spend / total_revenue * 100, 1) if total_revenue > 0 else None,
            "roas": round(float(ads.get("roas") or 0.0), 2),
            # Ad sales use Amazon's 7-day attribution window (AdvertisingMetrics).
            "attribution_window": "7d",
        }

    @staticmethod
    def _change_percent(current: float, previous: float) -> float:
        if previous > 0:
            return round((current - previous) / previous * 100, 1)
        return 100.0 if current > 0 else 0.0
