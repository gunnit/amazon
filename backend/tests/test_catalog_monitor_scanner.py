"""Daily catalogue scan (R1-R3) with an in-memory repository and a fake SP-API client.

No database, no network: the repository keeps rows in dicts, the client serves
the Task 3 fixtures, and image downloads come from an injected coroutine.
"""
import copy
import io
import json
import pathlib
import threading
import time
from datetime import date, datetime
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from PIL import Image

from app.config import settings
from app.core.exceptions import AmazonAPIError
from app.models.amazon_account import AccountType
from app.models.catalog_monitor import CatalogAnomaly, ImageCheck, ListingContentVersion
from app.services import extraction_runner
from app.services.catalog_monitor import scanner
from app.services.catalog_monitor.content import (
    content_from_catalog,
    content_hash,
    content_to_dict,
)
from app.services.catalog_monitor.keywords import resolve_main_keywords
from app.services.catalog_monitor.repository import CatalogMonitorRepository
from app.services.catalog_monitor.rules import RULE_KEYS, evaluation_to_dict
from app.services.catalog_monitor.scanner import CatalogScanService, ScanSummary

FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "catalog_monitor"
MKT = "APJ6JRA9NG5V4"
DAY = date(2026, 11, 21)
PARENT = "B0TEST0100"


def _fixture(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text())


def _child(asin: str = "B0TEST0001", parents=(PARENT,)) -> dict:
    payload = _fixture("catalog_child")
    payload["asin"] = asin
    rels = payload["relationships"][0]["relationships"]
    if parents:
        rels[0]["parentAsins"] = list(parents)
    else:
        rels.clear()
    return payload


def _vendor_item(asin: str = "B0TEST0004") -> dict:
    payload = _fixture("catalog_vendor_minimal")
    payload["asin"] = asin
    return payload


def _png(fill: float = 0.9) -> bytes:
    img = Image.new("RGB", (100, 100), "white")
    side = int(100 * fill)
    offset = (100 - side) // 2
    img.paste((20, 20, 20), (offset, offset, offset + side, offset + side))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def _fetcher(data: bytes | None = None, exc: Exception | None = None):
    calls: list[str] = []

    async def fetch(url: str) -> bytes:
        calls.append(url)
        if exc is not None:
            raise exc
        return data if data is not None else _png()

    fetch.calls = calls
    return fetch


class _Result:
    def __init__(self, rows=()):
        self._rows = list(rows)

    def scalar_one_or_none(self):
        return None

    def scalar(self):
        return None

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None


class _Savepoint:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class FakeDb:
    """Every query finds nothing (or ``rows``); writes are recorded."""

    def __init__(self, rows=()):
        self.rows = list(rows)
        self.added: list = []
        self.commits = 0

    async def execute(self, _stmt):
        return _Result(self.rows)

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        pass

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        pass

    def begin_nested(self):
        return _Savepoint()


