"""End-to-end run of the catalogue monitor and the quarterly report on Postgres (R1-R5).

Each test seeds its own demo organization with ``scripts/dev_seed_catalog_monitor.py``
(Amazon answered by the FixtureClient from a temporary directory), then drives the
real API through ``app.main.app``: login, traffic lights, anomalies, history,
variations, restores through the approval queue, bulk export and upload, new items,
the quarterly deck and the dashboard brand filter. Skipped without TEST_DATABASE_URL.
"""
import importlib.util
import io
import os
import secrets
import sys
import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
import pytest_asyncio
from openpyxl import Workbook, load_workbook
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL not set"
)

SEED_PATH = Path(__file__).resolve().parents[1] / "scripts" / "dev_seed_catalog_monitor.py"
PPTX = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
EXPECTED_SELLER_ANOMALIES = [
    ("B0TEST0002", "content_changed", "title"),
    ("B0TEST0003", "content_changed", "bullets"),
    ("B0TEST0004", "content_changed", "images"),
    ("B0TEST0012", "child_detached", "parent:B0TEST0010"),
]


def _load_seed():
    name = "dev_seed_catalog_monitor"
    if name not in sys.modules:  # registered first: its dataclasses look themselves up
        spec = importlib.util.spec_from_file_location(name, SEED_PATH)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return sys.modules[name]


@dataclass
class Stack:
    client: httpx.AsyncClient
    sessions: Any
    seed: Any
    config: Any
    seller_id: str
    vendor_id: str

    async def get(self, path: str, **params) -> Any:
        response = await self.client.get(f"/api/v1{path}", params=params)
        assert response.status_code == 200, response.text
        return response.json()

    async def post(self, path: str, body: dict) -> Any:
        response = await self.client.post(f"/api/v1{path}", json=body)
        assert response.status_code == 200, response.text
        return response.json()

    async def rescan(self, account_id: str):
        from app.models.amazon_account import AmazonAccount
        from app.services.catalog_monitor.scanner import CatalogScanService

        async with self.sessions() as db:
            account = (await db.execute(
                select(AmazonAccount).where(AmazonAccount.id == uuid.UUID(account_id))
            )).scalar_one()
            return await CatalogScanService(
                db,
                client_factory=self.seed.fixture_client_factory(self.config.fixture_dir),
                image_fetch=self.seed.local_image_fetch(self.config.fixture_dir, self.config.image_base_url),
                sleep=lambda _: None,
            ).scan_account(account)

    async def baseline(self, account_id: str, asin: str) -> dict:
        from app.models.catalog_monitor import ListingContentBaseline

        async with self.sessions() as db:
            return (await db.execute(select(ListingContentBaseline.content).where(
                ListingContentBaseline.account_id == uuid.UUID(account_id),
                ListingContentBaseline.asin == asin,
            ))).scalar_one()

    async def anomalies(self, account_id: str, **params) -> list[dict]:
        return await self.get("/catalog-monitor/anomalies", account_id=account_id, **params)

    async def approve_and_submit(self, ids: list[str]) -> list[dict]:
        approved = await self.post("/catalog-monitor/changes/approve", {"ids": ids})
        assert [r["status"] for r in approved["requests"]] == ["approved"] * len(ids), approved
        submitted = await self.post("/catalog-monitor/changes/submit", {"ids": ids})
        return submitted["requests"]


