"""Catalogue monitor API (R1): pure helpers plus TestClient with faked data access."""
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.api import deps
from app.api.v1 import catalog_monitor as api
from app.models.user import UserRole

ORG = SimpleNamespace(id=uuid4())
USER = SimpleNamespace(id=uuid4())
ACCOUNT_ID = uuid4()


def _item(asin, state, score, rules=None, mandatory=None):
    mandatory = mandatory or {}
    results = [
        {"key": k, "state": s, "mandatory": mandatory.get(k, False), "code": "c", "details": {}}
        for k, s in (rules or {}).items()
    ]
    return {"asin": asin, "sku": f"SKU-{asin}", "title": f"Title {asin}", "state": state,
            "score": score, "results": results}


def _rows():
    return [
        _item("B0TEST0001", "green", 100, {"title": "green", "bullets": "green"}),
        _item("B0TEST0002", "red", 20, {"title": "red", "bullets": "yellow"}, {"title": True}),
        _item("B0TEST0003", "yellow", 60, {"title": "yellow", "bullets": "red"}),
        _item("B0TEST0004", "red", 10, {"title": "green", "bullets": "red"}),
        _item("B0TEST0005", "grey", 0, {"title": "grey", "bullets": "grey"}),
    ]


# ---- pure helpers ----


def test_quality_summary_counts_states():
    summary = api.summarize(_rows())
    assert (summary["green"], summary["yellow"], summary["red"], summary["grey"]) == (1, 1, 2, 1)
    assert summary["per_rule"]["title"] == {"green": 2, "red": 1, "yellow": 1, "grey": 1}
    assert summary["per_rule"]["bullets"]["red"] == 2


def test_quality_filter_by_rule_and_state():
    rows = _rows()
    assert [i["asin"] for i in api.filter_items(rows, state="red")] == ["B0TEST0002", "B0TEST0004"]
    by_rule = api.filter_items(rows, state="red", rule="bullets")
    assert [i["asin"] for i in by_rule] == ["B0TEST0003", "B0TEST0004"]
    # overall state stays the item's own state
    assert {i["asin"]: i["state"] for i in by_rule}["B0TEST0003"] == "yellow"


def test_mandatory_only_keeps_mandatory_results_without_recomputing():
    out = api.filter_items(_rows(), mandatory_only=True)
    by_asin = {i["asin"]: i for i in out}
    assert [r["key"] for r in by_asin["B0TEST0002"]["results"]] == ["title"]
    assert by_asin["B0TEST0002"]["state"] == "red"
    assert by_asin["B0TEST0001"]["results"] == []


def test_sort_worst_first():
    ordered = api.sort_items(_rows())
    assert [i["asin"] for i in ordered] == [
        "B0TEST0004", "B0TEST0002", "B0TEST0003", "B0TEST0005", "B0TEST0001",
    ]


def test_split_scanned_counts_products_without_snapshot():
    rows = [
        {"asin": "B0TEST0001", "components": {"state": "green", "score": 90, "results": []}, "score": 90},
        {"asin": "B0TEST0002", "components": None, "score": None},
    ]
    items, unscanned = api.split_scanned(rows)
    assert [i["asin"] for i in items] == ["B0TEST0001"] and unscanned == 1


def test_validate_overrides_rejects_unknown_rule_and_param():
    ok = api.RuleOverrideIn(rule_key="title", params={"max_length": 60})
    api.validate_overrides([ok])
    for bad in (
        api.RuleOverrideIn(rule_key="nope"),
        api.RuleOverrideIn(rule_key="title", params={"bogus": 1}),
    ):
        with pytest.raises(HTTPException) as exc:
            api.validate_overrides([bad])
        assert exc.value.status_code == 422


def test_apply_keywords_sets_manual_and_reports_unknown():
    p = SimpleNamespace(asin="B0TEST0001", main_keyword="old", main_keyword_source="auto")
    updated, unknown = api.apply_keywords(
        {"B0TEST0001": p},
        [api.KeywordItem(asin="B0TEST0001", keyword="  lego  "), api.KeywordItem(asin="B0NOPE", keyword="x")],
    )
    assert (p.main_keyword, p.main_keyword_source) == ("lego", "manual")
    assert (updated, unknown) == (1, ["B0NOPE"])
    api.apply_keywords({"B0TEST0001": p}, [api.KeywordItem(asin="B0TEST0001", keyword="")])
    assert (p.main_keyword, p.main_keyword_source) == (None, None)


