from datetime import datetime, date, timezone

from app.services.scheduled_report_utils import compute_next_run_at, resolve_report_period


def test_compute_next_run_at_for_weekly_uses_timezone():
    result = compute_next_run_at(
        "weekly",
        {"weekday": 0, "hour": 9, "minute": 30},
        "Europe/Rome",
        now=datetime(2026, 3, 31, 7, 0, tzinfo=timezone.utc),
    )

    assert result == datetime(2026, 4, 6, 7, 30, tzinfo=timezone.utc)


def test_compute_next_run_at_for_monthly_rolls_to_next_month():
    result = compute_next_run_at(
        "monthly",
        {"day_of_month": 31, "hour": 8, "minute": 0},
        "UTC",
        now=datetime(2026, 3, 31, 9, 0, tzinfo=timezone.utc),
    )

    assert result == datetime(2026, 4, 30, 8, 0, tzinfo=timezone.utc)


def test_resolve_report_period_for_weekly_uses_previous_seven_days():
    start_date, end_date = resolve_report_period(
        "weekly",
        "UTC",
        reference=datetime(2026, 4, 8, 10, 0, tzinfo=timezone.utc),
    )

    assert start_date == date(2026, 4, 1)
    assert end_date == date(2026, 4, 7)


def test_resolve_report_period_for_monthly_uses_previous_calendar_month():
    start_date, end_date = resolve_report_period(
        "monthly",
        "UTC",
        reference=datetime(2026, 4, 8, 10, 0, tzinfo=timezone.utc),
    )

    assert start_date == date(2026, 3, 1)
    assert end_date == date(2026, 3, 31)
