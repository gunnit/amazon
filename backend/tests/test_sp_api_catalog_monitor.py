"""Unit tests for the catalogue-monitor SP-API client calls (R1-R4).

SP-API is stubbed in sys.modules before the client is imported; each test
replaces the per-API factory (``_listings_api`` etc.) with a recording fake, so
no network is used.
"""
from __future__ import annotations

import importlib.metadata
import json
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
    "Feeds",
    "ProductTypeDefinitions",
    "AplusContent",
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
from app.core.exceptions import AmazonAPIError  # noqa: E402


class _Resp:
    def __init__(self, payload):
        self.payload = payload


class _Recorder:
    """Fake API object: every call is recorded; responses are queued by method."""

    def __init__(self, responses=None):
        self.calls = []
        self.responses = responses or {}

    def __getattr__(self, name):
        def call(*args, **kwargs):
            self.calls.append((name, args, kwargs))
            value = self.responses.get(name, {})
            if callable(value):
                value = value(*args, **kwargs)
            return _Resp(value) if isinstance(value, dict) else value

        return call


def _make_client(account_type: str = "seller") -> SPAPIClient:
    return SPAPIClient(
        {"refresh_token": "rt", "lwa_app_id": "app", "lwa_client_secret": "secret"},
        sp_api_base_stub.Marketplaces.IT,
        account_type=account_type,
    )


def _install(client, attr, fake, monkeypatch):
    monkeypatch.setattr(client, attr, lambda *a, **k: fake)
    return fake


def test_patch_listing_passes_validation_preview_mode(monkeypatch):
    client = _make_client()
    fake = _install(client, "_listings_api", _Recorder({"patch_listings_item": {"status": "VALID", "issues": []}}), monkeypatch)
    patches = [{"op": "replace", "path": "/attributes/item_name", "value": [{"value": "T"}]}]

    result = client.patch_listing("SELLER1", "TEST-SKU-001", "LUGGAGE", patches, mode="VALIDATION_PREVIEW")

    (_, _, kwargs), = fake.calls
    assert kwargs["mode"] == "VALIDATION_PREVIEW"
    assert kwargs["body"] == {"productType": "LUGGAGE", "patches": patches}
    assert result["status"] == "VALID"


def test_patch_listing_without_mode_omits_it(monkeypatch):
    client = _make_client()
    fake = _install(client, "_listings_api", _Recorder(), monkeypatch)
    client.patch_listing("SELLER1", "TEST-SKU-001", "LUGGAGE", [{"op": "replace", "path": "/attributes/x", "value": []}])
    assert "mode" not in fake.calls[0][2]


def test_patch_listing_returns_invalid_payload(monkeypatch):
    client = _make_client()
    payload = {"status": "INVALID", "issues": [{"code": "90220"}]}
    _install(client, "_listings_api", _Recorder({"patch_listings_item": payload}), monkeypatch)

    result = client.patch_listing(
        "SELLER1", "TEST-SKU-001", "LUGGAGE",
        [{"op": "replace", "path": "/attributes/x", "value": []}], mode="VALIDATION_PREVIEW",
    )

    assert result == payload


def test_put_listing_sends_attributes_and_mode(monkeypatch):
    client = _make_client()
    fake = _install(client, "_listings_api", _Recorder({"put_listings_item": {"status": "VALID"}}), monkeypatch)
    attrs = {"item_name": [{"value": "T", "marketplace_id": "X"}]}

    result = client.put_listing("SELLER1", "TEST-SKU-001", "LUGGAGE", attrs, mode="VALIDATION_PREVIEW")

    name, _, kwargs = fake.calls[0]
    assert name == "put_listings_item"
    assert kwargs["sellerId"] == "SELLER1" and kwargs["sku"] == "TEST-SKU-001"
    assert kwargs["mode"] == "VALIDATION_PREVIEW"
    assert kwargs["body"] == {"productType": "LUGGAGE", "requirements": "LISTING", "attributes": attrs}
    assert result == {"status": "VALID"}


def test_get_listing_default_included_data(monkeypatch):
    client = _make_client()
    fake = _install(client, "_listings_api", _Recorder(), monkeypatch)
    client.get_listing("SELLER1", "TEST-SKU-001")
    assert fake.calls[0][2]["includedData"] == [
        "summaries", "attributes", "issues", "offers", "relationships", "productTypes",
    ]


def test_get_catalog_item_full_requests_relationships_and_images(monkeypatch):
    client = _make_client()
    fake = _install(client, "_catalog_api", _Recorder({"get_catalog_item": {"asin": "B0TEST0001"}}), monkeypatch)

    result = client.get_catalog_item_full("B0TEST0001")

    kwargs = fake.calls[0][2]
    assert kwargs["asin"] == "B0TEST0001"
    assert set(kwargs["includedData"]) == {
        "attributes", "images", "relationships", "summaries",
        "classifications", "productTypes", "salesRanks", "identifiers",
    }
    assert result == {"asin": "B0TEST0001"}


def test_get_catalog_item_full_raises_on_api_error(monkeypatch):
    client = _make_client()

    def boom(**_kw):
        # The real library exception needs headers; bypass __init__ so the test
        # works with either the real class or a stub.
        raise sp_api_module.SellingApiException.__new__(sp_api_module.SellingApiException)

    class _Api:
        get_catalog_item = staticmethod(boom)

    _install(client, "_catalog_api", _Api(), monkeypatch)
    with pytest.raises(AmazonAPIError):
        client.get_catalog_item_full("B0TEST0001")


