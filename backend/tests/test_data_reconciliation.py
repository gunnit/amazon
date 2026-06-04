"""Tests covering data-reconciliation fixes:

* AnalyticsService no longer double-counts DAILY_TOTAL_ASIN + per-ASIN rows.
* Vendor PO fallback raises a structured warning so dashboards can flag it.
* Dashboard/comparison/trend math behaves correctly across a full 2025 range.
"""
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
DATA_EXTRACTION_PATH = ROOT / "app" / "services" / "data_extraction.py"


class _TableStub:
    """SQLAlchemy-friendly column proxy used by analytics_service queries."""

    def __init__(self, table_name: str, columns: list[str]):
        self._table = table(table_name, *(column(name) for name in columns))
        for name in columns:
            setattr(self, name, self._table.c[name])

    def __clause_element__(self):
        return self._table


def _ensure_package(name: str, path: Path) -> None:
    module = types.ModuleType(name)
    module.__path__ = [str(path)]
    sys.modules.setdefault(name, module)


_ensure_package("app", ROOT / "app")
_ensure_package("app.models", ROOT / "app" / "models")
_ensure_package("app.services", ROOT / "app" / "services")
_ensure_package("app.core", ROOT / "app" / "core")


def _stub_model_module(module_name: str, *class_names: str) -> None:
    module = types.ModuleType(module_name)
    for class_name in class_names:
        setattr(module, class_name, type(class_name, (), {}))
    sys.modules[module_name] = module


def _stub_table_module(module_name: str, **tables: list[str]) -> types.ModuleType:
    module = types.ModuleType(module_name)
    for class_name, columns in tables.items():
        setattr(module, class_name, _TableStub(class_name.lower(), columns))
    sys.modules[module_name] = module
    return module


class _AccountType:
    SELLER = "seller"
    VENDOR = "vendor"


class _SyncStatus:
    PENDING = "pending"
    SYNCING = "syncing"
    SUCCESS = "success"
    ERROR = "error"


amazon_account_module = types.ModuleType("app.models.amazon_account")
amazon_account_module.AccountType = _AccountType
amazon_account_module.SyncStatus = _SyncStatus
amazon_account_module.AmazonAccount = type("AmazonAccount", (), {})
sys.modules["app.models.amazon_account"] = amazon_account_module
setattr(sys.modules["app.models"], "amazon_account", amazon_account_module)

_stub_table_module(
    "app.models.advertising",
    AdvertisingCampaign=["id", "account_id"],
    AdvertisingMetrics=[
        "campaign_id",
        "cost",
        "attributed_sales_7d",
        "impressions",
        "clicks",
        "date",
    ],
    AdvertisingMetricsByAsin=[
        "account_id",
        "asin",
        "cost",
        "attributed_sales_7d",
        "date",
    ],
)
_stub_model_module("app.models.order", "Order", "OrderItem")
_stub_table_module(
    "app.models.returns_data",
    ReturnData=["account_id", "asin", "return_date", "quantity"],
)
_stub_table_module(
    "app.models.sales_data",
    SalesData=[
        "account_id",
        "asin",
        "date",
        "ordered_product_sales",
        "units_ordered",
        "total_order_items",
        "currency",
    ],
)
_stub_model_module("app.models.inventory", "InventoryData")
_stub_table_module(
    "app.models.product",
    Product=["account_id", "asin", "category", "title"],
    BSRHistory=["id"],
)

exceptions_module = types.ModuleType("app.core.exceptions")
exceptions_module.AmazonAPIError = type("AmazonAPIError", (Exception,), {})
sys.modules["app.core.exceptions"] = exceptions_module

DATA_EXTRACTION_SPEC = spec_from_file_location(
    "data_extraction_under_test_reconciliation", DATA_EXTRACTION_PATH
)
DATA_EXTRACTION_MODULE = module_from_spec(DATA_EXTRACTION_SPEC)
assert DATA_EXTRACTION_SPEC is not None and DATA_EXTRACTION_SPEC.loader is not None
DATA_EXTRACTION_SPEC.loader.exec_module(DATA_EXTRACTION_MODULE)
sys.modules["app.models.amazon_account"].AccountType = _AccountType


class FakeDb:
    """Minimal AsyncSession stand-in supporting flush() and execute()."""

    def __init__(self):
        self.flushes = 0
        self.executed = []

    async def flush(self):
        self.flushes += 1

    async def execute(self, statement):
        # Vendor-sales sync issues DELETE statements before repopulating a
        # window; the result is never inspected, so a no-op result is enough.
        self.executed.append(statement)
        return _FakeResult()


def test_vendor_sales_fallback_warning_constants_are_exposed():
    assert DATA_EXTRACTION_MODULE.VENDOR_SALES_FALLBACK_WARNING == "VENDOR_SALES_FROM_PO_FALLBACK"
    assert "estimated" in DATA_EXTRACTION_MODULE.VENDOR_SALES_FALLBACK_MESSAGE.lower()


