"""Tests for the period-aware ``GET /catalog/products`` endpoint logic.

The endpoint runs two queries when a date range is supplied: one for the
products themselves and one for the distinct ASINs that have sales in the
period (excluding the DAILY_TOTAL_ASIN sentinel). We load the real
``ProductResponse`` schema and the endpoint module, stub the heavy service
imports, and drive both queries through a small fake session. This mirrors
``test_accounts_summary.py``.
"""
from __future__ import annotations

import importlib.metadata
import sys
import types
from datetime import date
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest


ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "app" / "api" / "v1" / "catalog.py"
REPORT_SCHEMA_PATH = ROOT / "app" / "schemas" / "report.py"
CATALOG_SCHEMA_PATH = ROOT / "app" / "schemas" / "catalog.py"

DAILY_TOTAL_ASIN = "__DAILY_TOTAL__"


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


# email-validator stub so importing the report schema (EmailStr) is cheap.
email_validator_stub = types.ModuleType("email_validator")
email_validator_stub.EmailNotValidError = type("EmailNotValidError", (ValueError,), {})
email_validator_stub.validate_email = lambda value, *a, **kw: SimpleNamespace(normalized=value)
sys.modules.setdefault("email_validator", email_validator_stub)
_real_version = importlib.metadata.version
importlib.metadata.version = lambda name: "2.0.0" if name == "email-validator" else _real_version(name)


# Only the leaf-dependency stubs are registered here, and all via setdefault:
# the shared app.models.* / app.services.* modules are left for the real
# packages to populate. test_catalog_service.py and test_seller_listings_sync.py
# import the real AccountType / parse_import_rows / CatalogService, so planting
# fakes (or even setdefault fakes, when this module is collected first) under
# those names poisons them once the suite is collected together.
deps_stub = types.ModuleType("app.api.deps")
deps_stub.CurrentUser = object
deps_stub.CurrentOrganization = object
deps_stub.DbSession = object
sys.modules.setdefault("app.api.deps", deps_stub)

exceptions_stub = types.ModuleType("app.core.exceptions")
exceptions_stub.AmazonAPIError = type("AmazonAPIError", (Exception,), {})
sys.modules.setdefault("app.core.exceptions", exceptions_stub)


def _import_real(qualname: str, path: Path):
    """Import a real app module from disk, leaving any prior entry untouched."""
    if qualname in sys.modules:
        return sys.modules[qualname]
    spec = spec_from_file_location(qualname, path)
    module = module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    sys.modules[qualname] = module
    spec.loader.exec_module(module)
    return module


# Real shared modules: AccountType, SalesData, Product and the service classes
# are the same objects the sibling tests rely on. Importing the package (not a
# stub) keeps the trio consistent regardless of collection order.
_import_real("app.models.amazon_account", ROOT / "app" / "models" / "amazon_account.py")
_import_real("app.models.catalog_change_log", ROOT / "app" / "models" / "catalog_change_log.py")
_import_real("app.models.product", ROOT / "app" / "models" / "product.py")
_import_real("app.models.sales_data", ROOT / "app" / "models" / "sales_data.py")
_import_real("app.services.catalog_service", ROOT / "app" / "services" / "catalog_service.py")
_import_real("app.services.data_extraction", ROOT / "app" / "services" / "data_extraction.py")
_import_real("app.services.image_service", ROOT / "app" / "services" / "image_service.py")


def _load_real_module(qualname: str, path: Path):
    spec = spec_from_file_location(qualname, path)
    module = module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    sys.modules[qualname] = module
    spec.loader.exec_module(module)
    return module


# Real schema modules so FastAPI route response models stay valid and
# model_validate enforces the ProductResponse shape (incl. the new flag).
_load_real_module("app.schemas.catalog", CATALOG_SCHEMA_PATH)
report_module = _load_real_module("app.schemas.report", REPORT_SCHEMA_PATH)

catalog_spec = spec_from_file_location("catalog_under_test", CATALOG_PATH)
catalog = module_from_spec(catalog_spec)
assert catalog_spec is not None and catalog_spec.loader is not None
catalog_spec.loader.exec_module(catalog)


