"""Insights and actions for the quarterly business review (R5).

``rule_insights`` is deterministic: revenue growth or decline against the
previous quarter and the same quarter last year, the TACOS trend, the return
rate, the ASINs with the largest decline, the share of red listings and the open
catalogue anomalies. ``build_insights`` asks Claude for richer insights when an
API key is configured and falls back to the rules on any failure (no key, no
credit, provider error, unusable answer), so the deck is always complete.

``build_insights`` makes a blocking HTTP call: async callers run it in a thread.
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from typing import Literal

from app.config import settings
from app.services.ai_analysis_service import build_lang_instruction
from app.services.brand_analysis.deck.format import Formatter
from app.services.quarterly_report.data import (
    QuarterData,
    point_change,
    previous_quarter,
    quarter_label,
    relative_change,
)
from app.services.quarterly_report.deck import COPY, format_change, format_value, signed_currency, t

logger = logging.getLogger(__name__)

AI_MODEL = "claude-sonnet-4-6"  # same model as strategic_recommendations_service
AI_MAX_TOKENS = 1800
AI_TIMEOUT_S = 120.0
MAX_INSIGHTS = 6

# Rule thresholds
REVENUE_CHANGE_PCT = 5.0  # revenue change worth an insight, either way
TACOS_CHANGE_PP = 2.0
RETURN_RATE_CHANGE_PP = 1.0
RED_SHARE = 0.10  # share of red listings worth an insight
DECLINERS_SHOWN = 3


@dataclass
class Insight:
    title: str
    body: str
    action: str
    source: Literal["ai", "rules"]


def _metric(data: QuarterData, key: str):
    return next((m for m in data.kpis if m.key == key), None)


def rule_insights(data: QuarterData) -> list[Insight]:
    lang = data.scope.language
    fmt = Formatter(lang)
    scope = data.scope
    labels = {
        "current": quarter_label(scope.year, scope.quarter),
        "previous": quarter_label(*previous_quarter(scope.year, scope.quarter)),
        "last_year": quarter_label(scope.year - 1, scope.quarter),
    }
    insights: list[Insight] = []

    def add(title_key: str, body_key: str, action_key: str, **values) -> None:
        insights.append(Insight(t(lang, title_key), t(lang, body_key, **values),
                                t(lang, action_key), "rules"))

    def compared(metric, period: str) -> dict:
        base = getattr(metric, period)
        return {
            "quarter": labels["current"],
            "value": format_value(fmt, metric.unit, metric.value),
            "base": format_value(fmt, metric.unit, base),
            "base_quarter": labels[period],
            "change": format_change(fmt, metric.unit, metric.value, base),
        }

    revenue = _metric(data, "revenue")
    if revenue is not None:
        for period, suffix in (("previous", "prev"), ("last_year", "ly")):
            change = relative_change(revenue.value, getattr(revenue, period))
            if change is None or abs(change) < REVENUE_CHANGE_PCT:
                continue
            direction = "down" if change < 0 else "up"
            add(f"ins_rev_{direction}_{suffix}_title", "ins_rev_body", f"ins_rev_{direction}_action",
                **compared(revenue, period))

    tacos = _metric(data, "tacos")
    if tacos is not None:
        points = point_change(tacos.value, tacos.previous)
        if points is not None and abs(points) >= TACOS_CHANGE_PP:
            direction = "up" if points > 0 else "down"
            add(f"ins_tacos_{direction}_title", "ins_tacos_body", f"ins_tacos_{direction}_action",
                **compared(tacos, "previous"))

    returns = _metric(data, "return_rate")
    if returns is not None:
        points = point_change(returns.value, returns.previous)
        if points is not None and points >= RETURN_RATE_CHANGE_PP:
            add("ins_returns_up_title", "ins_returns_body", "ins_returns_action",
                **compared(returns, "previous"))

    if data.bottom_asins:
        items = "; ".join(f"{row['asin']} {signed_currency(fmt, row['change'])}"
                          for row in data.bottom_asins[:DECLINERS_SHOWN])
        add("ins_decliners_title", "ins_decliners_body", "ins_decliners_action",
            base_quarter=labels["previous"], items=items)

    catalogue = data.catalogue or {}
    total = catalogue.get("total") or 0
    red = (catalogue.get("states") or {}).get("red", 0)
    if total and red / total >= RED_SHARE:
        add("ins_red_title", "ins_red_body", "ins_red_action",
            red=red, total=total, share=fmt.share(red / total * 100))

    anomalies = catalogue.get("open_anomalies") or {}
    if anomalies:
        kinds = ", ".join(
            f"{t(lang, f'anomaly_{kind}') if f'anomaly_{kind}' in COPY['it'] else kind} {count}"
            for kind, count in sorted(anomalies.items(), key=lambda item: -item[1])
        )
        add("ins_anomalies_title", "ins_anomalies_body", "ins_anomalies_action",
            count=sum(anomalies.values()), kinds=kinds)

    if not insights:
        add("ins_stable_title", "ins_stable_body", "ins_stable_action")
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
