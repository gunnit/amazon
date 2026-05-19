"""Tests for the Brand Analysis data source adapters."""
import asyncio
from datetime import date
from decimal import Decimal
from pathlib import Path
import sys
from types import SimpleNamespace
from uuid import uuid4

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.brand_analysis_service import InsufficientDataError  # noqa: E402
from app.services.brand_analysis_sources import (  # noqa: E402
    AmazonAccountDataSource,
    ManualUploadDataSource,
)


class FakeResult:
    def __init__(self, *, rows=None, scalar=None, scalars=None, one=None):
        self._rows = rows or []
        self._scalar = scalar
        self._scalars = scalars or []
        self._one = one
        self._return_scalars = False

    def all(self):
        return self._scalars if self._return_scalars else self._rows

    def scalar_one_or_none(self):
        return self._scalar

    def one(self):
        return self._one if self._one is not None else (len(self._rows), len(self._rows), None, None)

    def scalars(self):
        self._return_scalars = True
        return self


class FakeDb:
    def __init__(self, rows, products=None, year_summary=None):
        self.rows = rows
        self.products = products or {}
        self.year_summary = year_summary
        self.execute_calls = 0

    async def execute(self, statement):
        self.execute_calls += 1
        statement_text = str(statement)
        if "count(" in statement_text.lower():
            if self.year_summary is not None:
                return FakeResult(one=self.year_summary)
            return FakeResult(one=(len(self.rows), len({row[0] for row in self.rows}), date(2025, 1, 1), date(2025, 12, 31)))
        if "FROM products" in statement_text:
            # The tests use one product snapshot unless they explicitly pass
            # an ASIN-keyed product map; SQLAlchemy bind values are not needed
            # because remote enrichment is monkeypatched below.
            if "products.asin =" in statement_text:
                product = self.products.get("__next__")
                return FakeResult(scalar=product)
            return FakeResult(scalars=self.products.get("__all__", []))
        return FakeResult(rows=self.rows)


def _csv_bytes(rows: list[dict]) -> bytes:
    return pd.DataFrame(rows).to_csv(index=False).encode("utf-8")


def _sample_rows() -> list[dict]:
    return [
        {"ASIN": "B001", "Product Name": "Knife", "Total Revenue": "100"},
        {"ASIN": "B002", "Product Name": "Pan", "Total Revenue": "50"},
    ]


def _run(coro):
    return asyncio.run(coro)


def test_manual_upload_data_source_parses_existing_files():
    files = {
        2024: (_csv_bytes(_sample_rows()), "2024.csv"),
        2025: (_csv_bytes(_sample_rows()), "2025.csv"),
    }
    source = ManualUploadDataSource(source_files=files)

    parsed = _run(source.fetch_year(2025))
    assert parsed.row_count == 2
    assert parsed.source_name == "manual_upload"
    assert parsed.year == 2025
    assert parsed.validation is not None
    assert "asin" in parsed.validation.detected_mapping


def test_manual_upload_data_source_raises_insufficient_when_year_missing():
    files = {2025: (_csv_bytes(_sample_rows()), "2025.csv")}
    source = ManualUploadDataSource(source_files=files)

    try:
        _run(source.fetch_year(2024))
    except InsufficientDataError as exc:
        assert exc.year == 2024
        assert exc.source_name == "manual_upload"
    else:
        raise AssertionError("Expected InsufficientDataError")


