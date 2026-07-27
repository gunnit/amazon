"""Unit tests for the Helium 10 fill-only enrichment (no network)."""
from app.core import helium10


def test_extract_metrics_from_nested_payload():
    payload = {
        "product": {
            "asin": "B000TEST00",
            "reviews": 1234,
            "rating": "4.3",
            "price": "€24,90",
            "sales": {"estimated_monthly_sales": 850, "monthly_revenue": 21165.0},
        }
    }
    metrics = helium10.extract_metrics(payload)
    assert metrics["review_count"] == 1234
    assert metrics["rating"] == 4.3
    assert metrics["price"] == 24.90
    assert metrics["estimated_monthly_sales"] == 850
    assert metrics["estimated_revenue"] == 21165.0


def test_extract_metrics_matches_key_spelling_variants():
    """Field keys are matched normalized, so casing/separators don't matter."""
    payload = {
        "Monthly Sales": 410,
        "monthlyRevenue": 9020.5,
        "Best Seller Rank": 1875,
        "averageRating": 4.6,
    }
    metrics = helium10.extract_metrics(payload)
    assert metrics["estimated_monthly_sales"] == 410
    assert metrics["estimated_revenue"] == 9020.5
    assert metrics["bsr"] == 1875
    assert metrics["rating"] == 4.6


def test_extract_metrics_rejects_implausible_values():
    metrics = helium10.extract_metrics({"rating": 47, "price": -3, "reviews": 0})
    assert metrics == {}


def test_fill_snapshot_gaps_only_touches_missing_fields(monkeypatch):
    class FakeClient:
        available = True

        def get_listing_details(self, asin, marketplace):
            return {"rating": 4.1, "reviews": 200, "price": 9.99}

    monkeypatch.setattr(helium10, "get_client", lambda: FakeClient())

    snapshot = {"asin": "B000TEST00", "price": 12.50, "rating": None}
    assert helium10.fill_snapshot_gaps(snapshot, "IT") is True
    assert snapshot["price"] == 12.50  # Amazon value preserved
    assert snapshot["rating"] == 4.1
    assert snapshot["review_count"] == 200
    assert "price" not in snapshot["helium10_fields"]
    assert {"rating", "review_count"} <= set(snapshot["helium10_fields"])


def test_fill_is_noop_when_unconfigured(monkeypatch):
    monkeypatch.setattr(helium10, "get_client", lambda: None)
    snapshot = {"asin": "B000TEST00"}
    assert helium10.fill_snapshot_gaps(snapshot, "IT") is False
    assert "helium10_fields" not in snapshot
    assert helium10.fill_market_items([snapshot], "IT") == 0


def test_fill_market_items_caps_fresh_calls(monkeypatch):
    calls = []

    class FakeClient:
        available = True

        def has_cached(self, asin, marketplace):
            return False

        def get_listing_details(self, asin, marketplace):
            calls.append(asin)
            return {"rating": 4.0, "reviews": 10}

    monkeypatch.setattr(helium10, "get_client", lambda: FakeClient())
    items = [{"asin": f"B{i:09d}"} for i in range(helium10.MARKET_SEARCH_CALL_CAP + 5)]
    changed = helium10.fill_market_items(items, "IT")
    assert changed == helium10.MARKET_SEARCH_CALL_CAP
    assert len(calls) == helium10.MARKET_SEARCH_CALL_CAP


def test_marketplace_code_from_sp_api_object():
    class Marketplace:
        code = "IT"
        marketplace_id = "APJ6JRA9NG5V4"

    assert helium10.marketplace_code(Marketplace()) == "IT"
    assert helium10.marketplace_code("it") == "IT"
