from datetime import date
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
import types
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy.sql import column, table


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

config_stub = types.ModuleType("app.config")
config_stub.settings = types.SimpleNamespace(ANTHROPIC_API_KEY=None)
sys.modules["app.config"] = config_stub

data_extraction_stub = types.ModuleType("app.services.data_extraction")
data_extraction_stub.DAILY_TOTAL_ASIN = "__DAILY_TOTAL__"
sys.modules["app.services.data_extraction"] = data_extraction_stub

analytics_service_stub = types.ModuleType("app.services.analytics_service")
analytics_service_stub.AnalyticsService = type("AnalyticsService", (), {})
sys.modules["app.services.analytics_service"] = analytics_service_stub

ai_analysis_stub = types.ModuleType("app.services.ai_analysis_service")
ai_analysis_stub.ProductTrendInsightsAnalysisService = type(
    "ProductTrendInsightsAnalysisService", (), {}
)
sys.modules["app.services.ai_analysis_service"] = ai_analysis_stub

product_trends_stub = types.ModuleType("app.services.product_trends_service")
product_trends_stub.ProductTrendsService = type("ProductTrendsService", (), {})
product_trends_stub.build_rule_based_insights = lambda *args, **kwargs: []
sys.modules["app.services.product_trends_service"] = product_trends_stub


class TableStub:
    def __init__(self, table_name: str, columns: list[str]):
        self._table = table(table_name, *(column(name) for name in columns))
        for name in columns:
            setattr(self, name, self._table.c[name])

    def __clause_element__(self):
        return self._table


def _stub_model_module(module_name: str, attr_name: str, table_name: str, columns: list[str]) -> None:
    module = types.ModuleType(module_name)
    setattr(module, attr_name, TableStub(table_name, columns))
    sys.modules[module_name] = module


_stub_model_module(
    "app.models.amazon_account",
    "AmazonAccount",
    "amazon_accounts",
    ["id", "organization_id", "is_active"],
)
_stub_model_module(
    "app.models.order",
    "Order",
    "orders",
    ["id", "account_id", "purchase_date"],
)

order_module = sys.modules["app.models.order"]
setattr(order_module, "OrderItem", TableStub("order_items", ["order_id", "asin", "quantity"]))

_stub_model_module(
    "app.models.returns_data",
    "ReturnData",
    "returns_data",
    [
        "account_id",
        "amazon_order_id",
        "asin",
        "sku",
        "return_date",
        "quantity",
        "reason",
        "disposition",
        "detailed_disposition",
    ],
)
_stub_model_module(
    "app.models.sales_data",
    "SalesData",
    "sales_data",
    ["account_id", "asin", "date", "ordered_product_sales", "units_ordered", "total_order_items", "currency"],
)

product_module = types.ModuleType("app.models.product")
product_module.Product = TableStub("products", ["account_id", "asin", "category", "title"])
product_module.BSRHistory = TableStub("bsr_history", ["id"])
sys.modules["app.models.product"] = product_module

advertising_module = types.ModuleType("app.models.advertising")
advertising_module.AdvertisingCampaign = TableStub("advertising_campaigns", ["id", "account_id"])
advertising_module.AdvertisingMetrics = TableStub(
    "advertising_metrics",
    ["campaign_id", "cost", "attributed_sales_7d", "impressions", "clicks", "date"],
)
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


class FakeResult:
    def __init__(self, *, rows=None, scalar_value=None):
        self._rows = rows or []
        self._scalar_value = scalar_value

    def all(self):
        return self._rows

    def scalar(self):
        return self._scalar_value


class FakeDb:
    def __init__(self, responses):
        self._responses = list(responses)
        self.queries = []

    async def execute(self, query):
        self.queries.append(query)
        return self._responses.pop(0)


