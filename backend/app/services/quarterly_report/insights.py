"""Insights and actions for the quarterly business review (R5).

``rule_insights`` is deterministic and names the products and competitors
behind each finding. In order of importance: revenue against the previous
quarter, red listings, open catalogue anomalies, the ASINs with the largest
decline, the TACOS trend, competitors cutting price or gaining rank, the search
term where our click share is lowest, the return rate, revenue against the same
quarter last year. At most ``MAX_INSIGHTS``, the number of cards on the deck's
insights slide, so nothing is dropped silently. Advertising advice is given only
when the scope has advertising data.

``build_insights`` asks Claude for richer insights when an API key is configured
and falls back to the rules on any failure (no key, no credit, provider error,
unusable answer), so the deck is always complete.

``build_insights`` makes a blocking HTTP call: async callers run it in a thread.
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from typing import Literal, Optional

from app.config import settings
from app.services.ai_analysis_service import build_lang_instruction
from app.services.brand_analysis.deck.format import EMPTY, Formatter, truncate
from app.services.quarterly_report.data import (
    Metric,
    QuarterData,
    point_change,
    previous_quarter,
    quarter_label,
    relative_change,
)
from app.services.quarterly_report.deck import (
    COPY,
    MAX_INSIGHTS,
    format_change,
    format_value,
    signed_currency,
    t,
)

logger = logging.getLogger(__name__)

AI_MODEL = "claude-sonnet-4-6"  # same model as strategic_recommendations_service
AI_MAX_TOKENS = 1800
AI_TIMEOUT_S = 120.0

# Rule thresholds
REVENUE_CHANGE_PCT = 5.0  # revenue change worth an insight, either way (inclusive)
TACOS_CHANGE_PP = 2.0
RETURN_RATE_CHANGE_PP = 1.0
RED_SHARE = 0.10  # share of red listings worth an insight
DECLINE_SHARE = 0.03  # named decliners must lose this share of last quarter's revenue
COMPETITOR_PRICE_DROP_PCT = 10.0
COMPETITOR_BSR_GAIN_PCT = 30.0  # BSR at least this much lower than at quarter start
DRIVERS_SHOWN = 2  # ASINs named in a revenue insight
DECLINERS_SHOWN = 3
COMPETITORS_SHOWN = 2
TITLE_CHARS = 30


@dataclass
class Insight:
    title: str
    body: str
    action: str
    source: Literal["ai", "rules"]


class _Rules:
    """What every rule needs: language, formatter, period labels, the data."""

    def __init__(self, data: QuarterData) -> None:
        scope = data.scope
        self.data = data
        self.lang = scope.language
        self.fmt = Formatter(self.lang)
        self.labels = {
            "current": quarter_label(scope.year, scope.quarter),
            "previous": quarter_label(*previous_quarter(scope.year, scope.quarter)),
            "last_year": quarter_label(scope.year - 1, scope.quarter),
        }
        ad_spend = self.metric("ad_spend")
        self.has_ads = ad_spend is not None and ad_spend.value is not None

    def metric(self, key: str) -> Optional[Metric]:
        return next((m for m in self.data.kpis if m.key == key), None)

    def t(self, key: str, **values) -> str:
        return t(self.lang, key, **values)

    def insight(self, title_key: str, body: str, action_key: str) -> Insight:
        return Insight(self.t(title_key), body, self.t(action_key), "rules")

    def ads_action(self, key: str) -> str:
        """The action with advertising advice, or the variant without it."""
        return key if self.has_ads else f"{key}_no_ads"

    def compared(self, metric: Metric, period: str) -> dict:
        base = getattr(metric, period)
        return {
            "quarter": self.labels["current"],
            "value": format_value(self.fmt, metric.unit, metric.value),
            "base": format_value(self.fmt, metric.unit, base),
            "base_quarter": self.labels[period],
            "change": format_change(self.fmt, metric.unit, metric.value, base),
        }


def _asin_label(row: dict) -> str:
    title = truncate(row.get("title") or "", TITLE_CHARS)
    return f"{row['asin']} ({title})" if title else row["asin"]


def _revenue_drivers(rules: _Rules, period: str, direction: str) -> str:
    """The ASINs behind a revenue change, from the top and bottom ASIN lists.

    Against the previous quarter: the largest gains or declines. Against last
    year no per-ASIN figures exist, so the quarter's leading ASINs are named.
    """
    fmt = rules.fmt
    if period == "previous" and direction == "down":
        items = [f"{_asin_label(r)} {signed_currency(fmt, r['change'])}"
                 for r in rules.data.bottom_asins[:DRIVERS_SHOWN]]
        key = "ins_rev_drivers_down"
    elif period == "previous":
        gains = sorted(((r["revenue"] - (r.get("previous_revenue") or 0.0), r)
                        for r in rules.data.top_asins), key=lambda gain: -gain[0])
        items = [f"{_asin_label(r)} {signed_currency(fmt, gain)}"
                 for gain, r in gains if gain > 0][:DRIVERS_SHOWN]
        key = "ins_rev_drivers_up"
    else:
        items = [f"{_asin_label(r)} {fmt.currency(r['revenue'])}"
                 for r in rules.data.top_asins[:DRIVERS_SHOWN]]
        key = "ins_rev_leaders"
    return rules.t(key, items="; ".join(items)) if items else ""


def _revenue(rules: _Rules, period: str) -> Optional[Insight]:
    revenue = rules.metric("revenue")
    if revenue is None:
        return None
    change = relative_change(revenue.value, getattr(revenue, period))
    if change is None or abs(change) < REVENUE_CHANGE_PCT:
        return None
    direction = "down" if change < 0 else "up"
    suffix = "prev" if period == "previous" else "ly"
    body = " ".join(part for part in (
        rules.t("ins_rev_body", **rules.compared(revenue, period)),
        _revenue_drivers(rules, period, direction),
    ) if part)
    return rules.insight(f"ins_rev_{direction}_{suffix}_title", body,
                         rules.ads_action(f"ins_rev_{direction}_action"))


def _red_share(rules: _Rules) -> Optional[Insight]:
    catalogue = rules.data.catalogue or {}
    total = catalogue.get("total") or 0
    red = (catalogue.get("states") or {}).get("red", 0)
    if not total or red / total < RED_SHARE:
        return None
    body = rules.t("ins_red_body", red=red, total=total, share=rules.fmt.share(red / total * 100))
    return rules.insight("ins_red_title", body, "ins_red_action")


def _anomalies(rules: _Rules) -> Optional[Insight]:
    anomalies = (rules.data.catalogue or {}).get("open_anomalies") or {}
    if not anomalies:
        return None
    kinds = ", ".join(
        f"{rules.t(f'anomaly_{kind}') if f'anomaly_{kind}' in COPY['it'] else kind} {count}"
        for kind, count in sorted(anomalies.items(), key=lambda item: -item[1])
    )
    body = rules.t("ins_anomalies_body", count=sum(anomalies.values()), kinds=kinds)
    return rules.insight("ins_anomalies_title", body, "ins_anomalies_action")


def _decliners(rules: _Rules) -> Optional[Insight]:
    revenue = rules.metric("revenue")
    base = revenue.previous if revenue is not None else None
    rows = rules.data.bottom_asins[:DECLINERS_SHOWN]
    if not rows or not base or base <= 0:
        return None
    drop = -sum(row["change"] for row in rows)
    if drop / base < DECLINE_SHARE:
        return None
    fmt = rules.fmt
    body = rules.t(
        "ins_decliners_body",
        base_quarter=rules.labels["previous"],
        total=fmt.currency(drop),
        share=fmt.share(drop / base * 100),
        items="; ".join(f"{_asin_label(r)} {signed_currency(fmt, r['change'])}" for r in rows),
    )
    return rules.insight("ins_decliners_title", body, "ins_decliners_action")


def _tacos(rules: _Rules) -> Optional[Insight]:
    tacos = rules.metric("tacos")
    points = point_change(tacos.value, tacos.previous) if tacos is not None else None
    if points is None or abs(points) < TACOS_CHANGE_PP:
        return None
    direction = "up" if points > 0 else "down"
    body = rules.t("ins_tacos_body", **rules.compared(tacos, "previous"))
    return rules.insight(f"ins_tacos_{direction}_title", body, f"ins_tacos_{direction}_action")


def _competitors(rules: _Rules) -> Optional[Insight]:
    fmt = rules.fmt
    flagged = []
    for comp in rules.data.competitors:
        price_change = comp.get("price_change_pct")
        bsr, bsr_change = comp.get("bsr"), comp.get("bsr_change")
        start_bsr = bsr - bsr_change if bsr is not None and bsr_change is not None else None
        bsr_gain = -bsr_change * 100.0 / start_bsr if start_bsr and start_bsr > 0 else None
        parts = []
        if price_change is not None and price_change <= -COMPETITOR_PRICE_DROP_PCT:
            parts.append(rules.t("ins_competitor_price", change=fmt.percent_signed(price_change),
                                 price=fmt.currency(comp.get("price"), 2)))
        if bsr_gain is not None and bsr_gain >= COMPETITOR_BSR_GAIN_PCT:
            parts.append(rules.t("ins_competitor_bsr", start=fmt.integer(start_bsr), end=fmt.integer(bsr)))
        if parts:
            name = " · ".join(p for p in (comp.get("brand"), truncate(comp.get("title") or "", TITLE_CHARS)) if p)
            where = ", ".join(p for p in (comp["asin"], comp.get("marketplace")) if p)
            strength = max(-(price_change or 0.0), bsr_gain or 0.0)
            flagged.append((strength, f"{name or comp['asin']} ({where}): {', '.join(parts)}"))
    if not flagged:
        return None
    flagged.sort(key=lambda item: -item[0])
    body = rules.t("ins_competitors_body", quarter=rules.labels["current"],
                   items="; ".join(item for _, item in flagged[:COMPETITORS_SHOWN]))
    return rules.insight("ins_competitors_title", body, "ins_competitors_action")


def _search_term(rules: _Rules) -> Optional[Insight]:
    """The most searched term where our click share is lowest and someone else leads."""
    candidates = [
        term for term in rules.data.search_terms
        if term.get("own_click_share") is not None
        and (term.get("top_click_share") is None or term["own_click_share"] < term["top_click_share"])
    ]
    if not candidates:
        return None
    term = min(candidates, key=lambda s: (s["own_click_share"], s.get("rank") is None, s.get("rank") or 0))
    fmt = rules.fmt
    top_share = term.get("top_click_share")
    body = rules.t(
        "ins_term_body",
        term=term["term"],
        country=term.get("country") or EMPTY,
        rank=fmt.integer(term.get("rank")),
        own=fmt.share(term["own_click_share"] * 100),
        top_asin=term.get("top_asin") or EMPTY,
        top=EMPTY if top_share is None else fmt.share(top_share * 100),
    )
    return rules.insight("ins_term_title", body, rules.ads_action("ins_term_action"))


def _returns(rules: _Rules) -> Optional[Insight]:
    returns = rules.metric("return_rate")
    points = point_change(returns.value, returns.previous) if returns is not None else None
    if points is None or points < RETURN_RATE_CHANGE_PP:
        return None
    body = rules.t("ins_returns_body", **rules.compared(returns, "previous"))
    return rules.insight("ins_returns_up_title", body, "ins_returns_action")


def rule_insights(data: QuarterData) -> list[Insight]:
    rules = _Rules(data)
    by_importance = (
        _revenue(rules, "previous"),
        _red_share(rules),
        _anomalies(rules),
        _decliners(rules),
        _tacos(rules),
        _competitors(rules),
        _search_term(rules),
        _returns(rules),
        _revenue(rules, "last_year"),
    )
    insights = [insight for insight in by_importance if insight is not None][:MAX_INSIGHTS]
    if not insights:
        insights = [rules.insight("ins_stable_title", rules.t("ins_stable_body"), "ins_stable_action")]
    return insights


def _anthropic_client(api_key: str):
    import anthropic

    return anthropic.Anthropic(api_key=api_key, timeout=AI_TIMEOUT_S)


def _prompt(data: QuarterData, rules: list[Insight]) -> str:
    scope = data.scope
    payload = {
        "quarter": quarter_label(scope.year, scope.quarter),
        "previous_quarter": quarter_label(*previous_quarter(scope.year, scope.quarter)),
        "same_quarter_last_year": quarter_label(scope.year - 1, scope.quarter),
        "scope": {
            "countries": sorted({a.get("country") for a in data.accounts if a.get("country")}),
            "brand": scope.brand,
            "category": scope.category,
            "asins": scope.asins,
        },
        "kpis": [asdict(metric) for metric in data.kpis],
        "monthly": data.monthly,
        "top_asins": data.top_asins,
        "bottom_asins": data.bottom_asins,
        "catalogue": data.catalogue,
        "search_terms": data.search_terms,
        "competitors": data.competitors,
        "data_gaps": data.data_gaps,
    }
    findings = [{"title": i.title, "body": i.body} for i in rules]
    return f"""You are an Amazon marketplace strategist writing the insights page of a quarterly business review.

