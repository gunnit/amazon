from datetime import date, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services.forecast_service import ForecastService


class FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class FakeAsyncSession:
    def __init__(self, responses):
        self._responses = list(responses)
        self.execute_calls = 0
        self.added = []
        self.flushed = False
        self.refreshed = False

    async def execute(self, query):
        self.execute_calls += 1
        if not self._responses:
            raise AssertionError("Unexpected execute call")
        return FakeResult(self._responses.pop(0))

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        self.flushed = True

    async def refresh(self, obj):
        self.refreshed = True


def _rows(count: int, start: date) -> list[SimpleNamespace]:
    return [
        SimpleNamespace(date=start + timedelta(days=offset), value=100 + offset)
        for offset in range(count)
    ]


@pytest.mark.asyncio
async def test_generate_forecast_for_asin_with_limited_daily_history():
    account_id = uuid4()
    session = FakeAsyncSession([
        _rows(15, date(2025, 10, 1)),
    ])
    service = ForecastService(session)  # type: ignore[arg-type]

    forecast = await service.generate_forecast(
        account_id=account_id,
        asin="B0TESTASIN",
        horizon_days=14,
        model="simple",
    )

    assert session.execute_calls == 1
    assert session.flushed is True
    assert session.refreshed is True
    assert forecast.asin == "B0TESTASIN"
    assert len(forecast.predictions) == 14
    assert forecast.data_quality_notes is not None
    assert "Less than 28 days of data" in forecast.data_quality_notes
    assert "Using simplified model due to limited history" in forecast.data_quality_notes


@pytest.mark.asyncio
async def test_generate_forecast_fails_when_history_is_insufficient():
    account_id = uuid4()
    session = FakeAsyncSession([
        _rows(5, date(2025, 10, 1)),
    ])
    service = ForecastService(session)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="Insufficient historical data"):
        await service.generate_forecast(
            account_id=account_id,
            asin="B0TESTASIN",
            horizon_days=14,
            model="simple",
        )

    assert session.execute_calls == 1
    assert session.added == []


@pytest.mark.asyncio
async def test_generate_forecast_sets_confidence_level_from_mape(monkeypatch):
    account_id = uuid4()
    session = FakeAsyncSession([
        _rows(20, date(2026, 1, 1)),
    ])
    service = ForecastService(session)  # type: ignore[arg-type]

    async def fake_metrics(*args, **kwargs):
        return 12.0, 5.0

    monkeypatch.setattr(service, "_calculate_metrics", fake_metrics)

    forecast = await service.generate_forecast(
        account_id=account_id,
        asin=None,
        horizon_days=7,
        model="simple",
    )

    assert forecast.confidence_level == "high"
    assert forecast.data_quality_notes is not None
    assert "Less than 28 days of data" in forecast.data_quality_notes


def _monthly_rows(start: date, count: int) -> list[SimpleNamespace]:
    """One row per calendar month, values cycling to look like real sales."""
    rows = []
    for i in range(count):
        month_index = (start.year * 12 + start.month - 1) + i
        d = date(month_index // 12, month_index % 12 + 1, 1)
        rows.append(SimpleNamespace(date=d, value=5000 + (i % 6) * 500))
    return rows


@pytest.mark.asyncio
async def test_monthly_forecast_projects_into_the_future_when_data_is_stale():
    """A stale vendor series must never emit a single point in the past — the
    forecast has to start at the current month and go forward."""
    account_id = uuid4()
    # 24 months ending two months before today, so the last data month is stale.
    today = date.today().replace(day=1)
    last_data = date(
        (today.year * 12 + today.month - 1 - 2) // 12,
        (today.year * 12 + today.month - 1 - 2) % 12 + 1,
        1,
    )
    start = date(
        (last_data.year * 12 + last_data.month - 1 - 23) // 12,
        (last_data.year * 12 + last_data.month - 1 - 23) % 12 + 1,
        1,
    )
    session = FakeAsyncSession([_monthly_rows(start, 24)])
    service = ForecastService(session)  # type: ignore[arg-type]

    forecast = await service.generate_forecast(
        account_id=account_id,
        asin=None,
        horizon_days=90,
        model="prophet",
    )

    assert forecast.model_used == "monthly"
    pred_dates = [
        date.fromisoformat(p["date"]) if isinstance(p["date"], str) else p["date"]
        for p in forecast.predictions
    ]
    assert len(pred_dates) == 3
    # First prediction is the current month, every prediction is >= today.
    assert pred_dates[0] == today
    assert all(d >= today for d in pred_dates)
    # Months are consecutive and forward.
    assert pred_dates == sorted(pred_dates)
    assert pred_dates[0] != pred_dates[1]


@pytest.mark.asyncio
async def test_calculate_metrics_uses_prophet_for_prophet_models(monkeypatch):
    service = ForecastService(FakeAsyncSession([]))  # type: ignore[arg-type]
    historical_data = [
        {"date": date(2026, 1, 1) + timedelta(days=offset), "value": float(100 + offset)}
        for offset in range(21)
    ]
    calls = []

    async def fake_prophet(train, horizon, strategy, fallback_horizon=None):
        calls.append((len(train), horizon, strategy["label"], fallback_horizon))
        return [
            {
                "date": (train[-1]["date"] + timedelta(days=index + 1)).isoformat(),
                "value": train[-1]["value"],
                "lower": train[-1]["value"] - 5,
                "upper": train[-1]["value"] + 5,
            }
            for index in range(horizon)
        ]

    monkeypatch.setattr(service, "_prophet_forecast", fake_prophet)

    mape, rmse = await service._calculate_metrics(
        historical_data,
        model="prophet",
        strategy={"label": "medium"},
    )

    assert calls == [(14, 7, "medium", 7)]
    assert mape >= 0
    assert rmse >= 0