@pytest.mark.asyncio
async def test_returns_endpoint_aggregates_counts_and_rates():
    db = FakeDb([
        FakeResult(rows=[
            SimpleNamespace(period_date=date(2026, 4, 1), returned_units=4),
            SimpleNamespace(period_date=date(2026, 4, 2), returned_units=2),
        ]),
        FakeResult(rows=[
            SimpleNamespace(reason="Damaged", quantity=4),
            SimpleNamespace(reason="No Longer Needed", quantity=2),
        ]),
        FakeResult(rows=[
            SimpleNamespace(asin="B001TEST", sku="SKU-1", quantity_returned=4),
            SimpleNamespace(asin="B002TEST", sku="SKU-2", quantity_returned=2),
        ]),
        FakeResult(scalar_value=120),
        FakeResult(rows=[
            SimpleNamespace(period_date=date(2026, 4, 1), ordered_units=100),
            SimpleNamespace(period_date=date(2026, 4, 2), ordered_units=20),
        ]),
        FakeResult(rows=[
            SimpleNamespace(asin="B001TEST", ordered_units=50),
            SimpleNamespace(asin="B002TEST", ordered_units=70),
        ]),
        FakeResult(rows=[
            SimpleNamespace(asin="B001TEST", reason="Damaged", disposition="SELLABLE", quantity=4),
            SimpleNamespace(asin="B002TEST", reason="No Longer Needed", disposition="DEFECTIVE", quantity=2),
        ]),
    ])

    response = await analytics.get_returns_analysis(
        current_user=None,
        organization=SimpleNamespace(id=uuid4()),
        db=db,
        account_id=uuid4(),
        account_ids=None,
        date_from=date(2026, 4, 1),
        date_to=date(2026, 4, 2),
        asin=None,
        limit=10,
    )

    assert response.summary.total_returns == 6
    assert response.summary.total_ordered_units == 120
    assert response.summary.return_rate_available is True
    assert response.summary.return_rate == 5.0
    assert response.summary.top_reason == "Damaged"
    assert response.summary.unique_asins == 2
    assert response.return_rate_over_time[0].return_rate == 4.0
    assert response.return_rate_over_time[1].return_rate == 10.0
    assert response.reason_breakdown[0].share_percent == pytest.approx(66.6667, rel=1e-4)
    assert response.top_asins_by_returns[0].asin == "B001TEST"
    assert response.top_asins_by_returns[0].primary_reason == "Damaged"
    assert response.top_asins_by_returns[0].return_rate == 8.0
    assert response.top_asins_by_return_rate[0].asin == "B001TEST"


@pytest.mark.asyncio
async def test_returns_endpoint_gracefully_falls_back_without_order_data():
    db = FakeDb([
        FakeResult(rows=[
            SimpleNamespace(period_date=date(2026, 4, 3), returned_units=3),
        ]),
        FakeResult(rows=[
            SimpleNamespace(reason="Unknown", quantity=3),
        ]),
        FakeResult(rows=[
            SimpleNamespace(asin="B009TEST", sku="SKU-9", quantity_returned=3),
        ]),
        FakeResult(scalar_value=0),
        FakeResult(rows=[]),
        FakeResult(rows=[]),
        FakeResult(rows=[
            SimpleNamespace(asin="B009TEST", reason="Unknown", disposition="SELLABLE", quantity=3),
        ]),
    ])

    response = await analytics.get_returns_analysis(
        current_user=None,
        organization=SimpleNamespace(id=uuid4()),
        db=db,
        account_id=None,
        account_ids=[uuid4()],
        date_from=date(2026, 4, 3),
        date_to=date(2026, 4, 3),
        asin=None,
        limit=10,
    )

    assert response.summary.total_returns == 3
    assert response.summary.total_ordered_units == 0
    assert response.summary.return_rate_available is False
    assert response.summary.return_rate is None
    assert response.return_rate_over_time[0].return_rate is None
    assert response.top_asins_by_returns[0].return_rate is None
    assert response.top_asins_by_return_rate == []
