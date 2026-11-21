"""Dev-only fixture seam: a FixtureClient answers the catalogue monitor's Amazon calls (R1-R4).

The seam is on only when DEV_FIXTURE_AMAZON_DIR is set outside production; production
always builds the real SP-API client.
"""
import json
import logging
from types import SimpleNamespace

import pytest

from app.config import settings
from app.core.exceptions import AmazonAPIError
from app.models.amazon_account import AccountType
from app.services.catalog_monitor import clients
from app.services.catalog_monitor.content import content_from_catalog
from app.services.catalog_monitor.fixture_client import (
    FixtureClient,
    active_fixture_dir,
    log_fixture_mode,
)

MP = "APJ6JRA9NG5V4"


def _write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _text(value):
    return [{"value": value, "language_tag": "it_IT", "marketplace_id": MP}]


def _catalog(asin, title, bullets=(), images=(), parents=(), children=()):
    relationship = {"type": "VARIATION", "parentAsins": list(parents), "childAsins": list(children)}
    if parents or children:
        relationship["variationTheme"] = {"attributes": ["color"], "theme": "COLOR"}
    return {
        "asin": asin,
        "attributes": {
            "item_name": _text(title),
            "brand": _text("TESTBRAND"),
            "bullet_point": [_text(b)[0] for b in bullets],
        },
        "images": [
            {
                "marketplaceId": MP,
                "images": [{"variant": v, "link": link, "width": 1000, "height": 1000} for v, link in images],
            }
        ],
        "productTypes": [{"marketplaceId": MP, "productType": "KITCHEN"}],
        "relationships": [
            {"marketplaceId": MP, "relationships": [relationship] if parents or children else []}
        ],
        "summaries": [{"marketplaceId": MP, "brand": "TESTBRAND", "itemName": title}],
    }


def _listing(sku, asin, keywords="mestolo cucina silicone"):
    return {
        "sku": sku,
        "summaries": [{"marketplaceId": MP, "asin": asin, "productType": "KITCHEN", "status": ["BUYABLE"]}],
        "attributes": {"generic_keyword": _text(keywords)},
        "issues": [],
    }


@pytest.fixture
def fixture_dir(tmp_path):
    images = [("MAIN", "http://img.test/main.png"), ("PT01", "http://img.test/a.png"),
              ("PT02", "http://img.test/b.png")]
    _write(tmp_path / "catalog" / "B0TEST0001.json",
           _catalog("B0TEST0001", "TESTBRAND Mestolo", ["Uno", "Due"], images))
    _write(tmp_path / "catalog" / "B0TEST0010.json",
           _catalog("B0TEST0010", "TESTBRAND Set", children=["B0TEST0011"]))
    _write(tmp_path / "catalog" / "B0TEST0011.json",
           _catalog("B0TEST0011", "TESTBRAND Set rosso", parents=["B0TEST0010"]))
    _write(tmp_path / "catalog" / "B0TEST0012.json", _catalog("B0TEST0012", "TESTBRAND Set blu"))
    _write(tmp_path / "listings" / "TEST-SKU-001.json", _listing("TEST-SKU-001", "B0TEST0001"))
    _write(tmp_path / "listings" / "TEST-SKU-010.json", _listing("TEST-SKU-010", "B0TEST0010"))
    _write(tmp_path / "listings" / "TEST-SKU-012.json", _listing("TEST-SKU-012", "B0TEST0012"))
    _write(tmp_path / "product_types" / "KITCHEN.json",
           {"required": ["item_name", "brand", "list_price"], "properties": {"item_name": {}, "brand": {}}})
    _write(tmp_path / "client.json", {"vendor_code": "TESTVENDOR", "aplus_modules": {"B0TEST0001": 4}})
    return tmp_path


@pytest.fixture
def dev_mode(monkeypatch, fixture_dir):
    monkeypatch.setattr(settings, "DEV_FIXTURE_AMAZON_DIR", str(fixture_dir))
    monkeypatch.setattr(settings, "APP_ENV", "development")
    return fixture_dir


def _account(account_type=AccountType.SELLER):
    return SimpleNamespace(
        id="acc", organization_id="org", marketplace_id=MP, marketplace_country="IT",
        account_type=account_type, seller_id="TESTSELLER",
    )


# ---- the seam ----


def test_factory_returns_the_fixture_client_outside_production(dev_mode):
    client = clients.default_client_factory(_account(), None)
    assert isinstance(client, FixtureClient)
    assert client.get_catalog_item_full("B0TEST0001")["asin"] == "B0TEST0001"


def test_production_ignores_the_fixture_dir(dev_mode, monkeypatch):
    monkeypatch.setattr(settings, "APP_ENV", "production")

    def real_credentials(account, organization):
        raise RuntimeError("real SP-API path")

    monkeypatch.setattr(clients, "resolve_credentials", real_credentials)
    assert active_fixture_dir() is None
    with pytest.raises(RuntimeError, match="real SP-API path"):
        clients.default_client_factory(_account(), None)


