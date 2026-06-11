"""Data Kiosk economics row normalization."""
from datetime import date
from decimal import Decimal

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
                "aggregatedDetail": {"totalAmount": {"amount": "-15.30", "currencyCode": "EUR"}},
            },
            {
                "feeTypeName": "Referral fees",
                "aggregatedDetail": {"totalAmount": {"amount": "-18.08", "currencyCode": "EUR"}},
            },
        ],
        "ads": {"adSpend": {"amount": "-12.00", "currencyCode": "EUR"}},
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
