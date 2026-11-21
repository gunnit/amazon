"""Catalogue monitor repository against Postgres (skipped without TEST_DATABASE_URL).

Each test creates its own organisation and account with unique names and rolls
the session back at the end, so nothing is left in the database.
"""
import os
import uuid
from datetime import date, datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.amazon_account import AccountType, AmazonAccount
from app.models.listing_quality import ListingQualitySnapshot
from app.models.user import Organization
from app.services.catalog_monitor.content import ListingContent
from app.services.catalog_monitor.repository import CatalogMonitorRepository
from app.services.catalog_monitor.rules import ListingEvaluation

pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL not set"
)

NOW = datetime(2026, 11, 21, 5, 0, tzinfo=timezone.utc)


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine(os.environ["TEST_DATABASE_URL"])
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        yield session
        await session.rollback()
    await engine.dispose()


@pytest_asyncio.fixture
async def account(db):
    tag = uuid.uuid4().hex[:12]
    org = Organization(name=f"Org {tag}", slug=f"org-{tag}")
    db.add(org)
    await db.flush()
    acc = AmazonAccount(
        organization_id=org.id,
        account_name=f"Acc {tag}",
        account_type=AccountType.SELLER,
        marketplace_id="APJ6JRA9NG5V4",
        marketplace_country="IT",
        seller_id="SELLER1",
    )
    db.add(acc)
    await db.flush()
    return acc


def _content(title="Title"):
    return ListingContent(asin="B0TEST0001", marketplace_id="APJ6JRA9NG5V4", title=title)


@pytest.mark.asyncio
async def test_save_version_dedupes_by_hash(db, account):
    repo = CatalogMonitorRepository(db)
    first, is_new = await repo.save_version(account.id, "B0TEST0001", _content(), NOW)
    assert is_new is True
    later = datetime(2026, 11, 22, 5, 0, tzinfo=timezone.utc)
    same, is_new = await repo.save_version(account.id, "B0TEST0001", _content(), later)
    assert is_new is False
    assert same.id == first.id
    assert same.last_seen_at == later
    changed, is_new = await repo.save_version(account.id, "B0TEST0001", _content("Other"), later)
    assert is_new is True and changed.id != first.id
    assert len(await repo.versions(account.id, "B0TEST0001")) == 2
    latest = await repo.latest_versions(account.id)
    assert latest["B0TEST0001"].id == changed.id


@pytest.mark.asyncio
async def test_save_version_a_b_a_creates_a_new_row(db, account):
    repo = CatalogMonitorRepository(db)
    t1, t2, t3, t4 = (datetime(2026, 11, d, 5, 0, tzinfo=timezone.utc) for d in (21, 22, 23, 24))
    a1, is_new = await repo.save_version(account.id, "B0TEST0001", _content("A"), t1)
    assert is_new is True
    b, is_new = await repo.save_version(account.id, "B0TEST0001", _content("B"), t2)
    assert is_new is True
    a2, is_new = await repo.save_version(account.id, "B0TEST0001", _content("A"), t3)
    assert is_new is True and a2.id not in (a1.id, b.id)
    assert a2.content_hash == a1.content_hash
    assert (await repo.latest_versions(account.id))["B0TEST0001"].id == a2.id
    same, is_new = await repo.save_version(account.id, "B0TEST0001", _content("A"), t4)
    assert is_new is False and same.id == a2.id and same.last_seen_at == t4
    assert len(await repo.versions(account.id, "B0TEST0001")) == 3


@pytest.mark.asyncio
async def test_latest_versions_returns_one_row_per_asin(db, account):
    repo = CatalogMonitorRepository(db)
    t1, t2 = (datetime(2026, 11, d, 5, 0, tzinfo=timezone.utc) for d in (21, 22))
    await repo.save_version(account.id, "B0TEST0001", _content("A"), t1)
    newest_1, _ = await repo.save_version(account.id, "B0TEST0001", _content("B"), t2)
    newest_2, _ = await repo.save_version(account.id, "B0TEST0002", _content("C"), t1)

    latest = await repo.latest_versions(account.id)
    assert {asin: row.id for asin, row in latest.items()} == {
        "B0TEST0001": newest_1.id,
        "B0TEST0002": newest_2.id,
    }
    only = await repo.latest_versions(account.id, ["B0TEST0002"])
    assert list(only) == ["B0TEST0002"]
    assert await repo.latest_versions(account.id, []) == {}


