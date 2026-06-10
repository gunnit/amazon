"""Focused tests for account sync/backfill scheduling helpers."""
from datetime import date

from app.services.extraction_runner import _resolve_backfill_window


def test_max_backfill_uses_two_calendar_years_not_720_days():
    assert _resolve_backfill_window(24, today=date(2026, 6, 10)) == (
        date(2024, 6, 10),
        date(2026, 6, 10),
    )


def test_backfill_calendar_math_handles_end_of_month():
    assert _resolve_backfill_window(1, today=date(2026, 3, 31)) == (
        date(2026, 2, 28),
        date(2026, 3, 31),
    )


def test_backfill_is_clamped_to_amazon_two_year_limit():
    assert _resolve_backfill_window(36, today=date(2026, 6, 10)) == (
        date(2024, 6, 10),
        date(2026, 6, 10),
    )