@pytest.mark.asyncio
async def test_vendor_sales_sets_fallback_flag_when_diagnostic_unavailable(monkeypatch):
    """When the Vendor Sales Diagnostic report fails, the service must flag the
    PO fallback so sync_account can surface a warning. Without this, dashboards
    would silently treat purchase-order netCost as Vendor Central shipped revenue.
    """
    db = FakeDb()
    service = DATA_EXTRACTION_MODULE.DataExtractionService(db)
    upserted = []

    async def fake_upsert(values):
        upserted.append(values.copy())

    diagnostic_error = DATA_EXTRACTION_MODULE.AmazonAPIError("not available")

    fake_client = SimpleNamespace(
        get_vendor_sales_report=lambda _start, _end: (_ for _ in ()).throw(diagnostic_error),
        get_vendor_purchase_orders=lambda _start, _end: [
            {
                "orderDetails": {
                    "purchaseOrderDate": "2025-03-01",
                    "items": [
                        {
                            "amazonProductIdentifier": "B0VENDOR1",
                            "vendorProductIdentifier": "VEN-1",
                            "netCost": {"amount": "10.50", "currencyCode": "EUR"},
                            "orderedQuantity": {"amount": 4},
                        }
                    ],
                }
            }
        ],
    )

    monkeypatch.setattr(service, "_create_sp_api_client", lambda *_args, **_kwargs: fake_client)
    monkeypatch.setattr(service, "_upsert_sales_record", fake_upsert)

    account = SimpleNamespace(id=uuid4(), account_name="Vendor Demo")
    count = await service.sync_vendor_sales_data(
        account,
        organization=None,
        start_date=date(2025, 3, 1),
        end_date=date(2025, 3, 31),
    )

    assert count >= 1
    assert service.vendor_sales_used_po_fallback is True
    # Daily-total sentinel must still be written so the dashboard renders,
    # but only via the warning-decorated fallback path.
    sentinels = [row for row in upserted if row["asin"] == DATA_EXTRACTION_MODULE.DAILY_TOTAL_ASIN]
    assert sentinels, "Expected at least one DAILY_TOTAL sentinel row from fallback"


@pytest.mark.asyncio
async def test_vendor_sales_clears_fallback_flag_when_diagnostic_succeeds(monkeypatch):
    """A successful diagnostic-report sync must clear the previous fallback warning,
    otherwise stale fallback warnings could persist after the underlying issue heals.
    """
    db = FakeDb()
    service = DATA_EXTRACTION_MODULE.DataExtractionService(db)
    service.vendor_sales_used_po_fallback = True  # simulate stale state

    fake_client = SimpleNamespace(
        get_vendor_sales_report=lambda _start, _end: {
            "salesByAsin": [
                {
                    "asin": "B0VENDOR1",
                    "startDate": "2025-03-01",
                    "orderedRevenue": {"amount": "100.00", "currencyCode": "EUR"},
                    "orderedUnits": 5,
                }
            ]
        },
        get_vendor_purchase_orders=lambda _start, _end: [],
    )

    monkeypatch.setattr(service, "_create_sp_api_client", lambda *_args, **_kwargs: fake_client)

    async def fake_upsert(_values):
        return None

    monkeypatch.setattr(service, "_upsert_sales_record", fake_upsert)

    # A full settled calendar month must be in range for the diagnostic report
    # to run; otherwise the service short-circuits to the PO fallback.
    await service.sync_vendor_sales_data(
        SimpleNamespace(id=uuid4(), account_name="Vendor Demo"),
        organization=None,
        start_date=date(2025, 3, 1),
        end_date=date(2025, 3, 31),
    )

    assert service.vendor_sales_used_po_fallback is False


# ---------------------------------------------------------------------------
# AnalyticsService double-counting fix + 2025 range
# ---------------------------------------------------------------------------


class _FakeRow:
    """Cheap row stand-in compatible with .revenue / .units / .orders / .date."""

    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


class _FakeResult:
    def __init__(self, *, one=None, rows=None, scalar=None):
        self._one = one
        self._rows = rows or []
        self._scalar = scalar

    def one(self):
        return self._one

    def all(self):
        return self._rows

    def scalar(self):
        return self._scalar


