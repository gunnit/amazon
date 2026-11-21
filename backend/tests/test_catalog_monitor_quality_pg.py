"""Latest-snapshot-per-ASIN query against Postgres (skipped without TEST_DATABASE_URL)."""
import os
import uuid
from datetime import date

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.v1.catalog_monitor import _load_quality_rows, split_scanned
from app.models.amazon_account import AccountType, AmazonAccount
from app.models.listing_quality import ListingQualitySnapshot
from app.models.product import Product
from app.models.user import Organization

pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL not set"
)


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine(os.environ["TEST_DATABASE_URL"])
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        yield session
        await session.rollback()
    await engine.dispose()


def _account(org_id, tag):
    return AmazonAccount(
        organization_id=org_id,
        account_name=f"Acc {tag}",
        account_type=AccountType.SELLER,
        marketplace_id="APJ6JRA9NG5V4",
        marketplace_country="IT",
        seller_id="SELLER1",
    )


def _snap(account_id, asin, day, score, state):
    return ListingQualitySnapshot(
        account_id=account_id, asin=asin, snapshot_date=day, score=score,
        components={"asin": asin, "state": state, "score": score, "results": []},
    )


@pytest.mark.asyncio
async def test_latest_snapshot_per_asin_scoped_to_account(db):
    tag = uuid.uuid4().hex[:12]
    org = Organization(name=f"Org {tag}", slug=f"org-{tag}")
    db.add(org)
    await db.flush()
    mine, other = _account(org.id, tag), _account(org.id, tag + "x")
    db.add_all([mine, other])
    await db.flush()
    db.add_all([
        Product(account_id=mine.id, asin="B0TEST0001", sku="TEST-SKU-001", title="One", is_active=True),
        Product(account_id=mine.id, asin="B0TEST0002", sku="TEST-SKU-002", title="Two", is_active=True),
        Product(account_id=mine.id, asin="B0TEST0003", sku="TEST-SKU-003", title="Off", is_active=False),
        Product(account_id=other.id, asin="B0TEST0001", sku="TEST-SKU-001", title="Other", is_active=True),
        Product(account_id=other.id, asin="B0TEST0009", sku="TEST-SKU-009", title="Other 9", is_active=True),
    ])
    db.add_all([
        _snap(mine.id, "B0TEST0001", date(2026, 11, 19), 30, "red"),
        _snap(mine.id, "B0TEST0001", date(2026, 11, 21), 90, "green"),
        _snap(mine.id, "B0TEST0003", date(2026, 11, 21), 50, "yellow"),
        _snap(other.id, "B0TEST0001", date(2026, 11, 21), 10, "red"),
        _snap(other.id, "B0TEST0009", date(2026, 11, 21), 10, "red"),
    ])
    await db.flush()

    rows = await _load_quality_rows(db, mine.id)
    assert sorted(r["asin"] for r in rows) == ["B0TEST0001", "B0TEST0002"]
    items, unscanned = split_scanned(rows)
    assert [(i["asin"], i["score"], i["state"]) for i in items] == [("B0TEST0001", 90, "green")]
    assert unscanned == 1
    assert [r["asin"] for r in await _load_quality_rows(db, mine.id, search="two")] == ["B0TEST0002"]
