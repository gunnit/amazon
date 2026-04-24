from enum import Enum
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
import types
from types import SimpleNamespace
from uuid import uuid4

import pytest


ROOT = Path(__file__).resolve().parents[1]
ACCOUNTS_PATH = ROOT / "app" / "api" / "v1" / "accounts.py"
SCHEMA_PATH = ROOT / "app" / "schemas" / "account.py"


def _ensure_package(name: str, path: Path) -> None:
    module = types.ModuleType(name)
    module.__path__ = [str(path)]
    sys.modules.setdefault(name, module)


_ensure_package("app", ROOT / "app")
_ensure_package("app.api", ROOT / "app" / "api")
_ensure_package("app.api.v1", ROOT / "app" / "api" / "v1")
_ensure_package("app.schemas", ROOT / "app" / "schemas")
_ensure_package("app.models", ROOT / "app" / "models")
_ensure_package("app.core", ROOT / "app" / "core")
_ensure_package("app.services", ROOT / "app" / "services")

deps_stub = types.ModuleType("app.api.deps")
deps_stub.CurrentUser = object
deps_stub.CurrentOrganization = object
deps_stub.DbSession = object
sys.modules["app.api.deps"] = deps_stub

security_stub = types.ModuleType("app.core.security")
security_stub.encrypt_value = lambda value: value
security_stub.decrypt_value = lambda value: value
sys.modules["app.core.security"] = security_stub

exceptions_stub = types.ModuleType("app.core.exceptions")
exceptions_stub.AmazonAPIError = type("AmazonAPIError", (Exception,), {})
sys.modules["app.core.exceptions"] = exceptions_stub

data_extraction_stub = types.ModuleType("app.services.data_extraction")
data_extraction_stub.DAILY_TOTAL_ASIN = "__DAILY_TOTAL__"
data_extraction_stub.DataExtractionService = type("DataExtractionService", (), {})
sys.modules["app.services.data_extraction"] = data_extraction_stub


class StubAccountType(str, Enum):
    SELLER = "seller"
    VENDOR = "vendor"


class StubSyncStatus(str, Enum):
    PENDING = "pending"
    SYNCING = "syncing"
    SUCCESS = "success"
    ERROR = "error"


amazon_account_module = types.ModuleType("app.models.amazon_account")
amazon_account_module.AccountType = StubAccountType
amazon_account_module.SyncStatus = StubSyncStatus
amazon_account_module.AmazonAccount = type("AmazonAccount", (), {})
sys.modules["app.models.amazon_account"] = amazon_account_module

product_module = types.ModuleType("app.models.product")
product_module.Product = type("Product", (), {})
sys.modules["app.models.product"] = product_module

sales_data_module = types.ModuleType("app.models.sales_data")
sales_data_module.SalesData = type("SalesData", (), {})
sys.modules["app.models.sales_data"] = sales_data_module

schema_spec = spec_from_file_location("app.schemas.account", SCHEMA_PATH)
schema_module = module_from_spec(schema_spec)
assert schema_spec is not None and schema_spec.loader is not None
sys.modules["app.schemas.account"] = schema_module
schema_spec.loader.exec_module(schema_module)

accounts_spec = spec_from_file_location("accounts_under_test", ACCOUNTS_PATH)
accounts = module_from_spec(accounts_spec)
assert accounts_spec is not None and accounts_spec.loader is not None
accounts_spec.loader.exec_module(accounts)


class FakeQuery:
    def where(self, *_args, **_kwargs):
        return self

    def order_by(self, *_args, **_kwargs):
        return self


class FakeScalarResult:
    def __init__(self, values):
        self._values = values

    def all(self):
        return self._values

    def scalar_one_or_none(self):
        return self._values[0] if self._values else None


class FakeResult:
    def __init__(self, values):
        self._values = values

    def scalars(self):
        return FakeScalarResult(self._values)

    def all(self):
        return self._values


class FakeDb:
    def __init__(self, values):
        self._values = values

    async def execute(self, _query):
        return FakeResult(self._values)


def _make_account(account_id, *, name: str):
    return SimpleNamespace(
        id=account_id,
        organization_id=uuid4(),
        account_name=name,
        account_type=StubAccountType.SELLER,
        marketplace_id="A1PA6795UKMFR9",
        marketplace_country="IT",
        is_active=True,
        last_sync_at=None,
        sync_status=StubSyncStatus.SUCCESS,
        sync_error_message=None,
        last_sync_started_at=None,
        last_sync_succeeded_at=None,
        last_sync_failed_at=None,
        last_sync_attempt_at=None,
        last_sync_heartbeat_at=None,
        sync_error_code=None,
        sync_error_kind=None,
        sp_api_refresh_token_encrypted="secret",
        created_at=None,
        updated_at=None,
    )


@pytest.mark.asyncio
async def test_get_accounts_summary_includes_account_metrics(monkeypatch):
    account_id = uuid4()
    account = _make_account(account_id, name="real")

    monkeypatch.setattr(accounts, "select", lambda *_args, **_kwargs: FakeQuery())
    monkeypatch.setattr(accounts.AmazonAccount, "organization_id", object(), raising=False)

    async def fake_load_metrics(_db, account_ids):
        assert account_ids == [account_id]
        return {
            account_id: {
                "total_sales_30d": 1234.56,
                "total_units_30d": 78,
                "active_asins": 9,
            }
        }

    monkeypatch.setattr(accounts, "_load_account_metrics", fake_load_metrics)

    summary = await accounts.get_accounts_summary(
        current_user=None,
        organization=SimpleNamespace(id=uuid4()),
        db=FakeDb([account]),
    )

    assert summary.total_accounts == 1
    assert summary.accounts[0].total_sales_30d == 1234.56
    assert summary.accounts[0].total_units_30d == 78
    assert summary.accounts[0].active_asins == 9


@pytest.mark.asyncio
async def test_get_accounts_summary_keeps_zero_defaults_without_metrics(monkeypatch):
    account_id = uuid4()
    account = _make_account(account_id, name="second account")

    monkeypatch.setattr(accounts, "select", lambda *_args, **_kwargs: FakeQuery())
    monkeypatch.setattr(accounts.AmazonAccount, "organization_id", object(), raising=False)

    async def fake_load_metrics(_db, _account_ids):
        return {}

    monkeypatch.setattr(accounts, "_load_account_metrics", fake_load_metrics)

    summary = await accounts.get_accounts_summary(
        current_user=None,
        organization=SimpleNamespace(id=uuid4()),
        db=FakeDb([account]),
    )

    assert summary.accounts[0].total_sales_30d == 0
    assert summary.accounts[0].total_units_30d == 0
    assert summary.accounts[0].active_asins == 0
