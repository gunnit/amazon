"""Figures of the quarterly business review (R5).

One quarter for a scope (accounts = countries, optional brand, category and
ASIN list) against two comparison periods: the previous quarter and the same
quarter last year.

Account totals come from the per-account daily total rows (asin
``__DAILY_TOTAL__``). A brand, category or ASIN filter sums the per-ASIN rows
of the matching products instead, never both, so nothing is counted twice.
Revenue and units follow the display rule of ``sales_metrics``: shipped,
falling back to ordered. Every figure here comes from Amazon reports, so its
provenance is "actual"; forecasts and Helium 10 figures would be "estimated".

Each query is a small ``fetch_*`` function so tests can replace it.
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal, Optional
from uuid import UUID

from sqlalchemy import Text, and_, bindparam, func, literal_column, select
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

from app.models.advertising import AdvertisingCampaign, AdvertisingMetrics, AdvertisingMetricsByAsin
from app.models.amazon_account import AmazonAccount
from app.models.brand_search_term import BrandSearchTerm
from app.models.catalog_monitor import CatalogAnomaly
from app.models.competitor import Competitor, CompetitorHistory
from app.models.listing_quality import ListingQualitySnapshot
from app.models.product import Product
from app.models.returns_data import ReturnData
from app.models.sales_data import SalesData
from app.services.data_extraction import DAILY_TOTAL_ASIN
from app.services.quarterly_report.deck import t
from app.services.product_scope import product_scope_conditions
from app.services.sales_metrics import display_revenue_expr, display_units_expr

Provenance = Literal["actual", "estimated"]

TOP_ASINS = 10
SEARCH_TERMS_PER_ACCOUNT = 10
QUALITY_STATES = ("green", "yellow", "red", "grey")
# Marketplaces that report in euro; any other country's amounts are summed unconverted.
EURO_MARKETPLACES = frozenset({"IT", "DE", "FR", "ES", "NL", "BE", "IE", "AT"})

# (key, unit, provenance). Every KPI is read from Amazon reports.
KPI_SPECS: tuple[tuple[str, str, Provenance], ...] = (
    ("revenue", "EUR", "actual"),
    ("units", "units", "actual"),
    ("ad_spend", "EUR", "actual"),
    ("ad_sales", "EUR", "actual"),
    ("roas", "x", "actual"),
    ("acos", "%", "actual"),
    ("tacos", "%", "actual"),
    ("return_rate", "%", "actual"),
)


@dataclass
class QuarterScope:
    organization_id: UUID
    account_ids: list[UUID]
    year: int
    quarter: int
    brand: Optional[str] = None
    category: Optional[str] = None
    asins: Optional[list[str]] = None
    language: Literal["it", "en"] = "it"

    @property
    def filtered(self) -> bool:
        return bool(self.brand or self.category or self.asins)


@dataclass
class Metric:
    key: str
    value: Optional[float]
    previous: Optional[float]
    last_year: Optional[float]
    provenance: Provenance
    unit: str


@dataclass
class QuarterData:
    scope: QuarterScope
    kpis: list[Metric]
    monthly: list[dict]
    top_asins: list[dict]
    bottom_asins: list[dict]
    catalogue: dict
    search_terms: list[dict]
    competitors: list[dict]
    data_gaps: list[str]
    # {"id", "name", "type": "seller"|"vendor", "country"} per account in scope.
    accounts: list[dict] = field(default_factory=list)


@dataclass
class PeriodTotals:
    """Raw sums of one period; None means no data at all."""

    revenue: Optional[float] = None
    units: Optional[float] = None
    ad_spend: Optional[float] = None
    ad_sales: Optional[float] = None
    returned_units: float = 0.0


# --- periods and arithmetic ----------------------------------------------------------


def quarter_bounds(year: int, quarter: int) -> tuple[date, date]:
    if quarter not in (1, 2, 3, 4):
        raise ValueError(f"quarter must be 1-4, got {quarter}")
    last_month = quarter * 3
    return (
        date(year, last_month - 2, 1),
        date(year, last_month, calendar.monthrange(year, last_month)[1]),
    )


def previous_quarter(year: int, quarter: int) -> tuple[int, int]:
    return (year - 1, 4) if quarter == 1 else (year, quarter - 1)


def quarter_label(year: int, quarter: int) -> str:
    return f"Q{quarter} {year}"


def ratio(numerator: Optional[float], denominator: Optional[float]) -> Optional[float]:
    """numerator / denominator; None when either is missing or the denominator is 0."""
    if numerator is None or not denominator:
        return None
    return numerator / denominator


def relative_change(value: Optional[float], base: Optional[float]) -> Optional[float]:
    """Percent change of ``value`` against ``base``; None when not comparable."""
    if value is None or not base:
        return None
    return (value - base) * 100.0 / abs(base)


def point_change(value: Optional[float], base: Optional[float]) -> Optional[float]:
    """Difference in percentage points between two fractions (0.12 vs 0.10 → 2.0)."""
    if value is None or base is None:
        return None
    return (value - base) * 100.0


def derive_metrics(totals: PeriodTotals) -> dict[str, Optional[float]]:
    return {
        "revenue": totals.revenue,
        "units": totals.units,
        "ad_spend": totals.ad_spend,
        "ad_sales": totals.ad_sales,
        "roas": ratio(totals.ad_sales, totals.ad_spend),
        "acos": ratio(totals.ad_spend, totals.ad_sales),
        "tacos": ratio(totals.ad_spend, totals.revenue),
        "return_rate": ratio(totals.returned_units, totals.units),
    }


def build_kpis(current: PeriodTotals, previous: PeriodTotals, last_year: PeriodTotals) -> list[Metric]:
    now, before, year_ago = derive_metrics(current), derive_metrics(previous), derive_metrics(last_year)
    return [
        Metric(key=key, value=now[key], previous=before[key], last_year=year_ago[key],
               provenance=provenance, unit=unit)
        for key, unit, provenance in KPI_SPECS
    ]


def _float(value: Any) -> Optional[float]:
    return None if value is None else float(value)


# --- queries ---------------------------------------------------------------------------


async def fetch_accounts(db, organization_id: UUID, account_ids: list[UUID]) -> list[dict]:
    """The organization's accounts in scope; all of them when ``account_ids`` is empty."""
    query = select(
        AmazonAccount.id,
        AmazonAccount.account_name,
        AmazonAccount.account_type,
        AmazonAccount.marketplace_country,
    ).where(AmazonAccount.organization_id == organization_id)
    if account_ids:
        query = query.where(AmazonAccount.id.in_(account_ids))
    rows = (await db.execute(query.order_by(AmazonAccount.marketplace_country))).all()
    return [
        {
            "id": row.id,
            "name": row.account_name,
            "type": getattr(row.account_type, "value", row.account_type),
            "country": (row.marketplace_country or "").upper(),
        }
        for row in rows
    ]