def test_search_listings_by_asins_chunks_by_20(monkeypatch):
    client = _make_client()
    fake = _install(
        client, "_listings_api",
        _Recorder({"search_listings_items": {"items": [{"sku": "TEST-SKU-001"}]}}),
        monkeypatch,
    )
    asins = [f"B0TEST{i:04d}" for i in range(45)]

    items = client.search_listings_by_asins("SELLER1", asins)

    assert len(fake.calls) == 3
    assert [len(c[2]["identifiers"]) for c in fake.calls] == [20, 20, 5]
    assert all(c[2]["identifiersType"] == "ASIN" for c in fake.calls)
    assert all(c[2]["includedData"] == ["summaries", "issues"] for c in fake.calls)
    assert len(items) == 3


def test_resolve_vendor_code_reads_selling_party(monkeypatch):
    client = _make_client("vendor")
    orders = [{"orderDetails": {"sellingParty": {"partyId": "TESTV"}}}]
    monkeypatch.setattr(client, "get_vendor_purchase_orders", lambda start, end: orders)
    assert client.resolve_vendor_code() == "TESTV"


def test_resolve_vendor_code_returns_none_without_orders(monkeypatch):
    client = _make_client("vendor")
    monkeypatch.setattr(client, "get_vendor_purchase_orders", lambda start, end: [])
    assert client.resolve_vendor_code() is None


def test_resolve_vendor_code_returns_none_for_seller(monkeypatch):
    client = _make_client("seller")

    def fail(*_a, **_k):
        raise AssertionError("must not query purchase orders for a seller")

    monkeypatch.setattr(client, "get_vendor_purchase_orders", fail)
    assert client.resolve_vendor_code() is None


def test_get_product_type_definition_requests_enforced_listing(monkeypatch):
    client = _make_client()
    fake = _install(
        client, "_product_type_definitions_api",
        _Recorder({"get_definitions_product_type": {"productType": "LUGGAGE"}}), monkeypatch,
    )

    result = client.get_product_type_definition("LUGGAGE", seller_id="SELLER1")

    kwargs = fake.calls[0][2]
    assert kwargs["productType"] == "LUGGAGE"
    assert kwargs["requirements"] == "LISTING"
    assert kwargs["requirementsEnforced"] == "ENFORCED"
    assert kwargs["locale"] == "it_IT"
    assert kwargs["sellerId"] == "SELLER1"
    assert result == {"productType": "LUGGAGE"}


def test_fetch_json_schema_uses_httpx_get(monkeypatch):
    import httpx

    seen = {}

    class _R:
        def raise_for_status(self):
            pass

        def json(self):
            return {"type": "object"}

    def fake_get(url, timeout):
        seen.update(url=url, timeout=timeout)
        return _R()

    monkeypatch.setattr(httpx, "get", fake_get)
    assert _make_client().fetch_json_schema("https://example.test/schema.json") == {"type": "object"}
    assert seen == {"url": "https://example.test/schema.json", "timeout": 30}


def test_get_aplus_publish_record_count(monkeypatch):
    client = _make_client()
    fake = _install(
        client, "_aplus_content_api",
        _Recorder({"search_content_publish_records": {"publishRecordSet": [{}, {}]}}), monkeypatch,
    )
    assert client.get_aplus_publish_record_count("B0TEST0001") == 2
    assert fake.calls[0][2]["asin"] == "B0TEST0001"


def test_submit_json_listings_feed_uploads_json_and_returns_feed_id(monkeypatch):
    client = _make_client()
    fake = _install(
        client, "_feeds_api",
        _Recorder({"submit_feed": [_Resp({"feedDocumentId": "D1"}), _Resp({"feedId": "F1"})]}),
        monkeypatch,
    )
    document = {"header": {"sellerId": "SELLER1"}, "messages": [{"sku": "TEST-SKU-001", "note": "caff\u00e8"}]}

    assert client.submit_json_listings_feed(document) == "F1"

    _, args, kwargs = fake.calls[0]
    feed_type, file = args[0], args[1]
    content_type = args[2] if len(args) > 2 else kwargs["content_type"]
    assert feed_type == "JSON_LISTINGS_FEED"
    assert content_type == "application/json; charset=UTF-8"
    assert json.loads(file.read().decode("utf-8")) == document
    assert kwargs["marketplaceIds"] == [client.marketplace.marketplace_id]


def test_get_feed_status_and_result(monkeypatch):
    client = _make_client()
    fake = _install(
        client, "_feeds_api",
        _Recorder({
            "get_feed": {"processingStatus": "DONE", "resultFeedDocumentId": "R1"},
            "get_feed_result_document": '{"summary": {"errors": 0}}',
        }),
        monkeypatch,
    )

    assert client.get_feed_status("F1") == {"processingStatus": "DONE", "resultFeedDocumentId": "R1"}
    assert client.get_feed_result("R1") == {"summary": {"errors": 0}}
    assert fake.calls[1][0] == "get_feed_result_document"


def test_get_feed_status_without_result_document(monkeypatch):
    client = _make_client()
    _install(client, "_feeds_api", _Recorder({"get_feed": {"processingStatus": "IN_PROGRESS"}}), monkeypatch)
    assert client.get_feed_status("F1") == {"processingStatus": "IN_PROGRESS", "resultFeedDocumentId": None}
