"""Competitor tracking snapshot mapping and price-change alert logic."""
from decimal import Decimal

from app.services.competitor_tracking_service import (
    PRICE_CHANGE_ALERT_THRESHOLD_PCT,
    price_change_percent,
    snapshot_to_fields,
)


def test_snapshot_to_fields_maps_all_metrics():
    fields = snapshot_to_fields({
        "asin": "B0TEST12345",
        "title": "Chef Knife",
        "brand": "ZWILLING",
        "price": 49.99,
        "bsr": 1234,
        "review_count": 120,
        "rating": 4.5,
    })
    assert fields["title"] == "Chef Knife"
    assert fields["brand"] == "ZWILLING"
    assert fields["price"] == Decimal("49.99")
    assert fields["bsr"] == 1234
    assert fields["review_count"] == 120
    assert fields["rating"] == Decimal("4.5")


def test_snapshot_to_fields_keeps_missing_metrics_none():
    fields = snapshot_to_fields({"asin": "B0TEST12345", "title": "Knife"})
    assert fields["price"] is None
    assert fields["bsr"] is None
    assert fields["review_count"] is None
    assert fields["rating"] is None


def test_price_change_percent():
    assert price_change_percent(Decimal("10.00"), Decimal("11.00")) == 10.0
    assert price_change_percent(Decimal("10.00"), Decimal("9.00")) == -10.0
    assert price_change_percent(None, Decimal("9.00")) is None
    assert price_change_percent(Decimal("10.00"), None) is None
    assert price_change_percent(Decimal("0"), Decimal("9.00")) is None


def test_small_price_moves_stay_below_alert_threshold():
    change = price_change_percent(Decimal("25.00"), Decimal("25.50"))
    assert abs(change) < PRICE_CHANGE_ALERT_THRESHOLD_PCT

    change = price_change_percent(Decimal("25.00"), Decimal("23.00"))
    assert abs(change) >= PRICE_CHANGE_ALERT_THRESHOLD_PCT
