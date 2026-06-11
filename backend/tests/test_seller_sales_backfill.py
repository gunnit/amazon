"""Seller Sales & Traffic historical backfill reliability tests."""
from datetime import date
from types import SimpleNamespace

import pytest

from app.core.exceptions import AmazonAPIError
from app.services import data_extraction
from app.services.data_extraction import DataExtractionService


class FakeDb:
    def __init__(self):
        self.commits = 0
        self.rollbacks = 0

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


@pytest.mark.asyncio
async def test_seller_backfill_retries_throttled_month_after_quota_cooldown(monkeypatch):
    db = FakeDb()
    service = DataExtractionService(db)
    calls = 0
    sleeps = []

    async def fake_sync(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise AmazonAPIError("quota exceeded", error_code="THROTTLED")
        return 7

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr(service, "sync_sales_data", fake_sync)
    monkeypatch.setattr(data_extraction.asyncio, "sleep", fake_sleep)

    count = await service.backfill_sales_data(
        SimpleNamespace(account_name="Bitron"),
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 31),
    )

    assert count == 7
    assert calls == 2
    assert db.rollbacks == 0
    assert db.commits == 1
    assert service.backfill_windows_skipped == 0
    assert data_extraction.SELLER_BACKFILL_THROTTLE_COOLDOWN_SECONDS in sleeps


@pytest.mark.asyncio
async def test_seller_backfill_counts_windows_skipped_after_exhausted_retries(monkeypatch):
    db = FakeDb()
    service = DataExtractionService(db)
    calls = 0

    async def fake_sync(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        # First window fails terminally; second window succeeds.
        if calls == 1:
            raise AmazonAPIError("report FATAL", error_code="REPORT_FAILED")
        return 5

    async def fake_sleep(_seconds):
        pass

    monkeypatch.setattr(service, "sync_sales_data", fake_sync)
    monkeypatch.setattr(data_extraction.asyncio, "sleep", fake_sleep)

    count = await service.backfill_sales_data(
        SimpleNamespace(account_name="Bitron"),
        start_date=date(2026, 1, 1),
        end_date=date(2026, 2, 28),
    )

    assert count == 5
    assert service.backfill_windows_skipped == 1
    assert db.commits == 1