# ---- HTTP ----


class _FakeResult:
    def __init__(self, value=None, row=None):
        self._value, self._row = value, row

    def scalar_one_or_none(self):
        return self._value

    def first(self):
        return self._row


class _FakeDb:
    def __init__(self, scalar=None, row=None):
        self.scalar, self.row, self.commits = scalar, row, 0

    async def execute(self, statement):
        return _FakeResult(self.scalar, self.row)

    async def commit(self):
        self.commits += 1


def _client(db=None, admin=True):
    db = db or _FakeDb()
    app = FastAPI()
    app.include_router(api.router, prefix="/catalog-monitor")

    async def _db():
        yield db

    app.dependency_overrides[deps.get_db] = _db
    app.dependency_overrides[deps.get_current_user] = lambda: USER
    app.dependency_overrides[deps.get_user_organization] = lambda: ORG
    if admin:
        app.dependency_overrides[deps.get_admin_organization] = lambda: ORG
    return TestClient(app), db


@pytest.fixture
def known_account(monkeypatch):
    async def _ok(db, organization_id, account_id):
        return SimpleNamespace(id=account_id, organization_id=organization_id)

    monkeypatch.setattr(api, "_account_or_404", _ok)


def test_quality_endpoint_summary_filter_and_pagination(monkeypatch, known_account):
    rows = [
        {"asin": it["asin"], "sku": it["sku"], "title": it["title"], "score": it["score"],
         "components": {"state": it["state"], "score": it["score"], "results": it["results"]},
         "created_at": datetime(2026, 11, 20, 5, tzinfo=timezone.utc)}
        for it in _rows()
    ]
    rows.append({"asin": "B0TEST0006", "sku": None, "title": "t", "score": None, "components": None,
                 "created_at": None})

    async def _load(db, account_id, search=None, asin=None):
        return rows

    async def _images(db, account_id, asins):
        return {a: f"https://img/{a}.jpg" for a in asins}

    monkeypatch.setattr(api, "_load_quality_rows", _load)
    monkeypatch.setattr(api, "_main_images", _images)
    client, _ = _client()
    r = client.get("/catalog-monitor/quality", params={"account_id": str(ACCOUNT_ID), "page_size": 2})
    body = r.json()
    assert r.status_code == 200
    assert body["total"] == 5 and body["unscanned"] == 1
    assert body["summary"]["red"] == 2
    assert [i["asin"] for i in body["items"]] == ["B0TEST0004", "B0TEST0002"]
    assert body["items"][0]["main_image_url"] == "https://img/B0TEST0004.jpg"
    assert body["last_scan_at"].startswith("2026-11-20")
    r = client.get("/catalog-monitor/quality",
                   params={"account_id": str(ACCOUNT_ID), "state": "red", "rule": "bullets"})
    assert [i["asin"] for i in r.json()["items"]] == ["B0TEST0004", "B0TEST0003"]


def test_account_from_other_org_is_404():
    client, _ = _client(db=_FakeDb(scalar=None))
    r = client.get("/catalog-monitor/quality", params={"account_id": str(uuid4())})
    assert r.status_code == 404


def test_rules_put_requires_admin():
    member_row = (ORG, UserRole.MEMBER)
    client, _ = _client(db=_FakeDb(row=member_row), admin=False)
    r = client.put("/catalog-monitor/rules", json={"overrides": []})
    assert r.status_code == 403


def test_rules_put_replaces_overrides_in_one_commit(monkeypatch):
    seen = {}

    async def _replace(db, organization_id, user_id, overrides):
        seen["n"] = len(overrides)

    async def _list(db, organization_id):
        return []

    monkeypatch.setattr(api, "_replace_overrides", _replace)
    monkeypatch.setattr(api, "_rule_overrides", _list)
    client, db = _client()
    ok = client.put("/catalog-monitor/rules",
                    json={"overrides": [{"rule_key": "title", "params": {"max_length": 60}}]})
    assert ok.status_code == 200 and seen["n"] == 1 and db.commits == 1
    bad = client.put("/catalog-monitor/rules", json={"overrides": [{"rule_key": "zzz"}]})
    assert bad.status_code == 422 and db.commits == 1