@pytest_asyncio.fixture
async def stack(tmp_path, monkeypatch):
    from app.api import deps
    from app.config import settings
    from app.main import app
    from app.models.catalog_monitor import ImageCheck, ProductTypeDefinitionCache
    from app.models.user import Organization, User

    seed = _load_seed()
    tag = uuid.uuid4().hex[:10]
    config = seed.SeedConfig(
        admin_email=f"e2e-{tag}@example.com",
        admin_password=secrets.token_urlsafe(12),
        fixture_dir=tmp_path / "fixtures",
        image_base_url=f"http://fixtures.test/{tag}",
        org_name=f"TEST E2E {tag}",
        org_slug=f"test-e2e-{tag}",
    )
    engine = create_async_engine(os.environ["TEST_DATABASE_URL"])
    sessions = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    seed.write_fixtures(config)
    async with sessions() as db:
        seeded = await seed.seed_database(db, config)
        report = await seed.run_scans(db, seeded, config)
    assert report[seed.SELLER_NAME]["open_anomalies"] == EXPECTED_SELLER_ANOMALIES

    # Routes build their Amazon client with default_client_factory: the fixture seam.
    monkeypatch.setattr(settings, "DEV_FIXTURE_AMAZON_DIR", str(config.fixture_dir))
    monkeypatch.setattr(settings, "APP_ENV", "development")

    async def test_db():
        async with sessions() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[deps.get_db] = test_db
    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://e2e.test", timeout=60) as client:
            login = await client.post(
                "/api/v1/auth/login",
                json={"email": config.admin_email, "password": config.admin_password},
            )
            assert login.status_code == 200, login.text
            client.headers["Authorization"] = f"Bearer {login.json()['access_token']}"
            yield Stack(client, sessions, seed, config, str(seeded.seller.id), str(seeded.vendor.id))
    finally:
        app.dependency_overrides.pop(deps.get_db, None)
        async with sessions() as db:
            await db.execute(delete(Organization).where(Organization.id == seeded.organization.id))
            await db.execute(delete(User).where(User.id == seeded.user.id))
            await db.execute(delete(ImageCheck).where(ImageCheck.url.startswith(config.image_base_url)))
            await db.execute(delete(ProductTypeDefinitionCache).where(
                ProductTypeDefinitionCache.product_type.in_(list(seed.REQUIRED_BY_TYPE))
            ))
            await db.commit()
        await engine.dispose()


def _key(anomaly: dict) -> tuple[str, str, str]:
    return anomaly["asin"], anomaly["kind"], anomaly["field"]


# ---- R1, R2, R3 after the seed ----


@pytest.mark.asyncio
async def test_quality_anomalies_history_and_variations(stack):
    quality = await stack.get("/catalog-monitor/quality", account_id=stack.seller_id, page_size=200)
    assert (quality["total"], quality["unscanned"]) == (12, 0)
    for item in quality["items"]:
        assert len(item["results"]) == 11, item["asin"]
    by_asin = {i["asin"]: i for i in quality["items"]}
    assert by_asin["B0TEST0001"]["state"] == "green"
    assert by_asin["B0TEST0006"]["state"] == "red"  # main image on a grey background
    assert {i["state"] for i in quality["items"]} == {"green", "yellow", "red"}
    per_rule = quality["summary"]["per_rule"]
    assert per_rule["video"] == {"grey": 12}
    for rule in ("title", "bullets", "images", "main_image", "aplus", "backend_keywords", "attributes"):
        assert len(per_rule[rule]) >= 2, (rule, per_rule[rule])
    main_image = {r["key"]: r for r in by_asin["B0TEST0005"]["results"]}["main_image"]
    assert (main_image["state"], main_image["details"]["fill_ratio"]) == ("yellow", 0.6)

    access = await stack.get("/catalog-monitor/capabilities", account_id=stack.vendor_id)
    assert access["vendor_code"] == "TESTVENDOR" and access["results"]["listings_read"]["ok"]
    vendor = await stack.get("/catalog-monitor/quality", account_id=stack.vendor_id)
    keywords = {
        i["asin"]: {r["key"]: r["state"] for r in i["results"]}["backend_keywords"] for i in vendor["items"]
    }
    # Read through Listings with the vendor code; grey (not red) where there is no SKU.
    assert keywords["B0TEST0004"] == "grey"
    assert all(state != "grey" for asin, state in keywords.items() if asin != "B0TEST0004")

    anomalies = await stack.anomalies(stack.seller_id)
    assert sorted(_key(a) for a in anomalies) == EXPECTED_SELLER_ANOMALIES
    title = next(a for a in anomalies if a["field"] == "title")
    assert title["baseline_value"].startswith("TESTBRAND Set di 3 spatole")
    assert "OFFERTA" in title["live_value"]
    images = next(a for a in anomalies if a["field"] == "images")
    assert images["change"] == "reordered"
    assert len(await stack.anomalies(stack.vendor_id)) == 3

    history = await stack.get("/catalog-monitor/history/B0TEST0002", account_id=stack.seller_id)
    assert len(history) == 2
    assert [c["field"] for c in history[0]["changes"]] == ["title"]

    variations = await stack.get("/catalog-monitor/variations", account_id=stack.seller_id)
    assert len(variations) == 1
    family = variations[0]
    assert (family["parent_asin"], family["status"]) == ("B0TEST0010", "partial")
    assert {c["asin"]: c["state"] for c in family["children"]} == {
        "B0TEST0011": "ok", "B0TEST0012": "detached",
    }


