"""Product trend scoring and insights service."""
from __future__ import annotations

from collections import Counter
from datetime import date, timedelta
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product, BSRHistory
from app.models.sales_data import SalesData
from app.services.data_extraction import DAILY_TOTAL_ASIN


MIN_COMBINED_UNITS = 5
UP_THRESHOLD = 15.0
DOWN_THRESHOLD = -15.0
MODERATE_STRENGTH_THRESHOLD = 25.0
STRONG_STRENGTH_THRESHOLD = 55.0
DEFAULT_RANKING_LIMIT = 8


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
    revenue_change_percent: float,
    units_change_percent: float,
    bsr_change_percent: Optional[float],
) -> float:
    revenue_component = _clamp(revenue_change_percent)
    units_component = _clamp(units_change_percent)

    if bsr_change_percent is None:
        revenue_weight = 0.5333
        units_weight = 0.4667
        return round((revenue_component * revenue_weight) + (units_component * units_weight), 2)

    bsr_component = _clamp(bsr_change_percent)
    return round(
        (revenue_component * 0.40) +
        (units_component * 0.35) +
        (bsr_component * 0.25),
        2,
    )


def _direction_from_score(score: float) -> str:
    if score >= UP_THRESHOLD:
        return "up"
    if score <= DOWN_THRESHOLD:
        return "down"
    return "stable"


