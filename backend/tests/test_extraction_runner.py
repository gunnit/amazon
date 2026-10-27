"""Focused tests for account sync/backfill scheduling helpers."""
from datetime import date

from app.services.extraction_runner import (
    VENDOR_BACKFILL_MAX_MONTHS,
    _resolve_backfill_window,
)


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


def test_vendor_backfill_window_reaches_four_years():
    assert VENDOR_BACKFILL_MAX_MONTHS == 48
    assert _resolve_backfill_window(
        VENDOR_BACKFILL_MAX_MONTHS,
        max_months=VENDOR_BACKFILL_MAX_MONTHS,
        today=date(2026, 6, 10),
    ) == (date(2022, 6, 10), date(2026, 6, 10))


def test_vendor_max_months_still_clamps_deeper_requests():
    assert _resolve_backfill_window(
        60, max_months=VENDOR_BACKFILL_MAX_MONTHS, today=date(2026, 6, 10)
    ) == (date(2022, 6, 10), date(2026, 6, 10))


# --- Per-account failure must not abort the whole scheduled run -------------

import asyncio  # noqa: E402

import pytest  # noqa: E402

from app.models.amazon_account import AccountType  # noqa: E402
from app.services import extraction_runner  # noqa: E402


class _ExpiringAccount:
    """Stands in for an ORM row: after a rollback, reading an attribute would
    lazy-load from inside a sync context and raise MissingGreenlet."""

    id = "acc-1"
    account_type = AccountType.SELLER

    def __init__(self):
        self.expired = False

    @property
    def account_name(self):
        if self.expired:
            raise RuntimeError("lazy load after rollback (MissingGreenlet)")
        return "TEST-ACCOUNT"


class _FakeResult:
    def __init__(self, account):
        self._account = account

    def scalar_one_or_none(self):
        return self._account


class _FakeSession:
    def __init__(self, account):
        self.account = account

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, _statement):
        return _FakeResult(self.account)

    async def commit(self):
        pass

    async def rollback(self):
        self.account.expired = True


class _FailingService:
    def __init__(self, _db):
        pass

    async def _load_organization(self, _account):
        return object()

    async def sync_orders(self, _account, _organization):
        raise RuntimeError("SP-API authentication failed")

    async def sync_sales_data(self, _account, _organization):
        raise RuntimeError("SP-API authentication failed")


@pytest.mark.parametrize(
    "refresh",
    [
        extraction_runner._refresh_recent_orders,
        extraction_runner._refresh_recent_seller_sales,
    ],
)
def test_account_failure_is_contained_after_rollback(refresh, monkeypatch, caplog):
    monkeypatch.setattr(extraction_runner, "DataExtractionService", _FailingService)
    account = _ExpiringAccount()

    count = asyncio.run(refresh(account.id, lambda: _FakeSession(account)))

    assert count == 0
    assert "TEST-ACCOUNT" in caplog.text
