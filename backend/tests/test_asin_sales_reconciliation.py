"""Per-ASIN rows must reconcile with the __DAILY_TOTAL__ sentinel.

Two independent defects broke that invariant:
* seller — the Sales & Traffic ASIN section is a whole-window aggregate stored
  under a single date, so summing a period multiplied every sale;
* vendor — a legitimate shipped value of 0 was read as "missing" and displayed
  as that day's ordered revenue on top of the shipped total.
"""
from datetime import date
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services.data_extraction import DAILY_TOTAL_ASIN, DataExtractionService
from app.services.sales_metrics import display_revenue_expr, display_units_expr


class FakeDb:
    def __init__(self):
        self.executed = []

    async def flush(self):
        pass

    async def execute(self, *args, **kwargs):
        self.executed.append(args[0] if args else None)
        return SimpleNamespace(rowcount=0)


def _report():
    return {
        "by_date": [
            {
                "date": "2026-07-01",
                "salesByDate": {"unitsOrdered": 3, "orderedProductSales": {"amount": "30.00"}},
                "trafficByDate": {},
            },
            {
                "date": "2026-07-02",
                "salesByDate": {"unitsOrdered": 5, "orderedProductSales": {"amount": "50.00"}},
                "trafficByDate": {},
            },
        ],
        "by_asin": [
            {
                "childAsin": "B00WINDOW1",
                "salesByAsin": {"unitsOrdered": 8, "orderedProductSales": {"amount": "80.00"}},
                "trafficByAsin": {},
            }
        ],
    }


async def _run_sales_sync(monkeypatch, start, end):
    service = DataExtractionService(FakeDb())
    written = []

    async def fake_upsert(values):
        written.append(values.copy())

    monkeypatch.setattr(
        service, "_create_sp_api_client",
        lambda *_a, **_k: SimpleNamespace(get_sales_report=lambda _s, _e: _report()),
    )
    monkeypatch.setattr(service, "_upsert_sales_record", fake_upsert)
    await service.sync_sales_data(
        SimpleNamespace(id=uuid4(), account_name="Seller"), None, start, end
    )
    return written


@pytest.mark.asyncio
async def test_multi_day_window_writes_no_per_asin_rows(monkeypatch):
    written = await _run_sales_sync(monkeypatch, date(2026, 7, 1), date(2026, 7, 2))

    assert [row["asin"] for row in written] == [DAILY_TOTAL_ASIN, DAILY_TOTAL_ASIN]


@pytest.mark.asyncio
async def test_single_day_window_writes_per_asin_rows(monkeypatch):
    written = await _run_sales_sync(monkeypatch, date(2026, 7, 2), date(2026, 7, 2))

    asin_rows = [row for row in written if row["asin"] != DAILY_TOTAL_ASIN]
    assert len(asin_rows) == 1
    assert asin_rows[0]["asin"] == "B00WINDOW1"
    assert asin_rows[0]["date"] == date(2026, 7, 2)


@pytest.mark.asyncio
async def test_vendor_asin_day_missing_from_sourcing_is_shipped_zero(monkeypatch):
    """Per-ASIN shipped sums must equal the sentinel shipped total: an ASIN-day
    the SOURCING report omitted shipped nothing, it is not unknown."""
    service = DataExtractionService(FakeDb())
    written = []

    def fake_report(_start, _end, distributor_view="MANUFACTURING"):
        if distributor_view == "SOURCING":
            return {
                "salesByAsin": [
                    {
                        "asin": "B0SHIPPED",
                        "startDate": "2026-03-02",
                        "shippedRevenue": {"amount": "92.00", "currencyCode": "EUR"},
                        "shippedUnits": 4,
                        "shippedCogs": {"amount": "60.00", "currencyCode": "EUR"},
                    }
                ],
                "salesAggregate": [
                    {
                        "startDate": "2026-03-02",
                        "shippedRevenue": {"amount": "92.00", "currencyCode": "EUR"},
                        "shippedUnits": 4,
                        "shippedCogs": {"amount": "60.00", "currencyCode": "EUR"},
                    }
                ],
            }
        return {
            "salesByAsin": [
                {
                    "asin": "B0SHIPPED",
                    "startDate": "2026-03-02",
                    "orderedRevenue": {"amount": "100.00", "currencyCode": "EUR"},
                    "orderedUnits": 5,
                },
                {
                    "asin": "B0ORDEREDONLY",
                    "startDate": "2026-03-02",
                    "orderedRevenue": {"amount": "40.00", "currencyCode": "EUR"},
                    "orderedUnits": 2,
                },
            ],
            "salesAggregate": [
                {
                    "startDate": "2026-03-02",
                    "orderedRevenue": {"amount": "140.00", "currencyCode": "EUR"},
                    "orderedUnits": 7,
                }
            ],
        }

    async def fake_upsert(values):
        written.append(values.copy())

    monkeypatch.setattr(
        service, "_create_sp_api_client",
        lambda *_a, **_k: SimpleNamespace(
            get_vendor_sales_report=fake_report, get_vendor_purchase_orders=lambda *_a: []
        ),
    )
    monkeypatch.setattr(service, "_upsert_sales_record", fake_upsert)

    await service.sync_vendor_sales_data(
        SimpleNamespace(id=uuid4(), account_name="Vendor", account_type="vendor"),
        organization=None,
        start_date=date(2026, 3, 1),
        end_date=date(2026, 3, 5),
    )

    ordered_only = next(r for r in written if r["asin"] == "B0ORDEREDONLY")
    assert ordered_only["shipped_revenue"] == 0
    assert ordered_only["shipped_units"] == 0

    def display(row):
        return (
            row["shipped_revenue"]
            if row["shipped_revenue"] is not None
            else row["ordered_product_sales"]
        )

    per_asin = sum(display(r) for r in written if r["asin"] != DAILY_TOTAL_ASIN)
    sentinel = sum(display(r) for r in written if r["asin"] == DAILY_TOTAL_ASIN)
    assert per_asin == sentinel == 92


def test_display_expressions_treat_zero_shipped_as_real():
    assert "nullif" not in str(display_revenue_expr()).lower()
    assert "nullif" not in str(display_units_expr()).lower()
