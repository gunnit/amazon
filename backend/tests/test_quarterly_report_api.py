"""Quarterly report API, brand list and dashboard brand/category scope (R5)."""
from datetime import date
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from app.api import deps
from app.api.v1 import analytics, catalog, reports
from app.schemas.report import ScheduledReportCreate
from app.services.data_extraction import DAILY_TOTAL_ASIN

ORG = SimpleNamespace(id=uuid4())
USER = SimpleNamespace(id=uuid4())
ACC_1, ACC_2 = uuid4(), uuid4()
PPTX = "application/vnd.openxmlformats-officedocument.presentationml.presentation"


class _Result:
    def __init__(self, values):
        self._values = values

    def scalars(self):
        return self

    def all(self):
        return self._values


class _FakeDb:
    def __init__(self, values):
        self.values, self.statements = values, []

    async def execute(self, statement):
        self.statements.append(statement)
        return _Result(self.values)


def _client(router, prefix, db):
    app = FastAPI()
    app.include_router(router, prefix=prefix)

    async def _db():
        yield db

    app.dependency_overrides[deps.get_db] = _db
    app.dependency_overrides[deps.get_current_user] = lambda: USER
    app.dependency_overrides[deps.get_user_organization] = lambda: ORG
    return TestClient(app)


def _body(**overrides):
    body = {"account_ids": [str(ACC_1)], "year": 2026, "quarter": 3, "language": "it"}
    body.update(overrides)
    return body


def _sql(statement) -> str:
    return str(statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))


# ---- POST /reports/quarterly ----


def test_quarterly_endpoint_rejects_quarter_5():
    client = _client(reports.router, "/reports", _FakeDb([ACC_1]))
    assert client.post("/reports/quarterly", json=_body(quarter=5)).status_code == 422
    assert client.post("/reports/quarterly", json=_body(quarter=0)).status_code == 422


@pytest.mark.parametrize(
    "overrides",
    [
        {"year": 2019},
        {"year": 2101},
        {"account_ids": []},
        {"language": "fr"},
        {"asins": [f"B0TEST{i:04d}" for i in range(501)]},
    ],
)
def test_quarterly_endpoint_validates_body(overrides):
    client = _client(reports.router, "/reports", _FakeDb([ACC_1]))
    assert client.post("/reports/quarterly", json=_body(**overrides)).status_code == 422


def test_quarterly_endpoint_unknown_account_is_404():
    client = _client(reports.router, "/reports", _FakeDb([ACC_1]))  # ACC_2 not in the org
    response = client.post("/reports/quarterly", json=_body(account_ids=[str(ACC_1), str(ACC_2)]))
    assert response.status_code == 404