@pytest.mark.asyncio
async def test_content_restores_go_through_approval_and_resolve_on_rescan(stack):
    chosen = [a for a in await stack.anomalies(stack.seller_id) if a["field"] in ("title", "images")]
    batch = await stack.post("/catalog-monitor/anomalies/restore", {"anomaly_ids": [a["id"] for a in chosen]})
    requests = {r["asin"]: r for r in batch["requests"]}
    assert sorted(requests) == ["B0TEST0002", "B0TEST0004"]
    for request in requests.values():
        assert (request["status"], request["file_only"], request["validation_issues"]) == ("valid", False, [])
    submitted = await stack.approve_and_submit([r["id"] for r in requests.values()])
    assert [r["status"] for r in submitted] == ["accepted", "accepted"], submitted

    summary = await stack.rescan(stack.seller_id)
    assert summary.anomalies_resolved == 2 and summary.failed == 0
    remaining = sorted(_key(a) for a in await stack.anomalies(stack.seller_id))
    assert remaining == [EXPECTED_SELLER_ANOMALIES[1], EXPECTED_SELLER_ANOMALIES[3]]
    resolved = await stack.anomalies(stack.seller_id, status="resolved")
    assert sorted((a["field"], a["change_request_id"]) for a in resolved) == sorted([
        ("images", requests["B0TEST0004"]["id"]), ("title", requests["B0TEST0002"]["id"]),
    ])

    # Vendor: checked with the vendor code where there is a SKU, a file where there is none.
    vendor = {a["asin"]: a for a in await stack.anomalies(stack.vendor_id) if a["asin"] != "B0TEST0002"}
    vendor_batch = await stack.post("/catalog-monitor/anomalies/restore",
                                    {"anomaly_ids": [a["id"] for a in vendor.values()]})
    assert sorted((r["asin"], r["status"], r["file_only"]) for r in vendor_batch["requests"]) == [
        ("B0TEST0003", "valid", False), ("B0TEST0004", "file_only", True),
    ]


@pytest.mark.asyncio
async def test_a_batch_over_the_feed_threshold_goes_through_a_listings_feed(stack, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "CATALOG_FEED_THRESHOLD", 1)
    bullets = next(a for a in await stack.anomalies(stack.seller_id) if a["field"] == "bullets")
    batch = await stack.post("/catalog-monitor/anomalies/restore", {"anomaly_ids": [bullets["id"]]})
    [request] = batch["requests"]
    assert request["status"] == "valid", request
    [submitted] = await stack.approve_and_submit([request["id"]])
    assert (submitted["status"], bool(submitted["feed_id"])) == ("submitted", True), submitted
    settled = await stack.post("/catalog-monitor/changes/refresh-feed",
                               {"account_id": stack.seller_id, "feed_id": submitted["feed_id"]})
    assert [r["status"] for r in settled] == ["accepted"], settled

    await stack.rescan(stack.seller_id)
    assert all(a["field"] != "bullets" for a in await stack.anomalies(stack.seller_id))


