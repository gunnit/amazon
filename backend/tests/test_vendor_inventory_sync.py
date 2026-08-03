from datetime import date
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
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
sys.modules.setdefault("app.models.amazon_account", amazon_account_module)


def _stub_model_module(module_name: str, *class_names: str) -> None:
    module = types.ModuleType(module_name)
    for class_name in class_names:
        setattr(module, class_name, type(class_name, (), {}))
    sys.modules.setdefault(module_name, module)


_stub_model_module(
    "app.models.advertising",
    "AdvertisingCampaign",
    "AdvertisingMetrics",
    "AdvertisingMetricsByAsin",
)
_stub_model_module("app.models.order", "Order", "OrderItem")
_stub_model_module("app.models.returns_data", "ReturnData")
_stub_model_module("app.models.sales_data", "SalesData")
_stub_model_module("app.models.inventory", "InventoryData")
_stub_model_module("app.models.product", "BSRHistory", "Product")

exceptions_module = types.ModuleType("app.core.exceptions")
exceptions_module.AmazonAPIError = type("AmazonAPIError", (Exception,), {})
sys.modules.setdefault("app.core.exceptions", exceptions_module)

DATA_EXTRACTION_SPEC = spec_from_file_location("vendor_inventory_under_test", DATA_EXTRACTION_PATH)
DATA_EXTRACTION_MODULE = module_from_spec(DATA_EXTRACTION_SPEC)
assert DATA_EXTRACTION_SPEC is not None and DATA_EXTRACTION_SPEC.loader is not None
DATA_EXTRACTION_SPEC.loader.exec_module(DATA_EXTRACTION_MODULE)


class FakeDb:
    def __init__(self):
        self.flushes = 0

    async def flush(self):
        self.flushes += 1


@pytest.mark.parametrize(
    "today, expected_start, expected_end",
    [
        # Saturday: last COMPLETE week ends the previous Saturday.
        (date(2026, 8, 1), date(2026, 7, 19), date(2026, 7, 25)),
        # Sunday through Friday: week ending the most recent Saturday.
        (date(2026, 8, 2), date(2026, 7, 26), date(2026, 8, 1)),
        (date(2026, 8, 3), date(2026, 7, 26), date(2026, 8, 1)),
        (date(2026, 8, 7), date(2026, 7, 26), date(2026, 8, 1)),
    ],
)
def test_vendor_inventory_week_is_sunday_to_saturday(today, expected_start, expected_end):
    start, end = DATA_EXTRACTION_MODULE.vendor_inventory_week(today)
    assert (start, end) == (expected_start, expected_end)
    assert start.weekday() == 6  # Sunday
    assert end.weekday() == 5  # Saturday
    assert (end - start).days == 6
    assert end < today


@pytest.mark.asyncio
async def test_sync_vendor_inventory_maps_report_rows(monkeypatch):
    db = FakeDb()
    service = DATA_EXTRACTION_MODULE.DataExtractionService(db)
    upserted = []

    async def fake_upsert(values):
        upserted.append(values.copy())

    payload = {
        "reportSpecification": {"reportType": "GET_VENDOR_INVENTORY_REPORT"},
        "inventoryByAsin": [
            {
                "asin": "B001VEND",
                "sellableOnHandInventoryUnits": 120,
                "unsellableOnHandInventoryUnits": 5,
                "openPurchaseOrderUnits": 40,
            },
            {
                "asin": "B002VEND",
                "sellableOnHandInventoryUnits": None,
            },
            {"asin": ""},
        ],
    }
    windows = []

    fake_client = SimpleNamespace(
        get_vendor_inventory_report=lambda start, end: (windows.append((start, end)), payload)[1],
    )
    monkeypatch.setattr(service, "_create_sp_api_client", lambda _acc, _org=None: fake_client)
    monkeypatch.setattr(service, "_upsert_inventory_record", fake_upsert)

    account = SimpleNamespace(id=uuid4(), account_name="Dialcos")
    count = await service.sync_vendor_inventory(account, SimpleNamespace(id=uuid4()))

    assert count == 2
    assert db.flushes == 1
    start, end = windows[0]
    assert start.weekday() == 6 and end.weekday() == 5

    first = upserted[0]
    assert first["asin"] == "B001VEND"
    assert first["snapshot_date"] == end
    assert first["afn_fulfillable_quantity"] == 120
    assert first["afn_reserved_quantity"] == 5
    assert first["afn_inbound_working_quantity"] == 40
    assert first["afn_total_quantity"] == 125
    assert first["mfn_fulfillable_quantity"] == 0

    second = upserted[1]
    assert second["asin"] == "B002VEND"
    assert second["afn_fulfillable_quantity"] == 0
    assert second["afn_total_quantity"] == 0