def test_quarterly_endpoint_returns_pptx_attachment(monkeypatch):
    seen = {}

    async def fake_generate(db, scope):
        seen["scope"] = scope
        return b"PPTX-BYTES"

    monkeypatch.setattr(reports, "generate_quarterly_deck", fake_generate)
    client = _client(reports.router, "/reports", _FakeDb([ACC_1]))
    response = client.post(
        "/reports/quarterly",
        json=_body(brand="TESTBRAND", category="Toys", asins=["B0TEST0001"], language="en"),
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith(PPTX)
    assert response.headers["content-disposition"] == 'attachment; filename="report-trimestrale-2026-Q3.pptx"'
    assert response.content == b"PPTX-BYTES"
    scope = seen["scope"]
    assert (scope.organization_id, scope.account_ids) == (ORG.id, [ACC_1])
    assert (scope.year, scope.quarter, scope.language) == (2026, 3, "en")
    assert (scope.brand, scope.category, scope.asins) == ("TESTBRAND", "Toys", ["B0TEST0001"])


def test_quarterly_endpoint_value_error_is_422_with_message(monkeypatch):
    async def fake_generate(db, scope):
        raise ValueError("No Amazon account in scope")

    monkeypatch.setattr(reports, "generate_quarterly_deck", fake_generate)
    client = _client(reports.router, "/reports", _FakeDb([ACC_1]))
    response = client.post("/reports/quarterly", json=_body())
    assert response.status_code == 422
    assert response.json()["detail"] == "No Amazon account in scope"


# ---- GET /catalog/brands ----


def test_brands_are_sorted_distinct_and_non_empty():
    db = _FakeDb(["Zeta", "TESTBRAND", "Alpha ", "Beta", "Zeta", "testbrand"])
    client = _client(catalog.router, "/catalog", db)
    response = client.get("/catalog/brands", params={"account_ids": [str(ACC_1)]})
    assert response.status_code == 200
    assert response.json() == ["Alpha", "Beta", "TESTBRAND", "Zeta"]
    sql = _sql(db.statements[0])
    assert "products.brand IS NOT NULL" in sql
    assert "amazon_accounts.organization_id" in sql


# ---- dashboard brand/category scope ----


def test_dashboard_brand_filter_applied():
    scoped = _sql(analytics._sales_period_query(select(1), date(2026, 7, 1), date(2026, 9, 30), brand="TestBrand"))
    assert "JOIN products" in scoped
    assert "lower(trim(products.brand)) = 'testbrand'" in scoped
    # per-ASIN rows only: the daily-total row is excluded, never summed with them
    assert f"sales_data.asin != '{DAILY_TOTAL_ASIN}'" in scoped
    assert "products.category" not in scoped


def test_dashboard_brand_and_category_combine():
    scoped = _sql(
        analytics._sales_daily_revenue_query(
            select(1), date(2026, 7, 1), date(2026, 9, 30), category="Toys", brand="TESTBRAND"
        )
    )
    assert "lower(trim(products.brand)) = 'testbrand'" in scoped
    assert "trim(products.category) = 'Toys'" in scoped
    assert f"sales_data.asin != '{DAILY_TOTAL_ASIN}'" in scoped


def test_dashboard_without_filter_uses_daily_total_rows():
    plain = _sql(analytics._sales_period_query(select(1), date(2026, 7, 1), date(2026, 9, 30)))
    assert "JOIN products" not in plain
    assert f"sales_data.asin = '{DAILY_TOTAL_ASIN}'" in plain
    blank = _sql(analytics._sales_period_query(select(1), date(2026, 7, 1), date(2026, 9, 30), brand="  "))
    assert "JOIN products" not in blank


# ---- schedule validation ----


def _schedule(**overrides):
    payload = {
        "name": "Trimestrale",
        "report_types": ["quarterly_review"],
        "frequency": "quarterly",
        "format": "pdf",
        "recipients": ["team@example.com"],
        "schedule_config": {"hour": 8, "minute": 0},
    }
    payload.update(overrides)
    return ScheduledReportCreate(**payload)


def test_quarterly_schedule_accepts_hour_and_minute_only():
    assert _schedule().frequency == "quarterly"


@pytest.mark.parametrize(
    "overrides",
    [
        {"schedule_config": {"hour": 25, "minute": 0}},
        {"schedule_config": {"minute": 0}},
        {"report_types": ["sales"]},
        {"report_types": ["quarterly_review", "sales"]},
        {"frequency": "monthly", "schedule_config": {"day_of_month": 1, "hour": 8, "minute": 0}},
    ],
)
def test_quarterly_schedule_rejects_invalid_combinations(overrides):
    with pytest.raises(ValueError):
        _schedule(**overrides)


# ---- trimmed matching and the other scoped paths ----


class _EmptyDb:
    def __init__(self):
        self.statements = []

    async def execute(self, statement):
        self.statements.append(statement)
        return _Result([])


def test_scope_conditions_trim_brand_and_category():
    from app.services.product_scope import product_scope_conditions

    sql = " ".join(_sql(c) for c in product_scope_conditions(" TestBrand ", " Toys "))
    assert "lower(trim(products.brand)) = 'testbrand'" in sql
    assert "trim(products.category) = 'Toys'" in sql


def test_quarterly_scope_asins_use_the_shared_trimmed_predicate():
    import asyncio

    from app.services.quarterly_report.data import fetch_scope_asins

    db = _EmptyDb()
    asyncio.run(fetch_scope_asins(db, [ACC_1], "TestBrand", "Toys", None))
    sql = _sql(db.statements[0])
    assert "lower(trim(products.brand)) = 'testbrand'" in sql
    assert "trim(products.category) = 'Toys'" in sql


@pytest.mark.asyncio
async def test_returns_count_scoped_path_joins_products():
    db = _EmptyDb()
    db.execute_result = None

    async def execute(statement):
        db.statements.append(statement)
        return SimpleNamespace(scalar=lambda: 0)

    db.execute = execute
    await analytics._get_returns_period_count(
        db, select(1), date(2026, 7, 1), date(2026, 9, 30), category="Toys", brand="TESTBRAND"
    )
    sql = _sql(db.statements[0])
    assert "JOIN products" in sql
    assert "lower(trim(products.brand)) = 'testbrand'" in sql
    assert "trim(products.category) = 'Toys'" in sql


@pytest.mark.asyncio
async def test_trends_endpoint_scoped_path_uses_asin_rows():
    db = _EmptyDb()
    await analytics.get_trends(
        current_user=USER, organization=ORG, db=db, metrics=["revenue", "units"],
        start_date=date(2026, 7, 1), end_date=date(2026, 9, 30), account_ids=None,
        brand="TESTBRAND", category=None,
    )
    sql = _sql(db.statements[-1])
    assert "JOIN products" in sql
    assert "lower(trim(products.brand)) = 'testbrand'" in sql
    assert f"sales_data.asin != '{DAILY_TOTAL_ASIN}'" in sql


@pytest.mark.asyncio
async def test_product_trends_sales_timeseries_scoped_path():
    from app.services.product_trends_service import ProductTrendsService

    db = _EmptyDb()
    await ProductTrendsService(db)._sales_timeseries(
        account_ids=[ACC_1], start_date=date(2026, 7, 1), end_date=date(2026, 9, 30),
        brand="TESTBRAND", category="Toys",
    )
    sql = _sql(db.statements[0])
    assert "JOIN products" in sql
    assert "lower(trim(products.brand)) = 'testbrand'" in sql
    assert "trim(products.category) = 'Toys'" in sql
