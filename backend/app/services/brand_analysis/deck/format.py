"""Deck-facing value formatting.

Locale-aware (Italian thousands grouping), a real euro symbol, and a single
graceful EMPTY token so technical states ("EUR 1,234", "N/A", "New") never leak
into a client-facing card. Kept separate from the module-level ``format_*``
helpers in the service, which the narrative LLM contract still depends on.
"""
from __future__ import annotations

from typing import Optional

EMPTY = "—"  # em dash, the universal "no value" mark


def _to_float(value) -> Optional[float]:
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if result != result:  # NaN
        return None
    return result


def _group(value: float, digits: int) -> str:
    """Italian-style grouping: '.' for thousands, ',' for decimals."""
    text = f"{value:,.{digits}f}"  # en grouping, e.g. "1,234.50"
    return text.translate(str.maketrans({",": ".", ".": ","}))


def currency(value, digits: int = 0) -> str:
    number = _to_float(value)
    if number is None:
        return EMPTY
    return f"€ {_group(number, digits)}"


def percent_signed(value) -> str:
    """Signed YoY-style percentage. Returns EMPTY (never 'New') when absent."""
    number = _to_float(value)
    if number is None:
        return EMPTY
    sign = "+" if number >= 0 else ""
    return f"{sign}{_group(number, 1)}%"


def share(value) -> str:
    number = _to_float(value)
    if number is None:
        return EMPTY
    return f"{_group(number, 1)}%"


def number(value, digits: int = 0) -> str:
    parsed = _to_float(value)
    if parsed is None:
        return EMPTY
    return _group(parsed, digits)


def integer(value) -> str:
    parsed = _to_float(value)
    if parsed is None:
        return EMPTY
    return _group(parsed, 0)


def truncate(text, limit: int) -> str:
    text = str(text or "")
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"