def test_without_the_setting_the_factory_builds_sp_api(monkeypatch):
    monkeypatch.setattr(settings, "DEV_FIXTURE_AMAZON_DIR", None)
    monkeypatch.setattr(settings, "APP_ENV", "development")
    built = {}

    class FakeSPAPI:
        def __init__(self, credentials, marketplace, account_type):
            built.update(credentials=credentials, account_type=account_type)

    monkeypatch.setattr(clients, "resolve_credentials", lambda a, o: {"token": "x"})
    monkeypatch.setattr(clients, "SPAPIClient", FakeSPAPI)
    assert isinstance(clients.default_client_factory(_account(), None), FakeSPAPI)
    assert built == {"credentials": {"token": "x"}, "account_type": "seller"}


def test_startup_log_warns_when_active_and_errors_in_production(dev_mode, monkeypatch, caplog):
    log = logging.getLogger("fixture-test")
    with caplog.at_level(logging.WARNING, logger="fixture-test"):
        log_fixture_mode(log)
    assert [r.levelno for r in caplog.records] == [logging.WARNING]
    caplog.clear()
    monkeypatch.setattr(settings, "APP_ENV", "production")
    with caplog.at_level(logging.WARNING, logger="fixture-test"):
        log_fixture_mode(log)
    assert [r.levelno for r in caplog.records] == [logging.ERROR]
    caplog.clear()
    monkeypatch.setattr(settings, "DEV_FIXTURE_AMAZON_DIR", None)
    with caplog.at_level(logging.WARNING, logger="fixture-test"):
        log_fixture_mode(log)
    assert caplog.records == []


# ---- reads ----


def test_reads_catalog_listing_schema_aplus(fixture_dir):
    client = FixtureClient(str(fixture_dir), MP)
    content = content_from_catalog(client.get_catalog_item_full("B0TEST0001"), MP)
    assert (content.title, content.bullets) == ("TESTBRAND Mestolo", ["Uno", "Due"])
    assert client.get_listing("TESTSELLER", "TEST-SKU-001")["sku"] == "TEST-SKU-001"
    with pytest.raises(AmazonAPIError):
        client.get_catalog_item_full("B0TEST9999")
    with pytest.raises(AmazonAPIError):
        client.get_listing("TESTSELLER", "TEST-SKU-404")
    definition = client.get_product_type_definition("KITCHEN")
    schema = client.fetch_json_schema(definition["schema"]["link"]["resource"])
    assert schema["required"] == ["item_name", "brand", "list_price"]
    with pytest.raises(AmazonAPIError):
        client.get_product_type_definition("UNKNOWN_TYPE")
    assert client.get_aplus_publish_record_count("B0TEST0001") == 4
    assert client.get_aplus_publish_record_count("B0TEST0010") == 0
    assert [i["sku"] for i in client.search_listings_by_asins("TESTSELLER", ["B0TEST0001"])] == [
        "TEST-SKU-001"
    ]
    assert client.list_recent_feeds(page_size=1) == []


def test_vendor_code_only_for_vendor_accounts(fixture_dir):
    assert FixtureClient(str(fixture_dir), MP, account_type="vendor").resolve_vendor_code() == "TESTVENDOR"
    assert FixtureClient(str(fixture_dir), MP).resolve_vendor_code() is None


# ---- writes ----


def _title_patch(title):
    return [{"op": "replace", "path": "/attributes/item_name", "value": _text(title)}]


def test_preview_is_valid_or_invalid_and_never_writes(fixture_dir):
    client = FixtureClient(str(fixture_dir), MP)
    valid = client.patch_listing("TESTSELLER", "TEST-SKU-001", "KITCHEN", _title_patch("Nuovo"),
                                 mode="VALIDATION_PREVIEW")
    assert (valid["status"], valid["issues"]) == ("VALID", [])
    invalid = client.patch_listing("TESTSELLER", "TEST-SKU-001", "KITCHEN", _title_patch("x" * 201),
                                   mode="VALIDATION_PREVIEW")
    assert invalid["status"] == "INVALID"
    assert [i["severity"] for i in invalid["issues"]] == ["ERROR"]
    assert client.get_catalog_item_full("B0TEST0001")["attributes"]["item_name"][0]["value"] == (
        "TESTBRAND Mestolo"
    )


def test_live_patch_is_accepted_and_the_next_client_reads_it(fixture_dir):
    patches = _title_patch("TESTBRAND Mestolo nuovo") + [
        {"op": "replace", "path": "/attributes/bullet_point", "value": _text("Uno") + _text("Tre")},
        {"op": "replace", "path": "/attributes/generic_keyword", "value": _text("parole nuove")},
        {"op": "replace", "path": "/attributes/other_product_image_locator_1",
         "value": [{"media_location": "http://img.test/b.png", "marketplace_id": MP}]},
        {"op": "replace", "path": "/attributes/other_product_image_locator_2",
         "value": [{"media_location": "http://img.test/a.png", "marketplace_id": MP}]},
    ]
    answer = FixtureClient(str(fixture_dir), MP).patch_listing(
        "TESTSELLER", "TEST-SKU-001", "KITCHEN", patches
    )
    assert answer["status"] == "ACCEPTED" and answer["submissionId"]
    client = FixtureClient(str(fixture_dir), MP)
    content = content_from_catalog(client.get_catalog_item_full("B0TEST0001"), MP)
    assert content.title == "TESTBRAND Mestolo nuovo"
    assert content.bullets == ["Uno", "Tre"]
    assert [i.url for i in content.images] == [
        "http://img.test/main.png", "http://img.test/b.png", "http://img.test/a.png"
    ]
    listing = client.get_listing("TESTSELLER", "TEST-SKU-001")
    assert listing["attributes"]["generic_keyword"][0]["value"] == "parole nuove"