class FakeRepo(CatalogMonitorRepository):
    """Dict-backed repository with the same contract as the Postgres one."""

    def __init__(self, products, capability=None, baselines=None, families=None):
        super().__init__(db=None)
        self.products = list(products)
        self.cap = capability
        self.baseline_rows = dict(baselines or {})
        self.families = list(families or [])
        self.versions_by_asin: dict[str, list[ListingContentVersion]] = {}
        self.anomalies: list[CatalogAnomaly] = []
        self.snapshots: dict[tuple[str, date], dict] = {}

    async def products_to_scan(self, account_id):
        return sorted(self.products, key=lambda p: p.asin)

    async def latest_versions(self, account_id, asins=None):
        latest = {asin: rows[-1] for asin, rows in self.versions_by_asin.items() if rows}
        if asins is not None:
            latest = {asin: row for asin, row in latest.items() if asin in asins}
        return latest

    async def save_version(self, account_id, asin, content, seen_at):
        digest = content_hash(content)
        rows = self.versions_by_asin.setdefault(asin, [])
        if rows and rows[-1].content_hash == digest:
            rows[-1].last_seen_at = seen_at
            return rows[-1], False
        row = ListingContentVersion(
            account_id=account_id,
            asin=asin,
            content_hash=digest,
            content=content_to_dict(content),
            first_seen_at=seen_at,
            last_seen_at=seen_at,
        )
        rows.append(row)
        return row, True

    async def baselines(self, account_id):
        return dict(self.baseline_rows)

    async def family_baselines(self, account_id):
        return list(self.families)

    async def open_anomalies(self, account_id):
        return {(a.asin, a.kind, a.field): a for a in self.anomalies if a.status != "resolved"}

    async def open_or_touch_anomaly(
        self, account_id, asin, kind, field, baseline_value, live_value, now
    ):
        existing = (await self.open_anomalies(account_id)).get((asin, kind, field))
        if existing is not None:
            existing.last_seen_at = now
            existing.live_value = live_value
            return existing, False
        anomaly = CatalogAnomaly(
            account_id=account_id,
            asin=asin,
            kind=kind,
            field=field,
            baseline_value=baseline_value,
            live_value=live_value,
            status="open",
            detected_at=now,
            last_seen_at=now,
        )
        self.anomalies.append(anomaly)
        return anomaly, True

    async def resolve_anomaly(self, anomaly, now):
        anomaly.status = "resolved"
        anomaly.resolved_at = now

    async def save_quality_snapshot(self, account_id, asin, evaluation, day):
        self.snapshots[(asin, day)] = evaluation_to_dict(evaluation)

    async def rule_overrides(self, organization_id):
        return []

    async def capability(self, account_id):
        return self.cap

    # helpers for assertions
    def open_rows(self):
        return [a for a in self.anomalies if a.status != "resolved"]

    def rules(self, asin, day=DAY):
        return {r["key"]: r for r in self.snapshots[(asin, day)]["results"]}


class FakeClient:
    def __init__(self, catalog, listings=None, aplus=None, required=("item_name", "brand")):
        self.catalog = dict(catalog)
        self.listings = dict(listings or {})
        self.aplus = dict(aplus or {})
        self.required = list(required)
        self.fail: set[tuple[str, str]] = set()
        self.calls: list[tuple[str, str]] = []

    def _check(self, name, key):
        self.calls.append((name, key))
        if (name, key) in self.fail:
            raise AmazonAPIError(f"{name} failed for {key}", error_code="SERVER_ERROR")

    def get_catalog_item_full(self, asin):
        self._check("catalog", asin)
        if asin not in self.catalog:
            raise AmazonAPIError(f"{asin} not found", error_code="NOT_FOUND")
        return copy.deepcopy(self.catalog[asin])

    def get_listing(self, seller_id, sku, included_data=None):
        self._check("listing", sku)
        return copy.deepcopy(self.listings[sku])

    def get_aplus_publish_record_count(self, asin):
        self._check("aplus", asin)
        return self.aplus.get(asin, 0)

    def get_product_type_definition(self, product_type, seller_id=None, locale="it_IT"):
        self._check("ptd", product_type)
        return {"schema": {"link": {"resource": "https://example.test/schema.json"}}}

    def fetch_json_schema(self, url):
        return {"required": list(self.required), "properties": {n: {} for n in self.required}}

    def count(self, name):
        return sum(1 for call, _ in self.calls if call == name)


def _account(kind=AccountType.SELLER, seller_id="SELLER1"):
    return SimpleNamespace(
        id=uuid4(),
        organization_id=uuid4(),
        account_type=kind,
        seller_id=seller_id,
        marketplace_id=MKT,
        account_name="Test account",
    )


def _product(asin, sku=None, main_keyword=None, source=None):
    return SimpleNamespace(
        asin=asin, sku=sku, main_keyword=main_keyword, main_keyword_source=source, is_active=True
    )


