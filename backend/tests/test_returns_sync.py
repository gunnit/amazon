from datetime import date, datetime, timedelta
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import builtins
import sys
import types
from types import SimpleNamespace
from uuid import uuid4

import pytest


ROOT = Path(__file__).resolve().parents[1]
DATA_EXTRACTION_PATH = ROOT / "app" / "services" / "data_extraction.py"


def _ensure_package(name: str, path: Path) -> None:
    module = types.ModuleType(name)
    module.__path__ = [str(path)]
    sys.modules.setdefault(name, module)


_ensure_package("app", ROOT / "app")
_ensure_package("app.models", ROOT / "app" / "models")
_ensure_package("app.services", ROOT / "app" / "services")
_ensure_package("app.core", ROOT / "app" / "core")

amazon_account_module = types.ModuleType("app.models.amazon_account")


class AccountType:
    SELLER = "seller"
    VENDOR = "vendor"


class SyncStatus:
    PENDING = "pending"
    SYNCING = "syncing"
    SUCCESS = "success"
    ERROR = "error"


amazon_account_module.AccountType = AccountType
amazon_account_module.SyncStatus = SyncStatus
amazon_account_module.AmazonAccount = type("AmazonAccount", (), {})
sys.modules["app.models.amazon_account"] = amazon_account_module
setattr(sys.modules["app.models"], "amazon_account", amazon_account_module)


def _stub_model_module(module_name: str, *class_names: str) -> None:
    module = types.ModuleType(module_name)
    for class_name in class_names:
        setattr(module, class_name, type(class_name, (), {}))
    sys.modules[module_name] = module


_stub_model_module("app.models.advertising", "AdvertisingCampaign", "AdvertisingMetrics")
_stub_model_module("app.models.order", "Order", "OrderItem")
_stub_model_module("app.models.returns_data", "ReturnData")
_stub_model_module("app.models.sales_data", "SalesData")
_stub_model_module("app.models.inventory", "InventoryData")
_stub_model_module("app.models.product", "BSRHistory", "Product")

exceptions_module = types.ModuleType("app.core.exceptions")
exceptions_module.AmazonAPIError = type("AmazonAPIError", (Exception,), {})
sys.modules["app.core.exceptions"] = exceptions_module

DATA_EXTRACTION_SPEC = spec_from_file_location("data_extraction_under_test", DATA_EXTRACTION_PATH)
DATA_EXTRACTION_MODULE = module_from_spec(DATA_EXTRACTION_SPEC)
assert DATA_EXTRACTION_SPEC is not None and DATA_EXTRACTION_SPEC.loader is not None
DATA_EXTRACTION_SPEC.loader.exec_module(DATA_EXTRACTION_MODULE)
sys.modules["app.models.amazon_account"].AccountType = AccountType


class FakeDb:
    def __init__(self):
        self.flushes = 0

    async def flush(self):
        self.flushes += 1


class FakeLookupResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class FakeSyncDb(FakeDb):
    def __init__(self, account):
        super().__init__()
        self.account = account
        self.execute_calls = 0

    async def execute(self, _query):
        self.execute_calls += 1
        return FakeLookupResult(self.account)


@pytest.mark.asyncio
async def test_sync_returns_dedupes_rows_and_skips_invalid_quantities(monkeypatch):
    db = FakeDb()
    service = DATA_EXTRACTION_MODULE.DataExtractionService(db)
    upserted_rows = []

    async def fake_upsert(values):
        upserted_rows.append(values.copy())

    async def fake_touch(_account):
        return None

    async def fake_load_organization(_account):
        return SimpleNamespace(id=uuid4())

    fake_client = SimpleNamespace(
        fetch_returns_report=lambda: [
            {
                "amazon_order_id": "ORDER-1",
                "asin": "b001test",
                "sku": "SKU-1",
                "return_date": date(2026, 4, 1),
                "quantity": 2,
                "reason": "Damaged",
                "disposition": "SELLABLE",
                "detailed_disposition": "Customer Damaged",
            },
            {
                "amazon_order_id": "ORDER-1",
                "asin": "B001TEST",
                "sku": "SKU-1",
                "return_date": date(2026, 4, 1),
                "quantity": 2,
                "reason": "Damaged",
                "disposition": "SELLABLE",
                "detailed_disposition": "Customer Damaged",
            },
            {
                "amazon_order_id": None,
                "asin": None,
                "sku": "SKU-2",
                "return_date": date(2026, 4, 2),
                "quantity": 1,
                "reason": "No Longer Needed",
                "disposition": "DEFECTIVE",
                "detailed_disposition": "Warehouse Damaged",
            },
            {
                "amazon_order_id": "ORDER-3",
                "asin": "B009ZERO",
                "sku": "SKU-3",
                "return_date": date(2026, 4, 3),
                "quantity": 0,
                "reason": "Damaged",
                "disposition": "DEFECTIVE",
                "detailed_disposition": "Warehouse Damaged",
            },
        ]
    )

    monkeypatch.setattr(service, "_create_sp_api_client", lambda *_args, **_kwargs: fake_client)
    monkeypatch.setattr(service, "_upsert_return_record", fake_upsert)
    monkeypatch.setattr(service, "_touch_sync", fake_touch)

    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "app.models.amazon_account" and "AccountType" in fromlist:
            return SimpleNamespace(AccountType=AccountType)
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    account = SimpleNamespace(
        id=uuid4(),
        account_name="Test Seller",
        account_type=AccountType.SELLER,
    )

    synced_count = await service.sync_returns(account)

    assert synced_count == 2
    assert len(upserted_rows) == 2
    assert {row["asin"] for row in upserted_rows} == {"B001TEST", None}
    assert db.flushes == 1