def test_amazon_account_data_source_success_path_enriches_internal_rows():
    account_id = uuid4()
    org_id = uuid4()
    source = AmazonAccountDataSource(
        db=FakeDb(rows=[("B001", 12, Decimal("1234.50"))]),
        account_id=account_id,
        organization_id=org_id,
        brand_filter="Acme",
    )

    async def fake_catalog(asin: str):
        return {
            "asin": asin,
            "title": "Chef Knife",
            "brand": "Acme",
            "category": "Kitchen",
            "subcategory": "Knives",
            "price": 102.88,
            "rating": 4.7,
            "review_count": 31,
            "images_count": 8,
            "sellers_count": 2,
            "buy_box_owner": "Seller A",
            "bsr": 12345,
            "status": "active",
        }

    source._fetch_catalog_via_market_research = fake_catalog  # type: ignore[method-assign]

    parsed = _run(source.fetch_year(2025))
    row = parsed.rows.iloc[0]

    assert parsed.source_name == "internal"
    assert row["asin"] == "B001"
    assert row["product_name"] == "Chef Knife"
    assert row["brand"] == "Acme"
    assert row["category"] == "Kitchen"
    assert row["subcategory"] == "Knives"
    assert row["revenue"] == 1234.5
    assert row["units"] == 12
    assert row["image_count"] == 8
    assert row["seller_count"] == 2
    assert row["reseller_count"] == 2
    assert row["buy_box_seller"] == "Seller A"
    assert row["status"] == "active"


def test_amazon_account_data_source_filters_by_brand_from_market_research():
    source = AmazonAccountDataSource(
        db=FakeDb(rows=[("B001", 1, Decimal("10")), ("B002", 1, Decimal("20"))]),
        account_id=uuid4(),
        organization_id=uuid4(),
        brand_filter="Acme",
    )

    async def fake_catalog(asin: str):
        return {
            "asin": asin,
            "title": asin,
            "brand": "Acme" if asin == "B001" else "Other Brand",
            "category": "Kitchen",
        }

    source._fetch_catalog_via_market_research = fake_catalog  # type: ignore[method-assign]

    parsed = _run(source.fetch_year(2025))
    assert list(parsed.rows["asin"]) == ["B001"]


def test_amazon_account_data_source_filters_by_explicit_asin_list():
    source = AmazonAccountDataSource(
        db=FakeDb(rows=[("B001", 1, Decimal("10")), ("B002", 1, Decimal("20"))]),
        account_id=uuid4(),
        organization_id=uuid4(),
        asin_list=["b002"],
    )

    async def fake_catalog(asin: str):
        return {"asin": asin, "title": asin, "brand": "Acme", "category": "Kitchen"}

    source._fetch_catalog_via_market_research = fake_catalog  # type: ignore[method-assign]

    parsed = _run(source.fetch_year(2025))
    assert list(parsed.rows["asin"]) == ["B002"]


def test_amazon_account_data_source_includes_local_brand_asins_without_sales_as_zero():
    product_1 = SimpleNamespace(
        asin="B001",
        title="Acme Knife",
        brand="Acme",
        category="Kitchen",
        subcategory="Knives",
        current_price=Decimal("19.99"),
        current_bsr=321,
        review_count=44,
        rating=Decimal("4.4"),
        is_active=True,
        is_available=True,
    )
    product_2 = SimpleNamespace(
        asin="B002",
        title="Acme Pan",
        brand="Acme",
        category="Kitchen",
        subcategory="Pans",
        current_price=Decimal("29.99"),
        current_bsr=654,
        review_count=8,
        rating=Decimal("4.1"),
        is_active=True,
        is_available=True,
    )
    source = AmazonAccountDataSource(
        db=FakeDb(
            rows=[("B001", 3, Decimal("60"))],
            products={"__all__": [product_1, product_2]},
        ),
        account_id=uuid4(),
        organization_id=uuid4(),
        brand_filter="Acme",
    )

    async def fake_catalog(asin: str):
        return source._catalog_cache.get(asin, {"asin": asin, "brand": "Acme", "title": asin})

    source._fetch_catalog_via_market_research = fake_catalog  # type: ignore[method-assign]

    parsed = _run(source.fetch_year(2025))

    by_asin = {row.asin: row for row in parsed.rows.itertuples(index=False)}
    assert set(by_asin) == {"B001", "B002"}
    assert by_asin["B001"].revenue == 60
    assert by_asin["B002"].revenue == 0
    assert by_asin["B002"].status == "inactive"
    assert source.year_diagnostics[2025]["zero_revenue_asins_count"] == 1