async def fetch_scope_asins(db, account_ids: list[UUID], brand: Optional[str],
                            category: Optional[str], asins: Optional[list[str]]) -> list[str]:
    """ASINs of the products matching the brand (any case), category and ASIN list."""
    wanted = sorted({a.strip().upper() for a in asins or [] if a and a.strip()})
    if not brand and not category:
        return wanted
    query = select(Product.asin).where(Product.account_id.in_(account_ids)).distinct()
    query = query.where(*product_scope_conditions(brand, category))
    if wanted:
        query = query.where(Product.asin.in_(wanted))
    return sorted({row.asin for row in (await db.execute(query)).all()})


async def fetch_daily_sales(db, account_ids: list[UUID], start: date, end: date,
                            asins: Optional[list[str]]) -> list:
    """Rows (day, revenue, units): account totals, or the given ASINs' rows."""
    if asins is not None and not asins:
        return []
    query = (
        select(
            SalesData.date.label("day"),
            func.sum(display_revenue_expr()).label("revenue"),
            func.sum(display_units_expr()).label("units"),
        )
        .where(
            SalesData.account_id.in_(account_ids),
            SalesData.date >= start,
            SalesData.date <= end,
        )
        .group_by(SalesData.date)
        .order_by(SalesData.date)
    )
    if asins is None:
        query = query.where(SalesData.asin == DAILY_TOTAL_ASIN)
    else:
        query = query.where(SalesData.asin.in_(asins))
    return (await db.execute(query)).all()


