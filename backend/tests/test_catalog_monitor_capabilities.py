"""Per-account Amazon access check (R1-R4): probes never raise, vendor code is resolved."""
from types import SimpleNamespace

from app.core.exceptions import AmazonAPIError
from app.models.amazon_account import AccountType
from app.services.catalog_monitor.capabilities import (
    CAPABILITY_KEYS,
    listing_seller_id,
    probe_capabilities,
)


class FakeClient:
    def __init__(self, fail=(), vendor_code=None, is_vendor=False):
        self.fail = set(fail)
        self.vendor_code = vendor_code
        self.is_vendor = is_vendor
        self.calls = []

    def _call(self, name, result, *args):
        self.calls.append((name, args))
        if name in self.fail:
            raise AmazonAPIError(f"{name} denied", error_code="FORBIDDEN")
        return result

    def get_catalog_item_full(self, asin):
        return self._call("catalog", {"asin": asin}, asin)

    def get_listing(self, seller_id, sku, included_data=None):
        return self._call("listing", {}, seller_id, sku)

    def get_product_type_definition(self, product_type, seller_id=None, locale="it_IT"):
        return self._call("ptd", {}, product_type)

    def get_aplus_publish_record_count(self, asin):
        return self._call("aplus", 0, asin)

    def list_recent_feeds(self, page_size=1):
        return self._call("feeds", [])

    def resolve_vendor_code(self):
        return self.vendor_code


def _account(kind=AccountType.SELLER, seller_id="SELLER1"):
    return SimpleNamespace(account_type=kind, seller_id=seller_id)


def test_probe_marks_each_failure_without_raising():
    client = FakeClient(fail={"listing", "feeds"})
    results, vendor_code = probe_capabilities(client, _account(), "B0TEST0001", "TEST-SKU-001")
    assert tuple(results) == CAPABILITY_KEYS
    assert results["listings_read"]["ok"] is False
    assert "AmazonAPIError" in results["listings_read"]["error"]
    assert results["feeds"]["ok"] is False
    for key in ("catalog_items", "product_type_definitions", "aplus"):
        assert results[key] == {"ok": True, "error": None}
    assert vendor_code is None


def test_probe_without_sample_marks_checks_not_run():
    client = FakeClient()
    results, _ = probe_capabilities(client, _account(seller_id=None), None, None)
    assert results["catalog_items"] == {"ok": False, "error": "no_sample_asin"}
    assert results["aplus"] == {"ok": False, "error": "no_sample_asin"}
    assert results["listings_read"] == {"ok": False, "error": "no_listing_identity"}
    assert results["feeds"]["ok"] is True


def test_probe_resolves_vendor_code_for_vendor():
    client = FakeClient(vendor_code="VND01", is_vendor=True)
    account = _account(AccountType.VENDOR, seller_id=None)
    results, vendor_code = probe_capabilities(client, account, "B0TEST0001", "TEST-SKU-001")
    assert vendor_code == "VND01"
    assert results["listings_read"]["ok"] is True
    assert ("listing", ("VND01", "TEST-SKU-001")) in client.calls


def test_probe_survives_vendor_code_failure():
    client = FakeClient()
    client.resolve_vendor_code = lambda: (_ for _ in ()).throw(AmazonAPIError("x"))
    account = _account(AccountType.VENDOR, seller_id=None)
    results, vendor_code = probe_capabilities(client, account, "B0TEST0001", "TEST-SKU-001")
    assert vendor_code is None
    assert results["listings_read"] == {"ok": False, "error": "no_listing_identity"}


def test_listing_seller_id_for_seller_and_vendor():
    seller = _account(AccountType.SELLER, seller_id="SELLER1")
    vendor = _account(AccountType.VENDOR, seller_id=None)
    assert listing_seller_id(seller, None) == "SELLER1"
    assert listing_seller_id(vendor, None) is None
    assert listing_seller_id(vendor, SimpleNamespace(vendor_code="VND01")) == "VND01"
    assert listing_seller_id(seller, SimpleNamespace(vendor_code="VND01")) == "SELLER1"


def test_probe_uses_sample_product_type_and_fetches_catalog_once():
    client = FakeClient()
    client.get_catalog_item_full = lambda asin: client._call(
        "catalog", {"productTypes": [{"productType": "TESTTYPE"}]}, asin
    )
    probe_capabilities(client, _account(), "B0TEST0001", "TEST-SKU-001")
    assert ("ptd", ("TESTTYPE",)) in client.calls
    assert [c for c in client.calls if c[0] == "catalog"] == [("catalog", ("B0TEST0001",))]