def test_live_patch_with_errors_is_invalid_and_writes_nothing(fixture_dir):
    client = FixtureClient(str(fixture_dir), MP)
    answer = client.patch_listing("TESTSELLER", "TEST-SKU-001", "KITCHEN", _title_patch("x" * 201))
    assert answer["status"] == "INVALID"
    assert client.get_catalog_item_full("B0TEST0001")["attributes"]["item_name"][0]["value"] == (
        "TESTBRAND Mestolo"
    )
    unknown = client.patch_listing("TESTSELLER", "TEST-SKU-404", "KITCHEN", _title_patch("Nuovo"),
                                   mode="VALIDATION_PREVIEW")
    assert unknown["status"] == "INVALID"


def test_image_delete_removes_the_slot(fixture_dir):
    client = FixtureClient(str(fixture_dir), MP)
    client.patch_listing("TESTSELLER", "TEST-SKU-001", "KITCHEN", [
        {"op": "delete", "path": "/attributes/other_product_image_locator_2",
         "value": [{"marketplace_id": MP}]},
    ])
    content = content_from_catalog(client.get_catalog_item_full("B0TEST0001"), MP)
    assert [i.variant for i in content.images] == ["MAIN", "PT01"]


def test_variation_patch_reattaches_the_child(fixture_dir):
    client = FixtureClient(str(fixture_dir), MP)
    answer = client.patch_listing("TESTSELLER", "TEST-SKU-012", "KITCHEN", [
        {"op": "replace", "path": "/attributes/parentage_level",
         "value": [{"marketplace_id": MP, "value": "child"}]},
        {"op": "replace", "path": "/attributes/child_parent_sku_relationship",
         "value": [{"marketplace_id": MP, "child_relationship_type": "variation",
                    "parent_sku": "TEST-SKU-010"}]},
        {"op": "replace", "path": "/attributes/variation_theme", "value": [{"name": "COLOR"}]},
    ])
    assert answer["status"] == "ACCEPTED"
    child = content_from_catalog(client.get_catalog_item_full("B0TEST0012"), MP)
    parent = content_from_catalog(client.get_catalog_item_full("B0TEST0010"), MP)
    assert child.parent_asins == ["B0TEST0010"]
    assert parent.child_asins == ["B0TEST0011", "B0TEST0012"]
    assert "child_parent_sku_relationship" not in child.attributes


def test_put_listing_preview_and_create(fixture_dir):
    client = FixtureClient(str(fixture_dir), MP)
    attributes = {"item_name": _text("TESTBRAND Nuovo articolo"), "brand": _text("TESTBRAND")}
    preview = client.put_listing("TESTSELLER", "TEST-SKU-NEW", "KITCHEN", attributes,
                                 mode="VALIDATION_PREVIEW")
    assert preview["status"] == "VALID"
    with pytest.raises(AmazonAPIError):
        client.get_listing("TESTSELLER", "TEST-SKU-NEW")
    assert client.put_listing("TESTSELLER", "TEST-SKU-NEW", "KITCHEN", attributes)["status"] == "ACCEPTED"
    assert client.get_listing("TESTSELLER", "TEST-SKU-NEW")["attributes"]["brand"] == _text("TESTBRAND")


def test_feed_round_trip(fixture_dir):
    client = FixtureClient(str(fixture_dir), MP)
    document = {
        "header": {"sellerId": "TESTSELLER", "version": "2.0", "issueLocale": "it_IT"},
        "messages": [
            {"messageId": 1, "sku": "TEST-SKU-001", "operationType": "PATCH", "productType": "KITCHEN",
             "patches": _title_patch("TESTBRAND Da feed")},
            {"messageId": 2, "sku": "TEST-SKU-001", "operationType": "PATCH", "productType": "KITCHEN",
             "patches": _title_patch("y" * 250)},
        ],
    }
    feed_id = client.submit_json_listings_feed(document)
    status = client.get_feed_status(feed_id)
    assert status["processingStatus"] == "DONE"
    report = client.get_feed_result(status["resultFeedDocumentId"])
    assert [(i["messageId"], i["severity"]) for i in report["issues"]] == [(2, "ERROR")]
    assert [f["feedId"] for f in client.list_recent_feeds(page_size=5)] == [feed_id]
    content = content_from_catalog(client.get_catalog_item_full("B0TEST0001"), MP)
    assert content.title == "TESTBRAND Da feed"
