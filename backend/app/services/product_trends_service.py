"""Product trend scoring and insights service."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert import Alert, AlertRule
from app.models.inventory import InventoryData
from app.models.product import BSRHistory, Product
from app.models.sales_data import SalesData
from app.services.data_extraction import DAILY_TOTAL_ASIN


MIN_COMBINED_UNITS = 5
TREND_WINDOW_DAYS = 7
SPARKLINE_WINDOW_DAYS = 14
ALERT_COOLDOWN_HOURS = 12
DEFAULT_RANKING_LIMIT = 25
TREND_ALERT_TYPE = "product_trend"
TREND_ALERT_RULE_NAME = "Automatic product trend alerts"
TREND_ALERT_EVENT_KIND = "product_trend_declining_fast"
TREND_ALERT_CLASSES = {"declining_fast"}


def _clamp(value: float, *, minimum: float = -100.0, maximum: float = 100.0) -> float:
    return max(minimum, min(maximum, value))


def _percent_change(current: float, previous: float) -> float:
    if previous == 0:
        return 100.0 if current > 0 else 0.0
    return ((current - previous) / previous) * 100.0


def _bsr_change_percent(current_bsr: Optional[int], previous_bsr: Optional[int]) -> Optional[float]:
    if current_bsr is None or previous_bsr is None or previous_bsr <= 0:
        return None
    return ((previous_bsr - current_bsr) / previous_bsr) * 100.0


def _score_components(
    sales_change_percent: float,
    units_change_percent: float,
    bsr_change_percent: Optional[float],
    review_velocity_change_percent: Optional[float] = None,
) -> float:
    weighted_components = [
        (_clamp(sales_change_percent), 0.60),
        (_clamp(units_change_percent), 0.25),
    ]
    if bsr_change_percent is not None:
        weighted_components.append((_clamp(bsr_change_percent), 0.15))
    if review_velocity_change_percent is not None:
        weighted_components.append((_clamp(review_velocity_change_percent), 0.05))

    total_weight = sum(weight for _, weight in weighted_components)
    if total_weight <= 0:
        return 0.0

    return round(
        sum(component * weight for component, weight in weighted_components) / total_weight,
        2,
    )


def _trend_class_from_delta(sales_delta_percent: float) -> str:
    if sales_delta_percent > 20:
        return "rising_fast"
    if sales_delta_percent > 5:
        return "rising"
    if sales_delta_percent < -20:
        return "declining_fast"
    if sales_delta_percent < -5:
        return "declining"
    return "stable"


def _direction_from_trend_class(trend_class: str) -> str:
    if trend_class.startswith("rising"):
        return "up"
    if trend_class.startswith("declining"):
        return "down"
    return "stable"


def _direction_from_score(score: float) -> str:
    if score > 5:
        return "up"
    if score < -5:
        return "down"
    return "stable"


def _strength_from_score(score: float) -> str:
    magnitude = abs(score)
    if magnitude >= 40:
        return "strong"
    if magnitude >= 12:
        return "moderate"
    return "weak"


def _strength_from_trend_class(trend_class: str, score: float) -> str:
    if trend_class in {"rising_fast", "declining_fast"}:
        return "strong"
    if trend_class in {"rising", "declining"}:
        return "moderate" if abs(score) >= 12 else "weak"
    return "weak"


def _data_quality(
    *,
    current_units: int,
    previous_units: int,
    current_revenue: float,
    previous_revenue: float,
    current_bsr: Optional[int],
    previous_bsr: Optional[int],
) -> str:
    has_current = current_units > 0 or current_revenue > 0
    has_previous = previous_units > 0 or previous_revenue > 0
    has_bsr = current_bsr is not None and previous_bsr is not None

    if has_current and has_previous and has_bsr:
        return "high"
    if has_current and has_previous:
        return "medium"
    return "low"


def _reason_tags(
    *,
    sales_change_percent: float,
    units_change_percent: float,
    bsr_change_percent: Optional[float],
    quality: str,
) -> List[str]:
    tags: List[str] = []
    if sales_change_percent >= 10:
        tags.append("revenue_growth")
    elif sales_change_percent <= -10:
        tags.append("revenue_decline")

    if units_change_percent >= 10:
        tags.append("units_growth")
    elif units_change_percent <= -10:
        tags.append("units_decline")

    if bsr_change_percent is None:
        tags.append("bsr_missing")
    elif bsr_change_percent >= 8:
        tags.append("bsr_improved")
    elif bsr_change_percent <= -8:
        tags.append("bsr_declined")

    if quality == "low":
        tags.append("limited_history")

    return tags


def _empty_response(language: str) -> Dict[str, Any]:
    if language == "it":
        summary = "Dati insufficienti per identificare trend affidabili nel periodo selezionato."
    else:
        summary = "There is not enough product history to identify reliable trends for the selected period."

    return {
        "summary": {
            "eligible_products": 0,
            "rising_count": 0,
            "declining_count": 0,
            "stable_count": 0,
            "average_trend_score": 0.0,
            "trend_class_counts": {
                "rising_fast": 0,
                "rising": 0,
                "stable": 0,
                "declining": 0,
                "declining_fast": 0,
            },
            "strongest_riser": None,
            "strongest_decliner": None,
        },
        "rising_products": [],
        "declining_products": [],
        "products": [],
        "insights": {
            "summary": summary,
            "key_trends": [],
            "risks": [],
            "opportunities": [],
            "recommendations": [],
        },
        "generated_with_ai": False,
        "ai_available": False,
    }


def _display_name(product: Dict[str, Any]) -> str:
    return product.get("title") or product.get("asin") or "Unknown product"


def _build_recommendation(
    *,
    priority: str,
    action: str,
    rationale: str,
    expected_impact: str,
) -> Dict[str, str]:
    return {
        "priority": priority,
        "action": action,
        "rationale": rationale,
        "expected_impact": expected_impact,
    }


def build_rule_based_insights(
    summary: Dict[str, Any],
    rising_products: List[Dict[str, Any]],
    declining_products: List[Dict[str, Any]],
    *,
    language: str = "en",
) -> Dict[str, Any]:
    if summary.get("eligible_products", 0) == 0:
        if language == "it":
            return {
                "summary": "Dati insufficienti per generare insight affidabili sui trend prodotto nel periodo selezionato.",
                "key_trends": [],
                "risks": [],
                "opportunities": [],
                "recommendations": [],
            }
        return {
            "summary": "There is not enough product history to generate reliable product-trend insights for the selected period.",
            "key_trends": [],
            "risks": [],
            "opportunities": [],
            "recommendations": [],
        }

    strongest_riser = summary.get("strongest_riser")
    strongest_decliner = summary.get("strongest_decliner")
    trend_class_counts = summary.get("trend_class_counts") or {}
    declining_fast_count = int(trend_class_counts.get("declining_fast", 0))

    opportunities: List[str] = []
    risks: List[str] = []
    key_trends: List[str] = []
    recommendations: List[Dict[str, str]] = []

    if language == "it":
        summary_text = (
            f"{summary['rising_count']} prodotti sono in crescita e "
            f"{summary['declining_count']} mostrano un trend in calo nel periodo selezionato."
        )
        if declining_fast_count:
            summary_text += f" {declining_fast_count} richiedono attenzione immediata."
        if strongest_riser:
            key_trends.append(
                f"{_display_name(strongest_riser)} è il prodotto con il momentum più forte "
                f"({strongest_riser['trend_score']:.1f})."
            )
            opportunities.append(
                f"Rafforzare la disponibilità e il supporto marketing di {_display_name(strongest_riser)}."
            )
            recommendations.append(
                _build_recommendation(
                    priority="high",
                    action=f"Proteggi stock e visibilità di {_display_name(strongest_riser)}.",
                    rationale="È il prodotto con il trend score più alto del portafoglio.",
                    expected_impact="Aiuta a convertire il momentum attuale in crescita sostenibile.",
                )
            )
        if strongest_decliner:
            key_trends.append(
                f"{_display_name(strongest_decliner)} è il prodotto più debole del periodo "
                f"({strongest_decliner['trend_score']:.1f})."
            )
            risks.append(
                f"Analizzare rapidamente {_display_name(strongest_decliner)} per evitare ulteriore erosione."
            )
            recommendations.append(
                _build_recommendation(
                    priority="high",
                    action=f"Rivedi prezzo, stock e supporto ads di {_display_name(strongest_decliner)}.",
                    rationale="Mostra il peggior trend score e richiede una diagnosi prioritaria.",
                    expected_impact="Riduce il rischio di perdita di vendite e ranking.",
                )
            )
        if declining_fast_count:
            risks.append(
                f"{declining_fast_count} prodotti sono in declino rapido e meritano un controllo immediato."
            )
        elif declining_products:
            risks.append(
                f"{len(declining_products)} prodotti stanno rallentando: serve una revisione focalizzata delle cause."
            )
        if rising_products:
            opportunities.append(
                f"{len(rising_products)} prodotti stanno guadagnando trazione e possono ricevere supporto selettivo."
            )
        recommendations.append(
            _build_recommendation(
                priority="medium",
                action="Confronta i segnali dei prodotti in crescita e in calo per individuare pattern ricorrenti.",
                rationale="Il ranking mostra se il segnale arriva da ricavi, unità, BSR o pressione di stock.",
                expected_impact="Permette decisioni più rapide su pricing, inventory e campagne.",
            )
        )
    else:
        summary_text = (
            f"{summary['rising_count']} products are trending up while "
            f"{summary['declining_count']} are losing momentum in the selected period."
        )
        if declining_fast_count:
            summary_text += f" {declining_fast_count} need immediate attention."
        if strongest_riser:
            key_trends.append(
                f"{_display_name(strongest_riser)} is the strongest momentum product "
                f"({strongest_riser['trend_score']:.1f})."
            )
            opportunities.append(
                f"Protect inventory and commercial support behind {_display_name(strongest_riser)}."
            )
            recommendations.append(
                _build_recommendation(
                    priority="high",
                    action=f"Protect stock coverage and visibility for {_display_name(strongest_riser)}.",
                    rationale="It has the highest trend score in the portfolio.",
                    expected_impact="Helps convert current momentum into sustained growth.",
                )
            )
        if strongest_decliner:
            key_trends.append(
                f"{_display_name(strongest_decliner)} is the weakest product this period "
                f"({strongest_decliner['trend_score']:.1f})."
            )
            risks.append(
                f"Review {_display_name(strongest_decliner)} quickly to prevent further erosion."
            )
            recommendations.append(
                _build_recommendation(
                    priority="high",
                    action=f"Review pricing, stock position, and ad support for {_display_name(strongest_decliner)}.",
                    rationale="It has the lowest trend score and needs immediate diagnosis.",
                    expected_impact="Reduces the risk of further sales and ranking deterioration.",
                )
            )
        if declining_fast_count:
            risks.append(
                f"{declining_fast_count} products are in rapid decline and should be triaged immediately."
            )
        elif declining_products:
            risks.append(
                f"{len(declining_products)} products are slowing down and need a focused root-cause review."
            )
        if rising_products:
            opportunities.append(
                f"{len(rising_products)} products are gaining traction and can support selective reinvestment."
            )
        recommendations.append(
            _build_recommendation(
                priority="medium",
                action="Compare supporting signals across rising and declining products to identify repeated patterns.",
                rationale="The ranking shows whether momentum is driven by revenue, units, BSR, or inventory pressure.",
                expected_impact="Supports faster decisions on pricing, inventory, and campaigns.",
            )
        )

    return {
        "summary": summary_text,
        "key_trends": key_trends[:3],
        "risks": risks[:3],
        "opportunities": opportunities[:3],
        "recommendations": recommendations[:4],
    }


def _category_breakdown(products: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    counter = Counter(product.get("category") or "Uncategorized" for product in products)
    return [
        {"category": category, "count": count}
        for category, count in counter.most_common(3)
    ]


def _inventory_days_of_cover(current_inventory: Optional[int], current_units: int) -> Optional[float]:
    if current_inventory is None or current_units <= 0:
        return None
    daily_units = current_units / TREND_WINDOW_DAYS
    if daily_units <= 0:
        return None
    return round(current_inventory / daily_units, 1)


def _format_percent_signal(label: str, change_percent: float, days: int) -> str:
    sign = "+" if change_percent > 0 else ""
    return f"{label} {sign}{change_percent:.0f}% vs previous {days} days"


def _format_percent_signal_it(label: str, change_percent: float, days: int) -> str:
    sign = "+" if change_percent > 0 else ""
    return f"{label} {sign}{change_percent:.0f}% vs i {days} giorni precedenti"


def _build_dedup_key(event_kind: str, account_id: Optional[UUID], asin: Optional[str]) -> str:
    return f"{event_kind}:{account_id or '-'}:{asin or '-'}"


class ProductTrendsService:
    """Compute product trends and deterministic insights."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_product_trends(
        self,
        *,
        account_ids: List[UUID],
        start_date: date,
        end_date: date,
        language: str = "en",
        organization_id: Optional[UUID] = None,
        asin: Optional[str] = None,
        trend_class: Optional[str] = None,
        limit: int = DEFAULT_RANKING_LIMIT,
    ) -> Dict[str, Any]:
        if not account_ids:
            return _empty_response(language)

        current_end = end_date
        current_start = current_end - timedelta(days=TREND_WINDOW_DAYS - 1)
        previous_end = current_start - timedelta(days=1)
        previous_start = previous_end - timedelta(days=TREND_WINDOW_DAYS - 1)

        sales_timeseries = await self._sales_timeseries(
            account_ids=account_ids,
            start_date=previous_start,
            end_date=current_end,
        )
        asins = set(sales_timeseries.keys())
        if not asins:
            return _empty_response(language)

        metadata = await self._product_metadata(account_ids, list(asins))
        bsr_snapshots = await self._bsr_snapshots(
            account_ids=account_ids,
            asins=list(asins),
            previous_start=previous_start,
            previous_end=previous_end,
            current_start=current_start,
            current_end=current_end,
        )
        inventory_snapshots = await self._inventory_snapshots(
            account_ids=account_ids,
            asins=list(asins),
            previous_start=previous_start,
            previous_end=previous_end,
            current_start=current_start,
            current_end=current_end,
        )

        all_products: List[Dict[str, Any]] = []
        for product_asin in sorted(asins):
            product_series = sales_timeseries.get(product_asin, {})
            current_revenue = self._sum_metric(product_series, current_start, current_end, "revenue")
            previous_revenue = self._sum_metric(product_series, previous_start, previous_end, "revenue")
            current_units = int(self._sum_metric(product_series, current_start, current_end, "units"))
            previous_units = int(self._sum_metric(product_series, previous_start, previous_end, "units"))

            if current_units + previous_units < MIN_COMBINED_UNITS:
                continue

            product_meta = metadata.get(product_asin, {})
            bsr_snapshot = bsr_snapshots.get(product_asin, {})
            inventory_snapshot = inventory_snapshots.get(product_asin, {})
            current_bsr = bsr_snapshot.get("current_bsr") or product_meta.get("current_bsr")
            previous_bsr = bsr_snapshot.get("previous_bsr")
            bsr_change_percent = _bsr_change_percent(current_bsr, previous_bsr)
            if bsr_change_percent is not None:
                bsr_change_percent = round(bsr_change_percent, 2)

            bsr_position_change = None
            if current_bsr is not None and previous_bsr is not None:
                bsr_position_change = previous_bsr - current_bsr

            sales_delta_percent = round(_percent_change(current_revenue, previous_revenue), 2)
            units_change_percent = round(_percent_change(current_units, previous_units), 2)
            trend_score = _score_components(
                sales_change_percent=sales_delta_percent,
                units_change_percent=units_change_percent,
                bsr_change_percent=bsr_change_percent,
                review_velocity_change_percent=None,
            )
            product_trend_class = _trend_class_from_delta(sales_delta_percent)
            direction = _direction_from_trend_class(product_trend_class)
            strength = _strength_from_trend_class(product_trend_class, trend_score)
            quality = _data_quality(
                current_units=current_units,
                previous_units=previous_units,
                current_revenue=current_revenue,
                previous_revenue=previous_revenue,
                current_bsr=current_bsr,
                previous_bsr=previous_bsr,
            )

            current_inventory = inventory_snapshot.get("current_inventory")
            previous_inventory = inventory_snapshot.get("previous_inventory")
            inventory_days_of_cover = _inventory_days_of_cover(current_inventory, current_units)
            supporting_signals = self._supporting_signals(
                language=language,
                sales_delta_percent=sales_delta_percent,
                units_change_percent=units_change_percent,
                bsr_position_change=bsr_position_change,
                current_inventory=current_inventory,
                previous_inventory=previous_inventory,
                inventory_days_of_cover=inventory_days_of_cover,
            )

            all_products.append(
                {
                    "asin": product_asin,
                    "account_id": self._single_account_id(product_meta.get("account_ids") or []),
                    "title": product_meta.get("title"),
                    "category": product_meta.get("category"),
                    "trend_class": product_trend_class,
                    "trend_score": trend_score,
                    "direction": direction,
                    "strength": strength,
                    "sales_delta_percent": sales_delta_percent,
                    "current_revenue": round(current_revenue, 2),
                    "previous_revenue": round(previous_revenue, 2),
                    "current_units": current_units,
                    "previous_units": previous_units,
                    "revenue_change_percent": sales_delta_percent,
                    "units_change_percent": units_change_percent,
                    "current_bsr": current_bsr,
                    "previous_bsr": previous_bsr,
                    "bsr_change_percent": bsr_change_percent,
                    "bsr_position_change": bsr_position_change,
                    "current_inventory": current_inventory,
                    "previous_inventory": previous_inventory,
                    "inventory_days_of_cover": inventory_days_of_cover,
                    "review_velocity_change_percent": None,
                    "supporting_signals": supporting_signals,
                    "recent_sales": self._recent_sales_points(product_series, current_end),
                    "data_quality": quality,
                    "reason_tags": _reason_tags(
                        sales_change_percent=sales_delta_percent,
                        units_change_percent=units_change_percent,
                        bsr_change_percent=bsr_change_percent,
                        quality=quality,
                    ),
                }
            )

        if organization_id and all_products:
            await self._sync_declining_fast_alerts(
                organization_id=organization_id,
                account_ids=account_ids,
                products=all_products,
            )

        filtered_products = all_products
        if asin:
            normalized_asin = asin.strip().upper()
            filtered_products = [
                item for item in filtered_products
                if item["asin"].upper() == normalized_asin
            ]
        if trend_class:
            filtered_products = [
                item for item in filtered_products
                if item["trend_class"] == trend_class
            ]

        summary = self._build_summary(filtered_products)
        sorted_products = sorted(
            filtered_products,
            key=lambda item: (item["trend_score"], item["sales_delta_percent"]),
            reverse=True,
        )
        rising_products = [
            item for item in sorted_products
            if item["trend_class"] in {"rising_fast", "rising"}
        ][:limit]
        declining_products = [
            item for item in sorted(
                filtered_products,
                key=lambda item: (item["trend_score"], item["sales_delta_percent"]),
            )
            if item["trend_class"] in {"declining", "declining_fast"}
        ][:limit]

        return {
            "summary": summary,
            "rising_products": rising_products,
            "declining_products": declining_products,
            "products": sorted_products[:limit],
            "insights_context": {
                "summary": summary,
                "top_rising_products": rising_products[:5],
                "top_declining_products": declining_products[:5],
                "rising_categories": _category_breakdown(rising_products),
                "declining_categories": _category_breakdown(declining_products),
            },
        }

    async def _sales_timeseries(
        self,
        *,
        account_ids: List[UUID],
        start_date: date,
        end_date: date,
    ) -> Dict[str, Dict[date, Dict[str, float]]]:
        result = await self.db.execute(
            select(
                SalesData.asin,
                SalesData.date,
                func.sum(SalesData.ordered_product_sales).label("revenue"),
                func.sum(SalesData.units_ordered).label("units"),
            )
            .where(
                SalesData.account_id.in_(account_ids),
                SalesData.asin != DAILY_TOTAL_ASIN,
                SalesData.date >= start_date,
                SalesData.date <= end_date,
            )
            .group_by(SalesData.asin, SalesData.date)
            .order_by(SalesData.asin, SalesData.date.asc())
        )

        series: Dict[str, Dict[date, Dict[str, float]]] = defaultdict(dict)
        for row in result.all():
            series[row.asin][row.date] = {
                "revenue": float(row.revenue or 0.0),
                "units": float(row.units or 0),
            }
        return dict(series)

    def _sum_metric(
        self,
        product_series: Dict[date, Dict[str, float]],
        start_date: date,
        end_date: date,
        key: str,
    ) -> float:
        total = 0.0
        current_day = start_date
        while current_day <= end_date:
            total += float(product_series.get(current_day, {}).get(key, 0.0))
            current_day += timedelta(days=1)
        return total

    async def _product_metadata(
        self,
        account_ids: List[UUID],
        asins: List[str],
    ) -> Dict[str, Dict[str, Any]]:
        if not asins:
            return {}

        result = await self.db.execute(
            select(
                Product.account_id,
                Product.asin,
                Product.title,
                Product.category,
                Product.current_bsr,
                Product.review_count,
            )
            .where(
                Product.account_id.in_(account_ids),
                Product.asin.in_(asins),
            )
            .order_by(Product.asin, Product.updated_at.desc())
        )

        metadata: Dict[str, Dict[str, Any]] = {}
        for row in result.all():
            current = metadata.setdefault(
                row.asin,
                {
                    "title": None,
                    "category": None,
                    "current_bsr": None,
                    "review_count": None,
                    "account_ids": [],
                },
            )
            if current["title"] is None and row.title:
                current["title"] = row.title
            if current["category"] is None and row.category:
                current["category"] = row.category
            if current["current_bsr"] is None and row.current_bsr is not None:
                current["current_bsr"] = int(row.current_bsr)
            if current["review_count"] is None and row.review_count is not None:
                current["review_count"] = int(row.review_count)
            current["account_ids"].append(row.account_id)
        return metadata

    async def _bsr_snapshots(
        self,
        *,
        account_ids: List[UUID],
        asins: List[str],
        previous_start: date,
        previous_end: date,
        current_start: date,
        current_end: date,
    ) -> Dict[str, Dict[str, Optional[int]]]:
        if not asins:
            return {}

        result = await self.db.execute(
            select(Product.asin, BSRHistory.date, BSRHistory.bsr)
            .select_from(BSRHistory)
            .join(Product, Product.id == BSRHistory.product_id)
            .where(
                Product.account_id.in_(account_ids),
                Product.asin.in_(asins),
                BSRHistory.bsr.is_not(None),
                BSRHistory.date >= previous_start,
                BSRHistory.date <= current_end,
            )
            .order_by(Product.asin, BSRHistory.date.desc(), BSRHistory.bsr.asc())
        )

        snapshots: Dict[str, Dict[str, Optional[int]]] = {
            asin: {"current_bsr": None, "previous_bsr": None}
            for asin in asins
        }
        for row in result.all():
            asin_snapshots = snapshots.setdefault(row.asin, {"current_bsr": None, "previous_bsr": None})
            if current_start <= row.date <= current_end and asin_snapshots["current_bsr"] is None:
                asin_snapshots["current_bsr"] = int(row.bsr)
            elif previous_start <= row.date <= previous_end and asin_snapshots["previous_bsr"] is None:
                asin_snapshots["previous_bsr"] = int(row.bsr)
        return snapshots

    async def _inventory_snapshots(
        self,
        *,
        account_ids: List[UUID],
        asins: List[str],
        previous_start: date,
        previous_end: date,
        current_start: date,
        current_end: date,
    ) -> Dict[str, Dict[str, Optional[int]]]:
        if not asins:
            return {}

        result = await self.db.execute(
            select(
                InventoryData.asin,
                InventoryData.snapshot_date,
                (
                    func.sum(InventoryData.afn_fulfillable_quantity)
                    + func.sum(InventoryData.mfn_fulfillable_quantity)
                ).label("current_inventory"),
            )
            .where(
                InventoryData.account_id.in_(account_ids),
                InventoryData.asin.in_(asins),
                InventoryData.snapshot_date >= previous_start,
                InventoryData.snapshot_date <= current_end,
            )
            .group_by(InventoryData.asin, InventoryData.snapshot_date)
            .order_by(InventoryData.asin, InventoryData.snapshot_date.desc())
        )

        snapshots: Dict[str, Dict[str, Optional[int]]] = {
            asin: {"current_inventory": None, "previous_inventory": None}
            for asin in asins
        }
        for row in result.all():
            asin_snapshots = snapshots.setdefault(
                row.asin,
                {"current_inventory": None, "previous_inventory": None},
            )
            inventory_value = int(row.current_inventory or 0)
            if current_start <= row.snapshot_date <= current_end and asin_snapshots["current_inventory"] is None:
                asin_snapshots["current_inventory"] = inventory_value
            elif previous_start <= row.snapshot_date <= previous_end and asin_snapshots["previous_inventory"] is None:
                asin_snapshots["previous_inventory"] = inventory_value
        return snapshots

    def _recent_sales_points(
        self,
        product_series: Dict[date, Dict[str, float]],
        current_end: date,
    ) -> List[Dict[str, Any]]:
        start_date = current_end - timedelta(days=SPARKLINE_WINDOW_DAYS - 1)
        points: List[Dict[str, Any]] = []
        cursor = start_date
        while cursor <= current_end:
            point = product_series.get(cursor, {})
            points.append(
                {
                    "date": cursor,
                    "revenue": round(float(point.get("revenue", 0.0)), 2),
                    "units": int(point.get("units", 0)),
                }
            )
            cursor += timedelta(days=1)
        return points

    def _build_summary(self, products: List[Dict[str, Any]]) -> Dict[str, Any]:
        class_counts = {
            "rising_fast": 0,
            "rising": 0,
            "stable": 0,
            "declining": 0,
            "declining_fast": 0,
        }
        for product in products:
            class_counts[product["trend_class"]] = class_counts.get(product["trend_class"], 0) + 1

        rising_products = [
            item for item in sorted(products, key=lambda item: item["trend_score"], reverse=True)
            if item["trend_class"] in {"rising_fast", "rising"}
        ]
        declining_products = [
            item for item in sorted(products, key=lambda item: item["trend_score"])
            if item["trend_class"] in {"declining", "declining_fast"}
        ]

        return {
            "eligible_products": len(products),
            "rising_count": class_counts["rising_fast"] + class_counts["rising"],
            "declining_count": class_counts["declining_fast"] + class_counts["declining"],
            "stable_count": class_counts["stable"],
            "average_trend_score": round(
                sum(item["trend_score"] for item in products) / len(products),
                2,
            ) if products else 0.0,
            "trend_class_counts": class_counts,
            "strongest_riser": rising_products[0] if rising_products else None,
            "strongest_decliner": declining_products[0] if declining_products else None,
        }

    def _supporting_signals(
        self,
        *,
        language: str,
        sales_delta_percent: float,
        units_change_percent: float,
        bsr_position_change: Optional[int],
        current_inventory: Optional[int],
        previous_inventory: Optional[int],
        inventory_days_of_cover: Optional[float],
    ) -> List[str]:
        if language == "it":
            signals = [
                _format_percent_signal_it("Vendite", sales_delta_percent, TREND_WINDOW_DAYS),
            ]
        else:
            signals = [
                _format_percent_signal("Sales", sales_delta_percent, TREND_WINDOW_DAYS),
            ]
        if abs(units_change_percent - sales_delta_percent) >= 3 or abs(units_change_percent) >= 5:
            signals.append(
                _format_percent_signal_it("Unità", units_change_percent, TREND_WINDOW_DAYS)
                if language == "it"
                else _format_percent_signal("Units", units_change_percent, TREND_WINDOW_DAYS)
            )
        if bsr_position_change:
            if bsr_position_change > 0:
                signals.append(
                    f"BSR migliorato di {bsr_position_change:,} posizioni"
                    if language == "it"
                    else f"BSR improved by {bsr_position_change:,} positions"
                )
            else:
                signals.append(
                    f"BSR peggiorato di {abs(bsr_position_change):,} posizioni"
                    if language == "it"
                    else f"BSR worsened by {abs(bsr_position_change):,} positions"
                )
        if current_inventory is not None:
            if current_inventory <= 0:
                signals.append("Attualmente esaurito" if language == "it" else "Currently out of stock")
            elif inventory_days_of_cover is not None and inventory_days_of_cover <= TREND_WINDOW_DAYS:
                signals.append(
                    (
                        f"Solo {current_inventory:,} unità disponibili, circa {inventory_days_of_cover:.1f} giorni di copertura"
                        if language == "it"
                        else f"Only {current_inventory:,} units on hand, about {inventory_days_of_cover:.1f} days of cover"
                    )
                )
            elif previous_inventory is not None and current_inventory < previous_inventory:
                signals.append(
                    (
                        f"Inventario sceso da {previous_inventory:,} a {current_inventory:,} unità"
                        if language == "it"
                        else f"Inventory fell from {previous_inventory:,} to {current_inventory:,} units"
                    )
                )
        return signals[:4]

    def _single_account_id(self, account_ids: List[UUID]) -> Optional[UUID]:
        unique_account_ids = list(dict.fromkeys(account_ids))
        if len(unique_account_ids) == 1:
            return unique_account_ids[0]
        return None

    async def _ensure_trend_alert_rule(self, organization_id: UUID) -> AlertRule:
        result = await self.db.execute(
            select(AlertRule).where(
                AlertRule.organization_id == organization_id,
                AlertRule.alert_type == TREND_ALERT_TYPE,
            )
        )
        existing_rule = result.scalars().first()
        if existing_rule:
            return existing_rule

        rule = AlertRule(
            id=uuid4(),
            organization_id=organization_id,
            name=TREND_ALERT_RULE_NAME,
            alert_type=TREND_ALERT_TYPE,
            conditions={
                "trend_class": "declining_fast",
                "cooldown_hours": ALERT_COOLDOWN_HOURS,
                "auto_created": True,
            },
            applies_to_accounts=None,
            applies_to_asins=None,
            notification_channels=[],
            notification_emails=None,
            webhook_url=None,
            is_enabled=True,
        )
        self.db.add(rule)
        if hasattr(self.db, "flush"):
            await self.db.flush()
        return rule

    async def _sync_declining_fast_alerts(
        self,
        *,
        organization_id: UUID,
        account_ids: List[UUID],
        products: List[Dict[str, Any]],
    ) -> None:
        rule = await self._ensure_trend_alert_rule(organization_id)
        now = datetime.utcnow()
        cooldown_start = now - timedelta(hours=ALERT_COOLDOWN_HOURS)
        active_alert_keys: set[str] = set()
        scope_asins = {product["asin"] for product in products}
        changed = False
        alert_candidates: List[tuple[Dict[str, Any], str]] = []

        for product in products:
            if product["trend_class"] not in TREND_ALERT_CLASSES:
                continue

            dedup_key = _build_dedup_key(
                TREND_ALERT_EVENT_KIND,
                product.get("account_id"),
                product["asin"],
            )
            active_alert_keys.add(dedup_key)
            alert_candidates.append((product, dedup_key))

        existing_alerts_by_key: Dict[str, Alert] = {}
        if active_alert_keys:
            existing_result = await self.db.execute(
                select(Alert)
                .where(
                    Alert.rule_id == rule.id,
                    Alert.dedup_key.in_(list(active_alert_keys)),
                )
                .order_by(Alert.dedup_key, Alert.triggered_at.desc())
            )
            for existing_alert in existing_result.scalars().all():
                existing_alerts_by_key.setdefault(existing_alert.dedup_key, existing_alert)

        for product, dedup_key in alert_candidates:
            existing_alert = existing_alerts_by_key.get(dedup_key)
            message = (
                f"{_display_name(product)} is declining fast "
                f"({product['sales_delta_percent']:+.0f}% sales vs previous {TREND_WINDOW_DAYS} days)"
            )
            details = {
                "trend_class": product["trend_class"],
                "trend_score": product["trend_score"],
                "sales_delta_percent": product["sales_delta_percent"],
                "current_revenue": product["current_revenue"],
                "previous_revenue": product["previous_revenue"],
                "current_units": product["current_units"],
                "previous_units": product["previous_units"],
                "supporting_signals": product["supporting_signals"],
            }

            if existing_alert:
                if existing_alert.resolved_at is None:
                    existing_alert.message = message
                    existing_alert.details = details
                    existing_alert.severity = "warning"
                    existing_alert.last_seen_at = now
                    changed = True
                    continue
                if existing_alert.triggered_at >= cooldown_start:
                    continue

            alert = Alert(
                id=uuid4(),
                rule_id=rule.id,
                account_id=product.get("account_id"),
                asin=product["asin"],
                event_kind=TREND_ALERT_EVENT_KIND,
                dedup_key=dedup_key,
                message=message,
                details=details,
                severity="warning",
                is_read=False,
                triggered_at=now,
                last_seen_at=now,
                notification_status="pending",
            )
            self.db.add(alert)
            rule.last_triggered_at = now
            changed = True

        existing_scope_result = await self.db.execute(
            select(Alert).where(
                Alert.rule_id == rule.id,
                Alert.event_kind == TREND_ALERT_EVENT_KIND,
                Alert.resolved_at.is_(None),
            )
        )
        for alert in existing_scope_result.scalars().all():
            in_scope = (
                (alert.account_id is not None and alert.account_id in account_ids)
                or (alert.account_id is None and alert.asin in scope_asins)
            )
            if not in_scope:
                continue
            if alert.dedup_key in active_alert_keys:
                continue
            alert.resolved_at = now
            alert.last_seen_at = now
            changed = True

        if changed and hasattr(self.db, "commit"):
            await self.db.commit()