async def fetch_asin_sales(db, account_ids: list[UUID], start: date, end: date,
                           asins: Optional[list[str]]) -> list:
    """Rows (asin, title, revenue, units) per ASIN, never the daily total rows."""
    if asins is not None and not asins:
        return []
    query = (
        select(
            SalesData.asin,
            func.max(Product.title).label("title"),
            func.sum(display_revenue_expr()).label("revenue"),
            func.sum(display_units_expr()).label("units"),
        )
        .select_from(SalesData)
        .outerjoin(
            Product,
            and_(Product.account_id == SalesData.account_id, Product.asin == SalesData.asin),
        )
        .where(
            SalesData.account_id.in_(account_ids),
            SalesData.asin != DAILY_TOTAL_ASIN,
            SalesData.date >= start,
            SalesData.date <= end,
        )
        .group_by(SalesData.asin)
    )
    if asins is not None:
        query = query.where(SalesData.asin.in_(asins))
    return (await db.execute(query)).all()


async def fetch_campaign_ads(db, account_ids: list[UUID], start: date,
                             end: date) -> Optional[tuple[float, float]]:
    """(spend, attributed sales 7d) over all campaigns; None without any metric row."""
    query = (
        select(
            func.sum(AdvertisingMetrics.cost).label("spend"),
            func.sum(AdvertisingMetrics.attributed_sales_7d).label("sales"),
            func.count().label("rows"),
        )
        .select_from(AdvertisingMetrics)
        .join(AdvertisingCampaign, AdvertisingCampaign.id == AdvertisingMetrics.campaign_id)
        .where(
            AdvertisingCampaign.account_id.in_(account_ids),
            AdvertisingMetrics.date >= start,
            AdvertisingMetrics.date <= end,
        )
    )
    row = (await db.execute(query)).one()
    if not row.rows:
        return None
    return float(row.spend or 0), float(row.sales or 0)


async def fetch_asin_ads(db, account_ids: list[UUID], start: date, end: date,
                         asins: list[str]) -> Optional[tuple[float, float]]:
    """(spend, attributed sales 7d) of Sponsored Products advertised-product rows."""
    if not asins:
        return None
    query = select(
        func.sum(AdvertisingMetricsByAsin.cost).label("spend"),
        func.sum(AdvertisingMetricsByAsin.attributed_sales_7d).label("sales"),
        func.count().label("rows"),
    ).where(
        AdvertisingMetricsByAsin.account_id.in_(account_ids),
        AdvertisingMetricsByAsin.asin.in_(asins),
        AdvertisingMetricsByAsin.date >= start,
        AdvertisingMetricsByAsin.date <= end,
    )
    row = (await db.execute(query)).one()
    if not row.rows:
        return None
    return float(row.spend or 0), float(row.sales or 0)


async def fetch_returned_units(db, account_ids: list[UUID], start: date, end: date,
                               asins: Optional[list[str]]) -> float:
    if asins is not None and not asins:
        return 0.0
    query = select(func.coalesce(func.sum(ReturnData.quantity), 0)).where(
        ReturnData.account_id.in_(account_ids),
        ReturnData.return_date >= start,
        ReturnData.return_date <= end,
    )
    if asins is not None:
        query = query.where(ReturnData.asin.in_(asins))
    return float((await db.execute(query)).scalar() or 0)


