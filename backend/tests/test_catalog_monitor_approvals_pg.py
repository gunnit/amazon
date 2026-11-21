"""Approval queue against Postgres: FOR UPDATE load and anomaly reopening (skipped without TEST_DATABASE_URL)."""
import os
import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.v1 import catalog_monitor as api
from app.models.amazon_account import AccountType, AmazonAccount
from app.models.catalog_monitor import CatalogAnomaly
from app.models.user import Organization
from app.services.catalog_monitor.changes import ChangeItem, ChangeRequestService

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


@pytest_asyncio.fixture
async def account(db):
    tag = uuid.uuid4().hex[:12]
    org = Organization(name=f"Org {tag}", slug=f"org-{tag}")
    db.add(org)
    await db.flush()
    acc = AmazonAccount(
        organization_id=org.id, account_name=f"Acc {tag}", account_type=AccountType.SELLER,
        marketplace_id="APJ6JRA9NG5V4", marketplace_country="IT", seller_id="SELLER1",
    )
    db.add(acc)
    await db.flush()
    return acc


async def _restore_request(db, account):
    anomaly = CatalogAnomaly(
        account_id=account.id, asin="B0TEST0001", kind="content_changed", field="title",
        baseline_value="old", live_value="new", status="open",
    )
    db.add(anomaly)
    await db.flush()
    item = ChangeItem(
        asin="B0TEST0001", sku="TEST-SKU-001", product_type="LUGGAGE", kind="content_restore",
        patches=[{"op": "replace", "path": "/attributes/item_name", "value": []}],
        anomalies=[anomaly],
    )
    [row] = await ChangeRequestService(db).create(account, [item], None)
    return anomaly, row


@pytest.mark.asyncio
async def test_locked_load_is_scoped_to_the_organization(db, account):
    _, row = await _restore_request(db, account)
    assert [r.id for r in await api._requests_for_update(db, account.organization_id, [row.id])] == [row.id]
    assert await api._requests_for_update(db, uuid.uuid4(), [row.id]) == []


@pytest.mark.asyncio
async def test_rejected_restore_reopens_its_anomaly(db, account):
    anomaly, row = await _restore_request(db, account)
    assert (anomaly.status, anomaly.change_request_id) == ("restore_requested", row.id)
    [locked] = await api._requests_for_update(db, account.organization_id, [row.id])
    await ChangeRequestService(db).reject([locked], None)
    await api._reopen_for_requests(db, [locked])
    await db.flush()  # the route's commit flushes; refresh() alone would discard the change
    await db.refresh(anomaly)
    assert (anomaly.status, anomaly.change_request_id) == ("open", None)


@pytest.mark.asyncio
async def test_pending_restore_keeps_its_anomaly_linked(db, account):
    anomaly, row = await _restore_request(db, account)
    await api._reopen_for_requests(db, [row])  # still pending: nothing to reopen
    await db.refresh(anomaly)
    assert anomaly.status == "restore_requested"


@pytest.mark.asyncio
async def test_marked_upload_persists_as_submitted(db, account):
    item = ChangeItem(
        asin="B0TEST0002", sku=None, product_type="LUGGAGE", kind="bulk_update",
        patches=[{"op": "replace", "path": "/attributes/item_name", "value": []}],
    )
    service = ChangeRequestService(db)
    [row] = await service.create(account, [item], None)  # no SKU: file only
    await service.approve([row], None, True)
    [locked] = await api._requests_for_update(db, account.organization_id, [row.id])
    assert api.mark_uploaded_skip_reason(locked) is None
    api.mark_uploaded([locked], None, datetime.now(timezone.utc))
    await db.flush()
    await db.refresh(row)
    assert row.status == "submitted" and row.submission_result["manual"] is True