def _capability(aplus_ok=True, vendor_code=None):
    results = {
        "catalog_items": {"ok": True, "error": None},
        "listings_read": {"ok": True, "error": None},
        "product_type_definitions": {"ok": True, "error": None},
        "aplus": {"ok": aplus_ok, "error": None if aplus_ok else "denied"},
        "feeds": {"ok": True, "error": None},
    }
    return SimpleNamespace(results=results, vendor_code=vendor_code)


def _baseline(payload):
    return SimpleNamespace(content=content_to_dict(content_from_catalog(payload, MKT)))


def _family(children, parent=PARENT, theme="COLOR"):
    return SimpleNamespace(parent_asin=parent, variation_theme=theme, child_asins=list(children))


def _service(repo, client, fetch=None, db=None, sleeps=None):
    return CatalogScanService(
        db if db is not None else FakeDb(),
        repo=repo,
        client_factory=lambda account, organization: client,
        image_fetch=fetch or _fetcher(),
        sleep=sleeps.append if sleeps is not None else (lambda _s: None),
        today=lambda: DAY,
    )


# ---- R1: content and traffic lights ----


@pytest.mark.asyncio
async def test_scan_vendor_without_listing_access_uses_catalog_only():
    account = _account(AccountType.VENDOR, seller_id=None)
    repo = FakeRepo(
        [_product("B0TEST0004", sku="TEST-SKU-004")],
        capability=_capability(aplus_ok=False, vendor_code=None),
    )
    client = FakeClient({"B0TEST0004": _vendor_item()})

    summary = await _service(repo, client).scan_account(account)

    assert (summary.scanned, summary.failed, summary.errors) == (1, 0, [])
    assert client.count("listing") == 0
    assert client.count("aplus") == 0
    rules = repo.rules("B0TEST0004")
    assert rules["backend_keywords"]["state"] == "grey"
    assert rules["aplus"]["state"] == "grey"
    assert rules["title"]["state"] in ("green", "yellow")
    stored = repo.versions_by_asin["B0TEST0004"][0].content
    assert stored["title"] == "TESTBRAND Vendor di prova"


@pytest.mark.asyncio
async def test_quality_snapshot_saved_per_asin():
    account = _account()
    repo = FakeRepo(
        [
            _product("B0TEST0001", main_keyword="prodotto di prova", source="manual"),
            _product("B0TEST0004"),
        ]
    )
    client = FakeClient({"B0TEST0001": _child(), "B0TEST0004": _vendor_item()})

    summary = await _service(repo, client).scan_account(account)

    assert summary.scanned == 2 and summary.new_versions == 2
    assert set(repo.snapshots) == {("B0TEST0001", DAY), ("B0TEST0004", DAY)}
    snapshot = repo.snapshots[("B0TEST0001", DAY)]
    assert snapshot["asin"] == "B0TEST0001"
    assert isinstance(snapshot["score"], int)
    assert [r["key"] for r in snapshot["results"]] == list(RULE_KEYS)
    assert repo.rules("B0TEST0001")["title"]["details"]["keyword_checked"] is True
    assert repo.rules("B0TEST0004")["title"]["details"]["keyword_checked"] is False
    assert repo.rules("B0TEST0001")["main_image"]["state"] == "green"
    assert repo.rules("B0TEST0001")["attributes"]["state"] != "grey"


@pytest.mark.asyncio
async def test_image_download_failure_gives_grey_main_image():
    account = _account()
    repo = FakeRepo([_product("B0TEST0001")])
    client = FakeClient({"B0TEST0001": _child()})
    fetch = _fetcher(exc=httpx.ConnectError("unreachable"))

    summary = await _service(repo, client, fetch=fetch).scan_account(account)

    assert summary.scanned == 1 and summary.failed == 0
    main = repo.rules("B0TEST0001")["main_image"]
    assert main["state"] == "grey" and main["code"] == "analysis_failed"


