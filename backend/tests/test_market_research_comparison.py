"""Tests for the client-vs-competitor comparison matrix.

Focus: partial competitor data must not crash the matrix nor produce a
misleading overall_score. Each dimension reports how many competitors
contributed a value via ``competitors_with_data``; dimensions that lack
enough comparable data are still surfaced but excluded from scoring.
"""
from pathlib import Path
import sys
from types import SimpleNamespace
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.market_research_service import MarketResearchService


def _fake_report(product_snapshot, competitor_data):
    return SimpleNamespace(
        id=uuid4(),
        product_snapshot=product_snapshot,
        competitor_data=competitor_data,
    )


def _matrix(product_snapshot, competitor_data):
    service = MarketResearchService.__new__(MarketResearchService)
    service.db = None
    return service.get_comparison_matrix(_fake_report(product_snapshot, competitor_data))


def test_comparison_matrix_handles_full_data():
    matrix = _matrix(
        product_snapshot={"asin": "B0CLIENT", "price": 10.0, "bsr": 500, "review_count": 100, "rating": 4.5},
        competitor_data=[
            {"asin": "B0C1", "price": 12.0, "bsr": 700, "review_count": 50, "rating": 4.2},
            {"asin": "B0C2", "price": 11.0, "bsr": 600, "review_count": 80, "rating": 4.4},
        ],
    )
    by_name = {dim["name"]: dim for dim in matrix["dimensions"]}
    assert by_name["price"]["competitors_with_data"] == 2
    assert by_name["price"]["client_rank"] == 1  # lower price = better
    assert matrix["overall_score"] is not None
    assert 0 <= matrix["overall_score"] <= 100


def test_comparison_matrix_with_partial_competitor_data():
    """Competitors missing a metric should not crash or fake a ranking."""
    matrix = _matrix(
        product_snapshot={"asin": "B0CLIENT", "price": 10.0, "bsr": 500, "review_count": 100, "rating": 4.5},
        competitor_data=[
            # Only price; missing bsr/reviews/rating.
            {"asin": "B0C1", "price": 12.0},
            # Only rating.
            {"asin": "B0C2", "rating": 4.0},
        ],
    )
    by_name = {dim["name"]: dim for dim in matrix["dimensions"]}
    assert by_name["price"]["competitors_with_data"] == 1
    assert by_name["bsr"]["competitors_with_data"] == 0
    assert by_name["rating"]["competitors_with_data"] == 1
    # bsr dimension still surfaces (so UI can label it N/A) but
    # contributes nothing to overall_score because no competitor has BSR.
    assert by_name["bsr"]["competitor_avg"] is None
    # overall_score is computed from dimensions that have at least one
    # comparable competitor — price and rating here.
    assert matrix["overall_score"] is not None


def test_comparison_matrix_returns_none_score_when_nothing_comparable():
    """If no dimension has a usable competitor value, overall_score is None.

    The previous code returned ``0.0`` which looked like "worst possible"
    instead of "no data to compare". Regression test.
    """
    matrix = _matrix(
        product_snapshot={"asin": "B0CLIENT", "price": 10.0, "bsr": 500, "review_count": 100, "rating": 4.5},
        competitor_data=[
            # All competitors lack every comparable metric. They might
            # still carry a title and an ASIN.
            {"asin": "B0C1", "title": "No metrics A", "fetch_errors": ["catalog:forbidden"]},
            {"asin": "B0C2", "title": "No metrics B", "fetch_errors": ["pricing:forbidden"]},
        ],
    )
    assert matrix["overall_score"] is None
    for dimension in matrix["dimensions"]:
        assert dimension["competitors_with_data"] == 0
        assert dimension["competitor_avg"] is None


def test_comparison_matrix_does_not_score_when_client_value_missing():
    """If the client lacks a metric, the dimension cannot rank it."""
    matrix = _matrix(
        product_snapshot={"asin": "B0CLIENT"},  # no price/bsr/rating/reviews
        competitor_data=[
            {"asin": "B0C1", "price": 12.0, "bsr": 700},
            {"asin": "B0C2", "price": 11.0, "bsr": 600},
        ],
    )
    for dimension in matrix["dimensions"]:
        assert dimension["client_rank"] is None
    assert matrix["overall_score"] is None
