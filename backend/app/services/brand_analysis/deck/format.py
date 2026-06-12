"""Deck-facing value formatting.

Locale-aware grouping per deck language ("€78,255" for English decks, matching
the agency reference; "€ 78.255" for Italian ones), a real euro symbol, and a
single graceful EMPTY token so technical states ("EUR 1,234", "N/A", "New")
never leak into a client-facing card. Kept separate from the module-level
``format_*`` helpers in the service, which the narrative LLM contract still
depends on.
"""
from __future__ import annotations

from typing import Optional

EMPTY = "—"  # em dash, the universal "no value" mark

_IT_GROUPING = str.maketrans({",": ".", ".": ","})


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


class Formatter:
    """Number formatting bound to the deck language."""

    def __init__(self, language: str = "it") -> None:
        self.italian = str(language or "").lower().startswith("it")

    EMPTY = EMPTY

    def _group(self, value: float, digits: int) -> str:
        text = f"{value:,.{digits}f}"  # en grouping, e.g. "1,234.50"
        return text.translate(_IT_GROUPING) if self.italian else text

    def currency(self, value, digits: int = 0) -> str:
        number = _to_float(value)
        if number is None:
            return EMPTY
        return f"€ {self._group(number, digits)}" if self.italian else f"€{self._group(number, digits)}"

    def percent_signed(self, value) -> str:
        """Signed YoY-style percentage. Returns EMPTY (never 'New') when absent."""
        number = _to_float(value)
        if number is None:
            return EMPTY
        sign = "+" if number >= 0 else ""
        return f"{sign}{self._group(number, 1)}%"

    def share(self, value) -> str:
        number = _to_float(value)
        if number is None:
            return EMPTY
        return f"{self._group(number, 1)}%"

    def number(self, value, digits: int = 0) -> str:
        parsed = _to_float(value)
        if parsed is None:
            return EMPTY
        return self._group(parsed, digits)

    def integer(self, value) -> str:
        parsed = _to_float(value)
        if parsed is None:
            return EMPTY
        return self._group(parsed, 0)

    @staticmethod
    def truncate(text, limit: int) -> str:
        return truncate(text, limit)


_DEFAULT = Formatter("it")


def currency(value, digits: int = 0) -> str:
    return _DEFAULT.currency(value, digits)


def percent_signed(value) -> str:
    return _DEFAULT.percent_signed(value)


def share(value) -> str:
    return _DEFAULT.share(value)


def number(value, digits: int = 0) -> str:
    return _DEFAULT.number(value, digits)


def integer(value) -> str:
    return _DEFAULT.integer(value)


def real_category(name) -> Optional[str]:
    """A subcategory name worth showing to a client — drops the
    'Uncategorized' bucket and empty values so a placeholder never becomes
    a KPI or a recommendation."""
    text = str(name or "").strip()
    if not text or text.lower() in ("uncategorized", "uncategorised", "n/a", "other", "altro"):
        return None
    return text


def product_label(name, brand: str = "", limit: int = 40) -> str:
    """Chart/table label for a product. Strips the redundant brand prefix
    (every slide is already brand-scoped) so truncation keeps the part that
    distinguishes one ASIN from another."""
    text = str(name or "")
    if brand:
        lowered = text.lower()
        prefix = brand.lower()
        if lowered.startswith(prefix):
            text = text[len(brand):].lstrip(" ,–-|:")
    return truncate(text or name, limit)


def truncate(text, limit: int) -> str:
    text = str(text or "")
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"
