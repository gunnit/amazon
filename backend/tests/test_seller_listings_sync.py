"""Unit tests for seller listings enumeration and listing-only product sync.

SP-API is mocked: SPAPIClient is built against the stubbed sp_api modules and
its Reports round-trips are monkeypatched. sync_products is exercised with the
same FakeAsyncSession pattern used by test_catalog_service.
"""
from __future__ import annotations

import importlib.metadata
import sys
import types
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest


ROOT = Path(__file__).resolve().parents[1]


def _ensure_package(name: str, path: Path) -> None:
    module = types.ModuleType(name)
    module.__path__ = [str(path)]
    sys.modules.setdefault(name, module)


_ensure_package("app", ROOT / "app")
_ensure_package("app.core", ROOT / "app" / "core")
_ensure_package("app.models", ROOT / "app" / "models")
_ensure_package("app.services", ROOT / "app" / "services")


sp_api_base_stub = types.ModuleType("sp_api.base")


class _Marketplace:
    def __init__(self, marketplace_id: str):
        self.marketplace_id = marketplace_id


_MARKETPLACE_CODES = (
    "IT", "DE", "FR", "ES", "UK", "GB", "US", "CA", "MX", "BR",
    "JP", "AU", "IN", "AE", "SG", "NL", "SE", "PL", "TR", "BE",
)
sp_api_base_stub.Marketplaces = SimpleNamespace(
    **{code: _Marketplace(f"MP-{code}") for code in _MARKETPLACE_CODES}
)
sp_api_base_stub.SellingApiException = type("SellingApiException", (Exception,), {})
sp_api_base_stub.SellingApiRequestThrottledException = type(
    "SellingApiRequestThrottledException", (sp_api_base_stub.SellingApiException,), {}
)
sys.modules.setdefault("sp_api.base", sp_api_base_stub)


sp_api_api_stub = types.ModuleType("sp_api.api")


class _ApiStub:
    def __init__(self, **_kwargs):
        pass


for _name in (
    "Reports",
    "Inventories",
    "CatalogItems",
    "Products",
    "Orders",
    "VendorOrders",
    "ListingsItems",
):
    setattr(sp_api_api_stub, _name, _ApiStub)
sys.modules.setdefault("sp_api.api", sp_api_api_stub)


email_validator_stub = types.ModuleType("email_validator")


class _EmailNotValidError(ValueError):
    pass


def _validate_email(value, *args, **kwargs):
    return SimpleNamespace(normalized=value)


email_validator_stub.EmailNotValidError = _EmailNotValidError
email_validator_stub.validate_email = _validate_email
sys.modules.setdefault("email_validator", email_validator_stub)
_real_version = importlib.metadata.version


def _fake_version(name: str) -> str:
    if name == "email-validator":
        return "2.0.0"
    return _real_version(name)


importlib.metadata.version = _fake_version


sys.path.insert(0, str(ROOT))


from app.core.amazon import sp_api_client as sp_api_module  # noqa: E402
from app.core.amazon.sp_api_client import SPAPIClient  # noqa: E402
from app.models.amazon_account import AccountType  # noqa: E402


LISTINGS_TSV = (
    "item-name\tseller-sku\tasin1\tprice\tquantity\tstatus\n"
    "Widget Pro\tSKU-A\tB000000001\t19.99\t5\tActive\n"
    "Old Gadget\tSKU-B\tB000000002\t4.50\t0\tInactive\n"
    "Half Listing\tSKU-C\tB000000003\t\t\tIncomplete\n"
)


def _make_client(account_type: str = "seller") -> SPAPIClient:
    credentials = {
        "refresh_token": "rt",
        "lwa_app_id": "app",
        "lwa_client_secret": "secret",
    }
    return SPAPIClient(
        credentials,
        sp_api_base_stub.Marketplaces.IT,
        account_type=account_type,
    )


def _wire_report(client, monkeypatch, *, status="DONE", document_text=LISTINGS_TSV):
    """Make the merchant listings report return one document without network."""
    monkeypatch.setattr(sp_api_module.time, "sleep", lambda *_a: None)
    monkeypatch.setattr(client, "_reports_api", lambda: MagicMock())
    monkeypatch.setattr(
        client, "_create_report_request", lambda *_a, **_kw: {"reportId": "R1"}
    )
    monkeypatch.setattr(
        client,
        "_get_report_status",
        lambda *_a, **_kw: {"processingStatus": status, "reportDocumentId": "D1"},
    )
    monkeypatch.setattr(
        client, "_download_report_document", lambda *_a, **_kw: {"document": document_text}
    )


# ---------------------------------------------------------------------
# fetch_merchant_listings
# ---------------------------------------------------------------------


def test_fetch_merchant_listings_parses_tsv(monkeypatch):
    client = _make_client("seller")
    _wire_report(client, monkeypatch)

    listings = client.fetch_merchant_listings()

    by_asin = {row["asin"]: row for row in listings}
    assert set(by_asin) == {"B000000001", "B000000002", "B000000003"}
    assert by_asin["B000000001"] == {
        "asin": "B000000001",
        "sku": "SKU-A",
        "title": "Widget Pro",
        "price": "19.99",
        "quantity": "5",
        "status": "Active",
    }
    assert by_asin["B000000002"]["status"] == "Inactive"
    assert by_asin["B000000003"]["price"] is None


