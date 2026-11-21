"""Listing quality scoring."""
from decimal import Decimal
from types import SimpleNamespace

from app.services.listing_quality_service import score_product


def _product(**overrides):
    base = dict(
        title="Premium Stainless Steel Chef Knife 20cm with Ergonomic Handle, Dishwasher Safe Kitchen Tool",
        brand="ZWILLING",
        category="Kitchen",
        current_price=Decimal("49.99"),
        is_active=True,
        is_available=True,
        rating=Decimal("4.5"),
        review_count=120,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_complete_listing_scores_100():
    result = score_product(_product())
    assert result["score"] == 100
    assert result["issues"] == []


def test_empty_listing_scores_0():
    result = score_product(
        _product(
            title=None, brand=None, category=None, current_price=None,
            is_active=False, is_available=False, rating=None, review_count=0,
        )
    )
    assert result["score"] == 0
    assert len(result["issues"]) == 7


def test_short_title_earns_partial_credit_and_flags_issue():
    result = score_product(_product(title="Chef Knife 20cm with handle grip"))
    assert result["components"]["title"]["earned"] == 15
    assert any("Title" in issue for issue in result["issues"])


def test_unavailable_listing_loses_availability_points():
    result = score_product(_product(is_available=False))
    assert result["score"] == 80
    assert result["components"]["availability"]["earned"] == 0


def test_component_points_sum_to_100():
    result = score_product(_product())
    assert sum(c["max"] for c in result["components"].values()) == 100


def test_strategic_signals_read_daily_scan_snapshots():
    from app.services.strategic_recommendations_service import failing_listing_components

    daily = {
        "asin": "B0TEST0001",
        "state": "red",
        "score": 40,
        "results": [
            {"key": "title", "state": "green", "mandatory": True, "code": "ok", "details": {}},
            {"key": "bullets", "state": "red", "mandatory": True, "code": "too_few", "details": {}},
            {"key": "video", "state": "grey", "mandatory": False, "code": "n/a", "details": {}},
            {"key": "aplus", "state": "red", "mandatory": False, "code": "missing", "details": {}},
        ],
    }
    assert failing_listing_components(daily) == ["bullets", "aplus"]


def test_strategic_signals_still_read_older_weekly_snapshots():
    from app.services.strategic_recommendations_service import failing_listing_components

    weekly = score_product(_product(rating=None, review_count=0))["components"]
    assert failing_listing_components(weekly) == ["rating", "reviews"]
    assert failing_listing_components(None) == []
