"""Backfill honesty: ads gap detection, reclaimable failures, PARTIAL status."""
from datetime import date, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.exceptions import AmazonAPIError
from app.models.amazon_account import AccountType, BackfillStatus
from app.services import economics_service, extraction_runner
from app.services.data_extraction import ADS_LOOKBACK_DAYS
from app.services.extraction_runner import (
    ADS_SYNC_WINDOW_DAYS,
    _ads_backfill_needed,
    _backfill_ads_history,
    _initial_sync_one,
    _persist_sync_failure_state,
    _run_sales_backfill,
)

ADS_RETENTION_DAYS = max(ADS_LOOKBACK_DAYS.values()) - 7


class FakeResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value

    def one(self):
        return self._value


class FakeDb:
    """Serves the account for every account lookup and `aggregates` for the
    ads coverage min/max query."""

    def __init__(self, account, aggregates=(None, None)):
        self.account = account
        self.aggregates = aggregates
        self.commits = 0

    async def execute(self, stmt):
        text = str(stmt)
        if "min(" in text and "max(" in text:
            return FakeResult(self.aggregates)
        return FakeResult(self.account)

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        pass


def _session_factory(db):
    class _Ctx:
        async def __aenter__(self):
            return db

        async def __aexit__(self, *_exc):
            return False

    return lambda: _Ctx()


def _account(**overrides):
    account = SimpleNamespace(
        id=uuid4(),
        account_name="Test",
        account_type=AccountType.SELLER,
        advertising_refresh_token_encrypted=None,
        sync_status=None,
        sync_error_message=None,
        sync_error_code=None,
        sync_error_kind=None,
        last_sync_failed_at=None,
        last_sync_heartbeat_at=None,
        last_backfill_status=None,
        last_backfill_started_at=None,
        last_backfill_completed_at=None,
        last_backfill_records=None,
        last_backfill_windows_skipped=None,
        last_backfill_error=None,
        last_backfill_range_start=None,
        last_backfill_range_end=None,
    )
    for key, value in overrides.items():
        setattr(account, key, value)
    return account


# --- 1. ads guard looks at both ends of the coverage -------------------------


def test_ads_backfill_runs_when_a_recent_hole_is_out_of_the_daily_window():
    today = date(2026, 8, 27)
    # Prod shape: coverage starts at the retention bound but stops 7+ days ago
    # after an auth outage, so the daily sync's rolling window cannot reach it.
    assert _ads_backfill_needed(
        today - timedelta(days=ADS_RETENTION_DAYS),
        today - timedelta(days=ADS_SYNC_WINDOW_DAYS + 1),
        today=today,
    )


def test_ads_backfill_skipped_when_coverage_is_intact():
    today = date(2026, 8, 27)
    assert not _ads_backfill_needed(
        today - timedelta(days=ADS_RETENTION_DAYS),
        today - timedelta(days=1),
        today=today,
    )


def test_ads_backfill_still_runs_when_history_is_too_shallow():
    today = date(2026, 8, 27)
    assert _ads_backfill_needed(today - timedelta(days=10), today - timedelta(days=1), today=today)
    assert _ads_backfill_needed(None, None, today=today)


@pytest.mark.asyncio
async def test_ads_history_backfill_uses_the_newest_row_not_just_the_oldest(monkeypatch):
    calls = []

    class FakeService:
        def __init__(self, _db):
            pass

        async def _load_organization(self, _account):
            return SimpleNamespace(id=uuid4())

        async def backfill_advertising_history(self, _account, _organization):
            calls.append("ads")
            return 42

    monkeypatch.setattr(extraction_runner, "DataExtractionService", FakeService)
    today = date.today()
    db = FakeDb(
        _account(advertising_refresh_token_encrypted="token"),
        aggregates=(
            today - timedelta(days=ADS_RETENTION_DAYS),
            today - timedelta(days=ADS_SYNC_WINDOW_DAYS + 7),
        ),
    )

    failed = await _backfill_ads_history(uuid4(), _session_factory(db))

    assert calls == ["ads"]
    assert failed == []


# --- 2. a phase-1 failure must leave a state the sweep can claim -------------