@pytest.mark.asyncio
async def test_open_or_touch_anomaly_no_duplicate(db, account):
    repo = CatalogMonitorRepository(db)
    a1, opened = await repo.open_or_touch_anomaly(
        account.id, "B0TEST0001", "content_changed", "title", "A", "B", NOW
    )
    assert opened is True
    a2, opened = await repo.open_or_touch_anomaly(
        account.id, "B0TEST0001", "content_changed", "title", "A", "B", NOW
    )
    assert opened is False and a2.id == a1.id
    open_ = await repo.open_anomalies(account.id)
    assert list(open_) == [("B0TEST0001", "content_changed", "title")]
    touched, opened = await repo.open_or_touch_anomaly(
        account.id, "B0TEST0001", "content_changed", "title", "A", "C", NOW
    )
    assert opened is False and touched.id == a1.id and touched.live_value == "C"
    other, opened = await repo.open_or_touch_anomaly(
        account.id, "B0TEST0001", "content_changed", "description", "A", "B", NOW
    )
    assert opened is True and other.id != a1.id


@pytest.mark.asyncio
async def test_resolve_then_reopen_creates_new_row(db, account):
    repo = CatalogMonitorRepository(db)
    a1, _ = await repo.open_or_touch_anomaly(
        account.id, "B0TEST0001", "content_changed", "title", "A", "B", NOW
    )
    await repo.resolve_anomaly(a1, NOW)
    assert a1.status == "resolved" and a1.resolved_at == NOW
    assert await repo.open_anomalies(account.id) == {}
    a2, opened = await repo.open_or_touch_anomaly(
        account.id, "B0TEST0001", "content_changed", "title", "A", "B", NOW
    )
    assert opened is True and a2.id != a1.id


@pytest.mark.asyncio
async def test_baselines_quality_snapshot_and_capability_upsert(db, account):
    repo = CatalogMonitorRepository(db)
    b1 = await repo.upsert_baseline(account.id, "B0TEST0001", _content(), "live_snapshot", None)
    b2 = await repo.upsert_baseline(account.id, "B0TEST0001", _content("New"), "excel_upload", None)
    assert b1.id == b2.id and b2.source == "excel_upload"
    assert (await repo.baselines(account.id))["B0TEST0001"].content["title"] == "New"

    f1 = await repo.upsert_family_baseline(account.id, "B0TEST0002", "COLOR", ["B0TEST0003"])
    f2 = await repo.upsert_family_baseline(account.id, "B0TEST0002", "SIZE", ["B0TEST0003", "B0TEST0004"])
    assert f1.id == f2.id and f2.child_asins == ["B0TEST0003", "B0TEST0004"]
    assert len(await repo.family_baselines(account.id)) == 1

    ev = ListingEvaluation("B0TEST0001", "green", 90, [])
    day = date(2026, 11, 21)
    await repo.save_quality_snapshot(account.id, "B0TEST0001", ev, day)
    ev2 = ListingEvaluation("B0TEST0001", "amber", 70, [])
    await repo.save_quality_snapshot(account.id, "B0TEST0001", ev2, day)
    rows = (await db.execute(
        ListingQualitySnapshot.__table__.select().where(
            ListingQualitySnapshot.account_id == account.id
        )
    )).all()
    assert len(rows) == 1 and rows[0].score == 70

    assert await repo.capability(account.id) is None
    await repo.save_capability(account.id, {"feeds": {"ok": True, "error": None}}, None, NOW)
    cap = await repo.save_capability(account.id, {"feeds": {"ok": False, "error": "x"}}, "VND01", NOW)
    assert cap.vendor_code == "VND01"
    assert (await repo.capability(account.id)).results["feeds"]["ok"] is False
