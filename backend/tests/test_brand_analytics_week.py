"""Brand Analytics reporting-week alignment (Sunday..Saturday + settle lag)."""
from datetime import date

from app.services.brand_analytics_ingest_service import resolve_last_settled_ba_week


def test_mid_week_uses_last_closed_week():
    # Thursday 2026-06-11 -> week ended Saturday 2026-06-06 (5 days ago, settled)
    assert resolve_last_settled_ba_week(date(2026, 6, 11)) == (
        date(2026, 5, 31),
        date(2026, 6, 6),
    )


def test_week_too_fresh_falls_back_to_previous_week():
    # Monday 2026-06-08 -> Saturday 2026-06-06 closed only 2 days ago (< 3-day
    # settle lag), so the previous week is used.
    assert resolve_last_settled_ba_week(date(2026, 6, 8)) == (
        date(2026, 5, 24),
        date(2026, 5, 30),
    )


def test_saturday_never_uses_the_running_week():
    # Saturday itself: the current week has not closed; last Saturday is 7 days
    # back and well past the settle lag.
    assert resolve_last_settled_ba_week(date(2026, 6, 13)) == (
        date(2026, 5, 31),
        date(2026, 6, 6),
    )


def test_window_is_always_seven_days_sunday_to_saturday():
    for day in range(1, 29):
        week_start, week_end = resolve_last_settled_ba_week(date(2026, 6, day))
        assert (week_end - week_start).days == 6
        assert week_start.weekday() == 6  # Sunday
        assert week_end.weekday() == 5  # Saturday