@pytest.mark.asyncio
async def test_phase_one_failure_leaves_a_reclaimable_backfill(monkeypatch):
    class FailingService:
        def __init__(self, _db):
            pass

        async def sync_account(self, _account_id):
            raise AmazonAPIError("throttled", error_code="QuotaExceeded")

    monkeypatch.setattr(extraction_runner, "DataExtractionService", FailingService)
    account = _account()
    db = FakeDb(account)

    await _initial_sync_one(account.id, 24, _session_factory(db))

    # The hourly sweep claims error + a recorded range; NULL is claimed by nobody.
    assert account.last_backfill_status == BackfillStatus.ERROR.value
    assert account.last_backfill_range_start is not None
    assert account.last_backfill_range_end is not None
    assert account.last_backfill_started_at is not None


# --- 3. failing extras downgrade the status to PARTIAL -----------------------


@pytest.mark.asyncio
async def test_failing_history_extra_downgrades_backfill_to_partial(monkeypatch):
    class FakeService:
        backfill_windows_skipped = 0

        def __init__(self, _db):
            pass

        async def _load_organization(self, _account):
            return SimpleNamespace(id=uuid4())

        async def backfill_sales_data(self, _account, _organization, *, start_date, end_date):
            return 100

        async def backfill_orders_history(self, _account, _organization, *, start_date, end_date):
            raise AmazonAPIError("orders blew up")

        async def backfill_returns_history(self, _account, _organization, *, start_date, end_date):
            return 3

    class FakeEconomics:
        def __init__(self, _db):
            pass

        async def backfill_economics_history(self, _account, _organization, *, start_date, end_date):
            return 7

    monkeypatch.setattr(extraction_runner, "DataExtractionService", FakeService)
    monkeypatch.setattr(economics_service, "EconomicsService", FakeEconomics)
    account = _account()
    db = FakeDb(account)

    await _run_sales_backfill(
        account.id, _session_factory(db), date(2026, 6, 1), date(2026, 8, 1)
    )

    assert account.last_backfill_status == BackfillStatus.PARTIAL.value
    assert account.last_backfill_windows_skipped == 1
    assert "orders" in account.last_backfill_error
    assert account.last_backfill_records == 100


@pytest.mark.asyncio
async def test_all_extras_succeeding_still_reports_success(monkeypatch):
    class FakeService:
        backfill_windows_skipped = 0

        def __init__(self, _db):
            pass

        async def _load_organization(self, _account):
            return SimpleNamespace(id=uuid4())

        async def backfill_sales_data(self, _account, _organization, *, start_date, end_date):
            return 100

        async def backfill_orders_history(self, _account, _organization, *, start_date, end_date):
            return 5

        async def backfill_returns_history(self, _account, _organization, *, start_date, end_date):
            return 3

    class FakeEconomics:
        def __init__(self, _db):
            pass

        async def backfill_economics_history(self, _account, _organization, *, start_date, end_date):
            return 7

    monkeypatch.setattr(extraction_runner, "DataExtractionService", FakeService)
    monkeypatch.setattr(economics_service, "EconomicsService", FakeEconomics)
    account = _account()
    db = FakeDb(account)

    await _run_sales_backfill(
        account.id, _session_factory(db), date(2026, 6, 1), date(2026, 8, 1)
    )

    assert account.last_backfill_status == BackfillStatus.SUCCESS.value
    assert account.last_backfill_error is None


# --- 4. an expired LWA secret gets its own error code ------------------------


@pytest.mark.asyncio
async def test_expired_lwa_secret_gets_its_own_error_code():
    account = _account()
    db = FakeDb(account)
    exc = AmazonAPIError(
        "403 Forbidden: The LWA secret token you provided has expired.",
        error_code="AUTH_FAILED",
    )

    await _persist_sync_failure_state(account.id, _session_factory(db), exc)

    assert account.sync_error_code == "LWA_SECRET_EXPIRED"


@pytest.mark.asyncio
async def test_other_auth_failures_keep_the_generic_code():
    account = _account()
    db = FakeDb(account)
    exc = AmazonAPIError("403 Forbidden: Access to requested resource is denied.",
                         error_code="AUTH_FAILED")

    await _persist_sync_failure_state(account.id, _session_factory(db), exc)

    assert account.sync_error_code == "AUTH_FAILED"