@pytest.mark.asyncio
async def test_scan_continues_after_one_failed_asin():
    account = _account()
    repo = FakeRepo([_product("B0TEST0001"), _product("B0TEST0004")])
    client = FakeClient({"B0TEST0001": _child(), "B0TEST0004": _vendor_item()})
    client.fail.add(("catalog", "B0TEST0001"))

    summary = await _service(repo, client).scan_account(account)

    assert (summary.scanned, summary.failed) == (1, 1)
    assert len(summary.errors) == 1 and summary.errors[0].startswith("B0TEST0001")
    assert set(repo.snapshots) == {("B0TEST0004", DAY)}


@pytest.mark.asyncio
async def test_catalog_calls_are_spaced_and_work_is_committed_every_25_products():
    account = _account()
    asins = [f"B0TEST{1000 + i}" for i in range(30)]
    repo = FakeRepo([_product(a) for a in asins])
    client = FakeClient({a: _vendor_item(a) for a in asins})
    db, sleeps, fetch = FakeDb(), [], _fetcher()

    summary = await _service(repo, client, fetch=fetch, db=db, sleeps=sleeps).scan_account(account)

    assert summary.scanned == 30
    assert sleeps == [settings.CATALOG_SCAN_REQUEST_INTERVAL_S] * 29
    assert db.commits == 2  # after product 25 and at the end
    # one image download and one image_checks row per URL per scan, one PTD lookup per type
    assert fetch.calls == ["https://example.test/img/MAIN-1000.jpg"]
    assert sum(isinstance(o, ImageCheck) for o in db.added) == 1
    assert client.count("ptd") == 1


# ---- R3: content changes against the baseline ----


def _changed_title(payload, title="TESTBRAND Titolo cambiato da terzi"):
    payload["attributes"]["item_name"][0]["value"] = title
    return payload


@pytest.mark.asyncio
async def test_scan_opens_anomaly_on_title_change_and_does_not_duplicate():
    account = _account()
    original = _child()
    repo = FakeRepo([_product("B0TEST0001")], baselines={"B0TEST0001": _baseline(original)})
    client = FakeClient({"B0TEST0001": _changed_title(_child())})
    service = _service(repo, client)

    first = await service.scan_account(account)
    second = await service.scan_account(account)

    assert first.anomalies_opened == 1 and second.anomalies_opened == 0
    [anomaly] = repo.open_rows()
    assert (anomaly.asin, anomaly.kind, anomaly.field) == ("B0TEST0001", "content_changed", "title")
    assert anomaly.baseline_value == "TESTBRAND Prodotto di prova 500 ml"
    assert anomaly.live_value == "TESTBRAND Titolo cambiato da terzi"
    assert len(repo.anomalies) == 1


@pytest.mark.asyncio
async def test_scan_resolves_anomaly_when_content_reverts():
    account = _account()
    original = _child()
    repo = FakeRepo([_product("B0TEST0001")], baselines={"B0TEST0001": _baseline(original)})
    client = FakeClient({"B0TEST0001": _changed_title(_child())})
    service = _service(repo, client)
    await service.scan_account(account)
    assert len(repo.open_rows()) == 1

    client.catalog["B0TEST0001"] = _child()
    summary = await service.scan_account(account)

    assert summary.anomalies_resolved == 1
    assert repo.open_rows() == []
    assert repo.anomalies[0].status == "resolved"


@pytest.mark.asyncio
async def test_failed_listing_or_aplus_call_creates_no_new_version():
    account = _account()
    repo = FakeRepo(
        [_product("B0TEST0001", sku="TEST-SKU-001")], capability=_capability(aplus_ok=True)
    )
    client = FakeClient(
        {"B0TEST0001": _child()},
        listings={"TEST-SKU-001": _fixture("listing_seller")},
        aplus={"B0TEST0001": 3},
    )
    service = _service(repo, client)
    first = await service.scan_account(account)
    assert first.new_versions == 1
    stored = repo.versions_by_asin["B0TEST0001"][0].content
    assert stored["backend_keywords"] == "parola uno parola due"
    assert stored["aplus_module_count"] == 3
    repo.baseline_rows["B0TEST0001"] = SimpleNamespace(content=copy.deepcopy(stored))

    client.fail |= {("listing", "TEST-SKU-001"), ("aplus", "B0TEST0001")}
    second = await service.scan_account(account)

    assert (second.scanned, second.failed) == (1, 0)
    assert second.new_versions == 0
    assert len(repo.versions_by_asin["B0TEST0001"]) == 1
    assert second.anomalies_opened == 0 and repo.open_rows() == []
    rules = repo.rules("B0TEST0001")
    assert rules["backend_keywords"]["state"] != "grey"
    assert rules["aplus"]["state"] != "grey"


