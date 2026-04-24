from datetime import date
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import SimpleNamespace
import sys
import types
from uuid import uuid4

import pytest
from sqlalchemy.sql import column, table


ROOT = Path(__file__).resolve().parents[1]
SERVICE_PATH = ROOT / "app" / "services" / "analytics_service.py"


def _ensure_package(name: str, path: Path) -> None:
    module = types.ModuleType(name)
    module.__path__ = [str(path)]
    sys.modules.setdefault(name, module)


class _TableProxy:
    def __init__(self, table_name: str, *columns: str):
        self._table = table(table_name, *[column(name) for name in columns])
        for name in columns:
            setattr(self, name, getattr(self._table.c, name))

    def __clause_element__(self):
        return self._table


_ensure_package("app", ROOT / "app")
_ensure_package("app.models", ROOT / "app" / "models")
_ensure_package("app.services", ROOT / "app" / "services")

sales_module = types.ModuleType("app.models.sales_data")
sales_module.SalesData = _TableProxy(
    "sales_data",
    "account_id",
    "date",
    "asin",
    "ordered_product_sales",
    "units_ordered",
    "total_order_items",
)
sys.modules["app.models.sales_data"] = sales_module

advertising_module = types.ModuleType("app.models.advertising")
advertising_module.AdvertisingCampaign = _TableProxy(
    "advertising_campaigns",
    "id",
    "account_id",
)
advertising_module.AdvertisingMetrics = _TableProxy(
    "advertising_metrics",
    "campaign_id",
    "date",
    "attributed_sales_7d",
)
sys.modules["app.models.advertising"] = advertising_module

product_module = types.ModuleType("app.models.product")
product_module.Product = _TableProxy("products", "account_id", "asin", "title")
product_module.BSRHistory = type("BSRHistory", (), {})
sys.modules["app.models.product"] = product_module

data_extraction_module = types.ModuleType("app.services.data_extraction")
data_extraction_module.DAILY_TOTAL_ASIN = "__DAILY_TOTAL__"
sys.modules["app.services.data_extraction"] = data_extraction_module

service_spec = spec_from_file_location("analytics_service_under_test", SERVICE_PATH)
service_module = module_from_spec(service_spec)
assert service_spec is not None and service_spec.loader is not None
service_spec.loader.exec_module(service_module)
AnalyticsService = service_module.AnalyticsService


class FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class FakeAsyncSession:
    def __init__(self, responses):
        self._responses = list(responses)
        self.execute_calls = 0

    async def execute(self, query):
        self.execute_calls += 1
        if not self._responses:
            raise AssertionError("Unexpected execute call")
        return FakeResult(self._responses.pop(0))


def _sales_row(account_id, bucket_date: date, total_sales: float):
    return SimpleNamespace(account_id=account_id, bucket_date=bucket_date, total_sales=total_sales)


def _ads_row(account_id, bucket_date: date, ad_sales: float):
    return SimpleNamespace(account_id=account_id, bucket_date=bucket_date, ad_sales=ad_sales)


def _asin_row(asin: str, title: str, total_sales: float):
    return SimpleNamespace(asin=asin, title=title, total_sales=total_sales)


@pytest.mark.asyncio
async def test_get_ads_vs_organic_combines_sales_ads_and_breakdown():
    account_a = uuid4()
    account_b = uuid4()
    session = FakeAsyncSession(
        [
            [
                _sales_row(account_a, date(2026, 3, 1), 100),
                _sales_row(account_b, date(2026, 3, 1), 50),
                _sales_row(account_a, date(2026, 3, 2), 80),
            ],
            [
                _ads_row(account_a, date(2026, 3, 1), 30),
                _ads_row(account_b, date(2026, 3, 1), 5),
                _ads_row(account_a, date(2026, 3, 2), 10),
            ],
            [
                _sales_row(account_a, date(2026, 2, 27), 90),
                _sales_row(account_b, date(2026, 2, 27), 40),
                _sales_row(account_a, date(2026, 2, 28), 70),
            ],
            [
                _ads_row(account_a, date(2026, 2, 27), 20),
                _ads_row(account_b, date(2026, 2, 27), 10),
                _ads_row(account_a, date(2026, 2, 28), 10),
            ],
            [
                _asin_row("B0AAA", "Alpha", 120),
                _asin_row("B0BBB", "Beta", 110),
            ],
        ]
    )

    service = AnalyticsService(session)  # type: ignore[arg-type]
    result = await service.get_ads_vs_organic(
        account_ids=[account_a, account_b],
        date_from=date(2026, 3, 1),
        date_to=date(2026, 3, 2),
    )

    assert session.execute_calls == 5
    assert [point["date"] for point in result["time_series"]] == [date(2026, 3, 1), date(2026, 3, 2)]
    assert result["time_series"][0]["total_sales"] == 150.0
    assert result["time_series"][0]["ad_sales"] == 35.0
    assert result["time_series"][0]["organic_sales"] == 115.0
    assert result["summary"]["total_sales"]["value"] == 230.0
    assert result["summary"]["ad_sales"]["value"] == 45.0
    assert result["summary"]["organic_sales"]["value"] == 185.0
    assert result["summary"]["ad_share_pct"]["value"] == pytest.approx(19.57, abs=0.01)
    assert result["summary"]["organic_share_pct"]["value"] == pytest.approx(80.43, abs=0.01)
    assert result["summary"]["total_sales"]["previous_value"] == 200.0
    assert result["asin_breakdown"][0]["asin"] == "B0AAA"
    assert result["asin_breakdown"][0]["sales_share_pct"] == pytest.approx(52.17, abs=0.01)