{build_lang_instruction(scope.language)}

Quarter data. KPI units: "EUR" amounts, "units" counts, "x" multiples, "%" fractions (0.12 = 12%).
"previous" is the previous quarter, "last_year" the same quarter last year. "provenance" says whether a
figure is an Amazon actual or an estimate.
{json.dumps(payload, ensure_ascii=False, indent=2, default=str)}

Findings already computed from the same data by fixed rules:
{json.dumps(findings, ensure_ascii=False, indent=2)}

Return a JSON object with exactly this structure:
{{"insights": [{{"title": "...", "body": "...", "action": "..."}}]}}

Rules:
- 4 to {MAX_INSIGHTS} insights, most important first.
- title: under 70 characters. body: one or two sentences quoting the concrete figures and periods.
  action: one concrete operational step for the account team.
- Use only figures present in the data; never invent numbers. Call an estimate an estimate.
- Draw no conclusion from a section listed in data_gaps.
- Never infer organic sales share from attributed sales. Use TACOS only when the KPI has a value.
- Return ONLY the JSON object, no markdown or commentary."""


def _parse(text: str) -> list[Insight]:
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    payload = json.loads(text)
    insights = []
    for item in payload.get("insights") or []:
        if not isinstance(item, dict):
            continue
        title, body, action = (str(item.get(k) or "").strip() for k in ("title", "body", "action"))
        if title and body and action:
            insights.append(Insight(title[:120], body, action, "ai"))
    return insights[:MAX_INSIGHTS]


def build_insights(data: QuarterData) -> list[Insight]:
    rules = rule_insights(data)
    api_key = settings.ANTHROPIC_API_KEY
    if not api_key:
        return rules
    try:
        message = _anthropic_client(api_key).messages.create(
            model=AI_MODEL,
            max_tokens=AI_MAX_TOKENS,
            messages=[{"role": "user", "content": _prompt(data, rules)}],
        )
        insights = _parse(message.content[0].text)
    except Exception as exc:  # noqa: BLE001 - no credit, provider error or bad JSON: use the rules
        logger.warning("Quarterly review AI insights unavailable (%s); using rule insights",
                       type(exc).__name__)
        return rules
    return insights or rules
