"""Pure scheduling utilities for recurring operational reports."""
from __future__ import annotations

import calendar
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Optional
from zoneinfo import ZoneInfo


def utcnow() -> datetime:
    """Return the current UTC timestamp."""
    return datetime.now(timezone.utc)


def get_timezone(tz_name: str) -> ZoneInfo:
    """Resolve a timezone name or raise a validation-friendly error."""
    try:
        return ZoneInfo(tz_name)
    except Exception as exc:
        raise ValueError("Invalid timezone") from exc


def local_to_utc(local_dt: datetime, tz_name: str) -> datetime:
    """Attach a timezone and convert to UTC."""
    return local_dt.replace(tzinfo=get_timezone(tz_name)).astimezone(timezone.utc)


def _require_int(config: dict[str, Any], key: str, *, min_value: int, max_value: int) -> int:
    value = config.get(key)
    if not isinstance(value, int):
        raise ValueError(f"Invalid schedule config: {key}")
    if value < min_value or value > max_value:
        raise ValueError(f"Invalid schedule config: {key}")
    return value


def compute_next_run_at(
    frequency: str,
    schedule_config: dict[str, Any],
    tz_name: str,
    now: Optional[datetime] = None,
) -> datetime:
    """Compute the next UTC execution timestamp for a schedule."""
    now_utc = now or utcnow()
    tz = get_timezone(tz_name)
    local_now = now_utc.astimezone(tz)

    hour = _require_int(schedule_config, "hour", min_value=0, max_value=23)
    minute = _require_int(schedule_config, "minute", min_value=0, max_value=59)

    if frequency == "weekly":
        weekday = _require_int(schedule_config, "weekday", min_value=0, max_value=6)
        target_date = local_now.date() + timedelta((weekday - local_now.weekday()) % 7)
        candidate = datetime.combine(target_date, time(hour, minute))
        if candidate <= local_now.replace(tzinfo=None):
            candidate = candidate + timedelta(days=7)
        return local_to_utc(candidate, tz_name)

    if frequency == "quarterly":
        # First day of the next quarter, at the configured local time.
        quarter_first_month = (local_now.month - 1) // 3 * 3 + 1
        year, month = local_now.year, quarter_first_month + 3
        if month > 12:
            year, month = year + 1, 1
        return local_to_utc(datetime(year, month, 1, hour, minute), tz_name)

    day_of_month = _require_int(schedule_config, "day_of_month", min_value=1, max_value=31)
    year = local_now.year
    month = local_now.month
    day = min(day_of_month, calendar.monthrange(year, month)[1])
    candidate = datetime(year, month, day, hour, minute)
    if candidate <= local_now.replace(tzinfo=None):
        if month == 12:
            year += 1
            month = 1
        else:
            month += 1
        day = min(day_of_month, calendar.monthrange(year, month)[1])
        candidate = datetime(year, month, day, hour, minute)
    return local_to_utc(candidate, tz_name)


def previous_full_quarter(today: date) -> tuple[date, date]:
    """First and last day of the calendar quarter before the one containing ``today``."""
    year, quarter = today.year, (today.month - 1) // 3 + 1
    year, quarter = (year - 1, 4) if quarter == 1 else (year, quarter - 1)
    first_month = (quarter - 1) * 3 + 1
    last_month = first_month + 2
    return (
        date(year, first_month, 1),
        date(year, last_month, calendar.monthrange(year, last_month)[1]),
    )


def resolve_report_period(
    frequency: str,
    tz_name: str,
    reference: Optional[datetime] = None,
) -> tuple[date, date]:
    """Resolve the reporting window based on the frequency and local timezone."""
    now_utc = reference or utcnow()
    local_today = now_utc.astimezone(get_timezone(tz_name)).date()

    if frequency == "weekly":
        end_date = local_today - timedelta(days=1)
        start_date = end_date - timedelta(days=6)
        return start_date, end_date

    if frequency == "quarterly":
        return previous_full_quarter(local_today)

    current_month_start = local_today.replace(day=1)
    end_date = current_month_start - timedelta(days=1)
    start_date = end_date.replace(day=1)
    return start_date, end_date