class Comparison:
    """Records a column comparison so the test can assert on the operator/value."""

    def __init__(self, column, op, other):
        self.column = column
        self.op = op
        self.other = other

    def __repr__(self):
        return f"{self.column.name} {self.op} {self.other!r}"


class RecordingColumn:
    def __init__(self, name):
        self.name = name

    def __eq__(self, other):
        return Comparison(self, "==", other)

    def __ne__(self, other):
        return Comparison(self, "!=", other)

    def __ge__(self, other):
        return Comparison(self, ">=", other)

    def __le__(self, other):
        return Comparison(self, "<=", other)

    def in_(self, other):
        return Comparison(self, "in", other)

    def ilike(self, other):
        return Comparison(self, "ilike", other)

    def desc(self):
        return self

    __hash__ = None


class FakeQuery:
    def join(self, *_a, **_kw):
        return self

    def where(self, *_a, **_kw):
        return self

    def distinct(self, *_a, **_kw):
        return self

    def order_by(self, *_a, **_kw):
        return self

    def limit(self, *_a, **_kw):
        return self

    def offset(self, *_a, **_kw):
        return self


class FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class FakeDb:
    """Returns queued result-sets in order, one per ``execute`` call."""

    def __init__(self, result_sets):
        self._result_sets = list(result_sets)
        self.calls = 0

    async def execute(self, _query):
        self.calls += 1
        return FakeResult(self._result_sets.pop(0))


def _product(asin, *, account_id=None, title="Title", sku="SKU"):
    return SimpleNamespace(
        id=uuid4(),
        account_id=account_id or uuid4(),
        asin=asin,
        sku=sku,
        title=title,
        brand=None,
        category=None,
        current_price=None,
        current_bsr=None,
        review_count=None,
        rating=None,
        is_active=True,
        source="amazon_sync",
    )


@pytest.fixture(autouse=True)
def _stub_query_builders(monkeypatch):
    monkeypatch.setattr(catalog, "select", lambda *_a, **_kw: FakeQuery())
    func_stub = SimpleNamespace(distinct=lambda *_a, **_kw: object())
    monkeypatch.setattr(catalog, "func", func_stub)
    # Columns referenced inside .where(...) clauses record their comparisons.
    monkeypatch.setattr(catalog.AmazonAccount, "organization_id", RecordingColumn("organization_id"), raising=False)
    monkeypatch.setattr(catalog.AmazonAccount, "id", RecordingColumn("id"), raising=False)
    monkeypatch.setattr(catalog.AmazonAccount, "account_type", RecordingColumn("account_type"), raising=False)
    monkeypatch.setattr(catalog.SalesData, "asin", RecordingColumn("asin"), raising=False)
    monkeypatch.setattr(catalog.SalesData, "date", RecordingColumn("date"), raising=False)
    monkeypatch.setattr(catalog.SalesData, "account_id", RecordingColumn("account_id"), raising=False)
    monkeypatch.setattr(catalog.Product, "account_id", RecordingColumn("product_account_id"), raising=False)
    monkeypatch.setattr(catalog.Product, "updated_at", RecordingColumn("updated_at"), raising=False)
    monkeypatch.setattr(catalog.Product, "is_active", RecordingColumn("is_active"), raising=False)


@pytest.mark.asyncio
async def test_products_flagged_with_has_sales_in_period():
    org = SimpleNamespace(id=uuid4())
    account_id = uuid4()
    p1 = _product("B000000001", account_id=account_id)
    p2 = _product("B000000002", account_id=account_id)
    p3 = _product("B000000003", account_id=account_id)
    products = [
        (p1, SimpleNamespace(value="seller")),
        (p2, SimpleNamespace(value="seller")),
        (p3, SimpleNamespace(value="seller")),
    ]
    # 1st execute -> products; 2nd execute -> (account_id, asin) sales pairs.
    db = FakeDb(
        [products, [(account_id, "B000000001"), (account_id, "B000000002")]]
    )

    result = await catalog.list_products(
        current_user=None,
        organization=org,
        db=db,
        account_ids=None,
        date_from=date(2026, 1, 1),
        date_to=date(2026, 1, 31),
    )

    assert db.calls == 2
    by_asin = {r.asin: r.has_sales_in_period for r in result}
    assert by_asin == {
        "B000000001": True,
        "B000000002": True,
        "B000000003": False,
    }
    # No product was filtered out; the catalog still lists all three.
    assert len(result) == 3