# ---- R2: variation families ----


@pytest.mark.asyncio
async def test_detached_child_opens_variation_anomaly():
    account = _account()
    parent = _fixture("catalog_parent")
    parent["relationships"][0]["relationships"][0]["childAsins"] = ["B0TEST0001", "B0TEST0003"]
    repo = FakeRepo(
        [_product("B0TEST0001"), _product("B0TEST0002")],
        families=[_family(["B0TEST0001", "B0TEST0002", "B0TEST0003"])],
    )
    client = FakeClient(
        {
            "B0TEST0001": _child("B0TEST0001"),
            "B0TEST0002": _child("B0TEST0002", parents=()),
            "B0TEST0003": _child("B0TEST0003"),
            PARENT: parent,
        }
    )
    service = _service(repo, client)

    summary = await service.scan_account(account)

    assert summary.anomalies_opened == 1
    [anomaly] = repo.open_rows()
    assert (anomaly.asin, anomaly.kind, anomaly.field) == (
        "B0TEST0002",
        "child_detached",
        f"parent:{PARENT}",
    )
    # the parent and the unscanned child were read on demand, scanned ones were not re-read
    assert client.calls.count(("catalog", PARENT)) == 1
    assert client.calls.count(("catalog", "B0TEST0003")) == 1
    assert client.calls.count(("catalog", "B0TEST0001")) == 1

    client.catalog["B0TEST0002"] = _child("B0TEST0002")
    again = await service.scan_account(account)

    assert again.anomalies_resolved == 1 and again.anomalies_opened == 0
    assert repo.open_rows() == []


@pytest.mark.asyncio
async def test_partial_catalog_payload_neither_detaches_nor_resolves_child():
    """A payload without ``relationships`` is unknown for the family check.

    B0TEST0001 has an open detach anomaly and a stored version that still lists
    the parent: it must stay open (not resolved from stale data). B0TEST0002 has
    no anomaly: it must not get one (no false detach from the missing block).
    """
    account = _account()
    partial_1, partial_2 = _child("B0TEST0001"), _child("B0TEST0002")
    del partial_1["relationships"], partial_2["relationships"]
    repo = FakeRepo(
        [_product("B0TEST0001"), _product("B0TEST0002")],
        families=[_family(["B0TEST0001", "B0TEST0002"])],
    )
    stored = content_from_catalog(_child("B0TEST0001"), MKT)
    await repo.save_version(account.id, "B0TEST0001", stored, datetime(2026, 11, 20))
    known = CatalogAnomaly(
        account_id=account.id,
        asin="B0TEST0001",
        kind="child_detached",
        field=f"parent:{PARENT}",
        baseline_value=PARENT,
        live_value=[],
        status="open",
    )
    repo.anomalies.append(known)
    parent = _fixture("catalog_parent")
    parent["relationships"][0]["relationships"][0]["childAsins"] = ["B0TEST0001", "B0TEST0002"]
    client = FakeClient({"B0TEST0001": partial_1, "B0TEST0002": partial_2, PARENT: parent})

    summary = await _service(repo, client).scan_account(account)

    assert (summary.scanned, summary.failed) == (2, 0)
    assert summary.anomalies_opened == 0 and summary.anomalies_resolved == 0
    assert repo.open_rows() == [known]
    # the stored family of B0TEST0001 is kept, so its version does not change
    assert len(repo.versions_by_asin["B0TEST0001"]) == 1


# ---- main keyword ----


