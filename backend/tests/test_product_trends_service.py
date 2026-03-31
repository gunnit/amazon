from datetime import date
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services.ai_analysis_service import ProductTrendInsightsAnalysisService
from app.services.product_trends_service import (
    ProductTrendsService,
    _bsr_change_percent,
    _direction_from_score,
    _score_components,
    _strength_from_score,
    build_rule_based_insights,
)


class FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class FakeAsyncSession:
    def __init__(self, responses):
        self._responses = list(responses)

    async def execute(self, query):
        if not self._responses:
            raise AssertionError("Unexpected execute call")
        return FakeResult(self._responses.pop(0))


def test_score_renormalizes_without_bsr():
    score = _score_components(50.0, 25.0, None)
    assert score == pytest.approx(38.33, abs=0.01)


def test_bsr_change_rewards_lower_rank():
    assert _bsr_change_percent(800, 1000) == pytest.approx(20.0)
    assert _bsr_change_percent(1200, 1000) == pytest.approx(-20.0)


def test_direction_and_strength_thresholds():
    assert _direction_from_score(18) == "up"
    assert _direction_from_score(-18) == "down"
    assert _direction_from_score(6) == "stable"
    assert _strength_from_score(12) == "weak"
    assert _strength_from_score(30) == "moderate"
    assert _strength_from_score(70) == "strong"


@pytest.mark.asyncio
async def test_get_product_trends_excludes_sparse_products_and_ranks_results():
    account_id = uuid4()
    session = FakeAsyncSession(
        [
            [
                SimpleNamespace(asin="B0UP", revenue=500.0, units=20),
                SimpleNamespace(asin="B0DOWN", revenue=100.0, units=5),
                SimpleNamespace(asin="B0SPARSE", revenue=50.0, units=2),
            ],
            [
                SimpleNamespace(asin="B0UP", revenue=250.0, units=10),
                SimpleNamespace(asin="B0DOWN", revenue=400.0, units=12),
                SimpleNamespace(asin="B0SPARSE", revenue=0.0, units=1),
            ],
            [
                SimpleNamespace(asin="B0DOWN", title="Decliner", category="Home"),
                SimpleNamespace(asin="B0UP", title="Winner", category="Kitchen"),
            ],
            [
                SimpleNamespace(asin="B0UP", date=date(2026, 3, 30), bsr=800),
                SimpleNamespace(asin="B0UP", date=date(2026, 2, 28), bsr=1000),
                SimpleNamespace(asin="B0DOWN", date=date(2026, 3, 30), bsr=1500),
                SimpleNamespace(asin="B0DOWN", date=date(2026, 2, 28), bsr=1000),
            ],
        ]
    )

    service = ProductTrendsService(session)  # type: ignore[arg-type]
    result = await service.get_product_trends(
        account_ids=[account_id],
        start_date=date(2026, 3, 1),
        end_date=date(2026, 3, 31),
        limit=5,
    )

    assert result["summary"]["eligible_products"] == 2
    assert result["summary"]["rising_count"] == 1
    assert result["summary"]["declining_count"] == 1
    assert result["rising_products"][0]["asin"] == "B0UP"
    assert result["declining_products"][0]["asin"] == "B0DOWN"


def test_rule_based_insights_include_top_products():
    summary = {
        "eligible_products": 3,
        "rising_count": 2,
        "declining_count": 1,
        "strongest_riser": {"asin": "B0UP", "title": "Winner", "trend_score": 62.5},
        "strongest_decliner": {"asin": "B0DOWN", "title": "Decliner", "trend_score": -48.0},
    }
    insights = build_rule_based_insights(
        summary,
        [{"asin": "B0UP", "title": "Winner"}],
        [{"asin": "B0DOWN", "title": "Decliner"}],
        language="en",
    )

    assert "Winner" in insights["summary"] or insights["key_trends"]
    assert insights["recommendations"]


def test_product_trend_ai_service_repairs_missing_keys():
    service = ProductTrendInsightsAnalysisService.__new__(ProductTrendInsightsAnalysisService)

    class FakeMessages:
        @staticmethod
        def create(**kwargs):
            return SimpleNamespace(
                content=[SimpleNamespace(text='{"summary":"ok","recommendations":[{"action":"Act"}]}')]
            )

    service.client = SimpleNamespace(messages=FakeMessages())

    analysis = service.analyze(trend_data={"summary": {}}, language="en")

    assert analysis["summary"] == "ok"
    assert analysis["key_trends"] == []
    assert analysis["risks"] == []
    assert analysis["opportunities"] == []
    assert analysis["recommendations"][0]["priority"] == "medium"