@pytest.mark.asyncio
async def test_has_sales_in_period_is_scoped_per_account():
    """The same ASIN on two accounts must be flagged only for the account that
    actually had sales in the period, not for both."""
    org = SimpleNamespace(id=uuid4())
    account_with_sales = uuid4()
    account_without_sales = uuid4()
    sold = _product("B0SHARED01", account_id=account_with_sales)
    unsold = _product("B0SHARED01", account_id=account_without_sales)
    products = [
        (sold, SimpleNamespace(value="seller")),
        (unsold, SimpleNamespace(value="vendor")),
    ]
    # Only the first account has a sales row for the shared ASIN.
    db = FakeDb([products, [(account_with_sales, "B0SHARED01")]])

    result = await catalog.list_products(
        current_user=None,
        organization=org,
        db=db,
        account_ids=None,
        date_from=date(2026, 1, 1),
        date_to=date(2026, 1, 31),
    )

    flags = {r.account_id: r.has_sales_in_period for r in result}
    assert flags[account_with_sales] is True
    assert flags[account_without_sales] is False


@pytest.mark.asyncio
async def test_no_date_range_leaves_flag_unset_and_skips_sales_query():
    org = SimpleNamespace(id=uuid4())
    products = [(_product("B000000001"), SimpleNamespace(value="seller"))]
    db = FakeDb([products])

    result = await catalog.list_products(
        current_user=None,
        organization=org,
        db=db,
        account_ids=None,
    )

    # Only the products query ran; no sales lookup without a date range.
    assert db.calls == 1
    assert result[0].has_sales_in_period is None


@pytest.mark.asyncio
async def test_sales_query_excludes_daily_total_sentinel_and_is_org_scoped(monkeypatch):
    """The distinct-ASIN query must exclude DAILY_TOTAL_ASIN and scope to the
    org. We capture the where-clause comparisons to prove both constraints."""
    org_id = uuid4()
    captured: list = []

    class CapturingQuery(FakeQuery):
        def where(self, *args, **_kw):
            captured.extend(args)
            return self

    monkeypatch.setattr(catalog, "select", lambda *_a, **_kw: CapturingQuery())

    acc_a, acc_b = uuid4(), uuid4()
    db = FakeDb([[(acc_a, "B000000001"), (acc_b, "B000000002")]])

    keys = await catalog._asins_with_sales_in_period(
        db,
        org_id,
        date(2026, 1, 1),
        date(2026, 1, 31),
        None,
    )

    comparisons = [c for c in captured if isinstance(c, Comparison)]

    # Sentinel exclusion: asin != DAILY_TOTAL_ASIN.
    assert any(
        c.column.name == "asin" and c.op == "!=" and c.other == DAILY_TOTAL_ASIN
        for c in comparisons
    )
    # Org scoping: organization_id == org_id.
    assert any(
        c.column.name == "organization_id" and c.op == "==" and c.other == org_id
        for c in comparisons
    )
    # Period bounds applied.
    assert any(c.column.name == "date" and c.op == ">=" for c in comparisons)
    assert any(c.column.name == "date" and c.op == "<=" for c in comparisons)

    assert keys == {(acc_a, "B000000001"), (acc_b, "B000000002")}


@pytest.mark.asyncio
async def test_account_filter_scopes_sales_query(monkeypatch):
    """When account_ids is given, the sales query adds an account filter."""
    org_id = uuid4()
    account_id = uuid4()
    captured: list = []

    class CapturingQuery(FakeQuery):
        def where(self, *args, **_kw):
            captured.extend(args)
            return self

    monkeypatch.setattr(catalog, "select", lambda *_a, **_kw: CapturingQuery())

    db = FakeDb([[(account_id, "B000000001")]])

    await catalog._asins_with_sales_in_period(
        db,
        org_id,
        date(2026, 1, 1),
        date(2026, 1, 31),
        [account_id],
    )

    comparisons = [c for c in captured if isinstance(c, Comparison)]
    assert any(
        c.column.name == "id" and c.op == "in" and account_id in c.other
        for c in comparisons
    )