@pytest.mark.asyncio
async def test_main_keyword_manual_beats_brand_analytics():
    terms = [
        SimpleNamespace(
            search_term="crema viso",
            search_frequency_rank=10,
            top_clicked=[
                {"rank": 1, "asin": "B0TEST0001", "click_share": 0.30},
                {"rank": 2, "asin": "B0TEST0002", "click_share": 0.10},
            ],
        ),
        SimpleNamespace(
            search_term="crema idratante",
            search_frequency_rank=50,
            top_clicked=[{"rank": 1, "asin": "B0TEST0002", "click_share": 0.40}],
        ),
    ]
    products = [
        _product("B0TEST0001", main_keyword="siero viso", source="manual"),
        _product("B0TEST0002"),
        _product("B0TEST0003"),
    ]

    keywords = await resolve_main_keywords(FakeDb(rows=terms), uuid4(), products)

    assert keywords == {"B0TEST0001": "siero viso", "B0TEST0002": "crema idratante"}


# ---- runners and scan state ----


class _FakeEngine:
    async def dispose(self):
        pass


def _wait_until(predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


def test_start_account_scan_refuses_a_second_run_and_records_the_summary(monkeypatch):
    account_id = uuid4()
    started, release = threading.Event(), threading.Event()

    async def fake_scan(aid, session_factory, asins=None):
        started.set()
        release.wait(5)
        return ScanSummary(account_id=aid, scanned=3)

    monkeypatch.setattr(scanner, "_scan_account_by_id", fake_scan)
    monkeypatch.setattr(scanner, "_make_local_session_factory", lambda: (_FakeEngine(), None))

    assert scanner.scan_state(account_id) == {
        "running": False,
        "started_at": None,
        "finished_at": None,
        "summary": None,
    }
    assert scanner.start_account_scan(account_id) is True
    assert started.wait(5)
    running = scanner.scan_state(account_id)
    assert running["running"] is True and running["started_at"]
    assert scanner.start_account_scan(account_id) is False

    release.set()
    assert _wait_until(lambda: not scanner.scan_state(account_id)["running"])
    done = scanner.scan_state(account_id)
    assert done["finished_at"] and done["summary"]["scanned"] == 3
    assert done["summary"]["account_id"] == str(account_id)


def test_failed_background_scan_is_recorded_not_raised(monkeypatch):
    account_id = uuid4()

    async def broken_scan(aid, session_factory, asins=None):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(scanner, "_scan_account_by_id", broken_scan)
    monkeypatch.setattr(scanner, "_make_local_session_factory", lambda: (_FakeEngine(), None))

    assert scanner.start_account_scan(account_id) is True
    assert _wait_until(lambda: scanner.scan_state(account_id)["finished_at"] is not None)
    state = scanner.scan_state(account_id)
    assert state["running"] is False
    assert state["summary"]["errors"] == ["scan failed: RuntimeError"]


def test_run_catalog_scan_all_never_raises(monkeypatch):
    def unavailable():
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(extraction_runner, "_make_local_session_factory", unavailable)

    assert scanner.run_catalog_scan_all()["status"] == "error"


def test_scheduled_scan_skips_an_account_already_scanning(monkeypatch):
    import asyncio

    account_id = uuid4()
    calls = []

    async def fake_scan(aid, session_factory, asins=None):
        calls.append(aid)
        return ScanSummary(account_id=aid, scanned=1)

    monkeypatch.setattr(scanner, "_scan_account_by_id", fake_scan)
    assert scanner._claim(account_id) is True
    try:
        assert asyncio.run(scanner._scheduled_scan_one(account_id, None)) == 0
        assert calls == []
    finally:
        scanner._release(account_id, None)
    assert asyncio.run(scanner._scheduled_scan_one(account_id, None)) == 1
    assert scanner.scan_state(account_id)["summary"]["scanned"] == 1


def test_scan_summary_dict_is_json_ready():
    summary = ScanSummary(account_id=uuid4(), scanned=2, errors=["x"])
    data = summary.to_dict()
    assert json.loads(json.dumps(data)) == data
