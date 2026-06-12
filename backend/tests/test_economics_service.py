"""Data Kiosk economics row normalization and history backfill."""
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.models.amazon_account import AccountType
from app.services import economics_service
from app.services.economics_service import EconomicsService


def _row(**overrides):
    base = {
        "startDate": "2026-06-08",
        "endDate": "2026-06-08",
        "marketplaceId": "APJ6JRA9NG5V4",
        "childAsin": "B0TESTASIN",
        "sales": {
            "orderedProductSales": {"amount": "120.50", "currencyCode": "EUR"},
            "netProductSales": {"amount": "110.00", "currencyCode": "EUR"},
            "unitsOrdered": 10,
            "unitsRefunded": 1,
            "netUnitsSold": 9,
        },
        "fees": [
            {
                "feeTypeName": "FBA fulfillment fees",
                "charges": [
                    {"aggregatedDetail": {"totalAmount": {"amount": "-15.30", "currencyCode": "EUR"}}},
                ],
            },
            {
                "feeTypeName": "Referral fees",
                # Two charges for one fee type: the window straddles an Amazon
                # fee-change date — they must be summed.
                "charges": [
                    {"aggregatedDetail": {"totalAmount": {"amount": "-10.08", "currencyCode": "EUR"}}},
                    {"aggregatedDetail": {"totalAmount": {"amount": "-8.00", "currencyCode": "EUR"}}},
                ],
            },
        ],
        "ads": [
            {"adTypeName": "Sponsored Products charge", "charge": {"totalAmount": {"amount": "-9.00", "currencyCode": "EUR"}}},
            {"adTypeName": "Sponsored Brands charge", "charge": {"totalAmount": {"amount": "-3.00", "currencyCode": "EUR"}}},
            {"adTypeName": "No charge ads", "charge": None},
        ],
        "netProceeds": {
            "total": {"amount": "65.12", "currencyCode": "EUR"},
            "perUnit": {"amount": "7.2356", "currencyCode": "EUR"},
        },
    }
    base.update(overrides)
    return base


def test_normalize_row_maps_all_fields():
    values = EconomicsService._normalize_row(_row())
    assert values["date"] == date(2026, 6, 8)
    assert values["asin"] == "B0TESTASIN"
    assert values["units_ordered"] == 10
    assert values["net_units_sold"] == 9
    assert values["ordered_product_sales"] == Decimal("120.50")
    assert values["currency"] == "EUR"
    assert values["total_fees"] == Decimal("-33.38")
    assert values["ads_spend"] == Decimal("-12.00")
    assert values["net_proceeds_total"] == Decimal("65.12")
    assert values["fee_breakdown"] == {
        "FBA fulfillment fees": -15.30,
        "Referral fees": -18.08,
    }


def test_build_query_uses_live_schema_fields():
    query = EconomicsService._build_query("APJ6JRA9NG5V4", date(2026, 5, 1), date(2026, 5, 31))
    assert "charges { aggregatedDetail { totalAmount { amount currencyCode } } }" in query
    assert "charge { totalAmount { amount currencyCode } }" in query
    assert "adSpend" not in query


def test_normalize_row_without_asin_or_date_is_dropped():
    assert EconomicsService._normalize_row(_row(childAsin=None)) is None
    assert EconomicsService._normalize_row(_row(startDate=None)) is None


def test_normalize_row_tolerates_missing_sections():
    values = EconomicsService._normalize_row(
        {"startDate": "2026-06-08", "childAsin": "B0TESTASIN"}
    )
    assert values["asin"] == "B0TESTASIN"
    assert values["total_fees"] is None
    assert values["ads_spend"] is None
    assert values["fee_breakdown"] is None


def test_build_query_embeds_window_and_marketplace():
    query = EconomicsService._build_query("APJ6JRA9NG5V4", date(2026, 5, 1), date(2026, 5, 31))
    assert 'startDate: "2026-05-01"' in query
    assert 'endDate: "2026-05-31"' in query
    assert '"APJ6JRA9NG5V4"' in query
    assert "analytics_economics_2024_03_15" in query
    assert "aggregateBy: { date: DAY, productId: CHILD_ASIN }" in query


class FakeDb:
    def __init__(self):
        self.commits = 0

    async def commit(self):
        self.commits += 1


@pytest.mark.asyncio
async def test_backfill_economics_history_walks_month_windows(monkeypatch):
    db = FakeDb()
    service = EconomicsService(db)
    windows = []

    async def fake_sync(_account, _organization, *, start_date, end_date):
        windows.append((start_date, end_date))
        return 2

    async def fake_sleep(_seconds):
        pass

    monkeypatch.setattr(service, "sync_asin_economics", fake_sync)
    monkeypatch.setattr(economics_service.asyncio, "sleep", fake_sleep)

    total = await service.backfill_economics_history(
        SimpleNamespace(account_type=AccountType.SELLER),
        start_date=date(2026, 1, 15),
        end_date=date(2026, 3, 10),
    )

    assert windows == [
        (date(2026, 1, 15), date(2026, 1, 31)),
        (date(2026, 2, 1), date(2026, 2, 28)),
        (date(2026, 3, 1), date(2026, 3, 10)),
    ]
    assert total == 6
    assert db.commits == 3


@pytest.mark.asyncio
async def test_backfill_economics_history_skips_vendor_accounts():
    service = EconomicsService(FakeDb())
    total = await service.backfill_economics_history(
        SimpleNamespace(account_type=AccountType.VENDOR),
        start_date=date(2026, 1, 1),
        end_date=date(2026, 3, 1),
    )
    assert total == 0
