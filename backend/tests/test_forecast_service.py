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
async def test_generate_forecast_retries_with_longer_lookback_for_asin():
    account_id = uuid4()
    session = FakeAsyncSession([
        _rows(6, date(2026, 1, 1)),
        _rows(8, date(2025, 10, 1)),
    ])
    service = ForecastService(session)  # type: ignore[arg-type]

    forecast = await service.generate_forecast(
        account_id=account_id,
        asin="B0TESTASIN",
        horizon_days=14,
        model="simple",
    )

    assert session.execute_calls == 2
    assert session.flushed is True
    assert session.refreshed is True
    assert forecast.asin == "B0TESTASIN"
    assert len(forecast.predictions) == 14


@pytest.mark.asyncio
async def test_generate_forecast_still_fails_when_asin_history_is_insufficient():
    account_id = uuid4()
    session = FakeAsyncSession([
        _rows(3, date(2026, 1, 1)),
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

    assert session.execute_calls == 2
    assert session.added == []