def _strength_from_score(score: float) -> str:
    magnitude = abs(score)
    if magnitude >= STRONG_STRENGTH_THRESHOLD:
        return "strong"
    if magnitude >= MODERATE_STRENGTH_THRESHOLD:
        return "moderate"
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
    revenue_change_percent: float,
    units_change_percent: float,
    bsr_change_percent: Optional[float],
    quality: str,
) -> List[str]:
    tags: List[str] = []
    if revenue_change_percent >= 10:
        tags.append("revenue_growth")
    elif revenue_change_percent <= -10:
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
            "strongest_riser": None,
            "strongest_decliner": None,
        },
        "rising_products": [],
        "declining_products": [],
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

    opportunities: List[str] = []
    risks: List[str] = []
    key_trends: List[str] = []
    recommendations: List[Dict[str, str]] = []

    if language == "it":
        summary_text = (
            f"{summary['rising_count']} prodotti sono in crescita e "
            f"{summary['declining_count']} mostrano un trend in calo nel periodo selezionato."
        )
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
        if declining_products:
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
                action="Confronta i reason tag dei prodotti in crescita e in calo per individuare pattern ricorrenti.",
                rationale="Il ranking mostra se il segnale arriva da ricavi, unità o BSR.",
                expected_impact="Permette decisioni più rapide su pricing, inventory e campagne.",
            )
        )
    else:
        summary_text = (
            f"{summary['rising_count']} products are trending up while "
            f"{summary['declining_count']} are losing momentum in the selected period."
        )
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
        if declining_products:
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
                action="Compare reason tags across rising and declining products to identify repeated patterns.",
                rationale="The ranking shows whether momentum is driven by revenue, units, or BSR movement.",
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
        limit: int = DEFAULT_RANKING_LIMIT,
    ) -> Dict[str, Any]:
        if not account_ids:
            return {
                **_empty_response("en"),
                "summary": {
                    "eligible_products": 0,
                    "rising_count": 0,
                    "declining_count": 0,
                    "stable_count": 0,
                    "average_trend_score": 0.0,
                    "strongest_riser": None,
                    "strongest_decliner": None,
                },
            }

        window_days = (end_date - start_date).days + 1
        previous_end = start_date - timedelta(days=1)
        previous_start = start_date - timedelta(days=window_days)

        current_sales = await self._sales_aggregates(account_ids, start_date, end_date)
        previous_sales = await self._sales_aggregates(account_ids, previous_start, previous_end)

        asins = set(current_sales.keys()) | set(previous_sales.keys())
        if not asins:
            return _empty_response("en")

        metadata = await self._product_metadata(account_ids, list(asins))
        bsr_snapshots = await self._bsr_snapshots(
            account_ids=account_ids,
            asins=list(asins),
            previous_start=previous_start,
            previous_end=previous_end,
            current_start=start_date,
            current_end=end_date,
        )

        products: List[Dict[str, Any]] = []
        for asin in asins:
            current = current_sales.get(asin, {})
            previous = previous_sales.get(asin, {})
            current_revenue = float(current.get("revenue", 0.0))
            previous_revenue = float(previous.get("revenue", 0.0))
            current_units = int(current.get("units", 0))
            previous_units = int(previous.get("units", 0))
            combined_units = current_units + previous_units
            if combined_units < MIN_COMBINED_UNITS:
                continue

            current_bsr = bsr_snapshots.get(asin, {}).get("current_bsr")
            previous_bsr = bsr_snapshots.get(asin, {}).get("previous_bsr")
            revenue_change_percent = round(_percent_change(current_revenue, previous_revenue), 2)
            units_change_percent = round(_percent_change(current_units, previous_units), 2)
            bsr_change_percent = _bsr_change_percent(current_bsr, previous_bsr)
            if bsr_change_percent is not None:
                bsr_change_percent = round(bsr_change_percent, 2)

            trend_score = _score_components(
                revenue_change_percent=revenue_change_percent,
                units_change_percent=units_change_percent,
                bsr_change_percent=bsr_change_percent,
            )
            direction = _direction_from_score(trend_score)
            strength = _strength_from_score(trend_score)
            quality = _data_quality(
                current_units=current_units,
                previous_units=previous_units,
                current_revenue=current_revenue,
                previous_revenue=previous_revenue,
                current_bsr=current_bsr,
                previous_bsr=previous_bsr,
            )

            product_meta = metadata.get(asin, {})
            products.append(
                {
                    "asin": asin,
                    "title": product_meta.get("title"),
                    "category": product_meta.get("category"),
                    "trend_score": trend_score,
                    "direction": direction,
                    "strength": strength,
                    "current_revenue": round(current_revenue, 2),
                    "previous_revenue": round(previous_revenue, 2),
                    "current_units": current_units,
                    "previous_units": previous_units,
                    "revenue_change_percent": revenue_change_percent,
                    "units_change_percent": units_change_percent,
                    "current_bsr": current_bsr,
                    "previous_bsr": previous_bsr,
                    "bsr_change_percent": bsr_change_percent,
                    "data_quality": quality,
                    "reason_tags": _reason_tags(
                        revenue_change_percent=revenue_change_percent,
                        units_change_percent=units_change_percent,
                        bsr_change_percent=bsr_change_percent,
                        quality=quality,
                    ),
                }
            )

        products.sort(key=lambda item: item["trend_score"], reverse=True)
        rising_products = [item for item in products if item["direction"] == "up"][:limit]
        declining_products = sorted(
            [item for item in products if item["direction"] == "down"],
            key=lambda item: item["trend_score"],
        )[:limit]
        stable_count = sum(1 for item in products if item["direction"] == "stable")

        summary = {
            "eligible_products": len(products),
            "rising_count": len([item for item in products if item["direction"] == "up"]),
            "declining_count": len([item for item in products if item["direction"] == "down"]),
            "stable_count": stable_count,
            "average_trend_score": round(
                sum(item["trend_score"] for item in products) / len(products), 2
            ) if products else 0.0,
            "strongest_riser": rising_products[0] if rising_products else None,
            "strongest_decliner": declining_products[0] if declining_products else None,
        }

        return {
            "summary": summary,
            "rising_products": rising_products,
            "declining_products": declining_products,
            "insights_context": {
                "summary": summary,
                "top_rising_products": rising_products[:5],
                "top_declining_products": declining_products[:5],
                "rising_categories": _category_breakdown(rising_products),
                "declining_categories": _category_breakdown(declining_products),
            },
            "products": products,
        }

    async def _sales_aggregates(
        self,
        account_ids: List[UUID],
        start_date: date,
        end_date: date,
    ) -> Dict[str, Dict[str, Any]]:
        result = await self.db.execute(
            select(
                SalesData.asin,
                func.sum(SalesData.ordered_product_sales).label("revenue"),
                func.sum(SalesData.units_ordered).label("units"),
            )
            .where(
                SalesData.account_id.in_(account_ids),
                SalesData.asin != DAILY_TOTAL_ASIN,
                SalesData.date >= start_date,
                SalesData.date <= end_date,
            )
            .group_by(SalesData.asin)
        )

        return {
            row.asin: {
                "revenue": float(row.revenue or 0.0),
                "units": int(row.units or 0),
            }
            for row in result.all()
        }

    async def _product_metadata(
        self,
        account_ids: List[UUID],
        asins: List[str],
    ) -> Dict[str, Dict[str, Optional[str]]]:
        if not asins:
            return {}

        result = await self.db.execute(
            select(Product.asin, Product.title, Product.category)
            .where(
                Product.account_id.in_(account_ids),
                Product.asin.in_(asins),
            )
            .order_by(Product.asin, Product.updated_at.desc())
        )

        metadata: Dict[str, Dict[str, Optional[str]]] = {}
        for row in result.all():
            current = metadata.setdefault(row.asin, {"title": None, "category": None})
            if current["title"] is None and row.title:
                current["title"] = row.title
            if current["category"] is None and row.category:
                current["category"] = row.category
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