class _FakeAnalyticsDb:
    """Records execute() invocations and replays canned results in order."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.queries = []

    async def execute(self, query):
        self.queries.append(query)
        return self._responses.pop(0)


def _load_analytics_service():
    """Import AnalyticsService for behavioral tests.

    Other test files in this suite stub `app.services.product_trends_service`
    and friends; we sidestep those by loading the module directly here so the
    real DAILY_TOTAL_ASIN-aware queries are exercised.
    """
    sys.modules.setdefault("app.services.data_extraction", DATA_EXTRACTION_MODULE)

    analytics_service_path = ROOT / "app" / "services" / "analytics_service.py"
    spec = spec_from_file_location(
        "analytics_service_under_test_reconciliation", analytics_service_path
    )
    module = module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.mark.asyncio
async def test_analytics_service_period_metrics_filters_daily_total_sentinel():
    """`_get_period_metrics` must read totals from DAILY_TOTAL_ASIN rows and
    count active ASINs from real per-ASIN rows. If the SQL conflates them,
    revenue/units double-count and the sentinel itself appears as a product.
    """
    analytics_module = _load_analytics_service()
    AnalyticsService = analytics_module.AnalyticsService

    db = _FakeAnalyticsDb(
        [
            _FakeResult(one=_FakeRow(revenue=4321.0, units=200, orders=125)),
            _FakeResult(scalar=42),
        ]
    )
    service = AnalyticsService(db)

    result = await service._get_period_metrics(
        account_ids=[uuid4()],
        start_date=date(2025, 1, 1),
        end_date=date(2025, 12, 31),
    )

    assert result["revenue"] == 4321.0
    assert result["units"] == 200
    assert result["orders"] == 125
    assert result["active_asins"] == 42
    assert result["average_order_value"] == pytest.approx(4321.0 / 125)

    # Verify both queries were issued and that the totals query filters by the
    # daily-total sentinel while the active-ASIN query filters it out.
    rendered_queries = [str(q) for q in db.queries]
    assert len(rendered_queries) == 2
    assert "salesdata.asin =" in rendered_queries[0]
    assert "salesdata.asin !=" in rendered_queries[1]


@pytest.mark.asyncio
async def test_analytics_service_dashboard_kpis_handles_full_2025_range():
    """Sanity-check the full-year 2025 window that drives the dashboard."""
    analytics_module = _load_analytics_service()
    AnalyticsService = analytics_module.AnalyticsService

    db = _FakeAnalyticsDb(
        [
            _FakeResult(one=_FakeRow(revenue=120000.0, units=4800, orders=3200)),
            _FakeResult(scalar=180),
            _FakeResult(one=_FakeRow(revenue=80000.0, units=3200, orders=2400)),
            _FakeResult(scalar=150),
        ]
    )
    service = AnalyticsService(db)

    snapshot = await service.compute_dashboard_kpis(
        account_ids=[uuid4()],
        start_date=date(2025, 1, 1),
        end_date=date(2025, 12, 31),
    )

    assert snapshot["current"]["revenue"] == 120000.0
    assert snapshot["previous"]["revenue"] == 80000.0
    # +50% revenue growth period over period.
    assert snapshot["changes"]["revenue"]["percent"] == 50.0
    assert snapshot["changes"]["revenue"]["trend"] == "up"


@pytest.mark.asyncio
async def test_analytics_service_compute_trends_uses_daily_total_for_2025_range():
    """Trends for a 2025 range must read DAILY_TOTAL_ASIN rows so a few high-
    revenue days don't get inflated by adding per-ASIN rows on top.
    """
    analytics_module = _load_analytics_service()
    AnalyticsService = analytics_module.AnalyticsService

    db = _FakeAnalyticsDb(
        [
            _FakeResult(
                rows=[
                    _FakeRow(date=date(2025, 1, 1), value=1000.0),
                    _FakeRow(date=date(2025, 1, 2), value=1500.0),
                ]
            )
        ]
    )
    service = AnalyticsService(db)

    points = await service.compute_trends(
        account_ids=[uuid4()],
        metric="revenue",
        start_date=date(2025, 1, 1),
        end_date=date(2025, 12, 31),
    )

    assert points == [
        {"date": "2025-01-01", "value": 1000.0},
        {"date": "2025-01-02", "value": 1500.0},
    ]
    assert "salesdata.asin =" in str(db.queries[0])


@pytest.mark.asyncio
async def test_analytics_service_top_products_excludes_daily_total_sentinel():
    """`get_top_products` must never return DAILY_TOTAL_ASIN as a product."""
    analytics_module = _load_analytics_service()
    AnalyticsService = analytics_module.AnalyticsService

    class _NoneScalar:
        def scalar_one_or_none(self):
            return None

    responses = [
        _FakeResult(
            rows=[
                _FakeRow(asin="B00REAL1", revenue=900.0, units=60, orders=50),
                _FakeRow(asin="B00REAL2", revenue=600.0, units=40, orders=35),
            ]
        ),
        _FakeResult(rows=[]),
    ]

    db = _FakeAnalyticsDb(responses)

    async def execute(query):
        db.queries.append(query)
        if db._responses:
            return db._responses.pop(0)
        return _NoneScalar()

    db.execute = execute  # type: ignore[assignment]

    service = AnalyticsService(db)
    products = await service.get_top_products(
        account_ids=[uuid4()],
        start_date=date(2025, 1, 1),
        end_date=date(2025, 12, 31),
        sort_by="revenue",
        limit=10,
    )

    asins = {item["asin"] for item in products}
    assert asins == {"B00REAL1", "B00REAL2"}
    assert DATA_EXTRACTION_MODULE.DAILY_TOTAL_ASIN not in asins
    assert "salesdata.asin !=" in str(db.queries[0])
