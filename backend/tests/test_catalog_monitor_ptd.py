"""Product type requirements (R1, R4): required attributes and cache."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import httpx
import pytest

from app.core.exceptions import AmazonAPIError
from app.services.catalog_monitor.ptd import (
    ProductTypeDefinitionService,
    required_attributes_from_schema,
)

MKT = "APJ6JRA9NG5V4"


class FakeResult:
    def __init__(self, row):
        self._row = row

    def scalar_one_or_none(self):
        return self._row


class FakeDb:
    def __init__(self, row=None):
        self.row = row
        self.added = []

    async def execute(self, _stmt):
        return FakeResult(self.row)

    def add(self, obj):
        self.added.append(obj)


class FakeClient:
    def __init__(self, schema=None, exc=None, schema_exc=None):
        self.schema = schema
        self.exc = exc
        self.schema_exc = schema_exc
        self.calls = 0

    def get_product_type_definition(self, product_type, seller_id=None, locale="it_IT"):
        self.calls += 1
        if self.exc:
            raise self.exc
        return {"schema": {"link": {"resource": "https://example.test/s.json", "verb": "GET"}}}

    def fetch_json_schema(self, url):
        if self.schema_exc:
            raise self.schema_exc
        return self.schema


SCHEMA = {
    "required": [
        "item_name",
        "brand",
        "purchasable_offer",
        "list_price",
        "externally_assigned_product_identifier",
        "merchant_suggested_asin",
        "bullet_point",
    ],
    "properties": {"item_name": {}, "brand": {}, "bullet_point": {}},
}


def _row(age_days, required=("brand",), naive=False):
    ts = datetime.now(timezone.utc) - timedelta(days=age_days)
    if naive:
        ts = ts.replace(tzinfo=None)
    return SimpleNamespace(
        marketplace_id=MKT,
        product_type="TESTTYPE",
        required_attributes=list(required),
        property_names=[],
        fetched_at=ts,
    )


def test_required_from_schema_drops_offer_attributes():
    assert required_attributes_from_schema(SCHEMA) == ["brand", "bullet_point", "item_name"]


@pytest.mark.asyncio
async def test_cache_hit_skips_api():
    db = FakeDb(_row(1, ("brand", "item_name")))
    client = FakeClient(SCHEMA)
    out = await ProductTypeDefinitionService(db).required_attributes(client, MKT, "TESTTYPE")
    assert out == ["brand", "item_name"]
    assert client.calls == 0


@pytest.mark.asyncio
async def test_cache_hit_with_naive_timestamp():
    db = FakeDb(_row(1, naive=True))
    client = FakeClient(SCHEMA)
    out = await ProductTypeDefinitionService(db).required_attributes(client, MKT, "TESTTYPE")
    assert out == ["brand"]
    assert client.calls == 0


@pytest.mark.asyncio
async def test_miss_fetches_and_stores():
    db = FakeDb(None)
    out = await ProductTypeDefinitionService(db).required_attributes(
        FakeClient(SCHEMA), MKT, "TESTTYPE"
    )
    assert out == ["brand", "bullet_point", "item_name"]
    assert len(db.added) == 1
    assert db.added[0].property_names == ["brand", "bullet_point", "item_name"]
    assert db.added[0].fetched_at is not None


@pytest.mark.asyncio
async def test_expired_row_is_refreshed_in_place():
    row = _row(30)
    db = FakeDb(row)
    out = await ProductTypeDefinitionService(db).required_attributes(
        FakeClient(SCHEMA), MKT, "TESTTYPE"
    )
    assert out == ["brand", "bullet_point", "item_name"]
    assert row.required_attributes == out
    assert db.added == []


@pytest.mark.asyncio
async def test_api_failure_returns_none_without_cache():
    db = FakeDb(None)
    client = FakeClient(exc=AmazonAPIError("boom"))
    assert await ProductTypeDefinitionService(db).required_attributes(client, MKT, "T") is None
    client = FakeClient(schema_exc=httpx.ConnectError("down"))
    assert await ProductTypeDefinitionService(db).required_attributes(client, MKT, "T") is None


@pytest.mark.asyncio
async def test_api_failure_returns_stale_cache():
    db = FakeDb(_row(30, ("brand", "color")))
    client = FakeClient(exc=AmazonAPIError("boom"))
    out = await ProductTypeDefinitionService(db).required_attributes(client, MKT, "TESTTYPE")
    assert out == ["brand", "color"]


def _on_event_loop() -> bool:
    import asyncio

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return False
    return True


@pytest.mark.asyncio
async def test_amazon_calls_run_off_the_event_loop():
    class LoopCheckingClient(FakeClient):
        def get_product_type_definition(self, product_type, seller_id=None, locale="it_IT"):
            self.on_loop = _on_event_loop()
            return super().get_product_type_definition(product_type, seller_id, locale)

    client = LoopCheckingClient(schema=SCHEMA)
    assert await ProductTypeDefinitionService(FakeDb()).required_attributes(client, MKT, "T")
    assert client.on_loop is False  # a blocking SP-API call never stalls the API
