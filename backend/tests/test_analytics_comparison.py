from datetime import date
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
import types
from uuid import uuid4

import pytest


ROOT = Path(__file__).resolve().parents[1]
ANALYTICS_PATH = ROOT / "app" / "api" / "v1" / "analytics.py"
SCHEMA_PATH = ROOT / "app" / "schemas" / "analytics.py"


def _ensure_package(name: str, path: Path) -> None:
    module = types.ModuleType(name)
    module.__path__ = [str(path)]
    sys.modules.setdefault(name, module)


_ensure_package("app", ROOT / "app")
_ensure_package("app.api", ROOT / "app" / "api")
_ensure_package("app.api.v1", ROOT / "app" / "api" / "v1")
_ensure_package("app.schemas", ROOT / "app" / "schemas")
_ensure_package("app.models", ROOT / "app" / "models")
_ensure_package("app.services", ROOT / "app" / "services")

deps_stub = types.ModuleType("app.api.deps")
deps_stub.CurrentUser = object
deps_stub.CurrentOrganization = object
deps_stub.CurrentSuperuser = object
deps_stub.DbSession = object
sys.modules["app.api.deps"] = deps_stub

data_extraction_stub = types.ModuleType("app.services.data_extraction")
data_extraction_stub.DAILY_TOTAL_ASIN = "__DAILY_TOTAL__"
sys.modules["app.services.data_extraction"] = data_extraction_stub

config_stub = types.ModuleType("app.config")
config_stub.settings = types.SimpleNamespace()
sys.modules["app.config"] = config_stub

ai_analysis_stub = types.ModuleType("app.services.ai_analysis_service")
ai_analysis_stub.ProductTrendInsightsAnalysisService = type(
    "ProductTrendInsightsAnalysisService", (), {}
)
sys.modules["app.services.ai_analysis_service"] = ai_analysis_stub

product_trends_stub = types.ModuleType("app.services.product_trends_service")
product_trends_stub.ProductTrendsService = type("ProductTrendsService", (), {})
product_trends_stub.build_rule_based_insights = lambda *args, **kwargs: []
sys.modules["app.services.product_trends_service"] = product_trends_stub

analytics_service_stub = types.ModuleType("app.services.analytics_service")
analytics_service_stub.AnalyticsService = type("AnalyticsService", (), {})
sys.modules["app.services.analytics_service"] = analytics_service_stub


def _stub_model_module(module_name: str, class_name: str) -> None:
    module = types.ModuleType(module_name)
    stub_class = type(class_name, (), {})
    setattr(module, class_name, stub_class)
    sys.modules[module_name] = module


_stub_model_module("app.models.amazon_account", "AmazonAccount")
_stub_model_module("app.models.sales_data", "SalesData")
order_module = types.ModuleType("app.models.order")
order_module.Order = type("Order", (), {})
order_module.OrderItem = type("OrderItem", (), {})
sys.modules["app.models.order"] = order_module
_stub_model_module("app.models.returns_data", "ReturnData")

product_module = types.ModuleType("app.models.product")
product_module.Product = type("Product", (), {})
product_module.BSRHistory = type("BSRHistory", (), {})
sys.modules["app.models.product"] = product_module

advertising_module = types.ModuleType("app.models.advertising")
advertising_module.AdvertisingCampaign = type("AdvertisingCampaign", (), {})
advertising_module.AdvertisingMetrics = type("AdvertisingMetrics", (), {})
sys.modules["app.models.advertising"] = advertising_module

schema_spec = spec_from_file_location("app.schemas.analytics", SCHEMA_PATH)
schema_module = module_from_spec(schema_spec)
assert schema_spec is not None and schema_spec.loader is not None
sys.modules["app.schemas.analytics"] = schema_module
schema_spec.loader.exec_module(schema_module)

analytics_spec = spec_from_file_location("analytics_under_test", ANALYTICS_PATH)
analytics = module_from_spec(analytics_spec)
assert analytics_spec is not None and analytics_spec.loader is not None
analytics_spec.loader.exec_module(analytics)


def test_previous_period_uses_same_inclusive_length():
    prev_start, prev_end = analytics._previous_period(date(2026, 3, 1), date(2026, 3, 31))

    assert prev_start == date(2026, 1, 29)
    assert prev_end == date(2026, 2, 28)