def test_resolve_orders_sync_window_uses_previous_started_at_when_available():
    service = DATA_EXTRACTION_MODULE.DataExtractionService(FakeDb())
    previous_started_at = datetime(2026, 4, 13, 8, 0, 0)
    previous_succeeded_at = datetime(2026, 4, 13, 8, 20, 0)

    created_after, created_before = service._resolve_orders_sync_window(
        SimpleNamespace(
            last_sync_started_at=None,
            last_sync_succeeded_at=None,
            last_sync_at=None,
        ),
        last_sync_started_at=previous_started_at,
        last_sync_succeeded_at=previous_succeeded_at,
    )

    assert created_after == previous_started_at
    assert created_before > created_after


def test_resolve_orders_sync_window_adds_overlap_when_only_completion_is_safe():
    service = DATA_EXTRACTION_MODULE.DataExtractionService(FakeDb())
    previous_succeeded_at = datetime.utcnow() - timedelta(hours=2)
    current_attempt_started_at = previous_succeeded_at + timedelta(minutes=45)

    created_after, created_before = service._resolve_orders_sync_window(
        SimpleNamespace(
            last_sync_started_at=None,
            last_sync_succeeded_at=None,
            last_sync_at=None,
        ),
        last_sync_started_at=current_attempt_started_at,
        last_sync_succeeded_at=previous_succeeded_at,
    )

    assert created_after == previous_succeeded_at - timedelta(minutes=30)
    assert created_before > created_after


@pytest.mark.asyncio
async def test_sync_account_continues_when_inventory_step_fails(monkeypatch):
    account = SimpleNamespace(
        id=uuid4(),
        account_name="Test Seller",
        account_type=AccountType.SELLER,
        last_sync_started_at=None,
        last_sync_succeeded_at=None,
        last_sync_at=None,
        last_sync_attempt_at=None,
        last_sync_heartbeat_at=None,
        sync_status=SyncStatus.PENDING,
        sync_error_message=None,
        sync_error_code=None,
        sync_error_kind=None,
    )
    db = FakeSyncDb(account)
    service = DATA_EXTRACTION_MODULE.DataExtractionService(db)
    call_order = []

    class _FakeSelect:
        def where(self, *_args, **_kwargs):
            return self

    async def fake_touch(_account):
        return None

    async def fake_load_organization(_account):
        return SimpleNamespace(id=uuid4())

    async def fake_sales(_account, _organization):
        call_order.append("sales")
        return 5

    class InventoryUnavailableError(Exception):
        def __init__(self):
            self.message = "Inventory data unavailable for this marketplace"
            self.error_code = "INVENTORY_NOT_AVAILABLE"
            super().__init__(self.message)

    async def fake_inventory(_account, _organization):
        call_order.append("inventory")
        raise InventoryUnavailableError()

    async def fake_orders(_account, _organization, **_kwargs):
        call_order.append("orders")
        return 7

    async def fake_returns(_account, _organization):
        call_order.append("returns")
        return 3

    async def fake_products(_account, _organization):
        call_order.append("products")
        return 11

    async def fake_advertising(_account, _organization):
        call_order.append("advertising")
        return 13

    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "app.models.amazon_account" and "AccountType" in fromlist:
            return SimpleNamespace(AccountType=AccountType)
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    monkeypatch.setattr(DATA_EXTRACTION_MODULE, "select", lambda *_args, **_kwargs: _FakeSelect())
    monkeypatch.setattr(DATA_EXTRACTION_MODULE, "AmazonAccount", SimpleNamespace(id=object()))
    monkeypatch.setattr(service, "_load_organization", fake_load_organization)
    monkeypatch.setattr(service, "_create_sp_api_client", lambda *_args, **_kwargs: SimpleNamespace(smoke_test=lambda: None))
    monkeypatch.setattr(service, "_touch_sync", fake_touch)
    monkeypatch.setattr(service, "sync_sales_data", fake_sales)
    monkeypatch.setattr(service, "sync_inventory", fake_inventory)
    monkeypatch.setattr(service, "sync_orders", fake_orders)
    monkeypatch.setattr(service, "sync_returns", fake_returns)
    monkeypatch.setattr(service, "sync_products", fake_products)
    monkeypatch.setattr(service, "sync_advertising", fake_advertising)

    result = await service.sync_account(account.id)

    assert db.execute_calls == 1
    assert result["status"] == "success"
    assert result["sales_records"] == 5
    assert result["inventory_records"] == 0
    assert result["order_records"] == 7
    assert result["return_records"] == 3
    assert result["products"] == 11
    assert result["advertising_records"] == 13
    assert len(result["warnings"]) == 1
    assert "Inventory sync warning" in result["warnings"][0]
    assert call_order == ["sales", "inventory", "orders", "returns", "advertising", "products"]
    assert account.sync_status == SyncStatus.SUCCESS
    assert account.sync_error_kind == "warning"
    assert account.sync_error_code == "INVENTORY_NOT_AVAILABLE"
    assert "Inventory sync warning" in account.sync_error_message
    assert account.last_sync_at is not None
    assert account.last_sync_succeeded_at is not None