async def fetch_quality_states(db, account_ids: list[UUID], asins: Optional[list[str]]) -> list:
    """Rows (components, snapshot_date) of the latest R1 snapshot per account and ASIN."""
    if asins is not None and not asins:
        return []
    latest = select(
        ListingQualitySnapshot.account_id,
        ListingQualitySnapshot.asin,
        func.max(ListingQualitySnapshot.snapshot_date).label("latest"),
    ).where(ListingQualitySnapshot.account_id.in_(account_ids))
    if asins is not None:
        latest = latest.where(ListingQualitySnapshot.asin.in_(asins))
    latest = latest.group_by(ListingQualitySnapshot.account_id, ListingQualitySnapshot.asin).subquery()
    query = select(ListingQualitySnapshot.components, ListingQualitySnapshot.snapshot_date).join(
        latest,
        and_(
            ListingQualitySnapshot.account_id == latest.c.account_id,
            ListingQualitySnapshot.asin == latest.c.asin,
            ListingQualitySnapshot.snapshot_date == latest.c.latest,
        ),
    )
    return (await db.execute(query)).all()


async def fetch_open_anomalies(db, account_ids: list[UUID], asins: Optional[list[str]]) -> dict[str, int]:
    """Open (not resolved) R2/R3 anomalies counted by kind."""
    if asins is not None and not asins:
        return {}
    query = (
        select(CatalogAnomaly.kind, func.count().label("count"))
        .where(CatalogAnomaly.account_id.in_(account_ids), CatalogAnomaly.status != "resolved")
        .group_by(CatalogAnomaly.kind)
    )
    if asins is not None:
        query = query.where(CatalogAnomaly.asin.in_(asins))
    return {row.kind: int(row.count) for row in (await db.execute(query)).all()}


async def fetch_search_terms(db, account_ids: list[UUID], asins: Optional[list[str]],
                             per_account: int) -> list:
    """Each account's most searched Brand Analytics terms of its own latest week.

    With ``asins``, only terms whose top clicked ASINs include one of them.
    """
    if asins is not None and not asins:
        return []
    latest = (
        select(BrandSearchTerm.account_id, func.max(BrandSearchTerm.week_start).label("week"))
        .where(BrandSearchTerm.account_id.in_(account_ids))
        .group_by(BrandSearchTerm.account_id)
        .subquery()
    )
    position = func.row_number().over(
        partition_by=BrandSearchTerm.account_id,
        order_by=(BrandSearchTerm.search_frequency_rank.asc().nulls_last(), BrandSearchTerm.search_term),
    )
    ranked = select(
        BrandSearchTerm.account_id,
        BrandSearchTerm.week_start,
        BrandSearchTerm.week_end,
        BrandSearchTerm.search_term,
        BrandSearchTerm.search_frequency_rank,
        BrandSearchTerm.top_clicked,
        position.label("position"),
    ).join(
        latest,
        and_(BrandSearchTerm.account_id == latest.c.account_id, BrandSearchTerm.week_start == latest.c.week),
    )
    if asins is not None:
        # Lax jsonpath: a NULL or non-array top_clicked simply matches nothing.
        clicked_asins = func.jsonb_path_query_array(
            BrandSearchTerm.top_clicked, literal_column("'$[*].asin'::jsonpath"), type_=JSONB
        )
        ranked = ranked.where(
            clicked_asins.has_any(bindparam("scope_asins", list(asins), type_=ARRAY(Text)))
        )
    ranked = ranked.subquery()
    query = (
        select(ranked)
        .where(ranked.c.position <= per_account)
        .order_by(ranked.c.account_id, ranked.c.position)
    )
    return (await db.execute(query)).all()


async def fetch_owned_asins(db, account_ids: list[UUID], asins: set[str]) -> set[str]:
    """Which of ``asins`` are products of the given accounts."""
    if not asins:
        return set()
    query = select(Product.asin).where(Product.account_id.in_(account_ids), Product.asin.in_(sorted(asins)))
    return {row.asin for row in (await db.execute(query)).all()}


