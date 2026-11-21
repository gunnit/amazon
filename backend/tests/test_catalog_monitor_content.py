"""ListingContent normalisation from Catalog Items / Listings Items payloads (R1-R3)."""
import copy
import json
from pathlib import Path

from app.services.catalog_monitor.content import (
    VOLATILE_ATTRIBUTES,
    ListingContent,
    attribute_text,
    content_from_catalog,
    content_from_dict,
    content_hash,
    content_to_dict,
    merge_listing,
    with_aplus,
)

MP = "APJ6JRA9NG5V4"
FIX = Path(__file__).parent / "fixtures" / "catalog_monitor"


def load(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def test_child_payload_extracts_text_fields():
    c = content_from_catalog(load("catalog_child.json"), MP)
    assert c.asin == "B0TEST0001"
    assert c.marketplace_id == MP
    assert c.title == "TESTBRAND Prodotto di prova 500 ml"
    assert c.brand == "TESTBRAND"
    assert c.bullets == [f"Punto elenco {i}" for i in range(1, 6)]
    assert c.description == "Descrizione di prova del prodotto."
    assert c.item_highlights == "Highlight uno"
    assert c.product_type == "HEALTH_PERSONAL_CARE"
    assert c.classification_path == ["Root", "Mid", "Leaf"]
    assert c.browse_node_id == "333"


def test_images_main_first_and_largest_variant():
    c = content_from_catalog(load("catalog_child.json"), MP)
    assert [i.variant for i in c.images] == ["MAIN", "PT01", "PT02", "PT03", "PT10"]
    by = {i.variant: i for i in c.images}
    assert by["MAIN"].width == 1000 and by["MAIN"].url.endswith("MAIN-1000.jpg")
    assert by["PT01"].width == 1500
    assert "SWCH" not in by


def test_relationships_child_has_parent():
    c = content_from_catalog(load("catalog_child.json"), MP)
    assert c.parent_asins == ["B0TEST0100"]
    assert c.child_asins == []
    assert c.variation_theme == "COLOR"


def test_parent_payload_lists_children_and_theme():
    c = content_from_catalog(load("catalog_parent.json"), MP)
    assert c.child_asins == ["B0TEST0001", "B0TEST0002", "B0TEST0003"]
    assert c.parent_asins == []
    assert c.variation_theme == "COLOR"


def test_vendor_minimal_payload_has_grey_fields():
    c = content_from_catalog(load("catalog_vendor_minimal.json"), MP)
    assert c.title == "TESTBRAND Vendor di prova"
    assert c.bullets == []
    assert c.backend_keywords is None
    assert c.backend_keywords_readable is False
    assert c.listing_status is None
    assert c.sku is None
    assert c.has_video is None and c.aplus_module_count is None
    assert [i.variant for i in c.images] == ["MAIN", "PT01", "PT02"]


def test_merge_listing_sets_backend_keywords_and_issues():
    base = content_from_catalog(load("catalog_child.json"), MP)
    original = copy.deepcopy(content_to_dict(base))
    merged = merge_listing(base, load("listing_seller.json"))
    assert merged.sku == "TEST-SKU-001"
    assert merged.backend_keywords == "parola uno parola due"
    assert merged.backend_keywords_readable is True
    assert merged.listing_status == ["BUYABLE", "DISCOVERABLE"]
    assert merged.listing_issues[0]["code"] == "90220"
    # catalogue wins for shopper-visible text
    assert merged.title == base.title
    assert merged.bullets == base.bullets
    assert merged.attributes["special_feature"][0]["value"] == "Resistente"
    assert "merchant_shipping_group" not in merged.attributes
    # input not mutated
    assert content_to_dict(base) == original


def test_hash_ignores_issues_but_tracks_bullet_order():
    c = merge_listing(content_from_catalog(load("catalog_child.json"), MP), load("listing_seller.json"))
    h = content_hash(c)
    other_issues = merge_listing(c, {**load("listing_seller.json"), "issues": []})
    assert content_hash(other_issues) == h
    swapped = content_from_dict(content_to_dict(c))
    swapped.bullets[0], swapped.bullets[1] = swapped.bullets[1], swapped.bullets[0]
    assert content_hash(swapped) != h


def test_round_trip_dict():
    c = with_aplus(
        merge_listing(content_from_catalog(load("catalog_child.json"), MP), load("listing_seller.json")),
        3,
        True,
    )
    d = content_to_dict(c)
    assert json.loads(json.dumps(d)) == d
    assert content_from_dict(d) == c
    assert isinstance(c, ListingContent)
    assert c.aplus_module_count == 3 and c.aplus_available is True


def test_volatile_attributes_removed():
    c = content_from_catalog(load("catalog_child.json"), MP)
    for key in ("purchasable_offer", "list_price", "condition_type"):
        assert key in VOLATILE_ATTRIBUTES
        assert key not in c.attributes
    assert "color" in c.attributes


def test_attribute_text_filters_marketplace_in_order():
    attrs = load("catalog_child.json")["attributes"]
    values = attribute_text(attrs, "bullet_point", MP)
    assert values == [f"Punto elenco {i}" for i in range(1, 6)]
    assert len(attribute_text(attrs, "bullet_point")) == 6
    assert attribute_text(attrs, "missing", MP) == []
