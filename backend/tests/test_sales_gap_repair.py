"""Sales gap detection window grouping and per-account repair."""
from datetime import date, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.models.amazon_account import AccountType
from app.services.data_extraction import VENDOR_REPORT_LAG_DAYS
from app.services import extraction_runner
from app.services.extraction_runner import (
    SALES_GAP_LOOKBACK_DAYS,
    SALES_GAP_MAX_WINDOWS_PER_ACCOUNT,
    SALES_GAP_PUBLISH_LAG_DAYS,
    _missing_date_windows,
    _repair_sales_gaps_one,
)


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


def test_lookback_covers_amazon_two_year_history():
    assert SALES_GAP_LOOKBACK_DAYS == 730


class FakeResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value

    def scalar(self):
        return self._value

    def all(self):
        return self._value


class FakeRepairDb:
    """Answers `_repair_sales_gaps_one`'s queries in order: account lookup,
    earliest sentinel date, then existing sentinel dates."""

    def __init__(self, account, earliest, existing):
        self._results = [
            FakeResult(account),
            FakeResult(earliest),
            FakeResult([(d,) for d in sorted(existing)]),
        ]
        self.commits = 0

    async def execute(self, _stmt):
        return self._results.pop(0)

    async def commit(self):
        self.commits += 1


def _session_factory(db):
    class _Ctx:
        async def __aenter__(self):
            return db

        async def __aexit__(self, *_exc):
            return False

    return lambda: _Ctx()


class FakeExtractionService:
    calls = []

    def __init__(self, _db):
        pass

    async def _load_organization(self, _account):
        return SimpleNamespace(id=uuid4())

    async def sync_sales_data(self, _account, _organization, start, end):
        FakeExtractionService.calls.append(("seller", start, end))
        return 1

    async def backfill_vendor_sales_data(self, _account, _organization, *, start_date, end_date):
        FakeExtractionService.calls.append(("vendor", start_date, end_date))
        return 1


def _account(account_type=AccountType.SELLER):
    return SimpleNamespace(id=uuid4(), account_name="Test", account_type=account_type)


@pytest.fixture
def fake_service(monkeypatch):
    FakeExtractionService.calls = []
    monkeypatch.setattr(extraction_runner, "DataExtractionService", FakeExtractionService)
    return FakeExtractionService


@pytest.mark.asyncio
async def test_repair_never_probes_before_first_data_point(fake_service):
    today = date.today()
    earliest = today - timedelta(days=10)
    end = today - timedelta(days=SALES_GAP_PUBLISH_LAG_DAYS)
    hole = today - timedelta(days=8)
    existing = {
        earliest + timedelta(days=offset)
        for offset in range((end - earliest).days + 1)
    } - {hole}

    db = FakeRepairDb(_account(), earliest, existing)
    repaired = await _repair_sales_gaps_one(uuid4(), _session_factory(db))

    # Only the hole inside [earliest, end] is repaired even though the 730-day
    # lookback reaches far before the account's first data point.
    assert fake_service.calls == [("seller", hole, hole)]
    assert repaired == 1
    assert db.commits == 1


@pytest.mark.asyncio
async def test_repair_caps_windows_most_recent_first(fake_service):
    today = date.today()
    earliest = today - timedelta(days=40)
    end = today - timedelta(days=SALES_GAP_PUBLISH_LAG_DAYS)
    holes = [today - timedelta(days=d) for d in (4, 8, 12, 16, 20, 24, 28)]
    existing = {
        earliest + timedelta(days=offset)
        for offset in range((end - earliest).days + 1)
    } - set(holes)

    db = FakeRepairDb(_account(), earliest, existing)
    repaired = await _repair_sales_gaps_one(uuid4(), _session_factory(db))

    expected = [("seller", hole, hole) for hole in holes[:SALES_GAP_MAX_WINDOWS_PER_ACCOUNT]]
    assert fake_service.calls == expected
    assert repaired == SALES_GAP_MAX_WINDOWS_PER_ACCOUNT


@pytest.mark.asyncio
async def test_repair_skips_accounts_with_no_history(fake_service):
    db = FakeRepairDb(_account(), None, set())
    repaired = await _repair_sales_gaps_one(uuid4(), _session_factory(db))

    assert repaired == 0
    assert fake_service.calls == []
    assert db.commits == 0


@pytest.mark.asyncio
async def test_repair_covers_vendor_accounts_behind_their_publish_lag(fake_service):
    today = date.today()
    earliest = today - timedelta(days=20)
    end = today - timedelta(days=VENDOR_REPORT_LAG_DAYS)
    hole = today - timedelta(days=10)
    existing = {
        earliest + timedelta(days=offset)
        for offset in range((end - earliest).days + 1)
    } - {hole}

    db = FakeRepairDb(_account(AccountType.VENDOR), earliest, existing)
    repaired = await _repair_sales_gaps_one(uuid4(), _session_factory(db))

    # Vendor windows go through the vendor backfill, and days inside the
    # vendor publish lag are never treated as gaps.
    assert fake_service.calls == [("vendor", hole, hole)]
    assert repaired == 1