async def fetch_competitors(db, organization_id: UUID, marketplaces: list[str]) -> list:
    query = (
        select(
            Competitor.id,
            Competitor.asin,
            Competitor.title,
            Competitor.brand,
            Competitor.marketplace,
            Competitor.current_price,
            Competitor.current_bsr,
            Competitor.rating,
        )
        .where(
            Competitor.organization_id == organization_id,
            Competitor.is_tracking.is_(True),
            Competitor.marketplace.in_(marketplaces),
        )
        .order_by(Competitor.marketplace, Competitor.asin)
    )
    return (await db.execute(query)).all()


async def fetch_competitor_history(db, competitor_ids: list[UUID], start: date, end: date) -> list:
    if not competitor_ids:
        return []
    query = (
        select(
            CompetitorHistory.competitor_id,
            CompetitorHistory.date,
            CompetitorHistory.price,
            CompetitorHistory.bsr,
            CompetitorHistory.rating,
        )
        .where(
            CompetitorHistory.competitor_id.in_(competitor_ids),
            CompetitorHistory.date >= start,
            CompetitorHistory.date <= end,
        )
        .order_by(CompetitorHistory.date)
    )
    return (await db.execute(query)).all()


# --- assembly --------------------------------------------------------------------------


def _quality_state(components: Any) -> str:
    """R1 state of a stored snapshot; rows without one (pre-scan format) are grey."""
    state = components.get("state") if isinstance(components, dict) else None
    return state if state in QUALITY_STATES else "grey"


def _monthly(start: date, current_rows: list, last_year_rows: list) -> list[dict]:
    def by_month(rows):
        sums: dict[int, dict[str, float]] = {}
        for row in rows:
            bucket = sums.setdefault(row.day.month, {"revenue": 0.0, "units": 0.0})
            bucket["revenue"] += float(row.revenue or 0)
            bucket["units"] += float(row.units or 0)
        return sums

    now, year_ago = by_month(current_rows), by_month(last_year_rows)
    months = []
    for month in range(start.month, start.month + 3):
        months.append({
            "month": month,
            "revenue": now.get(month, {}).get("revenue"),
            "units": now.get(month, {}).get("units"),
            "revenue_last_year": year_ago.get(month, {}).get("revenue"),
            "units_last_year": year_ago.get(month, {}).get("units"),
        })
    return months


def _rank_asins(current_rows: list, previous_rows: list) -> tuple[list[dict], list[dict]]:
    """Top ASINs by revenue, and the largest absolute revenue declines."""
    now = {row.asin: row for row in current_rows}
    before = {row.asin: row for row in previous_rows}

    def title(asin):
        for row in (now.get(asin), before.get(asin)):
            if row is not None and row.title:
                return row.title
        return None

    top = []
    for row in sorted(current_rows, key=lambda r: float(r.revenue or 0), reverse=True)[:TOP_ASINS]:
        revenue = float(row.revenue or 0)
        previous = _float(before[row.asin].revenue) if row.asin in before else None
        top.append({
            "asin": row.asin,
            "title": title(row.asin),
            "revenue": revenue,
            "units": float(row.units or 0),
            "previous_revenue": previous,
            "change_pct": relative_change(revenue, previous),
        })

    declines = []
    for asin in set(now) | set(before):
        revenue = float(now[asin].revenue or 0) if asin in now else 0.0
        previous = float(before[asin].revenue or 0) if asin in before else 0.0
        if revenue < previous:
            declines.append({
                "asin": asin,
                "title": title(asin),
                "revenue": revenue,
                "previous_revenue": previous,
                "change": revenue - previous,
            })
    declines.sort(key=lambda d: (d["change"], d["asin"]))
    return top, declines[:TOP_ASINS]


