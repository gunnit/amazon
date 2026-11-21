"""Daily catalogue scan against Postgres (skipped without TEST_DATABASE_URL).

Checks what the in-memory fakes cannot: per-product savepoints keep a database
error on one product from breaking the rest of the scan, and the real
repository neither duplicates anomalies nor versions across scans. The scan
commits, so the test deletes its organisation (cascading to everything it
created) and its image and product-type cache rows at the end.
"""
import copy
import io
import json
import os
import pathlib
import uuid

import pytest
import pytest_asyncio
from PIL import Image
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.amazon_account import AccountType, AmazonAccount
from app.models.catalog_monitor import ImageCheck, ProductTypeDefinitionCache
from app.models.listing_quality import ListingQualitySnapshot
from app.models.product import Product
from app.models.user import Organization
from app.services.catalog_monitor.content import content_from_catalog
from app.services.catalog_monitor.repository import CatalogMonitorRepository
from app.services.catalog_monitor.scanner import CatalogScanService

pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL not set"
)

MKT = "APJ6JRA9NG5V4"
FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "catalog_monitor" / "catalog_vendor_minimal.json"


@pytest_asyncio.fixture
async def session_factory():
    engine = create_async_engine(os.environ["TEST_DATABASE_URL"])
    yield async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    await engine.dispose()


@pytest_asyncio.fixture
async def account(session_factory):
    tag = uuid.uuid4().hex[:12]
    async with session_factory() as db:
        org = Organization(name=f"Org {tag}", slug=f"org-{tag}")
        db.add(org)
        await db.flush()
        acc = AmazonAccount(
            organization_id=org.id,
            account_name=f"Acc {tag}",
            account_type=AccountType.SELLER,
            marketplace_id=MKT,
            marketplace_country="IT",
            seller_id="SELLER1",
        )
        db.add(acc)
        await db.flush()
        for asin in ("B0TEST0001", "B0TEST0002", "B0TEST0003"):
            db.add(Product(account_id=acc.id, asin=asin, is_active=True))
        await db.commit()
    yield acc, tag
    async with session_factory() as db:
        await db.execute(delete(Organization).where(Organization.id == acc.organization_id))
        await db.execute(delete(ImageCheck).where(ImageCheck.url.contains(tag)))
        await db.execute(
            delete(ProductTypeDefinitionCache).where(
                ProductTypeDefinitionCache.product_type == f"PT_{tag}"
            )
        )
        await db.commit()


def _item(asin: str, tag: str, title: str = "TESTBRAND Vendor di prova") -> dict:
    payload = json.loads(FIXTURE.read_text())
    payload["asin"] = asin
    payload["attributes"]["item_name"][0]["value"] = title
    payload["productTypes"][0]["productType"] = f"PT_{tag}"
    for image in payload["images"][0]["images"]:
        image["link"] = image["link"].replace("example.test", f"{tag}.example.test")
    return payload


class Client:
    def __init__(self, catalog):
        self.catalog = catalog

    def get_catalog_item_full(self, asin):
        return copy.deepcopy(self.catalog[asin])

    def get_product_type_definition(self, product_type, seller_id=None, locale="it_IT"):
        return {"schema": {"link": {"resource": "https://example.test/schema.json"}}}

    def fetch_json_schema(self, url):
        return {"required": ["item_name", "brand"], "properties": {}}


async def _png(url: str) -> bytes:
    img = Image.new("RGB", (100, 100), "white")
    img.paste((20, 20, 20), (5, 5, 95, 95))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def _service(db, client):
    return CatalogScanService(
        db, client_factory=lambda account, org: client, image_fetch=_png, sleep=lambda _s: None
    )


@pytest.mark.asyncio
async def test_scan_on_postgres_isolates_a_failing_product_and_keeps_anomalies_unique(
    session_factory, account
):
    acc, tag = account
    broken = _item("B0TEST0002", tag)
    broken["attributes"]["color"] = [{"value": float("nan"), "marketplace_id": MKT}]  # not JSON
    client = Client(
        {
            "B0TEST0001": _item("B0TEST0001", tag, title="TESTBRAND Titolo cambiato"),
            "B0TEST0002": broken,
            "B0TEST0003": _item("B0TEST0003", tag),
        }
    )
    async with session_factory() as db:
        await CatalogMonitorRepository(db).upsert_baseline(
            acc.id, "B0TEST0001", content_from_catalog(_item("B0TEST0001", tag), MKT),
            "live_snapshot", None,
        )
        await db.commit()
        first = await _service(db, client).scan_account(acc)

    assert (first.scanned, first.failed, first.new_versions) == (2, 1, 2)
    assert first.errors[0].startswith("B0TEST0002")
    assert first.anomalies_opened == 1

    async with session_factory() as db:
        second = await _service(db, client).scan_account(acc)
        open_ = await CatalogMonitorRepository(db).open_anomalies(acc.id)
        snapshots = (
            await db.execute(
                select(ListingQualitySnapshot.asin).where(ListingQualitySnapshot.account_id == acc.id)
            )
        ).scalars().all()
        image_rows = (
            await db.execute(
                select(func.count()).select_from(ImageCheck).where(ImageCheck.url.contains(tag))
            )
        ).scalar()

    assert (second.scanned, second.failed, second.new_versions) == (2, 1, 0)
    assert second.anomalies_opened == 0
    assert list(open_) == [("B0TEST0001", "content_changed", "title")]
    assert sorted(snapshots) == ["B0TEST0001", "B0TEST0003"]
    assert image_rows == 1
