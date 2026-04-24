from decimal import Decimal
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.amazon.sp_api_client import SPAPIClient
from app.services.market_research_service import _fetch_product_data


def _make_client() -> SPAPIClient:
    client = SPAPIClient.__new__(SPAPIClient)
    client.account_type = "seller"
    client.marketplace = SimpleNamespace(marketplace_id="ATVPDKIKX0DER")
    return client


def test_extract_catalog_price_amount_reads_attribute_schedule():
    client = _make_client()

    payload = {
        "attributes": {
            "our_price": [
                {
                    "schedule": [
                        {
                            "value_with_tax": "19.99",
                        }
                    ]
                }
            ]
        }
    }

    assert client._extract_catalog_price_amount(payload) == Decimal("19.99")


def test_get_competitive_pricing_falls_back_to_catalog_price(monkeypatch):
    client = _make_client()
    catalog_payload = {
        "attributes": {
            "list_price": [
                {
                    "value": "24.50",
                }
            ]
        }
    }
    products_api = SimpleNamespace(
        get_competitive_pricing_for_asins=lambda _asins: SimpleNamespace(payload={"products": []}),
        get_item_offers=lambda **_kwargs: SimpleNamespace(payload={"offers": []}),
    )

    monkeypatch.setattr(client, "_products_api", lambda: products_api)
    monkeypatch.setattr(client, "get_catalog_item_details", lambda _asin: catalog_payload)
    monkeypatch.setattr(client, "_extract_price_amount", lambda _payload: None)

    assert client.get_competitive_pricing("B0TEST1234") == Decimal("24.50")


def test_search_catalog_by_keyword_populates_price_from_catalog_attributes(monkeypatch):
    client = _make_client()
    call_args = {}
    search_payload = {
        "items": [
            {
                "asin": "B0TEST1234",
                "summaries": [
                    {
                        "itemName": "Example product",
                        "brand": "Acme",
                    }
                ],
                "classifications": [{"displayName": "Kitchen"}],
                "salesRanks": [{"ranks": [{"value": 321}]}],
                "attributes": {
                    "our_price": [
                        {
                            "schedule": [{"value_with_tax": "17.40"}],
                        }
                    ]
                },
            }
        ]
    }

    class FakeCatalogApi:
        def search_catalog_items(self, **kwargs):
            call_args.update(kwargs)
            return SimpleNamespace(payload=search_payload)

    monkeypatch.setattr(client, "_catalog_api", lambda: FakeCatalogApi())

    results = client.search_catalog_by_keyword("example", max_results=20)

    assert call_args["includedData"] == ["summaries", "salesRanks", "classifications", "attributes"]
    assert results == [
        {
            "asin": "B0TEST1234",
            "title": "Example product",
            "brand": "Acme",
            "category": "Kitchen",
            "price": 17.4,
            "bsr": 321,
        }
    ]


def test_get_market_prices_for_asins_uses_batch_pricing_and_batch_offers(monkeypatch):
    client = _make_client()

    competitive_payload = [
        {
            "ASIN": "B0HASPRICE",
            "Product": {
                "CompetitivePricing": {
                    "CompetitivePrices": [
                        {
                            "Price": {
                                "LandedPrice": {"Amount": "11.90"},
                            }
                        }
                    ]
                }
            },
        },
        {
            "ASIN": "B0NEEDSOFFER",
            "Product": {},
        },
    ]
    offers_payload = {
        "responses": [
            {
                "status": {"statusCode": 200},
                "body": {
                    "payload": {
                        "ASIN": "B0NEEDSOFFER",
                        "Offers": [
                            {
                                "ListingPrice": {"Amount": "14.50"},
                                "Shipping": {"Amount": "0.00"},
                            }
                        ],
                    }
                },
                "request": {
                    "uri": "/products/pricing/v0/items/B0NEEDSOFFER/offers",
                },
            }
        ]
    }

    monkeypatch.setattr(client, "_get_competitive_pricing_batch_payload", lambda asins: competitive_payload)
    monkeypatch.setattr(client, "_get_item_offers_batch_payload", lambda asins: offers_payload)

    prices = client.get_market_prices_for_asins(["B0HASPRICE", "B0NEEDSOFFER"])

    assert prices == {
        "B0HASPRICE": Decimal("11.90"),
        "B0NEEDSOFFER": Decimal("14.50"),
    }


def test_search_catalog_by_keyword_paginates_until_limit(monkeypatch):
    client = _make_client()
    calls = []
    payloads = [
        {
            "items": [
                {
                    "asin": "B0PAGEONE",
                    "summaries": [{"itemName": "Page 1", "brand": "Acme"}],
                    "classifications": [{"displayName": "Kitchen"}],
                    "salesRanks": [{"ranks": [{"value": 10}]}],
                    "attributes": {"our_price": [{"schedule": [{"value_with_tax": "9.99"}]}]},
                }
            ],
            "pagination": {"nextToken": "token-2"},
        },
        {
            "items": [
                {
                    "asin": "B0PAGETWO",
                    "summaries": [{"itemName": "Page 2", "brand": "Acme"}],
                    "classifications": [{"displayName": "Kitchen"}],
                    "salesRanks": [{"ranks": [{"value": 20}]}],
                    "attributes": {"our_price": [{"schedule": [{"value_with_tax": "12.99"}]}]},
                }
            ],
        },
    ]

    class FakeCatalogApi:
        def search_catalog_items(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(payload=payloads.pop(0))

    monkeypatch.setattr(client, "_catalog_api", lambda: FakeCatalogApi())

    results = client.search_catalog_by_keyword("example", max_results=2)

    assert len(calls) == 2
    assert calls[1]["pageToken"] == "token-2"
    assert [result["asin"] for result in results] == ["B0PAGEONE", "B0PAGETWO"]


def test_fetch_product_data_uses_catalog_price_when_pricing_is_empty():
    catalog_payload = {
        "summaries": [{"itemName": "Example product", "brand": "Acme"}],
        "classifications": [{"displayName": "Kitchen"}],
        "salesRanks": [{"ranks": [{"value": 321}]}],
        "attributes": {
            "our_price": [
                {
                    "schedule": [{"value_with_tax": "31.20"}],
                }
            ]
        },
    }

    class FakeCatalogApi:
        def get_catalog_item(self, **_kwargs):
            return SimpleNamespace(payload=catalog_payload)

    class FakeProductsApi:
        def get_competitive_pricing_for_asins(self, _asins):
            return SimpleNamespace(payload={"products": []})

        def get_item_offers(self, **_kwargs):
            return SimpleNamespace(payload={"offers": []})

    class FakeClient:
        is_vendor = False
        marketplace = SimpleNamespace(marketplace_id="ATVPDKIKX0DER")

        def _catalog_api(self):
            return FakeCatalogApi()

        def _products_api(self):
            return FakeProductsApi()

        def _extract_price_amount(self, _payload):
            return None

        def _extract_catalog_price_amount(self, _payload):
            return Decimal("31.20")

    snapshot = _fetch_product_data(FakeClient(), "B0TEST1234")

    assert snapshot["asin"] == "B0TEST1234"
    assert snapshot["title"] == "Example product"
    assert snapshot["brand"] == "Acme"
    assert snapshot["category"] == "Kitchen"
    assert snapshot["bsr"] == 321
    assert snapshot["price"] == 31.2