def test_amazon_account_data_source_discovers_brand_asins_via_market_research_search():
    class FakeClient:
        def search_catalog_by_keyword(self, query, max_results=80):
            assert query == "Acme"
            return [
                {"asin": "B001", "title": "Acme Knife", "brand": "Acme", "category": "Kitchen"},
                {"asin": "B003", "title": "Acme Spoon", "brand": "ACME", "category": "Kitchen"},
                {"asin": "B004", "title": "Other Spoon", "brand": "Other", "category": "Kitchen"},
            ]

    source = AmazonAccountDataSource(
        db=FakeDb(rows=[("B001", 2, Decimal("40"))]),
        account_id=uuid4(),
        organization_id=uuid4(),
        brand_filter="Acme",
    )

    async def fake_client():
        return FakeClient()

    async def fake_catalog(asin: str):
        return source._catalog_cache.get(asin, {"asin": asin, "brand": "Acme", "title": asin})

    source._build_sp_api_client = fake_client  # type: ignore[method-assign]
    source._fetch_catalog_via_market_research = fake_catalog  # type: ignore[method-assign]

    parsed = _run(source.fetch_year(2025))

    assert list(parsed.rows["asin"]) == ["B001", "B003"]
    assert parsed.rows.loc[parsed.rows["asin"] == "B003", "revenue"].iloc[0] == 0
    assert source.discovered_asins == {"B001", "B003"}


def test_amazon_account_data_source_raises_for_missing_year_data():
    source = AmazonAccountDataSource(
        db=FakeDb(rows=[]),
        account_id=uuid4(),
        organization_id=uuid4(),
    )

    try:
        _run(source.fetch_year(2024))
    except InsufficientDataError as exc:
        assert exc.year == 2024
        assert exc.source_name == "internal"
        assert "no synced sales_data" in str(exc)
    else:
        raise AssertionError("Expected InsufficientDataError")


def test_amazon_account_data_source_raises_for_missing_2025_data():
    source = AmazonAccountDataSource(
        db=FakeDb(rows=[]),
        account_id=uuid4(),
        organization_id=uuid4(),
    )

    try:
        _run(source.fetch_year(2025))
    except InsufficientDataError as exc:
        assert exc.year == 2025
        assert exc.source_name == "internal"
    else:
        raise AssertionError("Expected InsufficientDataError")


def test_amazon_account_data_source_uses_local_product_snapshot_when_available():
    product = SimpleNamespace(
        title="Local Knife",
        brand="Acme",
        category="Kitchen",
        subcategory="Knives",
        current_price=Decimal("19.99"),
        current_bsr=321,
        review_count=44,
        rating=Decimal("4.4"),
        is_active=True,
        is_available=True,
    )
    source = AmazonAccountDataSource(
        db=FakeDb(rows=[("B001", 2, Decimal("40"))], products={"__next__": product}),
        account_id=uuid4(),
        organization_id=uuid4(),
    )

    async def fake_catalog(_asin: str):
        return {}

    source._fetch_catalog_via_market_research = fake_catalog  # type: ignore[method-assign]

    parsed = _run(source.fetch_year(2025))
    row = parsed.rows.iloc[0]
    assert row["product_name"] == "Local Knife"
    assert row["price"] == 19.99
    assert row["reviews"] == 44
    assert row["bsr"] == 321


def test_amazon_account_data_source_marks_partial_catalog_enrichment():
    source = AmazonAccountDataSource(
        db=FakeDb(rows=[("B001", 1, Decimal("10")), ("B002", 1, Decimal("20"))]),
        account_id=uuid4(),
        organization_id=uuid4(),
    )

    async def fake_catalog(asin: str):
        return {"asin": asin, "title": "Good", "brand": "Acme"} if asin == "B001" else {"asin": asin}

    source._fetch_catalog_via_market_research = fake_catalog  # type: ignore[method-assign]

    _run(source.fetch_year(2025))
    assert source.enrichment_partial is True