def _shape_search_terms(rows: list, countries: dict, own_asins: set[str]) -> list[dict]:
    """One dict per term, grouped by country, most searched first within a country."""
    terms = []
    for row in rows:
        clicked = [e for e in row.top_clicked or [] if isinstance(e, dict) and e.get("asin")]
        first = min(clicked, key=lambda e: e.get("rank") or 99, default=None)
        own = [e for e in clicked if e["asin"] in own_asins]
        terms.append({
            "term": row.search_term,
            "country": countries.get(row.account_id, ""),
            "rank": row.search_frequency_rank,
            "week_start": row.week_start,
            "week_end": row.week_end,
            "top_asin": first["asin"] if first else None,
            "top_click_share": _float(first.get("click_share")) if first else None,
            "own_click_share": sum(float(e.get("click_share") or 0) for e in own) if own else None,
        })
    terms.sort(key=lambda term: (term["country"], term["rank"] is None, term["rank"] or 0))
    return terms


def _shape_competitors(competitors: list, history: list) -> list[dict]:
    points: dict[Any, list] = {}
    for row in history:
        points.setdefault(row.competitor_id, []).append(row)
    shaped = []
    for comp in competitors:
        rows = points.get(comp.id) or []
        first, last = (rows[0], rows[-1]) if rows else (None, None)
        price = _float(last.price) if last else _float(comp.current_price)
        bsr = last.bsr if last else comp.current_bsr
        rating = _float(last.rating) if last else _float(comp.rating)
        shaped.append({
            "asin": comp.asin,
            "title": comp.title,
            "brand": comp.brand,
            "marketplace": comp.marketplace,
            "price": price,
            "price_change_pct": relative_change(price, _float(first.price)) if first else None,
            "bsr": bsr,
            "bsr_change": bsr - first.bsr if first and bsr is not None and first.bsr is not None else None,
            "rating": rating,
            "rating_change": (rating - float(first.rating)
                              if first and rating is not None and first.rating is not None else None),
        })
    return shaped


def _sales_totals(rows: list) -> tuple[Optional[float], Optional[float]]:
    if not rows:
        return None, None
    return sum(float(r.revenue or 0) for r in rows), sum(float(r.units or 0) for r in rows)


def _kpi_gaps(lang: str, label: str, totals: PeriodTotals, filtered: bool) -> list[str]:
    """Why a current-quarter KPI is None, one note per cause."""
    gaps = []
    if totals.revenue is None:
        gaps.append(t(lang, "gap_no_sales", quarter=label))
    if totals.ad_spend is None:
        gaps.append(t(lang, "gap_ads_filter") if filtered else t(lang, "gap_ads_unavailable", quarter=label))
    else:
        if not totals.ad_spend:
            gaps.append(t(lang, "gap_roas_zero_spend"))
        if not totals.ad_sales:
            gaps.append(t(lang, "gap_acos_zero_sales"))
        if totals.revenue is not None and not totals.revenue:
            gaps.append(t(lang, "gap_tacos_zero_revenue"))
    if totals.units is not None and not totals.units:
        gaps.append(t(lang, "gap_return_rate_zero_units"))
    return gaps