@pytest.mark.asyncio
async def test_comparison_includes_returns_metric_and_daily_series_with_category(monkeypatch):
    async def fake_sales(*args, **kwargs):
        return {
            "revenue": 2500.0,
            "units": 125,
            "orders": 80,
            "average_order_value": 31.25,
        }

    async def fake_returns(_db, _accounts, start_date, _end_date, _category=None):
        return 12 if start_date.month == 3 else 9

    async def fake_daily_revenue(_db, _accounts, start_date, _end_date, _category=None):
        if start_date.month == 3:
            return {
                date(2026, 3, 1): 1000.0,
                date(2026, 3, 2): 900.0,
            }
        return {
            date(2026, 2, 1): 700.0,
            date(2026, 2, 2): 850.0,
        }

    monkeypatch.setattr(analytics, "_accounts_query", lambda *args, **kwargs: None)
    monkeypatch.setattr(analytics, "_get_sales_period_metrics", fake_sales)
    monkeypatch.setattr(analytics, "_get_returns_period_count", fake_returns)
    monkeypatch.setattr(analytics, "_get_sales_daily_revenue", fake_daily_revenue)

    comparison = await analytics._build_period_comparison(
        db=None,
        organization_id=uuid4(),
        period_1_start=date(2026, 3, 1),
        period_1_end=date(2026, 3, 31),
        period_2_start=date(2026, 2, 1),
        period_2_end=date(2026, 2, 28),
        category="Sports",
    )

    metrics = {metric.metric_name: metric for metric in comparison.metrics}

    assert metrics["returns"].is_available is True
    assert metrics["returns"].current_value == 12
    assert metrics["returns"].previous_value == 9
    assert metrics["roas"].is_available is False
    assert metrics["roas"].unavailable_reason == analytics.CATEGORY_FILTER_NOT_SUPPORTED
    assert metrics["ctr"].is_available is False
    assert metrics["ctr"].unavailable_reason == analytics.CATEGORY_FILTER_NOT_SUPPORTED
    assert comparison.daily_series is not None
    assert comparison.daily_series[0].day_offset == 0
    assert len(comparison.daily_series) == 31
    assert comparison.daily_series[0].period_1_date == date(2026, 3, 1)
    assert comparison.daily_series[0].period_1_revenue == 1000.0
    assert comparison.daily_series[0].period_2_date == date(2026, 2, 1)
    assert comparison.daily_series[0].period_2_revenue == 700.0
    assert comparison.daily_series[-1].period_1_date == date(2026, 3, 31)
    assert comparison.daily_series[-1].period_1_revenue == 0.0
    assert comparison.daily_series[-1].period_2_date is None
    assert comparison.daily_series[-1].period_2_revenue is None


@pytest.mark.asyncio
async def test_comparison_includes_ad_metrics_without_category(monkeypatch):
    sales_calls: list[tuple[date, date]] = []
    ads_calls: list[tuple[date, date]] = []

    async def fake_sales(_db, _accounts, start_date, end_date, _category=None):
        sales_calls.append((start_date, end_date))
        if start_date.month == 3:
            return {
                "revenue": 3200.0,
                "units": 160,
                "orders": 95,
                "average_order_value": 33.68,
            }
        return {
            "revenue": 2800.0,
            "units": 140,
            "orders": 90,
            "average_order_value": 31.11,
        }

    async def fake_ads(_db, _accounts, start_date, end_date):
        ads_calls.append((start_date, end_date))
        if start_date.month == 3:
            return {"roas": 4.2, "acos": 23.8, "ctr": 1.9}
        return {"roas": 3.6, "acos": 27.8, "ctr": 1.4}

    async def fake_returns(_db, _accounts, start_date, _end_date, _category=None):
        return 18 if start_date.month == 3 else 10

    async def fake_daily_revenue(_db, _accounts, start_date, _end_date, _category=None):
        if start_date.month == 3:
            return {
                date(2026, 3, 1): 100.0,
                date(2026, 3, 2): 110.0,
            }
        return {
            date(2026, 2, 1): 80.0,
            date(2026, 2, 2): 95.0,
        }

    monkeypatch.setattr(analytics, "_accounts_query", lambda *args, **kwargs: None)
    monkeypatch.setattr(analytics, "_get_sales_period_metrics", fake_sales)
    monkeypatch.setattr(analytics, "_get_advertising_period_metrics", fake_ads)
    monkeypatch.setattr(analytics, "_get_returns_period_count", fake_returns)
    monkeypatch.setattr(analytics, "_get_sales_daily_revenue", fake_daily_revenue)

    comparison = await analytics._build_period_comparison(
        db=None,
        organization_id=uuid4(),
        period_1_start=date(2026, 3, 1),
        period_1_end=date(2026, 3, 31),
        period_2_start=date(2026, 2, 1),
        period_2_end=date(2026, 2, 28),
    )

    metrics = {metric.metric_name: metric for metric in comparison.metrics}

    assert len(sales_calls) == 2
    assert len(ads_calls) == 2
    assert metrics["roas"].is_available is True
    assert metrics["roas"].current_value == 4.2
    assert metrics["roas"].previous_value == 3.6
    assert metrics["roas"].trend == "up"
    assert metrics["ctr"].is_available is True
    assert metrics["ctr"].current_value == 1.9
    assert metrics["ctr"].previous_value == 1.4
    assert metrics["returns"].current_value == 18
    assert metrics["returns"].previous_value == 10
    assert comparison.daily_series is not None
    assert len(comparison.daily_series) == 31
    assert comparison.daily_series[1].period_1_revenue == 110.0
    assert comparison.daily_series[1].period_2_revenue == 95.0
    assert comparison.daily_series[-1].period_1_date == date(2026, 3, 31)
    assert comparison.daily_series[-1].period_1_revenue == 0.0
    assert comparison.daily_series[-1].period_2_date is None
    assert comparison.daily_series[-1].period_2_revenue is None