def test_rules_get_lists_defaults(monkeypatch):
    async def _list(db, organization_id):
        return []

    monkeypatch.setattr(api, "_rule_overrides", _list)
    client, _ = _client()
    body = client.get("/catalog-monitor/rules").json()
    assert body["defaults"]["title"]["params"]["max_length"] == 75 and body["overrides"] == []


def test_keywords_put_sets_manual_source(monkeypatch, known_account):
    product = SimpleNamespace(asin="B0TEST0001", main_keyword=None, main_keyword_source=None)

    async def _products(db, account_id, asins):
        return {"B0TEST0001": product}

    monkeypatch.setattr(api, "_products_by_asin", _products)
    client, db = _client()
    r = client.put("/catalog-monitor/keywords", json={
        "account_id": str(ACCOUNT_ID),
        "items": [{"asin": "B0TEST0001", "keyword": "mattoncini"}, {"asin": "B0NOPE", "keyword": "x"}],
    })
    assert r.json() == {"updated": 1, "unknown": ["B0NOPE"]}
    assert (product.main_keyword, product.main_keyword_source) == ("mattoncini", "manual")
    assert db.commits == 1


def test_scan_start_and_state(monkeypatch, known_account):
    monkeypatch.setattr(api, "start_account_scan", lambda account_id: True)
    monkeypatch.setattr(api, "scan_state", lambda account_id: {
        "running": True, "started_at": "t", "finished_at": None, "summary": None})
    client, _ = _client()
    assert client.post("/catalog-monitor/scan", json={"account_id": str(ACCOUNT_ID)}).json() == {"started": True}
    assert client.get("/catalog-monitor/scan", params={"account_id": str(ACCOUNT_ID)}).json()["running"] is True


def test_capabilities_get_null_and_check(monkeypatch, known_account):
    stored = SimpleNamespace(account_id=ACCOUNT_ID, results={"catalog": {"ok": True}}, vendor_code=None,
                             checked_at=datetime(2026, 11, 21, tzinfo=timezone.utc))

    async def _none(db, account_id):
        return None

    async def _check(db, account):
        return stored

    monkeypatch.setattr(api, "_stored_capability", _none)
    monkeypatch.setattr(api, "check_account_capabilities", _check)
    client, db = _client()
    assert client.get("/catalog-monitor/capabilities", params={"account_id": str(ACCOUNT_ID)}).json() is None
    r = client.post("/catalog-monitor/capabilities/check", json={"account_id": str(ACCOUNT_ID)})
    assert r.json()["results"] == {"catalog": {"ok": True}} and db.commits == 1


def test_quality_detail_and_export(monkeypatch, known_account):
    row = {"asin": "B0TEST0001", "sku": "S", "title": "T", "score": 90, "main_keyword": "kw",
           "main_keyword_source": "manual",
           "components": {"state": "green", "score": 90,
                          "results": [{"key": "title", "state": "green", "mandatory": True,
                                       "code": "ok", "details": {}}]},
           "created_at": None}

    async def _load(db, account_id, search=None, asin=None):
        return [row]

    async def _images(db, account_id, asins):
        return {}

    async def _content(db, account_id, asin):
        return {"title": "T", "images": [{"variant": "MAIN", "url": "https://img/x.jpg"}]}

    monkeypatch.setattr(api, "_load_quality_rows", _load)
    monkeypatch.setattr(api, "_main_images", _images)
    monkeypatch.setattr(api, "_latest_content", _content)
    client, _ = _client()
    d = client.get("/catalog-monitor/quality/B0TEST0001", params={"account_id": str(ACCOUNT_ID)}).json()
    assert d["main_keyword"] == "kw" and d["content"]["title"] == "T"
    assert d["main_image_url"] == "https://img/x.jpg"
    x = client.get("/catalog-monitor/quality/export", params={"account_id": str(ACCOUNT_ID)})
    assert x.status_code == 200 and x.content[:2] == b"PK"
    assert client.get("/catalog-monitor/quality/B0MISSING", params={"account_id": str(ACCOUNT_ID)}).status_code == 404