@pytest.mark.asyncio
async def test_variation_restore_reattaches_the_child(stack):
    batch = await stack.post("/catalog-monitor/variations/restore",
                             {"account_id": stack.seller_id, "parent_asin": "B0TEST0010"})
    [request] = batch["requests"]
    assert (request["asin"], request["status"]) == ("B0TEST0012", "valid"), request
    [submitted] = await stack.approve_and_submit([request["id"]])
    assert submitted["status"] == "accepted", submitted

    await stack.rescan(stack.seller_id)
    variations = await stack.get("/catalog-monitor/variations", account_id=stack.seller_id)
    assert variations[0]["status"] == "ok"
    assert all(a["kind"] != "child_detached" for a in await stack.anomalies(stack.seller_id))


@pytest.mark.asyncio
async def test_bulk_export_edit_upload_approve_submit(stack):
    response = await stack.client.get("/api/v1/catalog-monitor/export",
                                      params={"account_id": stack.seller_id})
    assert response.status_code == 200, response.text
    workbook = load_workbook(io.BytesIO(response.content))
    sheet = workbook["Catalogo"]
    headers = [c.value for c in sheet[1]]
    rows = {row[headers.index("asin")].value: row for row in sheet.iter_rows(min_row=2)}
    assert len(rows) == 12
    new_bullet = "Manico in legno di faggio, più leggero e piacevole al tatto"
    rows["B0TEST0001"][headers.index("bullet_2")].value = new_bullet
    edited = io.BytesIO()
    workbook.save(edited)

    upload = await stack.client.post(
        "/api/v1/catalog-monitor/bulk/upload",
        data={"account_id": stack.seller_id, "mode": "update"},
        files={"file": ("catalogo.xlsx", edited.getvalue(),
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert upload.status_code == 200, upload.text
    body = upload.json()
    assert (body["rows"], body["changes"], body["unchanged"], body["row_errors"]) == (12, 1, 11, [])
    [request] = body["requests"]
    assert (request["asin"], request["status"]) == ("B0TEST0001", "valid"), request
    assert list(request["summary"]["fields"]) == ["bullets"]
    [submitted] = await stack.approve_and_submit([request["id"]])
    assert submitted["status"] == "accepted", submitted

    client = stack.seed.FixtureClient(str(stack.config.fixture_dir), stack.seed.MP)
    bullets = [b["value"] for b in client.get_catalog_item_full("B0TEST0001")["attributes"]["bullet_point"]]
    assert len(bullets) == 5 and bullets[1] == new_bullet
    assert bullets[0] == stack.seed.PRODUCT_BY_ASIN["B0TEST0001"].bullets[0]

    # The approved change is now the protected content: the next scan does not flag it.
    assert (await stack.baseline(stack.seller_id, "B0TEST0001"))["bullets"] == bullets
    summary = await stack.rescan(stack.seller_id)
    assert summary.anomalies_opened == 0
    assert sorted(_key(a) for a in await stack.anomalies(stack.seller_id)) == EXPECTED_SELLER_ANOMALIES


@pytest.mark.asyncio
async def test_a_change_marked_as_uploaded_by_hand_keeps_the_baseline(stack):
    response = await stack.client.get("/api/v1/catalog-monitor/export", params={"account_id": stack.vendor_id})
    workbook = load_workbook(io.BytesIO(response.content))
    sheet = workbook["Catalogo"]
    headers = [c.value for c in sheet[1]]
    row = next(r for r in sheet.iter_rows(min_row=2) if r[headers.index("asin")].value == "B0TEST0004")
    row[headers.index("bullet_2")].value = "Testo caricato a mano su Vendor Central"
    edited = io.BytesIO()
    workbook.save(edited)
    upload = await stack.client.post(
        "/api/v1/catalog-monitor/bulk/upload",
        data={"account_id": stack.vendor_id, "mode": "update"},
        files={"file": ("catalogo.xlsx", edited.getvalue(),
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert upload.status_code == 200, upload.text
    [request] = upload.json()["requests"]
    assert (request["asin"], request["status"]) == ("B0TEST0004", "file_only")  # no vendor SKU
    before = await stack.baseline(stack.vendor_id, "B0TEST0004")
    await stack.post("/catalog-monitor/changes/approve", {"ids": [request["id"]]})
    marked = await stack.post("/catalog-monitor/changes/mark-uploaded", {"ids": [request["id"]]})
    assert [r["status"] for r in marked["requests"]] == ["submitted"]
    # We cannot know it went live: the baseline stays, the next scan decides.
    assert await stack.baseline(stack.vendor_id, "B0TEST0004") == before


@pytest.mark.asyncio
async def test_new_item_template_and_upload(stack):
    response = await stack.client.get("/api/v1/catalog-monitor/new-items/template",
                                      params={"account_id": stack.seller_id, "product_type": "KITCHEN"})
    assert response.status_code == 200, response.text
    template = load_workbook(io.BytesIO(response.content)).active
    headers = [c.value for c in template[1]]
    assert headers[:2] == ["sku", "product_type"]
    assert set(stack.seed.REQUIRED_BY_TYPE["KITCHEN"]) <= set(headers)

    values = {
        "sku": "TEST-SKU-101", "product_type": "KITCHEN", "brand": "TESTBRAND",
        "item_name": "TESTBRAND Schiumarola in acciaio inox 35 cm",
        "bullet_point": "Schiumarola forata per fritture e verdure lesse",
        "item_type_keyword": "schiumarole", "material": "Acciaio inox", "color": "Argento",
    }
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(headers)
    sheet.append([values.get(h) for h in headers])
    filled = io.BytesIO()
    workbook.save(filled)
    upload = await stack.client.post(
        "/api/v1/catalog-monitor/new-items/upload",
        data={"account_id": stack.seller_id},
        files={"file": ("nuovi.xlsx", filled.getvalue(),
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert upload.status_code == 200, upload.text
    body = upload.json()
    assert (body["changes"], body["row_errors"]) == (1, [])
    [request] = body["requests"]
    assert (request["kind"], request["operation"], request["status"]) == ("new_item", "PUT", "valid"), request
    [submitted] = await stack.approve_and_submit([request["id"]])
    assert submitted["status"] == "accepted", submitted


def _last_full_quarter(today: date) -> tuple[int, int]:
    quarter = (today.month - 1) // 3 + 1
    return (today.year - 1, 4) if quarter == 1 else (today.year, quarter - 1)


@pytest.mark.asyncio
async def test_quarterly_report_and_dashboard_brand_filter(stack):
    from pptx import Presentation

    year, quarter = _last_full_quarter(date.today())
    response = await stack.client.post("/api/v1/reports/quarterly", json={
        "account_ids": [stack.seller_id, stack.vendor_id], "year": year, "quarter": quarter,
        "language": "it",
    })
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == PPTX
    deck = Presentation(io.BytesIO(response.content))
    assert len(deck.slides) >= 8
    tables = [
        [[cell.text for cell in row.cells] for row in shape.table.rows]
        for slide in deck.slides for shape in slide.shapes if shape.has_table
    ]
    kpis = next(t for t in tables if t[0][0] == "Indicatore")
    revenue = next(row for row in kpis if row[0] == "Ricavi")
    assert revenue[1].startswith("€") and revenue[2] != "—"  # vs the previous quarter
    asins = {row[0] for table in tables if table[0][0] == "ASIN" for row in table[1:]}
    assert {"B0TEST0001", "B0TEST0901"} <= asins  # own top ASINs and tracked competitors

    end = date.today() - timedelta(days=1)
    params = {"start_date": (end - timedelta(days=29)).isoformat(), "end_date": end.isoformat(),
              "account_ids": stack.seller_id}
    everything = await stack.get("/analytics/dashboard", **params)
    brand_two = await stack.get("/analytics/dashboard", **params, brand="TESTBRAND2")
    assert 0 < brand_two["total_revenue"]["value"] < everything["total_revenue"]["value"]
