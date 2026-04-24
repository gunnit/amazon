from datetime import date
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.models.alert import Alert, AlertRule
from app.services.ai_analysis_service import ProductTrendInsightsAnalysisService
from app.services.product_trends_service import (
    TREND_ALERT_EVENT_KIND,
    ProductTrendsService,
    _bsr_change_percent,
    _score_components,
    _trend_class_from_delta,
    build_rule_based_insights,
)


class FakeScalarResult:
    def __init__(self, rows):
        self._rows = list(rows)

    def all(self):
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None

    def one_or_none(self):
        if len(self._rows) > 1:
            raise AssertionError("Expected zero or one row")
        return self._rows[0] if self._rows else None


class FakeResult:
    def __init__(self, rows):
        self._rows = list(rows)

    def all(self):
        return list(self._rows)

    def scalars(self):
        return FakeScalarResult(self._rows)

    def scalar_one_or_none(self):
        return FakeScalarResult(self._rows).one_or_none()


class FakeAsyncSession:
    def __init__(self, responses):
        self._responses = list(responses)
        self.added = []
        self.commits = 0
        self.flushes = 0

    async def execute(self, query):
        if not self._responses:
            raise AssertionError("Unexpected execute call")
        return FakeResult(self._responses.pop(0))

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1

    async def flush(self):
        self.flushes += 1


def _sales_row(asin: str, day: date, revenue: float, units: int):
    return SimpleNamespace(asin=asin, date=day, revenue=revenue, units=units)


def _metadata_row(account_id, asin: str, title: str, category: str, current_bsr=None, review_count=None):
    return SimpleNamespace(
        account_id=account_id,
        asin=asin,
        title=title,
        category=category,
        current_bsr=current_bsr,
        review_count=review_count,
    )


def _bsr_row(asin: str, day: date, bsr: int):
    return SimpleNamespace(asin=asin, date=day, bsr=bsr)


def _inventory_row(asin: str, snapshot_date: date, current_inventory: int):
    return SimpleNamespace(asin=asin, snapshot_date=snapshot_date, current_inventory=current_inventory)


def test_score_renormalizes_without_optional_signals():
    score = _score_components(50.0, 25.0, None)
    assert score == pytest.approx(42.65, abs=0.01)


def test_bsr_change_rewards_lower_rank():
    assert _bsr_change_percent(800, 1000) == pytest.approx(20.0)
    assert _bsr_change_percent(1200, 1000) == pytest.approx(-20.0)


def test_trend_class_thresholds():
    assert _trend_class_from_delta(25) == "rising_fast"
    assert _trend_class_from_delta(8) == "rising"
    assert _trend_class_from_delta(2) == "stable"
    assert _trend_class_from_delta(-8) == "declining"
    assert _trend_class_from_delta(-25) == "declining_fast"


@pytest.mark.asyncio
async def test_get_product_trends_classifies_rising_declining_and_stable_products():
    account_id = uuid4()
    end_date = date(2026, 3, 31)
    session = FakeAsyncSession(
        [
            [
                *_make_window_rows("B0UP", date(2026, 3, 18), previous_revenue=100, current_revenue=140, previous_units=7, current_units=10),
                *_make_window_rows("B0DOWN", date(2026, 3, 18), previous_revenue=200, current_revenue=120, previous_units=14, current_units=8),
                *_make_window_rows("B0STABLE", date(2026, 3, 18), previous_revenue=100, current_revenue=103, previous_units=7, current_units=7),
            ],
            [
                _metadata_row(account_id, "B0UP", "Winner", "Kitchen", current_bsr=800),
                _metadata_row(account_id, "B0DOWN", "Decliner", "Home", current_bsr=1800),
                _metadata_row(account_id, "B0STABLE", "Steady", "Office"),
            ],
            [
                _bsr_row("B0UP", date(2026, 3, 31), 800),
                _bsr_row("B0UP", date(2026, 3, 24), 1200),
                _bsr_row("B0DOWN", date(2026, 3, 31), 1800),
                _bsr_row("B0DOWN", date(2026, 3, 24), 1200),
            ],
            [
                _inventory_row("B0UP", date(2026, 3, 31), 6),
                _inventory_row("B0UP", date(2026, 3, 24), 15),
                _inventory_row("B0DOWN", date(2026, 3, 31), 40),
                _inventory_row("B0DOWN", date(2026, 3, 24), 60),
            ],
        ]
    )

    service = ProductTrendsService(session)  # type: ignore[arg-type]
    result = await service.get_product_trends(
        account_ids=[account_id],
        start_date=date(2026, 3, 1),
        end_date=end_date,
        limit=10,
    )

    products = {item["asin"]: item for item in result["products"]}
    assert result["summary"]["eligible_products"] == 3
    assert result["summary"]["rising_count"] == 1
    assert result["summary"]["declining_count"] == 1
    assert result["summary"]["stable_count"] == 1

    assert products["B0UP"]["trend_class"] == "rising_fast"
    assert products["B0DOWN"]["trend_class"] == "declining_fast"
    assert products["B0STABLE"]["trend_class"] == "stable"
    assert "Sales +40% vs previous 7 days" in products["B0UP"]["supporting_signals"]
    assert "BSR improved by 400 positions" in products["B0UP"]["supporting_signals"]
    assert len(products["B0UP"]["recent_sales"]) == 14


