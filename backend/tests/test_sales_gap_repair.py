"""Sales gap detection window grouping."""
from datetime import date

from app.services.extraction_runner import _missing_date_windows


def test_no_gaps_returns_empty():
    start, end = date(2026, 6, 1), date(2026, 6, 5)
    existing = {date(2026, 6, d) for d in range(1, 6)}
    assert _missing_date_windows(existing, start, end) == []


def test_contiguous_missing_dates_group_into_one_window():
    start, end = date(2026, 6, 1), date(2026, 6, 10)
    existing = {date(2026, 6, d) for d in (1, 2, 6, 7, 8, 9, 10)}
    assert _missing_date_windows(existing, start, end) == [
        (date(2026, 6, 3), date(2026, 6, 5)),
    ]


def test_multiple_windows_are_most_recent_first():
    start, end = date(2026, 6, 1), date(2026, 6, 10)
    existing = {date(2026, 6, d) for d in (2, 3, 5, 6, 8, 9)}
    assert _missing_date_windows(existing, start, end) == [
        (date(2026, 6, 10), date(2026, 6, 10)),
        (date(2026, 6, 7), date(2026, 6, 7)),
        (date(2026, 6, 4), date(2026, 6, 4)),
        (date(2026, 6, 1), date(2026, 6, 1)),
    ]


def test_gap_extending_to_range_end_is_closed():
    start, end = date(2026, 6, 1), date(2026, 6, 5)
    existing = {date(2026, 6, 1), date(2026, 6, 2)}
    assert _missing_date_windows(existing, start, end) == [
        (date(2026, 6, 3), date(2026, 6, 5)),
    ]


def test_everything_missing_is_one_window():
    start, end = date(2026, 6, 1), date(2026, 6, 5)
    assert _missing_date_windows(set(), start, end) == [(start, end)]
