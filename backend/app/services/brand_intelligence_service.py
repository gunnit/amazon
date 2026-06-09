"""Weekly Brand Intelligence — scheduled, persisted, diff-based, LLM-synthesized.

The pipeline runs in three deterministic stages followed by one LLM call:

  1. aggregate  — this week vs the previous week using AnalyticsService primitives
  2. diff       — week-over-week deltas (decline thresholds imported from Brand Pulse)
  3. generate   — ONE JSON-validated Anthropic call producing exec_summary + the
                  fixed section taxonomy, with guardrails (never invent numbers,
                  every claim carries source/confidence/evidence) and a fully
                  deterministic fallback when the LLM fails or no key is set.

Each run is persisted (snapshot + diff + intelligence JSONB) so the next week can
answer "what changed since last week" — the thing the request-time Brand Pulse
structurally cannot do. A completion Alert is emitted on the worker's own session
after commit, mirroring the brand-analysis notification pattern.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.amazon_account import AmazonAccount
from app.models.brand_intelligence import (
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_GENERATING,
    BrandIntelligenceReport,
    BrandIntelligenceSchedule,
)
from app.services.analytics_service import AnalyticsService
from app.services.data_extraction import DAILY_TOTAL_ASIN
# Import the decline thresholds rather than re-declaring them, so Pulse and
# Intelligence never drift apart (the architecture review's drift hazard).
from app.services.brand_pulse_service import (
    DECLINE_FAST_THRESHOLD_PCT,
    DECLINE_THRESHOLD_PCT,
)

logger = logging.getLogger(__name__)

ANTHROPIC_MODEL = "claude-sonnet-4-6"
FALLBACK_MODEL = "deterministic-fallback"

# Section taxonomy is fixed by the API contract; the frontend renders by key.
SECTION_DEFS: List[Tuple[str, str]] = [
    ("market_category", "Market & Category"),
    ("brand_evolution", "Brand Evolution"),
    ("competitor_activity", "Competitor Activity"),
    ("opportunities", "Opportunities"),
    ("risks", "Risks"),
    ("product_trends", "Product Trends"),
    ("strategic_recommendations", "Strategic Recommendations"),
]
SECTION_KEYS = [key for key, _ in SECTION_DEFS]

BRAND_INTELLIGENCE_READY_ALERT_TYPE = "brand_intelligence_ready"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _round(value: Any, digits: int = 2) -> float:
    try:
        return round(float(value or 0.0), digits)
    except (TypeError, ValueError):
        return 0.0


def _pct_change(current: float, previous: float) -> Optional[float]:
    if previous > 0:
        return round((current - previous) / previous * 100, 1)
    if current > 0:
        return 100.0
    return None


def _trend(pct: Optional[float]) -> str:
    if pct is None:
        return "stable"
    if pct > 5:
        return "up"
    if pct < -5:
        return "down"
    return "stable"


def week_label_for(period_start: date, period_end: date) -> str:
    iso_year, iso_week, _ = period_end.isocalendar()
    return f"W{iso_week:02d} {iso_year}"


def resolve_week_period(reference: Optional[date] = None, window_days: int = 7) -> Tuple[date, date]:
    """Resolve the most recent full week ending the day before ``reference``.

    Mirrors ``resolve_report_period(frequency='weekly')`` — the window ends
    yesterday relative to the reference so partial-today data never skews it.
    """
    ref = reference or date.today()
    end_date = ref - timedelta(days=1)
    start_date = end_date - timedelta(days=window_days - 1)
    return start_date, end_date


class BrandIntelligenceService:
    """CRUD + serialization for brand-intelligence reports and schedules."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def resolve_account(self, organization_id: UUID, account_id: UUID) -> Optional[AmazonAccount]:
        result = await self.db.execute(
            select(AmazonAccount).where(
                AmazonAccount.id == account_id,
                AmazonAccount.organization_id == organization_id,
            )
        )
        return result.scalars().first()

    async def list_reports(
        self, organization_id: UUID, account_id: UUID, limit: int = 20
    ) -> List[BrandIntelligenceReport]:
        result = await self.db.execute(
            select(BrandIntelligenceReport)
            .where(
                BrandIntelligenceReport.organization_id == organization_id,
                BrandIntelligenceReport.account_id == account_id,
            )
            .order_by(BrandIntelligenceReport.period_end.desc(), BrandIntelligenceReport.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_report(
        self, organization_id: UUID, report_id: UUID
    ) -> Optional[BrandIntelligenceReport]:
        result = await self.db.execute(
            select(BrandIntelligenceReport).where(
                BrandIntelligenceReport.id == report_id,
                BrandIntelligenceReport.organization_id == organization_id,
            )
        )
        return result.scalars().first()

    async def get_latest_completed(
        self, organization_id: UUID, account_id: UUID
    ) -> Optional[BrandIntelligenceReport]:
        result = await self.db.execute(
            select(BrandIntelligenceReport)
            .where(
                BrandIntelligenceReport.organization_id == organization_id,
                BrandIntelligenceReport.account_id == account_id,
                BrandIntelligenceReport.status == STATUS_COMPLETED,
            )
            .order_by(BrandIntelligenceReport.period_end.desc())
            .limit(1)
        )
        return result.scalars().first()

    async def create_pending_report(
        self,
        organization_id: UUID,
        account: AmazonAccount,
        *,
        period_start: date,
        period_end: date,
        window_days: int = 7,
        generated_by: str = "manual",
    ) -> BrandIntelligenceReport:
        """Create (or reuse) a report row for an account/week.

        A unique constraint on (account, period_start, period_end) keeps weeks
        idempotent; regenerating an existing week resets it to pending.
        """
        previous_end = period_start - timedelta(days=1)
        previous_start = previous_end - timedelta(days=window_days - 1)

        existing = await self.db.execute(
            select(BrandIntelligenceReport).where(
                BrandIntelligenceReport.account_id == account.id,
                BrandIntelligenceReport.period_start == period_start,
                BrandIntelligenceReport.period_end == period_end,
            )
        )
        report = existing.scalars().first()
        if report is not None:
            report.status = "pending"
            report.error_message = None
            report.generated_by = generated_by
            report.heartbeat_at = utcnow()
            await self.db.flush()
            return report

        report = BrandIntelligenceReport(
            organization_id=organization_id,
            account_id=account.id,
            brand_label=account.account_name or "Brand",
            period_start=period_start,
            period_end=period_end,
            previous_start=previous_start,
            previous_end=previous_end,
            window_days=window_days,
            week_label=week_label_for(period_start, period_end),
            status="pending",
            generated_by=generated_by,
            heartbeat_at=utcnow(),
        )
        self.db.add(report)
        await self.db.flush()
        return report

    async def get_schedule(
        self, organization_id: UUID, account_id: UUID
    ) -> Optional[BrandIntelligenceSchedule]:
        result = await self.db.execute(
            select(BrandIntelligenceSchedule).where(
                BrandIntelligenceSchedule.organization_id == organization_id,
                BrandIntelligenceSchedule.account_id == account_id,
            )
        )
        return result.scalars().first()

    async def upsert_schedule(
        self,
        organization_id: UUID,
        account_id: UUID,
        *,
        is_enabled: bool,
        day_of_week: int,
        timezone_name: str,
    ) -> BrandIntelligenceSchedule:
        schedule = await self.get_schedule(organization_id, account_id)
        next_run = compute_next_weekly_run(day_of_week, timezone_name) if is_enabled else None
        if schedule is None:
            schedule = BrandIntelligenceSchedule(
                organization_id=organization_id,
                account_id=account_id,
                is_enabled=is_enabled,
                day_of_week=day_of_week,
                timezone=timezone_name,
                next_run_at=next_run,
            )
            self.db.add(schedule)
        else:
            schedule.is_enabled = is_enabled
            schedule.day_of_week = day_of_week
            schedule.timezone = timezone_name
            schedule.next_run_at = next_run
        await self.db.flush()
        return schedule


def compute_next_weekly_run(day_of_week: int, timezone_name: str) -> datetime:
    """Next UTC run for a weekly schedule at 06:00 local on ``day_of_week``."""
    from zoneinfo import ZoneInfo

    try:
        tz = ZoneInfo(timezone_name)
    except Exception:
        tz = ZoneInfo("UTC")
    now_local = utcnow().astimezone(tz)
    days_ahead = (day_of_week - now_local.weekday()) % 7
    candidate = now_local.replace(hour=6, minute=0, second=0, microsecond=0) + timedelta(days=days_ahead)
    if candidate <= now_local:
        candidate += timedelta(days=7)
    return candidate.astimezone(timezone.utc)


# --------------------------------------------------------------------------
# Pipeline stage 1: aggregate
# --------------------------------------------------------------------------
async def aggregate_snapshot(
    analytics: AnalyticsService,
    account_ids: List[UUID],
    *,
    period_start: date,
    period_end: date,
    previous_start: date,
    previous_end: date,
    top_limit: int = 10,
) -> Dict[str, Any]:
    """Deterministic metrics for this period and the previous one.

    Reuses the exact AnalyticsService primitives the dashboard and Brand Pulse
    use, so the numbers agree everywhere.
    """
    overview = await analytics.compute_dashboard_kpis(account_ids, period_start, period_end)
    current_map = await analytics.asin_sales_breakdown(account_ids, period_start, period_end)
    previous_map = await analytics.asin_sales_breakdown(account_ids, previous_start, previous_end)
    ads = await analytics.compute_advertising_metrics(account_ids, period_start, period_end)

    asins = sorted((set(current_map) | set(previous_map)) - {DAILY_TOTAL_ASIN})
    titles = await analytics._asin_titles(account_ids, asins) if asins else {}

    return {
        "overview": overview,
        "asin_sales": {a: _round(s) for a, s in current_map.items() if a != DAILY_TOTAL_ASIN},
        "previous_asin_sales": {a: _round(s) for a, s in previous_map.items() if a != DAILY_TOTAL_ASIN},
        "asin_titles": {a: titles.get(a) for a in asins},
        "ads": {
            "impressions": int(ads.get("impressions") or 0),
            "clicks": int(ads.get("clicks") or 0),
            "spend": _round(ads.get("cost")),
            "ad_sales": _round(ads.get("sales")),
            "acos": _round(ads.get("acos"), 1),
            "roas": _round(ads.get("roas"), 2),
            "is_available": bool(ads.get("impressions") or ads.get("clicks") or ads.get("cost")),
        },
        "top_limit": top_limit,
    }


# --------------------------------------------------------------------------
# Pipeline stage 2: diff (week-over-week)
# --------------------------------------------------------------------------
def diff_snapshot(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    """Week-over-week deltas: KPI changes, movers, decliners, new/dropped ASINs."""
    overview = snapshot.get("overview") or {}
    changes = overview.get("changes") or {}
    current = overview.get("current") or {}
    previous = overview.get("previous") or {}

    current_map: Dict[str, float] = snapshot.get("asin_sales") or {}
    previous_map: Dict[str, float] = snapshot.get("previous_asin_sales") or {}
    titles: Dict[str, Optional[str]] = snapshot.get("asin_titles") or {}
    top_limit = int(snapshot.get("top_limit") or 10)

    def _row(asin: str, current_sales: float, previous_sales: float) -> Dict[str, Any]:
        return {
            "asin": asin,
            "title": titles.get(asin),
            "revenue": _round(current_sales),
            "previous_revenue": _round(previous_sales),
            "change_percent": _pct_change(current_sales, previous_sales),
        }

    gainers = sorted(
        (
            _row(a, s, previous_map.get(a, 0.0))
            for a, s in current_map.items()
            if s > previous_map.get(a, 0.0)
        ),
        key=lambda r: (r["change_percent"] is None, -(r["change_percent"] or 0.0)),
    )[:top_limit]

    decliners: List[Dict[str, Any]] = []
    for asin, prev in previous_map.items():
        if prev <= 0:
            continue
        cur = current_map.get(asin, 0.0)
        change = (cur - prev) / prev * 100
        if change > DECLINE_THRESHOLD_PCT:
            continue
        row = _row(asin, cur, prev)
        row["trend_class"] = "declining_fast" if change < DECLINE_FAST_THRESHOLD_PCT else "declining"
        decliners.append(row)
    decliners.sort(key=lambda r: r["change_percent"] if r["change_percent"] is not None else 0.0)
    decliners = decliners[:top_limit]

    new_asins = [
        _row(a, s, 0.0) for a, s in current_map.items() if a not in previous_map and s > 0
    ]
    dropped_asins = [
        _row(a, 0.0, p) for a, p in previous_map.items() if a not in current_map and p > 0
    ]

    def _kpi(key: str) -> Dict[str, Any]:
        change = changes.get(key) or {}
        return {
            "current": _round(current.get(key)),
            "previous": _round(previous.get(key)),
            "delta_percent": _round(change.get("percent"), 1),
            "trend": change.get("trend", "stable"),
        }

    return {
        "kpis": {key: _kpi(key) for key in ("revenue", "units", "orders", "average_order_value")},
        "active_asins": {
            "current": int(current.get("active_asins") or 0),
            "previous": int(previous.get("active_asins") or 0),
        },
        "gainers": gainers,
        "decliners": decliners,
        "new_asins": new_asins[:top_limit],
        "dropped_asins": dropped_asins[:top_limit],
        "ads": snapshot.get("ads") or {},
    }


# --------------------------------------------------------------------------
# Pipeline stage 3: generate (LLM with deterministic fallback)
# --------------------------------------------------------------------------
def _fmt_eur(value: Any) -> str:
    return f"EUR {_round(value):,.2f}"


def _fmt_pct(value: Any) -> str:
    if value is None:
        return "new"
    return f"{float(value):+.1f}%"


def build_exec_summary(brand_label: str, diff: Dict[str, Any]) -> Dict[str, Any]:
    kpis_diff = diff.get("kpis") or {}
    rev = kpis_diff.get("revenue") or {}
    rev_delta = rev.get("delta_percent")
    direction = "up" if (rev_delta or 0) > 0 else ("down" if (rev_delta or 0) < 0 else "flat")
    headline = (
        f"{brand_label}: revenue {direction} {_fmt_pct(rev_delta)} week-over-week "
        f"to {_fmt_eur(rev.get('current'))}."
    )

    cards: List[Dict[str, Any]] = []
    labels = {
        "revenue": "Revenue",
        "units": "Units",
        "orders": "Orders",
        "average_order_value": "AOV",
    }
    for key, label in labels.items():
        block = kpis_diff.get(key) or {}
        value = (
            _fmt_eur(block.get("current"))
            if key in ("revenue", "average_order_value")
            else f"{int(block.get('current') or 0):,}"
        )
        cards.append(
            {
                "label": label,
                "value": value,
                "delta_percent": block.get("delta_percent"),
                "trend": block.get("trend", "stable"),
            }
        )
    return {"headline": headline, "kpis": cards}


def build_fallback_sections(brand_label: str, diff: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Deterministic, numbers-grounded sections used when no LLM is available.

    Every item carries Source/Confidence/Evidence so the contract shape is
    identical whether the narrative came from the LLM or this fallback.
    """
    kpis = diff.get("kpis") or {}
    rev = kpis.get("revenue") or {}
    units = kpis.get("units") or {}
    aov = kpis.get("average_order_value") or {}
    ads = diff.get("ads") or {}
    gainers = diff.get("gainers") or []
    decliners = diff.get("decliners") or []
    new_asins = diff.get("new_asins") or []
    active = diff.get("active_asins") or {}

    def item(title: str, detail: str, source: str, confidence: str, evidence: str) -> Dict[str, Any]:
        return {
            "title": title,
            "detail": detail,
            "source": source,
            "confidence": confidence,
            "evidence": evidence,
        }

    sections: Dict[str, Dict[str, Any]] = {}

    # market_category
    sections["market_category"] = {
        "narrative": (
            f"Catalog activity moved from {active.get('previous', 0)} to "
            f"{active.get('current', 0)} active ASINs week-over-week. First-party "
            f"market-share signals are not connected, so this view is limited to "
            f"the brand's own performance."
        ),
        "items": [
            item(
                "Active catalog breadth",
                f"{active.get('current', 0)} ASINs sold this week vs "
                f"{active.get('previous', 0)} last week.",
                "Internal sales (Amazon)",
                "high",
                f"active_asins current={active.get('current', 0)}, previous={active.get('previous', 0)}",
            )
        ],
    }

    # brand_evolution
    sections["brand_evolution"] = {
        "narrative": (
            f"Revenue is {_fmt_pct(rev.get('delta_percent'))} w/w at "
            f"{_fmt_eur(rev.get('current'))}; units {_fmt_pct(units.get('delta_percent'))} and "
            f"AOV {_fmt_pct(aov.get('delta_percent'))}."
        ),
        "items": [
            item(
                "Revenue movement",
                f"{_fmt_eur(rev.get('current'))} this week ({_fmt_pct(rev.get('delta_percent'))} vs "
                f"{_fmt_eur(rev.get('previous'))} last week).",
                "Internal sales (Amazon)",
                "high",
                f"revenue current={rev.get('current')}, previous={rev.get('previous')}",
            ),
            item(
                "Order economics",
                f"AOV {_fmt_eur(aov.get('current'))} ({_fmt_pct(aov.get('delta_percent'))} w/w).",
                "Internal sales (Amazon)",
                "high",
                f"average_order_value current={aov.get('current')}, previous={aov.get('previous')}",
            ),
        ],
    }

    # competitor_activity — gracefully omitted when no competitor data is wired.
    sections["competitor_activity"] = {
        "narrative": (
            "No competitor tracking data is connected for this account this week, "
            "so competitor moves cannot be reported."
        ),
        "items": [],
    }

    # opportunities
    opp_items: List[Dict[str, Any]] = []
    for row in gainers[:3]:
        opp_items.append(
            item(
                f"Scale {row['asin']}",
                f"{row.get('title') or row['asin']} grew {_fmt_pct(row.get('change_percent'))} to "
                f"{_fmt_eur(row.get('revenue'))}; protect momentum with ad headroom.",
                "Internal sales (Amazon)",
                "medium",
                f"asin={row['asin']} revenue {row.get('previous_revenue')}→{row.get('revenue')}",
            )
        )
    for row in new_asins[:2]:
        opp_items.append(
            item(
                f"New entrant {row['asin']}",
                f"{row.get('title') or row['asin']} sold {_fmt_eur(row.get('revenue'))} in its "
                f"first tracked week.",
                "Internal sales (Amazon)",
                "medium",
                f"asin={row['asin']} appeared this week",
            )
        )
    if ads.get("is_available") and (ads.get("acos") or 0) > 0 and (ads.get("acos") or 0) < 20:
        opp_items.append(
            item(
                "Advertising headroom",
                f"ACOS is {ads.get('acos')}% with ROAS {ads.get('roas')}x — efficient enough to "
                f"increase spend on top movers.",
                "Internal advertising (Amazon Ads)",
                "medium",
                f"acos={ads.get('acos')}, roas={ads.get('roas')}",
            )
        )
    sections["opportunities"] = {
        "narrative": (
            "Growth ASINs and under-leveraged ad efficiency are the clearest "
            "openings this week." if opp_items else "No standout growth signals this week."
        ),
        "items": opp_items,
    }

    # risks
    risk_items: List[Dict[str, Any]] = []
    for row in decliners[:3]:
        risk_items.append(
            item(
                f"Decline on {row['asin']}",
                f"{row.get('title') or row['asin']} fell {_fmt_pct(row.get('change_percent'))} to "
                f"{_fmt_eur(row.get('revenue'))} ({row.get('trend_class', 'declining')}).",
                "Internal sales (Amazon)",
                "high",
                f"asin={row['asin']} revenue {row.get('previous_revenue')}→{row.get('revenue')}",
            )
        )
    if (rev.get("delta_percent") or 0) < DECLINE_THRESHOLD_PCT:
        risk_items.append(
            item(
                "Overall revenue softening",
                f"Total revenue down {_fmt_pct(rev.get('delta_percent'))} w/w.",
                "Internal sales (Amazon)",
                "high",
                f"revenue delta={rev.get('delta_percent')}%",
            )
        )
    sections["risks"] = {
        "narrative": (
            "Fast decliners and overall softening are the main downside risks."
            if risk_items
            else "No material downside movers this week."
        ),
        "items": risk_items,
    }

    # product_trends
    trend_items: List[Dict[str, Any]] = []
    for row in gainers[:3]:
        trend_items.append(
            item(
                f"{row['asin']} accelerating",
                f"{row.get('title') or row['asin']} {_fmt_pct(row.get('change_percent'))} w/w.",
                "Internal sales (Amazon)",
                "high",
                f"asin={row['asin']} {row.get('previous_revenue')}→{row.get('revenue')}",
            )
        )
    for row in decliners[:3]:
        trend_items.append(
            item(
                f"{row['asin']} cooling",
                f"{row.get('title') or row['asin']} {_fmt_pct(row.get('change_percent'))} w/w.",
                "Internal sales (Amazon)",
                "high",
                f"asin={row['asin']} {row.get('previous_revenue')}→{row.get('revenue')}",
            )
        )
    sections["product_trends"] = {
        "narrative": (
            "Movers below are ranked by week-over-week revenue change."
            if trend_items
            else "No significant per-ASIN movement this week."
        ),
        "items": trend_items,
    }

    # strategic_recommendations
    rec_items: List[Dict[str, Any]] = []
    if decliners:
        top = decliners[0]
        rec_items.append(
            item(
                f"Stabilize {top['asin']}",
                f"Review pricing, Buy Box and content for {top.get('title') or top['asin']} "
                f"({_fmt_pct(top.get('change_percent'))} w/w).",
                "Internal sales (Amazon)",
                "high",
                f"asin={top['asin']} change={top.get('change_percent')}%",
            )
        )
    if gainers:
        top = gainers[0]
        rec_items.append(
            item(
                f"Double down on {top['asin']}",
                f"Reallocate ad budget to {top.get('title') or top['asin']} while demand is rising.",
                "Internal sales (Amazon)",
                "medium",
                f"asin={top['asin']} change={top.get('change_percent')}%",
            )
        )
    if not ads.get("is_available"):
        rec_items.append(
            item(
                "Connect advertising data",
                "No ad data covers this week; connect Amazon Ads to unlock ACOS/TACOS and "
                "ad-driven recommendations.",
                "Coverage gap",
                "high",
                "ads.is_available=false",
            )
        )
    if not rec_items:
        rec_items.append(
            item(
                "Maintain coverage and content quality",
                "No urgent movers this week; keep catalog coverage and content health steady.",
                "Internal sales (Amazon)",
                "medium",
                "no decliners or gainers exceeded thresholds",
            )
        )
    sections["strategic_recommendations"] = {
        "narrative": "Prioritized, evidence-backed actions for the coming week.",
        "items": rec_items[:5],
    }

    return [
        {
            "key": key,
            "title": title,
            "narrative": sections[key]["narrative"],
            "items": sections[key]["items"],
            "delta": None,
        }
        for key, title in SECTION_DEFS
    ]


def _llm_sections(brand_label: str, diff: Dict[str, Any], api_key: str) -> Optional[List[Dict[str, Any]]]:
    """One JSON-validated Anthropic call. Returns None on any failure so the
    caller falls back deterministically. Numbers are pre-computed — the model is
    told never to invent or recompute them."""
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=api_key)
        section_list = "\n".join(f'  - "{k}": {t}' for k, t in SECTION_DEFS)
        prompt = f"""You are an Amazon brand strategy analyst writing a weekly brand-intelligence briefing for "{brand_label}".

All numbers are already computed. Do NOT calculate, infer, invent, round or change any number.
Use ONLY these week-over-week deltas (JSON):
{json.dumps(diff, ensure_ascii=False, indent=2)}

Rules:
- Never invent competitor revenue, market size or search/market share.
- If a section has no supporting data, write a one-sentence narrative that says the data is not connected and return an empty items list for it — do not fabricate.
- Every item MUST carry: source (where the claim comes from, e.g. "Internal sales (Amazon)"), confidence ("high"|"medium"|"low"), and evidence (the exact metric path/values backing it).

Return ONLY valid JSON: an object with a "sections" array. Produce exactly these sections in this order, each with key, title, narrative, items:
{section_list}

Each item: {{"title": str, "detail": str, "source": str, "confidence": "high"|"medium"|"low", "evidence": str}}"""

        message = client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=3000,
            messages=[{"role": "user", "content": prompt}],
        )
        text = message.content[0].text.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            lines = lines[1:-1] if lines and lines[-1].strip() == "```" else lines[1:]
            text = "\n".join(lines)
        parsed = json.loads(text)
        return _validate_sections(parsed.get("sections"))
    except Exception:
        logger.exception("Brand intelligence LLM generation failed; using fallback")
        return None


def _validate_sections(sections: Any) -> List[Dict[str, Any]]:
    if not isinstance(sections, list):
        raise ValueError("sections must be a list")
    by_key = {s.get("key"): s for s in sections if isinstance(s, dict)}
    missing = set(SECTION_KEYS) - set(by_key)
    if missing:
        raise ValueError(f"LLM response missing sections: {missing}")
    out: List[Dict[str, Any]] = []
    for key, title in SECTION_DEFS:
        s = by_key[key]
        items = []
        for raw in s.get("items") or []:
            if not isinstance(raw, dict):
                continue
            items.append(
                {
                    "title": str(raw.get("title", "")),
                    "detail": str(raw.get("detail", "")),
                    "source": str(raw.get("source", "Internal sales (Amazon)")),
                    "confidence": str(raw.get("confidence", "medium")),
                    "evidence": str(raw.get("evidence", "")),
                }
            )
        out.append(
            {
                "key": key,
                "title": title,
                "narrative": str(s.get("narrative", "")),
                "items": items,
                "delta": None,
            }
        )
    return out


def generate_intelligence(
    brand_label: str,
    diff: Dict[str, Any],
    *,
    api_key: Optional[str] = None,
) -> Tuple[Dict[str, Any], str]:
    """Produce exec_summary + sections. Returns (intelligence, model_used)."""
    exec_summary = build_exec_summary(brand_label, diff)
    sections: Optional[List[Dict[str, Any]]] = None
    model = FALLBACK_MODEL
    if api_key:
        sections = _llm_sections(brand_label, diff, api_key)
        if sections is not None:
            model = ANTHROPIC_MODEL
    if sections is None:
        sections = build_fallback_sections(brand_label, diff)
    coverage_note = None
    if not (diff.get("ads") or {}).get("is_available"):
        coverage_note = "Advertising data is not connected for this period; ad-related sections are limited."
    return (
        {"exec_summary": exec_summary, "sections": sections, "coverage_note": coverage_note},
        model,
    )


# --------------------------------------------------------------------------
# Serialization (model -> API contract)
# --------------------------------------------------------------------------
def report_to_summary(report: BrandIntelligenceReport) -> Dict[str, Any]:
    return {
        "id": report.id,
        "account_id": report.account_id,
        "brand_label": report.brand_label,
        "period_start": report.period_start,
        "period_end": report.period_end,
        "week_label": report.week_label,
        "status": report.status,
        "generated_at": report.generated_at,
    }


def report_to_detail(report: BrandIntelligenceReport) -> Dict[str, Any]:
    intelligence = report.intelligence or {}
    exec_summary = intelligence.get("exec_summary") or {"headline": "", "kpis": []}
    sections = intelligence.get("sections") or []
    return {
        "id": report.id,
        "account_id": report.account_id,
        "brand_label": report.brand_label,
        "period": {
            "start": report.period_start,
            "end": report.period_end,
            "previous_start": report.previous_start,
            "previous_end": report.previous_end,
            "week_label": report.week_label,
            "window_days": report.window_days,
        },
        "status": report.status,
        "generated_at": report.generated_at,
        "model": report.model,
        "coverage_note": report.coverage_note or intelligence.get("coverage_note"),
        "exec_summary": exec_summary,
        "sections": sections,
    }


# --------------------------------------------------------------------------
# Worker entry: run the full pipeline for one persisted report row
# --------------------------------------------------------------------------
def process_brand_intelligence_report_job(report_id: str) -> None:
    """Synchronous Celery entry point — runs the async pipeline via run_async."""
    from workers.tasks.scheduled_reports import run_async

    return run_async(lambda: _process_report(report_id))


async def _process_report(report_id: str) -> None:
    from app.db import session as db_session

    async with db_session.AsyncSessionLocal() as db:
        report = await db.get(BrandIntelligenceReport, UUID(report_id))
        if report is None:
            logger.warning("Brand intelligence report %s vanished before processing", report_id)
            return

        report.status = STATUS_GENERATING
        report.heartbeat_at = utcnow()
        await db.commit()

        organization_id = report.organization_id
        account_id = report.account_id
        brand_label = report.brand_label
        try:
            analytics = AnalyticsService(db)
            account_ids = [account_id] if account_id else []
            snapshot = await aggregate_snapshot(
                analytics,
                account_ids,
                period_start=report.period_start,
                period_end=report.period_end,
                previous_start=report.previous_start,
                previous_end=report.previous_end,
            )
            diff = diff_snapshot(snapshot)
            intelligence, model = generate_intelligence(
                brand_label, diff, api_key=settings.ANTHROPIC_API_KEY
            )

            report.snapshot = snapshot
            report.diff = diff
            report.intelligence = intelligence
            report.coverage_note = intelligence.get("coverage_note")
            report.model = model
            report.status = STATUS_COMPLETED
            report.generated_at = utcnow()
            report.heartbeat_at = utcnow()
            await db.commit()
        except Exception:
            logger.exception("Brand intelligence pipeline failed for %s", report_id)
            report.status = STATUS_FAILED
            report.error_message = "Generation failed before completion"
            report.heartbeat_at = utcnow()
            await db.commit()
            return

    # Emit the completion alert on a fresh session, after the job's own commit,
    # mirroring the brand-analysis notification pattern.
    try:
        await _emit_ready_alert(organization_id, account_id, brand_label, report.id)
    except Exception as exc:  # best-effort; never fail the job on notification
        logger.warning("Brand intelligence notification emit failed for %s: %s", organization_id, exc)


async def _ensure_alert_rule(db: AsyncSession, organization_id: UUID, alert_type: str):
    from app.models.alert import AlertRule

    result = await db.execute(
        select(AlertRule).where(
            AlertRule.organization_id == organization_id,
            AlertRule.alert_type == alert_type,
        )
    )
    rule = result.scalars().first()
    if rule:
        return rule
    rule = AlertRule(
        organization_id=organization_id,
        name="Weekly Brand Intelligence",
        alert_type=alert_type,
        conditions={"auto_created": True},
        applies_to_accounts=None,
        applies_to_asins=None,
        notification_channels=[],
        notification_emails=None,
        webhook_url=None,
        is_enabled=True,
    )
    db.add(rule)
    await db.flush()
    return rule


async def _emit_ready_alert(
    organization_id: UUID, account_id: Optional[UUID], brand_label: str, report_id: UUID
) -> None:
    from app.db import session as db_session
    from app.models.alert import Alert

    alert_type = BRAND_INTELLIGENCE_READY_ALERT_TYPE
    dedup_key = f"{alert_type}:{report_id}"
    message = f"Weekly Brand Intelligence for {brand_label} is ready."
    now = datetime.utcnow()

    async with db_session.AsyncSessionLocal() as ndb:
        rule = await _ensure_alert_rule(ndb, organization_id, alert_type)
        existing = await ndb.execute(
            select(Alert).where(Alert.rule_id == rule.id, Alert.dedup_key == dedup_key)
        )
        if existing.scalars().first() is None:
            ndb.add(
                Alert(
                    rule_id=rule.id,
                    organization_id=organization_id,
                    account_id=account_id,
                    asin=None,
                    event_kind=alert_type,
                    dedup_key=dedup_key,
                    message=message,
                    details={"brand_label": brand_label, "report_id": str(report_id)},
                    severity="info",
                    is_read=False,
                    triggered_at=now,
                    last_seen_at=now,
                    notification_status="pending",
                )
            )
        rule.last_triggered_at = now
        await ndb.commit()