@pytest.mark.asyncio
async def test_get_product_trends_handles_missing_bsr_and_review_data():
    account_id = uuid4()
    session = FakeAsyncSession(
        [
            [
                *_make_window_rows("B0NOBSR", date(2026, 3, 18), previous_revenue=100, current_revenue=94, previous_units=7, current_units=7),
            ],
            [
                _metadata_row(account_id, "B0NOBSR", "No BSR", "Kitchen", current_bsr=None, review_count=None),
            ],
            [],
            [],
        ]
    )

    service = ProductTrendsService(session)  # type: ignore[arg-type]
    result = await service.get_product_trends(
        account_ids=[account_id],
        start_date=date(2026, 3, 1),
        end_date=date(2026, 3, 31),
        limit=5,
    )

    product = result["products"][0]
    assert product["trend_class"] == "declining"
    assert product["bsr_change_percent"] is None
    assert product["review_velocity_change_percent"] is None
    assert "Sales -6% vs previous 7 days" in product["supporting_signals"]


@pytest.mark.asyncio
async def test_get_product_trends_empty_response_uses_requested_language():
    service = ProductTrendsService(FakeAsyncSession([]))  # type: ignore[arg-type]

    result = await service.get_product_trends(
        account_ids=[],
        start_date=date(2026, 3, 1),
        end_date=date(2026, 3, 31),
        language="it",
    )

    assert result["summary"]["eligible_products"] == 0
    assert result["insights"]["summary"].startswith("Dati insufficienti")


@pytest.mark.asyncio
async def test_declining_fast_creates_warning_alert():
    account_id = uuid4()
    organization_id = uuid4()
    session = FakeAsyncSession(
        [
            [
                *_make_window_rows("B0ALERT", date(2026, 3, 18), previous_revenue=200, current_revenue=120, previous_units=14, current_units=8),
            ],
            [
                _metadata_row(account_id, "B0ALERT", "Alerted Product", "Home", current_bsr=1800),
            ],
            [],
            [],
            [],
            [],
            [],
        ]
    )

    service = ProductTrendsService(session)  # type: ignore[arg-type]
    await service.get_product_trends(
        account_ids=[account_id],
        organization_id=organization_id,
        start_date=date(2026, 3, 1),
        end_date=date(2026, 3, 31),
        limit=5,
    )

    created_rule = next(obj for obj in session.added if isinstance(obj, AlertRule))
    created_alert = next(obj for obj in session.added if isinstance(obj, Alert))
    assert created_rule.alert_type == "product_trend"
    assert created_alert.event_kind == TREND_ALERT_EVENT_KIND
    assert created_alert.severity == "warning"
    assert created_alert.asin == "B0ALERT"
    assert created_alert.details["trend_class"] == "declining_fast"
    assert session.commits == 1


def test_rule_based_insights_include_top_products():
    summary = {
        "eligible_products": 3,
        "rising_count": 2,
        "declining_count": 1,
        "trend_class_counts": {
            "rising_fast": 1,
            "rising": 1,
            "stable": 0,
            "declining": 0,
            "declining_fast": 1,
        },
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


def _make_window_rows(
    asin: str,
    start_day: date,
    *,
    previous_revenue: float,
    current_revenue: float,
    previous_units: int,
    current_units: int,
):
    rows = []

    def _distribute_int(total: int) -> list[int]:
        base = total // 7
        remainder = total % 7
        return [base + (1 if index < remainder else 0) for index in range(7)]

    def _distribute_money(total: float) -> list[float]:
        cents = int(round(total * 100))
        base = cents // 7
        remainder = cents % 7
        return [(base + (1 if index < remainder else 0)) / 100 for index in range(7)]

    previous_units_daily = _distribute_int(previous_units)
    current_units_daily = _distribute_int(current_units)
    previous_revenue_daily = _distribute_money(previous_revenue)
    current_revenue_daily = _distribute_money(current_revenue)

    for index in range(7):
        rows.append(
            _sales_row(
                asin,
                date.fromordinal(start_day.toordinal() + index),
                previous_revenue_daily[index],
                previous_units_daily[index],
            )
        )
    for index in range(7):
        rows.append(
            _sales_row(
                asin,
                date.fromordinal(start_day.toordinal() + 7 + index),
                current_revenue_daily[index],
                current_units_daily[index],
            )
        )

    return rows
