"""Quarterly business review (R5): figures, insights and the PPTX deck.

``collect_quarter_data`` reads one quarter and its two comparison periods,
``build_insights`` turns them into insights and actions (AI when available,
deterministic rules otherwise), ``build_quarterly_deck`` renders the deck.
"""
from app.services.quarterly_report.data import (
    Metric,
    QuarterData,
    QuarterScope,
    collect_quarter_data,
    previous_quarter,
    quarter_bounds,
)
from app.services.quarterly_report.deck import build_quarterly_deck
from app.services.quarterly_report.insights import Insight, build_insights, rule_insights

__all__ = [
    "Insight",
    "Metric",
    "QuarterData",
    "QuarterScope",
    "build_insights",
    "build_quarterly_deck",
    "collect_quarter_data",
    "previous_quarter",
    "quarter_bounds",
    "rule_insights",
]
