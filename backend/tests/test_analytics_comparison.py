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


def _stub_model_module(module_name: str, class_name: str) -> None:
    module = types.ModuleType(module_name)
    stub_class = type(class_name, (), {})
    setattr(module, class_name, stub_class)
    sys.modules[module_name] = module


_stub_model_module("app.models.amazon_account", "AmazonAccount")
_stub_model_module("app.models.sales_data", "SalesData")

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
async def test_comparison_marks_returns_and_category_limited_metrics_unavailable(monkeypatch):
    async def fake_sales(*args, **kwargs):
        return {
            "revenue": 2500.0,
            "units": 125,
            "orders": 80,
            "average_order_value": 31.25,
        }

    monkeypatch.setattr(analytics, "_accounts_query", lambda *args, **kwargs: None)
    monkeypatch.setattr(analytics, "_get_sales_period_metrics", fake_sales)

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

    assert metrics["returns"].is_available is False
    assert metrics["returns"].unavailable_reason == analytics.MISSING_DATA_SOURCE
    assert metrics["roas"].is_available is False
    assert metrics["roas"].unavailable_reason == analytics.CATEGORY_FILTER_NOT_SUPPORTED
    assert metrics["ctr"].is_available is False
    assert metrics["ctr"].unavailable_reason == analytics.CATEGORY_FILTER_NOT_SUPPORTED


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

    monkeypatch.setattr(analytics, "_accounts_query", lambda *args, **kwargs: None)
    monkeypatch.setattr(analytics, "_get_sales_period_metrics", fake_sales)
    monkeypatch.setattr(analytics, "_get_advertising_period_metrics", fake_ads)

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
