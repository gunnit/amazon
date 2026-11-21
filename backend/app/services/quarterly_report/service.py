"""Build the quarterly review deck for a scope (R5): data, insights, PPTX."""
from __future__ import annotations

import asyncio

from app.services.quarterly_report.data import QuarterScope, collect_quarter_data
from app.services.quarterly_report.deck import build_quarterly_deck
from app.services.quarterly_report.insights import build_insights

PPTX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.presentationml.presentation"


def quarterly_filename(year: int, quarter: int) -> str:
    return f"report-trimestrale-{year}-Q{quarter}.pptx"


def _render(data) -> bytes:
    # build_insights may call Anthropic synchronously; keep it off the event loop.
    return build_quarterly_deck(data, build_insights(data))


async def generate_quarterly_deck(db, scope: QuarterScope) -> bytes:
    """PPTX bytes for ``scope``. Raises ValueError when the scope has no accounts."""
    data = await collect_quarter_data(db, scope)
    return await asyncio.to_thread(_render, data)
