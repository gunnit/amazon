"""Onboarding history backfills: orders window-walking and the MFN returns
fallback in data_extraction."""
from datetime import date, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4
import itertools

import pytest

from app.core.exceptions import AmazonAPIError
from app.models.amazon_account import AccountType
from app.services import data_extraction
from app.services.data_extraction import DataExtractionService


class FakeDb:
    def __init__(self):
        self.commits = 0
        self.flushes = 0

    async def commit(self):
        self.commits += 1

    async def flush(self):
        self.flushes += 1


def _seller(**overrides):
    base = dict(
        id=uuid4(),
        account_name="Bitron",
        account_type=AccountType.SELLER,
        marketplace_id="APJ6JRA9NG5V4",
        last_sync_started_at=None,
        last_sync_succeeded_at=None,
        last_sync_at=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


# ---- Orders history ----


@pytest.mark.asyncio
async def test_backfill_orders_history_walks_month_windows(monkeypatch):
    db = FakeDb()
    service = DataExtractionService(db)
    fetched_windows = []
    persisted = []

    def fake_fetch_orders(created_after, created_before):
        fetched_windows.append((created_after, created_before))
        return [{"AmazonOrderId": f"order-{len(fetched_windows)}"}]

    async def fake_persist(_account, _client, raw_orders):
        persisted.append(raw_orders)
        return len(raw_orders), 0

    fake_client = SimpleNamespace(fetch_orders=fake_fetch_orders)
    monkeypatch.setattr(service, "_create_sp_api_client", lambda *_a, **_k: fake_client)
    monkeypatch.setattr(service, "_persist_orders", fake_persist)

    count = await service.backfill_orders_history(
        _seller(), start_date=date(2026, 1, 15), end_date=date(2026, 3, 10)
    )

    assert fetched_windows == [
        (datetime(2026, 1, 15), datetime(2026, 2, 1)),
        (datetime(2026, 2, 1), datetime(2026, 3, 1)),
        (datetime(2026, 3, 1), datetime(2026, 3, 11)),
    ]
    assert count == 3
    assert len(persisted) == 3
    assert db.commits == 3


@pytest.mark.asyncio
async def test_backfill_orders_history_skips_vendor_accounts(monkeypatch):
    service = DataExtractionService(FakeDb())

    def explode(*_a, **_k):
        raise AssertionError("vendor backfill must not create an SP-API client")

    monkeypatch.setattr(service, "_create_sp_api_client", explode)

    count = await service.backfill_orders_history(
        _seller(account_type=AccountType.VENDOR),
        start_date=date(2026, 1, 1),
        end_date=date(2026, 3, 1),
    )
    assert count == 0


@pytest.mark.asyncio
async def test_sync_orders_persists_through_shared_helper(monkeypatch):
    db = FakeDb()
    service = DataExtractionService(db)
    captured = {}

    fake_client = SimpleNamespace(
        fetch_orders=lambda _after, _before: [{"AmazonOrderId": "171-1"}]
    )
    monkeypatch.setattr(service, "_create_sp_api_client", lambda *_a, **_k: fake_client)

    async def fake_touch(_account):
        return None

    async def fake_persist(_account, _client, raw_orders):
        captured["raw_orders"] = raw_orders
        return len(raw_orders), 2

    monkeypatch.setattr(service, "_touch_sync", fake_touch)
    monkeypatch.setattr(service, "_persist_orders", fake_persist)

    count = await service.sync_orders(_seller())

    assert count == 1
    assert captured["raw_orders"] == [{"AmazonOrderId": "171-1"}]
    assert db.flushes == 1


@pytest.mark.asyncio
async def test_persist_orders_maps_orders_and_items(monkeypatch):
    db = FakeDb()
    service = DataExtractionService(db)
    upserted_orders = []
    replaced_items = []

    async def fake_upsert(values):
        upserted_orders.append(values)
        return 42

    async def fake_replace(order_id, item_values):
        replaced_items.append((order_id, item_values))

    async def fake_touch(_account):
        return None

    monkeypatch.setattr(service, "_upsert_order_record", fake_upsert)
    monkeypatch.setattr(service, "_replace_order_items", fake_replace)
    monkeypatch.setattr(service, "_touch_sync", fake_touch)
    # Neutralize the 1 req/s items pacing.
    monkeypatch.setattr(
        data_extraction,
        "time",
        SimpleNamespace(monotonic=lambda c=itertools.count(0, 10): float(next(c)), sleep=lambda _s: None),
    )

    account = _seller()
    raw_orders = [
        {
            "AmazonOrderId": "171-1",
            "PurchaseDate": "2026-01-05T10:00:00Z",
            "OrderStatus": "Shipped",
            "FulfillmentChannel": "MFN",
            "OrderTotal": {"Amount": "59.90", "CurrencyCode": "EUR"},
            "MarketplaceId": "APJ6JRA9NG5V4",
            "NumberOfItemsShipped": 1,
            "NumberOfItemsUnshipped": 0,
        },
        {"AmazonOrderId": "171-2"},  # no purchase date -> skipped
    ]
    fake_client = SimpleNamespace(
        fetch_order_items=lambda _order_id: [
            {
                "ASIN": "B0TEST",
                "SellerSKU": "SKU-1",
                "Title": "Widget",
                "QuantityOrdered": 1,
                "ItemPrice": {"Amount": "59.90", "CurrencyCode": "EUR"},
            }
        ]
    )

    synced_orders, synced_items = await service._persist_orders(account, fake_client, raw_orders)

    assert (synced_orders, synced_items) == (1, 1)
    assert len(upserted_orders) == 1
    order = upserted_orders[0]
    assert order["amazon_order_id"] == "171-1"
    assert order["order_status"] == "Shipped"
    assert order["number_of_items"] == 1
    assert str(order["order_total"]) == "59.90"
    assert replaced_items[0][0] == 42
    assert replaced_items[0][1][0]["asin"] == "B0TEST"
    assert replaced_items[0][1][0]["order_id"] == 42


# ---- MFN returns fallback ----


@pytest.mark.asyncio
async def test_sync_returns_falls_back_to_mfn_report_when_fba_is_cancelled(monkeypatch):
    db = FakeDb()
    service = DataExtractionService(db)
    upserted = []
    mfn_windows = []

    def fake_fba_report():
        raise AmazonAPIError("Report ended with status CANCELLED", error_code="REPORT_CANCELLED")

    def fake_mfn_report(start, end):
        mfn_windows.append((start, end))
        return [
            {
                "amazon_order_id": "171-1",
                "asin": "b0mfn001",
                "sku": "SKU-9",
                "return_date": date(2026, 5, 20),
                "quantity": 2,
                "reason": "Damaged",
                "disposition": "Refund",
                "detailed_disposition": None,
            }
        ]

    fake_client = SimpleNamespace(
        fetch_returns_report=fake_fba_report,
        fetch_mfn_returns_report=fake_mfn_report,
    )
    monkeypatch.setattr(service, "_create_sp_api_client", lambda *_a, **_k: fake_client)

    async def fake_upsert(values):
        upserted.append(values)

    async def fake_touch(_account):
        return None

    monkeypatch.setattr(service, "_upsert_return_record", fake_upsert)
    monkeypatch.setattr(service, "_touch_sync", fake_touch)

    account = _seller()
    count = await service.sync_returns(account)

    assert mfn_windows == [(date.today() - timedelta(days=60), date.today())]
    assert count == 1
    assert upserted == [
        {
            "account_id": account.id,
            "amazon_order_id": "171-1",
            "asin": "B0MFN001",
            "sku": "SKU-9",
            "return_date": date(2026, 5, 20),
            "quantity": 2,
            "reason": "Damaged",
            "disposition": "Refund",
            "detailed_disposition": None,
        }
    ]


@pytest.mark.asyncio
async def test_sync_returns_reraises_non_cancelled_failures(monkeypatch):
    service = DataExtractionService(FakeDb())

    def fake_fba_report():
        raise AmazonAPIError("throttled", error_code="THROTTLED")

    def explode(*_a, **_k):
        raise AssertionError("MFN fallback must not run for transient failures")

    fake_client = SimpleNamespace(
        fetch_returns_report=fake_fba_report,
        fetch_mfn_returns_report=explode,
    )
    monkeypatch.setattr(service, "_create_sp_api_client", lambda *_a, **_k: fake_client)

    with pytest.raises(AmazonAPIError):
        await service.sync_returns(_seller())


@pytest.mark.asyncio
async def test_backfill_returns_history_walks_60_day_windows_best_effort(monkeypatch):
    db = FakeDb()
    service = DataExtractionService(db)
    fetched_windows = []
    persisted = []

    def fake_mfn_report(start, end):
        fetched_windows.append((start, end))
        if len(fetched_windows) == 2:
            raise AmazonAPIError("report failed", error_code="REPORT_FATAL")
        return [{"return_date": start}]

    fake_client = SimpleNamespace(fetch_mfn_returns_report=fake_mfn_report)
    monkeypatch.setattr(service, "_create_sp_api_client", lambda *_a, **_k: fake_client)

    async def fake_persist(_account, raw_rows):
        persisted.append(raw_rows)
        return len(raw_rows)

    async def fake_sleep(_seconds):
        pass

    monkeypatch.setattr(service, "_persist_return_rows", fake_persist)
    monkeypatch.setattr(data_extraction.asyncio, "sleep", fake_sleep)

    start = date(2026, 1, 1)
    count = await service.backfill_returns_history(
        _seller(), start_date=start, end_date=start + timedelta(days=149)
    )

    assert fetched_windows == [
        (start, start + timedelta(days=59)),
        (start + timedelta(days=60), start + timedelta(days=119)),
        (start + timedelta(days=120), start + timedelta(days=149)),
    ]
    # The middle window failed and was skipped; the others were committed.
    assert count == 2
    assert len(persisted) == 2
    assert db.commits == 2


@pytest.mark.asyncio
async def test_backfill_returns_history_skips_vendor_accounts(monkeypatch):
    service = DataExtractionService(FakeDb())

    def explode(*_a, **_k):
        raise AssertionError("vendor backfill must not create an SP-API client")

    monkeypatch.setattr(service, "_create_sp_api_client", explode)

    count = await service.backfill_returns_history(
        _seller(account_type=AccountType.VENDOR),
        start_date=date(2026, 1, 1),
        end_date=date(2026, 3, 1),
    )
    assert count == 0