async def collect_quarter_data(db, scope: QuarterScope) -> QuarterData:
    """Every figure of the quarterly review for ``scope``.

    Raises ValueError for a quarter outside 1-4 or a scope without accounts.
    """
    lang = scope.language
    start, end = quarter_bounds(scope.year, scope.quarter)
    prev_year, prev_q = previous_quarter(scope.year, scope.quarter)
    periods = {
        "current": (quarter_label(scope.year, scope.quarter), (start, end)),
        "previous": (quarter_label(prev_year, prev_q), quarter_bounds(prev_year, prev_q)),
        "last_year": (quarter_label(scope.year - 1, scope.quarter), quarter_bounds(scope.year - 1, scope.quarter)),
    }

    accounts = await fetch_accounts(db, scope.organization_id, scope.account_ids)
    if not accounts:
        raise ValueError("No Amazon account in scope")
    account_ids = [a["id"] for a in accounts]
    gaps: list[str] = []

    scope_asins: Optional[list[str]] = None
    if scope.filtered:
        scope_asins = await fetch_scope_asins(db, account_ids, scope.brand, scope.category, scope.asins)
        if not scope_asins:
            gaps.append(t(lang, "gap_no_products"))

    totals: dict[str, PeriodTotals] = {}
    daily: dict[str, list] = {}
    for name, (_, (p_start, p_end)) in periods.items():
        daily[name] = await fetch_daily_sales(db, account_ids, p_start, p_end, scope_asins)
        revenue, units = _sales_totals(daily[name])
        if scope_asins is None:
            ads = await fetch_campaign_ads(db, account_ids, p_start, p_end)
        else:
            ads = await fetch_asin_ads(db, account_ids, p_start, p_end, scope_asins)
        returned = await fetch_returned_units(db, account_ids, p_start, p_end, scope_asins)
        totals[name] = PeriodTotals(
            revenue=revenue,
            units=units,
            ad_spend=ads[0] if ads else None,
            ad_sales=ads[1] if ads else None,
            returned_units=float(returned or 0),
        )

    current_label = periods["current"][0]
    gaps.extend(_kpi_gaps(lang, current_label, totals["current"], scope_asins is not None))
    for name in ("previous", "last_year"):
        if totals[name].revenue is None:
            gaps.append(t(lang, "gap_no_sales_comparison", quarter=periods[name][0]))
    if end >= date.today():
        gaps.append(t(lang, "gap_quarter_in_progress", quarter=current_label,
                      today=date.today().strftime("%d/%m/%Y")))
    foreign = sorted({a["country"] for a in accounts} - EURO_MARKETPLACES)
    if foreign:
        gaps.append(t(lang, "gap_currency", countries=", ".join(foreign)))

    prev_start, prev_end = periods["previous"][1]
    top, bottom = _rank_asins(
        await fetch_asin_sales(db, account_ids, start, end, scope_asins),
        await fetch_asin_sales(db, account_ids, prev_start, prev_end, scope_asins),
    )

    snapshots = await fetch_quality_states(db, account_ids, scope_asins)
    states = {state: 0 for state in QUALITY_STATES}
    for row in snapshots:
        states[_quality_state(row.components)] += 1
    catalogue = {
        "states": states,
        "total": len(snapshots),
        "as_of": max((row.snapshot_date for row in snapshots), default=None),
        "open_anomalies": await fetch_open_anomalies(db, account_ids, scope_asins),
    }
    if not snapshots:
        gaps.append(t(lang, "gap_catalogue_empty"))

    search_terms: list[dict] = []
    sellers = [a["id"] for a in accounts if a["type"] == "seller"]
    if any(a["type"] == "vendor" for a in accounts):
        gaps.append(t(lang, "gap_search_terms_vendor"))
    if sellers:
        rows = await fetch_search_terms(db, sellers, scope_asins, SEARCH_TERMS_PER_ACCOUNT)
        if scope_asins is not None:
            own = set(scope_asins)
        else:
            clicked = {e.get("asin") for r in rows for e in r.top_clicked or [] if isinstance(e, dict)}
            own = await fetch_owned_asins(db, sellers, {a for a in clicked if a})
        countries = {a["id"]: a["country"] for a in accounts}
        search_terms = _shape_search_terms(rows, countries, own)
        if not search_terms:
            gaps.append(t(lang, "gap_search_terms_empty"))

    competitor_rows = await fetch_competitors(
        db, scope.organization_id, sorted({a["country"] for a in accounts})
    )
    competitors = _shape_competitors(
        competitor_rows,
        await fetch_competitor_history(db, [c.id for c in competitor_rows], start, end),
    )
    if not competitors:
        gaps.append(t(lang, "gap_competitors_empty"))

    return QuarterData(
        scope=scope,
        kpis=build_kpis(totals["current"], totals["previous"], totals["last_year"]),
        monthly=_monthly(start, daily["current"], daily["last_year"]),
        top_asins=top,
        bottom_asins=bottom,
        catalogue=catalogue,
        search_terms=search_terms,
        competitors=competitors,
        data_gaps=gaps,
        accounts=accounts,
    )