@pytest.mark.asyncio
async def test_get_ads_vs_organic_defaults_missing_ads_to_zero():
    account_id = uuid4()
    session = FakeAsyncSession(
        [
            [_sales_row(account_id, date(2026, 3, 5), 100)],
            [],
            [],
            [],
            [],
        ]
    )

    service = AnalyticsService(session)  # type: ignore[arg-type]
    result = await service.get_ads_vs_organic(
        account_ids=[account_id],
        date_from=date(2026, 3, 5),
        date_to=date(2026, 3, 5),
    )

    point = result["time_series"][0]
    assert point["total_sales"] == 100.0
    assert point["ad_sales"] == 0.0
    assert point["organic_sales"] == 100.0
    assert point["organic_share_pct"] == 100.0


@pytest.mark.asyncio
async def test_get_ads_vs_organic_supports_week_grouping():
    account_id = uuid4()
    session = FakeAsyncSession(
        [
            [
                _sales_row(account_id, date(2026, 3, 2), 120),
                _sales_row(account_id, date(2026, 3, 9), 80),
            ],
            [
                _ads_row(account_id, date(2026, 3, 2), 30),
                _ads_row(account_id, date(2026, 3, 9), 10),
            ],
            [],
            [],
            [],
        ]
    )

    service = AnalyticsService(session)  # type: ignore[arg-type]
    result = await service.get_ads_vs_organic(
        account_ids=[account_id],
        date_from=date(2026, 3, 3),
        date_to=date(2026, 3, 15),
        group_by="week",
    )

    assert [point["date"] for point in result["time_series"]] == [date(2026, 3, 2), date(2026, 3, 9)]
    assert result["time_series"][1]["organic_sales"] == 70.0


@pytest.mark.asyncio
async def test_get_ads_vs_organic_supports_month_grouping():
    account_id = uuid4()
    session = FakeAsyncSession(
        [
            [
                _sales_row(account_id, date(2026, 3, 1), 100),
                _sales_row(account_id, date(2026, 4, 1), 200),
            ],
            [
                _ads_row(account_id, date(2026, 3, 1), 40),
                _ads_row(account_id, date(2026, 4, 1), 50),
            ],
            [],
            [],
            [],
        ]
    )

    service = AnalyticsService(session)  # type: ignore[arg-type]
    result = await service.get_ads_vs_organic(
        account_ids=[account_id],
        date_from=date(2026, 3, 1),
        date_to=date(2026, 4, 30),
        group_by="month",
    )

    assert [point["date"] for point in result["time_series"]] == [date(2026, 3, 1), date(2026, 4, 1)]
    assert result["summary"]["organic_sales"]["value"] == 210.0


@pytest.mark.asyncio
async def test_get_ads_vs_organic_applies_asin_filter_and_returns_note():
    account_id = uuid4()
    session = FakeAsyncSession(
        [
            [_sales_row(account_id, date(2026, 3, 5), 90)],
            [_ads_row(account_id, date(2026, 3, 5), 40)],
            [],
            [],
        ]
    )

    service = AnalyticsService(session)  # type: ignore[arg-type]
    result = await service.get_ads_vs_organic(
        account_ids=[account_id],
        date_from=date(2026, 3, 5),
        date_to=date(2026, 3, 5),
        asin="B0TESTASIN",
    )

    assert session.execute_calls == 4
    assert result["asin"] == "B0TESTASIN"
    assert result["asin_breakdown"] is None
    assert result["summary"]["total_sales"]["value"] == 90.0
    assert result["attribution_notes"]


@pytest.mark.asyncio
async def test_get_ads_vs_organic_normalizes_asin_filter():
    account_id = uuid4()
    session = FakeAsyncSession(
        [
            [_sales_row(account_id, date(2026, 3, 6), 25)],
            [_ads_row(account_id, date(2026, 3, 6), 5)],
            [],
            [],
        ]
    )

    service = AnalyticsService(session)  # type: ignore[arg-type]
    result = await service.get_ads_vs_organic(
        account_ids=[account_id],
        date_from=date(2026, 3, 6),
        date_to=date(2026, 3, 6),
        asin="  b0mixed123  ",
    )

    assert session.execute_calls == 4
    assert result["asin"] == "B0MIXED123"
    assert result["asin_breakdown"] is None
    assert result["summary"]["ad_sales"]["value"] == 5.0


@pytest.mark.asyncio
async def test_get_ads_vs_organic_clamps_organic_sales_when_ads_exceed_total():
    account_id = uuid4()
    session = FakeAsyncSession(
        [
            [_sales_row(account_id, date(2026, 3, 8), 50)],
            [_ads_row(account_id, date(2026, 3, 8), 80)],
            [],
            [],
            [],
        ]
    )

    service = AnalyticsService(session)  # type: ignore[arg-type]
    result = await service.get_ads_vs_organic(
        account_ids=[account_id],
        date_from=date(2026, 3, 8),
        date_to=date(2026, 3, 8),
    )

    point = result["time_series"][0]
    assert point["ad_sales"] == 80.0
    assert point["organic_sales"] == 0.0
    assert point["ad_share_pct"] == 160.0
    assert result["summary"]["organic_sales"]["value"] == 0.0