def test_fetch_merchant_listings_vendor_returns_empty_without_report(monkeypatch):
    client = _make_client("vendor")

    create = MagicMock()
    monkeypatch.setattr(client, "_create_report_request", create)

    assert client.fetch_merchant_listings() == []
    create.assert_not_called()


def test_fetch_merchant_listings_fatal_returns_empty(monkeypatch, caplog):
    client = _make_client("seller")
    _wire_report(client, monkeypatch, status="FATAL")

    with caplog.at_level("WARNING"):
        assert client.fetch_merchant_listings() == []
    assert any("FATAL" in rec.message or "FATAL" in str(rec.args) for rec in caplog.records)


def test_fetch_merchant_listings_throttle_returns_empty(monkeypatch, caplog):
    client = _make_client("seller")
    monkeypatch.setattr(sp_api_module.time, "sleep", lambda *_a: None)
    monkeypatch.setattr(client, "_reports_api", lambda: MagicMock())

    def _boom(*_a, **_kw):
        raise sp_api_base_stub.SellingApiRequestThrottledException("throttled")

    monkeypatch.setattr(client, "_create_report_request", _boom)

    with caplog.at_level("WARNING"):
        assert client.fetch_merchant_listings() == []
    assert caplog.records


def test_resolve_seller_id_reuses_listing_rows(monkeypatch):
    """The seller-id column is read from the same shared report rows."""
    client = _make_client("seller")
    tsv = (
        "item-name\tseller-sku\tasin1\tseller-id\n"
        "Widget\tSKU-A\tB000000001\tA1B2C3D4E5F6G7\n"
    )
    _wire_report(client, monkeypatch, document_text=tsv)

    assert client.resolve_seller_id() == "A1B2C3D4E5F6G7"


# ---------------------------------------------------------------------
# sync_products — listing-only ASINs
# ---------------------------------------------------------------------


class FakeScalarResult:
    def __init__(self, rows):
        self._rows = list(rows)

    def one_or_none(self):
        if len(self._rows) > 1:
            raise AssertionError("Expected zero or one row")
        return self._rows[0] if self._rows else None


class FakeResult:
    def __init__(self, rows):
        self._rows = list(rows)

    def __iter__(self):
        return iter(self._rows)

    def scalar_one_or_none(self):
        return FakeScalarResult(self._rows).one_or_none()


class FakeAsyncSession:
    def __init__(self, responses):
        self._responses = list(responses)
        self.added = []
        self.flushes = 0

    async def execute(self, _query):
        if not self._responses:
            raise AssertionError("Unexpected execute call")
        return FakeResult(self._responses.pop(0))

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        self.flushes += 1


def _account(account_type=AccountType.SELLER):
    return SimpleNamespace(
        id=uuid4(),
        organization_id=uuid4(),
        account_type=account_type,
        marketplace_country="IT",
        account_name="Test Acct",
    )


def _service(session, sp_client):
    from app.services.data_extraction import DataExtractionService

    service = DataExtractionService(session)
    service._create_sp_api_client = lambda *_a, **_kw: sp_client
    return service


@pytest.mark.asyncio
async def test_sync_products_adds_listing_only_asin():
    account = _account()
    # 1) sales ASINs (none), 2) inventory ASINs (none),
    # 3..5) Product lookups for each listing-only ASIN (none -> create).
    session = FakeAsyncSession([[], [], [], [], []])

    sp_client = MagicMock()
    sp_client.is_vendor = False
    sp_client.fetch_merchant_listings.return_value = [
        {
            "asin": "B000000001",
            "sku": "SKU-A",
            "title": "Widget Pro",
            "price": "19.99",
            "quantity": "5",
            "status": "Active",
        },
        {
            "asin": "B000000002",
            "sku": "SKU-B",
            "title": "Old Gadget",
            "price": "4.50",
            "quantity": "0",
            "status": "Inactive",
        },
        {
            "asin": "B000000003",
            "sku": "SKU-C",
            "title": "Half Listing",
            "price": None,
            "quantity": None,
            "status": "Incomplete",
        },
    ]

    service = _service(session, sp_client)
    count = await service.sync_products(account)

    assert count == 3
    products = {p.asin: p for p in session.added if p.__class__.__name__ == "Product"}
    assert set(products) == {"B000000001", "B000000002", "B000000003"}

    active = products["B000000001"]
    assert active.sku == "SKU-A"
    assert active.title == "Widget Pro"
    assert active.current_price == Decimal("19.99")
    assert active.is_active is True

    assert products["B000000002"].is_active is False
    assert products["B000000003"].is_active is False
    assert products["B000000003"].current_price is None

    # Catalog API must not be queried for listing-only ASINs.
    sp_client.get_catalog_item_details.assert_not_called()


@pytest.mark.asyncio
async def test_sync_products_vendor_skips_listings_enumeration():
    account = _account(AccountType.VENDOR)
    # Only the two ASIN-gathering queries run; both empty -> early return.
    session = FakeAsyncSession([[], []])

    sp_client = MagicMock()
    sp_client.is_vendor = True

    service = _service(session, sp_client)
    count = await service.sync_products(account)

    assert count == 0
    sp_client.fetch_merchant_listings.assert_not_called()
