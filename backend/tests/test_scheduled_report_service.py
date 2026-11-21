from datetime import datetime, date, timezone

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services import scheduled_report_service as srs
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


def test_quarterly_next_run_is_first_day_of_next_quarter():
    result = compute_next_run_at(
        "quarterly",
        {"hour": 8, "minute": 30},
        "Europe/Rome",
        now=datetime(2026, 11, 21, 12, 0, tzinfo=timezone.utc),
    )
    # 1 Jan 2027 08:30 in Rome (CET, UTC+1)
    assert result == datetime(2027, 1, 1, 7, 30, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    "now, expected",
    [
        (datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc), datetime(2026, 4, 1, 8, 0, tzinfo=timezone.utc)),
        (datetime(2026, 3, 31, 23, 0, tzinfo=timezone.utc), datetime(2026, 4, 1, 8, 0, tzinfo=timezone.utc)),
        (datetime(2026, 5, 15, 9, 0, tzinfo=timezone.utc), datetime(2026, 7, 1, 8, 0, tzinfo=timezone.utc)),
        (datetime(2026, 9, 30, 9, 0, tzinfo=timezone.utc), datetime(2026, 10, 1, 8, 0, tzinfo=timezone.utc)),
        (datetime(2026, 12, 31, 9, 0, tzinfo=timezone.utc), datetime(2027, 1, 1, 8, 0, tzinfo=timezone.utc)),
    ],
)
def test_quarterly_next_run_rolls_over_quarter_and_year(now, expected):
    assert compute_next_run_at("quarterly", {"hour": 8, "minute": 0}, "UTC", now=now) == expected


@pytest.mark.parametrize(
    "reference, start, end",
    [
        (datetime(2026, 7, 1, 8, 0, tzinfo=timezone.utc), date(2026, 4, 1), date(2026, 6, 30)),
        (datetime(2026, 8, 20, 8, 0, tzinfo=timezone.utc), date(2026, 4, 1), date(2026, 6, 30)),
        (datetime(2026, 10, 1, 8, 0, tzinfo=timezone.utc), date(2026, 7, 1), date(2026, 9, 30)),
        (datetime(2027, 1, 1, 8, 0, tzinfo=timezone.utc), date(2026, 10, 1), date(2026, 12, 31)),
    ],
)
def test_quarterly_period_is_previous_full_quarter(reference, start, end):
    assert resolve_report_period("quarterly", "UTC", reference=reference) == (start, end)


def test_quarterly_period_uses_local_date():
    # 31 Mar 23:30 UTC is already 1 Apr in Rome, so the previous full quarter is Q1 there,
    # while in UTC it is still 31 Mar and the previous full quarter is Q4 of the year before.
    reference = datetime(2026, 3, 31, 23, 30, tzinfo=timezone.utc)
    assert resolve_report_period("quarterly", "Europe/Rome", reference=reference) == (
        date(2026, 1, 1),
        date(2026, 3, 31),
    )
    assert resolve_report_period("quarterly", "UTC", reference=reference) == (
        date(2025, 10, 1),
        date(2025, 12, 31),
    )


class _FakeAccounts:
    def __init__(self, ids):
        self.ids = ids

    def all(self):
        return [(i,) for i in self.ids]


class _FakeDb:
    def __init__(self, account_ids=()):
        self.account_ids = list(account_ids)

    async def execute(self, statement):
        return _FakeAccounts(self.account_ids)


@pytest.mark.asyncio
async def test_quarterly_review_artifact_is_a_pptx_for_the_previous_quarter(monkeypatch):
    seen = {}

    async def fake_generate(db, scope):
        seen["scope"] = scope
        return b"PPTX"

    monkeypatch.setattr(srs, "generate_quarterly_deck", fake_generate)
    account = uuid4()
    schedule = SimpleNamespace(
        organization_id=uuid4(),
        report_types=["quarterly_review"],
        account_ids=[str(account)],
        parameters={"language": "en"},
        format="pdf",
    )
    run = SimpleNamespace(period_start=date(2026, 7, 1), period_end=date(2026, 9, 30))

    data, filename, content_type = await srs.ScheduledReportArtifactService(_FakeDb()).build_artifact(schedule, run)

    assert data == b"PPTX"
    assert filename == "report-trimestrale-2026-Q3.pptx"
    assert content_type == srs.PPTX_CONTENT_TYPE
    scope = seen["scope"]
    assert (scope.year, scope.quarter, scope.language) == (2026, 3, "en")
    assert scope.account_ids == [account]


@pytest.mark.asyncio
async def test_quarterly_review_without_accounts_uses_every_organization_account(monkeypatch):
    seen = {}

    async def fake_generate(db, scope):
        seen["scope"] = scope
        return b"PPTX"

    monkeypatch.setattr(srs, "generate_quarterly_deck", fake_generate)
    a, b = uuid4(), uuid4()
    schedule = SimpleNamespace(
        organization_id=uuid4(), report_types=["quarterly_review"], account_ids=[], parameters={}, format="pdf"
    )
    run = SimpleNamespace(period_start=date(2026, 10, 1), period_end=date(2026, 12, 31))

    await srs.ScheduledReportArtifactService(_FakeDb([a, b])).build_artifact(schedule, run)

    assert seen["scope"].account_ids == [a, b]
    assert (seen["scope"].year, seen["scope"].quarter) == (2026, 4)
