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

    async def flush(self):
        pass


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


def test_legacy_snapshot_without_results_is_unscanned():
    items, unscanned = api.split_scanned(
        [{"asin": "B0TEST0001", "score": 50, "components": {"title": {"earned": 1, "max": 2}}}]
    )
    assert items == [] and unscanned == 1


def test_rule_alone_keeps_items_where_that_rule_is_not_green():
    out = api.filter_items(_rows(), rule="title")
    assert [i["asin"] for i in out] == ["B0TEST0002", "B0TEST0003", "B0TEST0005"]


@pytest.mark.parametrize(
    "rule_key,params",
    [
        ("title", {"max_length": "75"}),
        ("title", {"max_length": 7.5}),
        ("title", {"max_length": True}),
        ("main_image", {"min_fill": "x"}),
        ("attributes", {"recommended_attributes": "color"}),
        ("attributes", {"recommended_attributes": ["color", 3]}),
    ],
)
def test_validate_overrides_rejects_wrong_param_types(rule_key, params):
    with pytest.raises(HTTPException) as exc:
        api.validate_overrides([api.RuleOverrideIn(rule_key=rule_key, params=params)])
    assert exc.value.status_code == 422


def test_validate_overrides_accepts_numeric_float_and_string_lists():
    api.validate_overrides([
        api.RuleOverrideIn(rule_key="main_image", params={"min_fill": 1}),
        api.RuleOverrideIn(rule_key="attributes", params={"recommended_attributes": ["color"]}),
    ])


_BODY = {"account_id": str(uuid4())}
_ACCOUNT_ROUTES = [
    ("get", "/catalog-monitor/quality", "params"),
    ("get", "/catalog-monitor/quality/export", "params"),
    ("get", "/catalog-monitor/quality/B0TEST0001", "params"),
    ("put", "/catalog-monitor/keywords", {**_BODY, "items": []}),
    ("post", "/catalog-monitor/scan", _BODY),
    ("get", "/catalog-monitor/scan", "params"),
    ("get", "/catalog-monitor/capabilities", "params"),
    ("post", "/catalog-monitor/capabilities/check", _BODY),
    ("get", "/catalog-monitor/export", "params"),
    ("get", "/catalog-monitor/new-items/template", "params+type"),
    ("post", "/catalog-monitor/bulk/upload", "form"),
    ("post", "/catalog-monitor/new-items/upload", "form"),
]


@pytest.mark.parametrize("method,path,payload", _ACCOUNT_ROUTES)
def test_every_account_route_404s_for_another_orgs_account(method, path, payload):
    client, _ = _client(db=_FakeDb(scalar=None))
    if payload == "params":
        kwargs = {"params": _BODY}
    elif payload == "params+type":
        kwargs = {"params": {**_BODY, "product_type": "HOME"}}
    elif payload == "form":
        kwargs = {"data": _BODY, "files": {"file": ("a.xlsx", b"x", "application/octet-stream")}}
    else:
        kwargs = {"json": payload}
    assert getattr(client, method)(path, **kwargs).status_code == 404


# ---- protection, variations and approvals (R2, R3) ----

from app.models.amazon_account import AccountType  # noqa: E402
from app.services.catalog_monitor.changes import ChangeItem  # noqa: E402
from app.services.catalog_monitor.content import (  # noqa: E402
    ImageRef,
    ListingContent,
    content_from_dict,
    content_to_dict,
)

MP = "APJ6JRA9NG5V4"
NOW = datetime(2026, 11, 21, 5, tzinfo=timezone.utc)


def _anomaly(asin, kind="content_changed", field="title", status="open", base="old", live="new"):
    return SimpleNamespace(
        id=uuid4(), account_id=ACCOUNT_ID, asin=asin, kind=kind, field=field, status=status,
        baseline_value=base, live_value=live, detected_at=NOW, last_seen_at=NOW,
        change_request_id=None,
    )


def _baseline_row(asin, **kw):
    content = ListingContent(
        asin=asin, marketplace_id=MP, title="Base title", bullets=["b1", "b2"],
        description="Base description", images=[ImageRef("MAIN", "https://x/1.jpg")], **kw,
    )
    return SimpleNamespace(content=content_to_dict(content))


def _req(status="pending", batch=None, **kw):
    base = dict(
        id=uuid4(), account_id=ACCOUNT_ID, batch_id=batch or uuid4(), asin="B0TEST0001",
        sku="TEST-SKU-001", kind="content_restore", operation="PATCH", product_type="LUGGAGE",
        status=status, payload={"patches": [{"op": "replace", "path": "/attributes/x"}],
                                "file_only": status == "file_only"},
        summary={}, validation_issues=None, submission_result=None, feed_id=None,
        created_at=NOW, approved_at=None, submitted_at=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def test_restore_groups_fields_per_asin():
    a1 = _anomaly("B0TEST0001", field="title")
    a2 = _anomaly("B0TEST0001", field="bullets")
    a3 = _anomaly("B0TEST0001", field="aplus", base=3, live=0)
    a4 = _anomaly("B0TEST0002", field="description")
    baselines = {"B0TEST0001": _baseline_row("B0TEST0001"), "B0TEST0002": _baseline_row("B0TEST0002")}
    versions = {
        "B0TEST0001": {"sku": "TEST-SKU-001", "product_type": "LUGGAGE"},
        "B0TEST0002": {"product_type": None},
    }
    items, not_restorable, skipped = api.build_restore_items(
        [a1, a2, a3, a4], baselines, versions, {"B0TEST0002": "TEST-SKU-002"}
    )
    assert [i.asin for i in items] == ["B0TEST0001", "B0TEST0002"]
    first = items[0]
    assert first.kind == "content_restore" and first.sku == "TEST-SKU-001"
    assert first.product_type == "LUGGAGE"
    assert [p["path"] for p in first.patches] == ["/attributes/item_name", "/attributes/bullet_point"]
    assert first.anomalies == [a1, a2]
    assert items[1].sku == "TEST-SKU-002"  # Product.sku when the version has none
    assert [n["field"] for n in not_restorable] == ["aplus"] and not_restorable[0]["anomaly_id"] == a3.id
    assert skipped == []


def test_restore_skips_asins_without_baseline_or_without_restorable_field():
    a = _anomaly("B0TEST0001", field="title")
    b = _anomaly("B0TEST0002", field="aplus")
    items, not_restorable, skipped = api.build_restore_items(
        [a, b], {"B0TEST0002": _baseline_row("B0TEST0002")}, {}, {}
    )
    assert items == [] and len(not_restorable) == 1
    assert [(s["asin"], s["reason"]) for s in skipped] == [("B0TEST0001", "no_baseline")]


def test_restore_endpoint_creates_validates_and_links(monkeypatch, known_account):
    a1 = _anomaly("B0TEST0001", field="title")
    a_other_kind = _anomaly("B0TEST0001", kind="family_broken", field="parent:B0TEST0001")
    seen = {}

    async def _by_ids(db, organization_id, ids, lock=False):
        assert lock is True
        return [a1, a_other_kind]

    async def _baselines(db, account_id, asins):
        assert asins == ["B0TEST0001"]  # only the ASINs being restored
        return {"B0TEST0001": _baseline_row("B0TEST0001")}

    async def _versions(db, account_id, asins):
        return {"B0TEST0001": {"sku": "TEST-SKU-001", "product_type": "LUGGAGE"}}

    async def _products(db, account_id, asins):
        return {}

    class _Svc:
        def __init__(self, db):
            pass

        async def create(self, account, items, user_id, batch_id=None):
            seen["items"] = items
            for item in items:
                for an in item.anomalies:
                    an.status = "restore_requested"
            return [_req(batch=uuid4())]

        async def validate(self, account, requests):
            seen["validated"] = list(requests)
            for r in requests:
                r.status = "valid"

    monkeypatch.setattr(api, "_anomalies_by_ids", _by_ids)
    monkeypatch.setattr(api, "_baselines", _baselines)
    monkeypatch.setattr(api, "_latest_content_dicts", _versions)
    monkeypatch.setattr(api, "_products_by_asin", _products)
    monkeypatch.setattr(api, "ChangeRequestService", _Svc)
    client, db = _client()
    res = client.post(
        "/catalog-monitor/anomalies/restore",
        json={"anomaly_ids": [str(a1.id), str(a_other_kind.id)]},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["requests"][0]["status"] == "valid"
    assert [s["reason"] for s in body["skipped"]] == ["not_content_anomaly"]
    assert len(seen["items"]) == 1 and a1.status == "restore_requested"
    assert db.commits == 1


def test_reopen_anomalies_clears_link_only_for_restore_requested():
    pending = _anomaly("B0TEST0001", status="restore_requested")
    pending.change_request_id = uuid4()
    resolved = _anomaly("B0TEST0002", status="resolved")
    resolved.change_request_id = uuid4()
    api.reopen_anomalies([pending, resolved])
    assert (pending.status, pending.change_request_id) == ("open", None)
    assert resolved.status == "resolved" and resolved.change_request_id is not None


def test_variations_status_from_anomalies():
    family = SimpleNamespace(
        parent_asin="B0TEST0010", variation_theme="SIZE_NAME",
        child_asins=["B0TEST0011", "B0TEST0012", "B0TEST0013"],
    )
    detached = _anomaly("B0TEST0011", "child_detached", "parent:B0TEST0010")
    unexpected = _anomaly("B0TEST0099", "unexpected_child", "parent:B0TEST0010")
    resolved = _anomaly("B0TEST0012", "child_detached", "parent:B0TEST0010", status="resolved")
    other_family = _anomaly("B0TEST0050", "child_detached", "parent:B0TEST0020")
    out = api.build_variations(
        [family], [detached, unexpected, resolved, other_family], {"B0TEST0011", "B0TEST0012"}
    )[0]
    assert out["status"] == "partial"
    assert {c["asin"]: c["state"] for c in out["children"]} == {
        "B0TEST0011": "detached", "B0TEST0012": "ok", "B0TEST0013": "unknown",
        "B0TEST0099": "unexpected",
    }
    assert out["anomaly_ids"] == [detached.id, unexpected.id]
    broken = _anomaly("B0TEST0010", "family_broken", "parent:B0TEST0010")
    assert api.build_variations([family], [broken, detached], set())[0]["status"] == "broken"
    assert api.build_variations([family], [], {"B0TEST0011"})[0]["status"] == "ok"


def test_variation_restore_items_use_parent_sku_and_flag_missing_skus():
    items, parent_missing = api.build_variation_items(
        "B0TEST0010", "SIZE_NAME", MP, "TEST-SKU-010",
        [("B0TEST0011", "TEST-SKU-011", "LUGGAGE")],
        {"B0TEST0011": [_anomaly("B0TEST0011", "child_detached", "parent:B0TEST0010")]},
    )
    assert not parent_missing
    item = items[0]
    assert item.kind == "variation_restore" and item.sku == "TEST-SKU-011"
    assert item.patches[1]["value"][0]["parent_sku"] == "TEST-SKU-010"
    assert len(item.anomalies) == 1
    _, parent_missing = api.build_variation_items(
        "B0TEST0010", None, MP, None, [("B0TEST0011", "TEST-SKU-011", None)], {}
    )
    assert parent_missing


def test_variation_restore_endpoint_marks_missing_sku_file_only(monkeypatch):
    async def _account(db, organization_id, account_id):
        return SimpleNamespace(id=account_id, organization_id=organization_id, marketplace_id=MP)

    monkeypatch.setattr(api, "_account_or_404", _account)
    detached = _anomaly("B0TEST0011", "child_detached", "parent:B0TEST0010")
    created = []

    async def _families(db, account_id):
        return [SimpleNamespace(parent_asin="B0TEST0010", variation_theme="SIZE_NAME",
                                child_asins=["B0TEST0011"])]

    async def _anoms(db, account_id, lock=False):
        assert lock is True
        return [detached]

    async def _content(db, account_id, asins):
        return {a: {"product_type": "LUGGAGE", "sku": None} for a in asins}

    async def _products(db, account_id, asins):
        return {"B0TEST0011": SimpleNamespace(sku="TEST-SKU-011")}

    class _Svc:
        def __init__(self, db):
            pass

        async def create(self, account, items, user_id, batch_id=None):
            created.extend(items)
            return [_req(status="pending", kind="variation_restore")]

        async def validate(self, account, requests):
            pass

    monkeypatch.setattr(api, "_family_baselines", _families)
    monkeypatch.setattr(api, "_variation_anomalies", _anoms)
    monkeypatch.setattr(api, "_latest_content_dicts", _content)
    monkeypatch.setattr(api, "_products_by_asin", _products)
    monkeypatch.setattr(api, "ChangeRequestService", _Svc)
    client, _ = _client()
    res = client.post(
        "/catalog-monitor/variations/restore",
        json={"account_id": str(ACCOUNT_ID), "parent_asin": "B0TEST0010"},
    )
    assert res.status_code == 200, res.text
    assert [i.asin for i in created] == ["B0TEST0011"]
    # the parent has no SKU anywhere: the request is a file, never an API write
    assert res.json()["requests"][0]["file_only"] is True


def test_history_lists_newest_first_with_changes_against_previous_version():
    def version(title, day):
        content = ListingContent(asin="B0TEST0001", marketplace_id=MP, title=title)
        return SimpleNamespace(
            id=uuid4(), content_hash=title, content=content_to_dict(content),
            first_seen_at=datetime(2026, 11, day, tzinfo=timezone.utc),
            last_seen_at=datetime(2026, 11, day, tzinfo=timezone.utc),
        )

    newest, middle, oldest = version("C", 20), version("B", 10), version("A", 1)
    out = api.build_history([newest, middle, oldest])
    assert [v["content_hash"] for v in out] == ["C", "B", "A"]
    assert out[2]["changes"] == []
    assert out[1]["changes"][0]["field"] == "title" and out[1]["changes"][0]["baseline"] == "A"
    assert out[0]["changes"][0]["live"] == "C"


def test_submit_requires_admin():
    client, _ = _client(db=_FakeDb(row=(ORG, UserRole.MEMBER)), admin=False)
    for action in ("submit", "approve", "refresh-feed"):
        body = {"ids": [str(uuid4())]} if action != "refresh-feed" else {
            "account_id": str(ACCOUNT_ID), "feed_id": "F1"}
        assert client.post(f"/catalog-monitor/changes/{action}", json=body).status_code == 403


def _approval_app(monkeypatch, rows):
    async def _lock(db, organization_id, ids):
        return [r for r in rows if r.id in set(ids)]

    async def _account(db, organization_id, account_id):
        return SimpleNamespace(id=account_id, organization_id=organization_id,
                               marketplace_id=MP, account_type=AccountType.SELLER)

    async def _reopen(db, requests):
        _reopen.seen = [r.id for r in requests]

    monkeypatch.setattr(api, "_requests_for_update", _lock)
    monkeypatch.setattr(api, "_account_or_404", _account)
    monkeypatch.setattr(api, "_reopen_for_requests", _reopen)
    return _reopen


def test_approve_skips_requests_in_other_statuses(monkeypatch):
    valid, invalid = _req("valid"), _req("invalid")
    _approval_app(monkeypatch, [valid, invalid])
    client, db = _client()
    missing = uuid4()
    res = client.post(
        "/catalog-monitor/changes/approve",
        json={"ids": [str(valid.id), str(invalid.id), str(missing)]},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert valid.status == "approved" and invalid.status == "invalid"
    assert body["skipped"] == {str(invalid.id): "status_invalid", str(missing): "not_found"}
    assert db.commits == 1


def test_reject_reopens_the_anomalies_of_rejected_requests(monkeypatch):
    pending, sent = _req("pending"), _req("accepted")
    reopen = _approval_app(monkeypatch, [pending, sent])
    client, _ = _client()
    res = client.post(
        "/catalog-monitor/changes/reject", json={"ids": [str(pending.id), str(sent.id)]}
    )
    assert res.status_code == 200, res.text
    assert pending.status == "rejected" and sent.status == "accepted"
    assert res.json()["skipped"] == {str(sent.id): "status_accepted"}
    assert pending.id in reopen.seen


def test_submit_reopens_failed_restores_and_skips_file_only(monkeypatch):
    approved = _req("approved", validation_issues=[])
    file_only = _req("approved", payload={"patches": [], "file_only": True})
    reopen = _approval_app(monkeypatch, [approved, file_only])

    class _Svc:
        def __init__(self, db):
            pass

        async def submit(self, account, requests):
            for r in requests:
                r.status = "failed"

    monkeypatch.setattr(api, "ChangeRequestService", _Svc)
    client, _ = _client()
    res = client.post(
        "/catalog-monitor/changes/submit", json={"ids": [str(approved.id), str(file_only.id)]}
    )
    assert res.status_code == 200, res.text
    assert approved.status == "failed" and file_only.status == "approved"
    assert res.json()["skipped"] == {str(file_only.id): "file_only"}
    assert approved.id in reopen.seen


def _file_only(status="approved", **kw):
    """A request that can only travel as a feed file (no listing access or no SKU)."""
    kw.setdefault("payload", {"patches": [{"op": "replace", "path": "/attributes/x"}],
                              "file_only": True})
    return _req(status, **kw)


def _feed_app(monkeypatch, batch, rows):
    async def _batch(db, organization_id, batch_id):
        assert batch_id == batch  # requests of other batches are never loaded
        return rows

    async def _account(db, organization_id, account_id):
        return SimpleNamespace(id=account_id, organization_id=organization_id,
                               marketplace_id=MP, account_type=AccountType.SELLER)

    async def _capability(db, account_id):
        return None

    monkeypatch.setattr(api, "_batch_requests", _batch)
    monkeypatch.setattr(api, "_account_or_404", _account)
    monkeypatch.setattr(api, "_stored_capability", _capability)
    monkeypatch.setattr(api, "listing_seller_id", lambda account, cap: "SELLER1")


def test_feed_file_contains_only_approved_file_only_requests_of_the_batch(monkeypatch):
    batch = uuid4()
    approved_file = _file_only(batch=batch, sku="TEST-SKU-001")
    approved_api = _req("approved", batch=batch, sku="TEST-SKU-002", validation_issues=[])
    not_approved = _file_only("file_only", batch=batch, sku="TEST-SKU-003")
    no_sku = _file_only(batch=batch, sku=None)
    pending = _req("pending", batch=batch, sku="TEST-SKU-004")
    _feed_app(monkeypatch, batch, [approved_file, approved_api, not_approved, no_sku, pending])
    client, _ = _client()
    res = client.get("/catalog-monitor/changes/feed-file", params={"batch_id": str(batch)})
    assert res.status_code == 200, res.text
    assert res.headers["content-disposition"] == f'attachment; filename="listings-feed-{batch}.json"'
    document = res.json()
    # An API request goes through Amazon's check and the API, never a file; a
    # file-only request goes into the file only once an admin approved it.
    assert [m["sku"] for m in document["messages"]] == ["TEST-SKU-001"]
    assert document["header"]["sellerId"] == "SELLER1"
    assert res.headers["x-skipped-requests"] == str(no_sku.id)


def test_feed_file_404_when_batch_has_no_approved_file_only_request(monkeypatch):
    batch = uuid4()
    _feed_app(monkeypatch, batch, [
        _req("pending", batch=batch), _file_only("file_only", batch=batch),
        _req("approved", batch=batch, validation_issues=[]),
    ])
    client, _ = _client()
    assert client.get(
        "/catalog-monitor/changes/feed-file", params={"batch_id": str(batch)}
    ).status_code == 404


def test_new_account_routes_404_for_another_orgs_account():
    client, _ = _client(db=_FakeDb(scalar=None))
    other = {"account_id": str(uuid4())}
    for method, path, kwargs in [
        ("get", "/catalog-monitor/anomalies", {"params": other}),
        ("get", "/catalog-monitor/history/B0TEST0001", {"params": other}),
        ("get", "/catalog-monitor/baselines/status", {"params": other}),
        ("post", "/catalog-monitor/baselines", {"json": other}),
        ("get", "/catalog-monitor/variations", {"params": other}),
        ("post", "/catalog-monitor/variations/restore", {"json": {**other, "parent_asin": "B0TEST0010"}}),
        ("get", "/catalog-monitor/changes", {"params": other}),
        ("post", "/catalog-monitor/changes/refresh-feed", {"json": {**other, "feed_id": "F1"}}),
    ]:
        assert getattr(client, method)(path, **kwargs).status_code == 404, path


def test_locked_request_load_uses_for_update_in_postgres():
    from sqlalchemy.dialects import postgresql

    captured = {}

    class _Db:
        async def execute(self, statement):
            captured["sql"] = str(statement.compile(dialect=postgresql.dialect()))
            return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: []))

    import asyncio

    asyncio.run(api._requests_for_update(_Db(), uuid4(), [uuid4()]))
    assert "FOR UPDATE" in captured["sql"] and "organization_id" in captured["sql"]


# ---- review follow-ups ----


class _ScalarsDb(_FakeDb):
    """Returns the given rows for every select (enough for the reopen query)."""

    def __init__(self, rows):
        super().__init__()
        self.rows = rows

    async def execute(self, statement):
        rows = self.rows
        return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: rows))


def test_second_variation_restore_creates_nothing(monkeypatch):
    pending = _anomaly("B0TEST0011", "child_detached", "parent:B0TEST0010", status="restore_requested")
    pending.change_request_id = uuid4()  # its restore still waits for approval
    created = []

    async def _statuses(db, ids):
        return {i: "approved" for i in ids}

    async def _account(db, organization_id, account_id):
        return SimpleNamespace(id=account_id, organization_id=organization_id, marketplace_id=MP)

    async def _families(db, account_id):
        return [SimpleNamespace(parent_asin="B0TEST0010", variation_theme=None,
                                child_asins=["B0TEST0011"])]

    async def _anoms(db, account_id, lock=False):
        assert lock is True
        return [pending]

    class _Svc:
        def __init__(self, db):
            pass

        async def create(self, *a, **k):
            created.append(a)
            return []

    monkeypatch.setattr(api, "_account_or_404", _account)
    monkeypatch.setattr(api, "_family_baselines", _families)
    monkeypatch.setattr(api, "_variation_anomalies", _anoms)
    monkeypatch.setattr(api, "_request_statuses", _statuses)
    monkeypatch.setattr(api, "ChangeRequestService", _Svc)
    client, _ = _client()
    for body in (
        {"account_id": str(ACCOUNT_ID), "parent_asin": "B0TEST0010"},
        {"account_id": str(ACCOUNT_ID), "parent_asin": "B0TEST0010", "child_asins": ["B0TEST0011"]},
    ):
        res = client.post("/catalog-monitor/variations/restore", json=body)
        assert res.status_code == 200, res.text
        assert res.json()["requests"] == [] and res.json()["batch_id"] is None
        assert [s["reason"] for s in res.json()["skipped"]] == ["status_restore_requested"]
    assert created == []


def test_existing_image_slots_is_highest_filled_other_slot():
    def content(*variants):
        return {"images": [{"variant": v, "url": f"https://x/{v}.jpg"} for v in variants]}

    assert api.existing_image_slots(None) == 0
    assert api.existing_image_slots(content("MAIN")) == 0
    assert api.existing_image_slots(content("MAIN", "PT01", "PT03")) == 3
    assert api.existing_image_slots(content("MAIN", "PT08")) == 8


def test_image_restore_deletes_only_live_filled_slots():
    anomaly = _anomaly("B0TEST0001", field="images")
    baselines = {"B0TEST0001": _baseline_row("B0TEST0001")}  # baseline: MAIN only
    live = {"images": [{"variant": v, "url": "https://x/a.jpg"} for v in ("MAIN", "PT01", "PT02")]}
    items, _, _ = api.build_restore_items([anomaly], baselines, {"B0TEST0001": live}, {})
    deletes = [p["path"] for p in items[0].patches if p["op"] == "delete"]
    assert deletes == [
        "/attributes/other_product_image_locator_1",
        "/attributes/other_product_image_locator_2",
    ]
    items, _, _ = api.build_restore_items([anomaly], baselines, {}, {})
    assert [p for p in items[0].patches if p["op"] == "delete"] == []


def test_feed_file_excludes_requests_with_missing_parent_sku(monkeypatch):
    batch = uuid4()
    good = _file_only(batch=batch, sku="TEST-SKU-001")
    bad = _file_only(batch=batch, sku="TEST-SKU-002", summary={"parent_sku_missing": True})
    _feed_app(monkeypatch, batch, [good, bad])
    client, _ = _client()
    res = client.get("/catalog-monitor/changes/feed-file", params={"batch_id": str(batch)})
    assert [m["sku"] for m in res.json()["messages"]] == ["TEST-SKU-001"]
    assert res.headers["x-skipped-requests"] == str(bad.id)


def test_restore_invalid_at_create_reopens_its_anomaly(monkeypatch, known_account):
    anomaly = _anomaly("B0TEST0001", field="title")

    async def _by_ids(db, organization_id, ids, lock=False):
        return [anomaly]

    async def _baselines(db, account_id, asins):
        assert asins == ["B0TEST0001"]  # only the ASINs being restored
        return {"B0TEST0001": _baseline_row("B0TEST0001")}

    async def _contents(db, account_id, asins):
        return {"B0TEST0001": {"sku": "TEST-SKU-001", "product_type": "LUGGAGE"}}

    async def _products(db, account_id, asins):
        return {}

    class _Svc:
        def __init__(self, db):
            pass

        async def create(self, account, items, user_id, batch_id=None):
            row = _req("pending")
            for an in items[0].anomalies:
                an.status, an.change_request_id = "restore_requested", row.id
            return [row]

        async def validate(self, account, requests):
            requests[0].status = "invalid"

    monkeypatch.setattr(api, "_anomalies_by_ids", _by_ids)
    monkeypatch.setattr(api, "_baselines", _baselines)
    monkeypatch.setattr(api, "_latest_content_dicts", _contents)
    monkeypatch.setattr(api, "_products_by_asin", _products)
    monkeypatch.setattr(api, "ChangeRequestService", _Svc)
    # the real _reopen_for_requests runs against a db that returns the linked anomaly
    client, _ = _client(db=_ScalarsDb([anomaly]))
    res = client.post("/catalog-monitor/anomalies/restore", json={"anomaly_ids": [str(anomaly.id)]})
    assert res.status_code == 200, res.text
    assert res.json()["requests"][0]["status"] == "invalid"
    assert (anomaly.status, anomaly.change_request_id) == ("open", None)


def test_refresh_feed_failure_reopens_anomalies(monkeypatch, known_account):
    anomaly = _anomaly("B0TEST0001", status="restore_requested")
    row = _req("submitted", feed_id="F1")
    anomaly.change_request_id = row.id

    class _Svc:
        def __init__(self, db, repo=None):
            pass

        async def refresh_feed(self, account, feed_id):
            row.status = "failed"

    class _Repo:
        def __init__(self, db):
            pass

        async def change_requests_for_feed(self, account_id, feed_id):
            return [row]

    monkeypatch.setattr(api, "ChangeRequestService", _Svc)
    monkeypatch.setattr(api, "CatalogMonitorRepository", _Repo)
    client, db = _client(db=_ScalarsDb([anomaly]))
    res = client.post(
        "/catalog-monitor/changes/refresh-feed", json={"account_id": str(ACCOUNT_ID), "feed_id": "F1"}
    )
    assert res.status_code == 200, res.text
    assert res.json()[0]["status"] == "failed"
    assert (anomaly.status, anomaly.change_request_id) == ("open", None)
    assert db.commits == 1


# ---- bulk export, upload and new items (R4) ----

import io  # noqa: E402

from openpyxl import Workbook, load_workbook  # noqa: E402

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _xlsx(headers, rows):
    wb = Workbook()
    ws = wb.active
    ws.title = "Catalogo"
    ws.append(headers)
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _live(asin, **kw):
    base = dict(asin=asin, marketplace_id=MP, sku=f"SKU-{asin}", title="Titolo vecchio",
                bullets=["Uno", "Due", "Tre", "Quattro", "Cinque"], product_type="HOME")
    base.update(kw)
    return content_to_dict(ListingContent(**base))


def _product(asin, keyword=None):
    return SimpleNamespace(asin=asin, sku=f"SKU-{asin}", title="T", main_keyword=keyword,
                           main_keyword_source=None)


@pytest.fixture
def bulk_account(monkeypatch):
    account = SimpleNamespace(id=ACCOUNT_ID, organization_id=ORG.id, marketplace_id=MP,
                              account_type=AccountType.SELLER)

    async def _ok(db, organization_id, account_id):
        return account

    monkeypatch.setattr(api, "_account_or_404", _ok)
    return account


class _BatchSvc:
    created: list = []

    def __init__(self, db, *a, **kw):
        pass

    async def create(self, account, items, user_id, batch_id=None):
        type(self).created = list(items)
        return [_req(batch=batch_id, asin=i.asin, sku=i.sku, kind=i.kind, operation=i.operation)
                for i in items]

    async def validate(self, account, requests):
        for r in requests:
            r.status = "valid"


def _upload(client, data, name="catalogo.xlsx", mode="update", **extra):
    return client.post(
        "/catalog-monitor/bulk/upload",
        data={"account_id": str(ACCOUNT_ID), "mode": mode, **extra},
        files={"file": (name, data, XLSX)},
    )


def _bulk_fakes(monkeypatch, products, contents):
    async def _products_of(db, account_id):
        return products

    async def _contents(db, account_id, asins):
        return {a: contents[a] for a in asins if a in contents}

    async def _no_live_skus(db, account_id):
        return set()

    monkeypatch.setattr(api, "_account_products", _products_of)
    monkeypatch.setattr(api, "_live_skus", _no_live_skus)
    monkeypatch.setattr(api, "_latest_content_dicts", _contents)
    _BatchSvc.created = []
    monkeypatch.setattr(api, "ChangeRequestService", _BatchSvc)


def test_upload_returns_row_errors_and_creates_only_changed(monkeypatch, bulk_account):
    p1, p2, p3 = _product("B0TEST0001"), _product("B0TEST0002", "vecchia"), _product("B0TEST0003")
    _bulk_fakes(monkeypatch, [p1, p2, p3], {a: _live(a) for a in ("B0TEST0001", "B0TEST0002", "B0TEST0003")})
    data = _xlsx(
        ["asin", "title", "bullet_2", "main_keyword"],
        [
            ["B0TEST0001", "Titolo nuovo", "", ""],         # changed
            ["B0TEST0002", "Titolo vecchio", "", "nuova"],  # unchanged content, keyword set
            ["B0NOPE0001", "Altro", "", ""],                # not in the account
            ["B0TEST0003", "x" * 201, "", ""],              # over the title limit
            ["B0TEST0001", "Duplicato", "", ""],            # same ASIN twice
        ],
    )
    client, db = _client()
    res = _upload(client, data)
    assert res.status_code == 200, res.text
    body = res.json()
    assert (body["rows"], body["changes"], body["unchanged"], body["keywords_updated"]) == (5, 1, 1, 1)
    assert body["batch_id"] and [r["status"] for r in body["requests"]] == ["valid"]
    errors = {e["row"]: e["message"] for e in body["row_errors"]}
    assert errors[4] == "ASIN non trovato in questo account"
    assert "title" in errors[5] and 6 in errors
    assert [i.asin for i in _BatchSvc.created] == ["B0TEST0001"]
    assert (p2.main_keyword, p2.main_keyword_source) == ("nuova", "manual")
    assert db.commits == 1


def test_upload_ignores_limits_of_cells_equal_to_the_live_content(monkeypatch, bulk_account):
    # Found in the end-to-end run: export, change bullet_2, upload -> the row was refused
    # because its untouched live highlights were already over 125 characters.
    live = _live("B0TEST0001", item_highlights="h" * 130)
    _bulk_fakes(monkeypatch, [_product("B0TEST0001")], {"B0TEST0001": live})
    data = _xlsx(["asin", "item_highlights", "bullet_2"], [["B0TEST0001", "h" * 130, "Due nuovo"]])
    client, _ = _client()
    body = _upload(client, data).json()
    assert (body["changes"], body["row_errors"]) == (1, [])
    assert list(_BatchSvc.created[0].summary["fields"]) == ["bullets"]
    over = _xlsx(["asin", "item_highlights"], [["B0TEST0001", "k" * 126]])
    errors = _upload(client, over).json()["row_errors"]
    assert [e["row"] for e in errors] == [2] and "item_highlights" in errors[0]["message"]


def test_upload_matches_by_sku_when_asin_is_missing(monkeypatch, bulk_account):
    _bulk_fakes(monkeypatch, [_product("B0TEST0001")], {"B0TEST0001": _live("B0TEST0001")})
    data = _xlsx(["sku", "title"], [["SKU-B0TEST0001", "Titolo nuovo"]])
    client, _ = _client()
    body = _upload(client, data).json()
    assert body["changes"] == 1 and _BatchSvc.created[0].asin == "B0TEST0001"


def test_upload_without_changes_creates_no_batch(monkeypatch, bulk_account):
    _bulk_fakes(monkeypatch, [_product("B0TEST0001")], {"B0TEST0001": _live("B0TEST0001")})
    data = _xlsx(["asin", "title"], [["B0TEST0001", "Titolo vecchio"]])
    client, _ = _client()
    body = _upload(client, data).json()
    assert (body["batch_id"], body["changes"], body["unchanged"], body["requests"]) == (None, 0, 1, [])
    assert _BatchSvc.created == []


@pytest.mark.parametrize("name,data", [
    ("catalogo.xlsx", b"not an excel file"),
    ("catalogo.csv", b"\xff\xfe\x00bad"),
    ("catalogo.pdf", b"%PDF"),
])
def test_unreadable_upload_is_422_not_500(monkeypatch, bulk_account, name, data):
    _bulk_fakes(monkeypatch, [], {})
    client, _ = _client()
    res = _upload(client, data, name=name)
    assert res.status_code == 422 and "file" in res.json()["detail"].lower()


def test_upload_over_ten_megabytes_is_413(monkeypatch, bulk_account):
    _bulk_fakes(monkeypatch, [], {})
    client, _ = _client()
    assert _upload(client, b"x" * (10 * 1024 * 1024 + 1)).status_code == 413


def test_baseline_mode_does_not_create_requests(monkeypatch, bulk_account):
    p1 = _product("B0TEST0001")
    _bulk_fakes(monkeypatch, [p1], {})
    seen = {}

    async def _import(repo, account_id, rows, user_id):
        seen["rows"] = rows
        return len(rows), []

    monkeypatch.setattr(api, "import_baseline_rows", _import)
    data = _xlsx(["asin", "title", "main_keyword"], [["B0TEST0001", "Titolo approvato", "chiave"], ["B0NOPE0001", "x", ""]])
    client, db = _client(db=_FakeDb(row=(ORG, UserRole.ADMIN)))
    res = _upload(client, data, mode="baseline")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["updated"] == 1 and body["keywords_updated"] == 1
    assert body["row_errors"][0]["message"] == "ASIN non trovato in questo account"
    assert seen["rows"] == [("B0TEST0001", {"title": "Titolo approvato"})]
    assert _BatchSvc.created == [] and p1.main_keyword == "chiave" and db.commits == 1


def test_baseline_mode_needs_admin(monkeypatch, bulk_account):
    _bulk_fakes(monkeypatch, [], {})
    client, _ = _client(db=_FakeDb(row=(ORG, UserRole.MEMBER)), admin=False)
    data = _xlsx(["asin", "title"], [["B0TEST0001", "x"]])
    assert _upload(client, data, mode="baseline").status_code == 403


def test_upload_rejects_unknown_mode(monkeypatch, bulk_account):
    _bulk_fakes(monkeypatch, [], {})
    client, _ = _client()
    assert _upload(client, _xlsx(["asin"], []), mode="nope").status_code == 422


def test_export_is_an_xlsx_with_one_row_per_product(monkeypatch, bulk_account):
    async def _products(db, account_id):
        return [_product("B0TEST0001"), _product("B0TEST0002")]

    async def _contents(db, account_id, asins):
        return {"B0TEST0001": content_from_dict(_live("B0TEST0001"))}

    monkeypatch.setattr(api, "_export_products", _products)
    monkeypatch.setattr(api, "_export_contents", _contents)
    client, _ = _client()
    res = client.get("/catalog-monitor/export", params={"account_id": str(ACCOUNT_ID)})
    assert res.status_code == 200 and "attachment" in res.headers["content-disposition"]
    ws = load_workbook(io.BytesIO(res.content))["Catalogo"]
    assert [r[0] for r in ws.iter_rows(min_row=2, values_only=True)] == ["B0TEST0001", "B0TEST0002"]


def test_export_reads_live_content_a_chunk_at_a_time(monkeypatch, bulk_account):
    asins = [f"B0TEST000{n}" for n in range(1, 6)]
    calls = []

    async def _products(db, account_id):
        return [_product(a) for a in asins]

    async def _contents(db, account_id, chunk):
        calls.append(list(chunk))
        extra = {"attributes": {"material": [{"value": "Legno", "marketplace_id": MP}]}}
        return {a: content_from_dict(_live(a, **(extra if a == "B0TEST0005" else {}))) for a in chunk}

    monkeypatch.setattr(api, "EXPORT_CHUNK", 2)
    monkeypatch.setattr(api, "_export_products", _products)
    monkeypatch.setattr(api, "_export_contents", _contents)
    client, _ = _client()
    res = client.get("/catalog-monitor/export", params={"account_id": str(ACCOUNT_ID)})
    assert res.status_code == 200, res.text
    assert all(len(c) <= 2 for c in calls) and {a for c in calls for a in c} == set(asins)
    ws = load_workbook(io.BytesIO(res.content))["Catalogo"]
    headers = [c.value for c in ws[1]]
    assert "attr:material" in headers  # found in the last chunk, a column for every row
    assert [r[0] for r in ws.iter_rows(min_row=2, values_only=True)] == asins


def _ptd(monkeypatch, required):
    async def _required(db, account, product_type):
        return required

    monkeypatch.setattr(api, "_product_type_required", _required)


def test_new_item_template_has_sku_type_required_then_recommended(monkeypatch, bulk_account):
    _ptd(monkeypatch, ["brand", "item_name"])
    client, _ = _client()
    res = client.get("/catalog-monitor/new-items/template",
                     params={"account_id": str(ACCOUNT_ID), "product_type": "HOME"})
    assert res.status_code == 200
    header = [c.value for c in load_workbook(io.BytesIO(res.content))["Nuovi articoli"][1]]
    assert header[:4] == ["sku", "product_type", "brand", "item_name"]
    assert "color" in header and header.count("brand") == 1


def test_new_item_template_422_when_definition_unavailable(monkeypatch, bulk_account):
    _ptd(monkeypatch, None)
    client, _ = _client()
    res = client.get("/catalog-monitor/new-items/template",
                     params={"account_id": str(ACCOUNT_ID), "product_type": "HOME"})
    assert res.status_code == 422
    assert "Definizione del tipo di prodotto non disponibile" in res.json()["detail"]


def test_new_item_upload_creates_put_requests_and_reports_row_errors(monkeypatch, bulk_account):
    _bulk_fakes(monkeypatch, [_product("B0TEST0001")], {})
    _ptd(monkeypatch, ["brand", "item_name"])
    data = _xlsx(
        ["sku", "product_type", "brand", "item_name", "item_weight.value", "item_weight.unit"],
        [
            ["TEST-NEW-001", "HOME", "TESTBRAND", "Nome", "2", "kilograms"],
            ["TEST-NEW-002", "HOME", "TESTBRAND", "", "", ""],            # item_name missing
            ["SKU-B0TEST0001", "HOME", "TESTBRAND", "Nome", "", ""],     # SKU already live
            ["", "HOME", "TESTBRAND", "Nome", "", ""],                    # sku missing
        ],
    )
    client, db = _client()
    res = client.post("/catalog-monitor/new-items/upload",
                      data={"account_id": str(ACCOUNT_ID)}, files={"file": ("nuovi.xlsx", data, XLSX)})
    assert res.status_code == 200, res.text
    body = res.json()
    assert (body["rows"], body["changes"]) == (4, 1) and body["requests"][0]["status"] == "valid"
    item = _BatchSvc.created[0]
    assert (item.operation, item.kind, item.sku, item.asin) == ("PUT", "new_item", "TEST-NEW-001", None)
    assert item.attributes["brand"] == [{"value": "TESTBRAND", "language_tag": "it_IT", "marketplace_id": MP}]
    assert item.attributes["item_weight"] == [{"value": "2", "unit": "kilograms", "marketplace_id": MP}]
    messages = {e["row"]: e["message"] for e in body["row_errors"]}
    assert "item_name" in messages[3] and "già presente" in messages[4] and "sku" in messages[5]
    assert db.commits == 1


def test_new_item_upload_row_error_when_definition_unavailable(monkeypatch, bulk_account):
    _bulk_fakes(monkeypatch, [], {})
    _ptd(monkeypatch, None)
    data = _xlsx(["sku", "product_type", "brand"], [["TEST-NEW-001", "HOME", "TESTBRAND"]])
    client, _ = _client()
    body = client.post("/catalog-monitor/new-items/upload", data={"account_id": str(ACCOUNT_ID)},
                       files={"file": ("n.xlsx", data, XLSX)}).json()
    assert body["changes"] == 0 and "non disponibile" in body["row_errors"][0]["message"]


def test_old_bulk_endpoint_is_gone_410():
    from app.api.v1 import catalog as old

    app = FastAPI()
    app.include_router(old.router, prefix="/catalog")
    app.dependency_overrides[deps.get_current_user] = lambda: USER
    client = TestClient(app)
    detail = "Usa Catalogo → Aggiornamento massivo: le modifiche ora passano dall'approvazione."
    res = client.post("/catalog/bulk-update", params={"account_id": str(uuid4())},
                      files={"file": ("a.xlsx", b"x", XLSX)})
    assert (res.status_code, res.json()["detail"]) == (410, detail)
    res = client.get("/catalog/bulk-update/template")
    assert (res.status_code, res.json()["detail"]) == (410, detail)


def test_submit_skip_reason_flags_requests_that_did_not_pass_validation():
    ok = _req("approved", validation_issues=[])
    bad = _req("approved", validation_issues=[{"severity": "ERROR", "code": "X", "message": "m"}])
    never = _req("approved", validation_issues=None)
    assert api.submit_skip_reason(ok) is None
    assert api.submit_skip_reason(bad) == "not_validated"
    assert api.submit_skip_reason(never) == "not_validated"
    assert api.submit_skip_reason(_req("valid")) == "status_valid"


def test_new_item_upload_refuses_a_sku_known_only_from_live_content(monkeypatch, bulk_account):
    _bulk_fakes(monkeypatch, [], {})  # no Product carries the SKU

    async def _live_skus(db, account_id):
        return {"TEST-LIVE-001"}

    monkeypatch.setattr(api, "_live_skus", _live_skus)
    _ptd(monkeypatch, ["brand"])
    data = _xlsx(["sku", "product_type", "brand"],
                 [["TEST-LIVE-001", "HOME", "TESTBRAND"], ["TEST-NEW-002", "HOME", "TESTBRAND"]])
    client, _ = _client()
    body = client.post("/catalog-monitor/new-items/upload", data={"account_id": str(ACCOUNT_ID)},
                       files={"file": ("n.xlsx", data, XLSX)}).json()
    assert [i.sku for i in _BatchSvc.created] == ["TEST-NEW-002"]
    assert body["row_errors"][0]["row"] == 2 and "già presente" in body["row_errors"][0]["message"]


# ---- Task 17 review: change type, manual upload, admin baselines ----

from app.services.catalog_monitor.diff import diff_content  # noqa: E402


def _content(**kw):
    return ListingContent(asin="B0TEST0001", marketplace_id=MP, **kw)


@pytest.mark.parametrize("baseline,live", [
    (_content(title="Borraccia 500 ml"), _content(title="Borraccia 750 ml")),
    (_content(title="Borraccia 500 ml"), _content(title="")),
    (_content(bullets=["a", "b", "c"]), _content(bullets=["c", "a", "b"])),
    (_content(bullets=["a", "b", "c"]), _content(bullets=["a", "b"])),
    (_content(bullets=["a", "b"]), _content(bullets=[])),
    (_content(images=[ImageRef("MAIN", "https://x/1.jpg"), ImageRef("PT01", "https://x/2.jpg")]),
     _content(images=[ImageRef("MAIN", "https://x/2.jpg"), ImageRef("PT01", "https://x/1.jpg")])),
    (_content(aplus_available=True, aplus_module_count=5),
     _content(aplus_available=True, aplus_module_count=0)),
    (_content(aplus_available=True, aplus_module_count=5),
     _content(aplus_available=True, aplus_module_count=3)),
    (_content(attributes={"material": [{"value": "Acciaio", "marketplace_id": MP}]}),
     _content(attributes={"material": [{"value": "Plastica", "marketplace_id": MP}]})),
    (_content(attributes={"color": [{"value": "Blu"}, {"value": "Rosso"}]}),
     _content(attributes={"color": [{"value": "Rosso"}, {"value": "Blu"}]})),
    (_content(attributes={"material": [{"value": "Acciaio"}]}), _content(attributes={})),
])
def test_anomaly_change_agrees_with_diff_content(baseline, live):
    changes = diff_content(baseline, live)
    assert changes
    for change in changes:
        assert api.anomaly_change("content_changed", change.baseline, change.live) == change.change


def test_anomaly_change_only_for_content_anomalies():
    assert api.anomaly_change("child_detached", "B0TEST0010", []) is None
    out = api.anomaly_out(_anomaly("B0TEST0001", field="bullets", base=["a", "b"], live=["b", "a"]))
    assert out.change == "reordered"


def test_anomalies_route_returns_the_change_type(monkeypatch, known_account):
    async def _list(db, account_id, kind, statuses, search):
        return [(_anomaly("B0TEST0001", field="title", base="Titolo", live=""), "Titolo")]

    monkeypatch.setattr(api, "_list_anomalies", _list)
    client, _ = _client()
    body = client.get("/catalog-monitor/anomalies", params={"account_id": str(ACCOUNT_ID)}).json()
    assert [(a["field"], a["change"]) for a in body] == [("title", "missing")]


def test_mark_uploaded_submits_only_approved_file_only_requests(monkeypatch):
    by_hand = _req("approved", payload={"patches": [], "file_only": True})
    through_api = _req("approved", validation_issues=[])
    not_approved = _req("file_only")
    _approval_app(monkeypatch, [by_hand, through_api, not_approved])
    client, db = _client()
    missing = uuid4()
    ids = [by_hand.id, through_api.id, not_approved.id, missing]
    res = client.post("/catalog-monitor/changes/mark-uploaded", json={"ids": [str(i) for i in ids]})
    assert res.status_code == 200, res.text
    assert by_hand.status == "submitted" and by_hand.submitted_at is not None
    assert by_hand.submission_result["manual"] is True
    assert by_hand.submission_result["by"] == str(USER.id)
    assert (through_api.status, not_approved.status) == ("approved", "file_only")
    assert res.json()["skipped"] == {
        str(through_api.id): "not_file_only",
        str(not_approved.id): "status_file_only",
        str(missing): "not_found",
    }
    assert db.commits == 1


def test_mark_uploaded_skips_requests_never_in_the_file(monkeypatch):
    in_file = _file_only()
    parent_missing = _file_only(summary={"parent_sku_missing": True})
    _approval_app(monkeypatch, [in_file, parent_missing])
    client, _ = _client()
    res = client.post(
        "/catalog-monitor/changes/mark-uploaded",
        json={"ids": [str(in_file.id), str(parent_missing.id)]},
    )
    assert res.status_code == 200, res.text
    assert (in_file.status, parent_missing.status) == ("submitted", "approved")
    assert res.json()["skipped"] == {str(parent_missing.id): "not_in_file"}


def test_mark_uploaded_and_baseline_approval_require_admin():
    client, _ = _client(db=_FakeDb(row=(ORG, UserRole.MEMBER)), admin=False)
    assert client.post(
        "/catalog-monitor/changes/mark-uploaded", json={"ids": [str(uuid4())]}
    ).status_code == 403
    assert client.post(
        "/catalog-monitor/baselines", json={"account_id": str(ACCOUNT_ID)}
    ).status_code == 403


def test_cors_exposes_the_download_headers():
    # Read from the source: importing app.main would load every router in this process.
    import ast
    import pathlib

    tree = ast.parse((pathlib.Path(api.__file__).parents[2] / "main.py").read_text())
    [cors] = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "add_middleware"
        and isinstance(node.args[0], ast.Name) and node.args[0].id == "CORSMiddleware"
    ]
    exposed = next(k.value for k in cors.keywords if k.arg == "expose_headers")
    assert {"X-Skipped-Requests", "Content-Disposition"} <= set(ast.literal_eval(exposed))


# ---- final review: stuck restore_requested anomalies ----


@pytest.mark.parametrize("request_status,in_progress", [
    ("pending", True), ("valid", True), ("file_only", True), ("approved", True),
    ("accepted", False), ("submitted", False), ("failed", False), ("rejected", False),
    ("invalid", False), (None, False),
])
def test_restore_in_progress_only_while_the_linked_request_can_still_go_out(
    request_status, in_progress
):
    anomaly = _anomaly("B0TEST0001", status="restore_requested")
    assert api.restore_in_progress(anomaly, request_status) is in_progress
    assert api.restore_in_progress(_anomaly("B0TEST0001"), request_status) is False


def _linked(status, request_status):
    anomaly = _anomaly("B0TEST0001", status=status)
    anomaly.change_request_id = uuid4()
    return anomaly, {anomaly.change_request_id: request_status}


def _accept_app(monkeypatch, anomaly, statuses):
    accepted = []

    async def _by_ids(db, organization_id, ids, lock=False):
        return [anomaly]

    async def _statuses(db, ids):
        return {i: statuses[i] for i in ids if i in statuses}

    async def _accept(repo, an, user_id, now):
        an.status = "resolved"
        accepted.append(an.id)

    monkeypatch.setattr(api, "_anomalies_by_ids", _by_ids)
    monkeypatch.setattr(api, "_request_statuses", _statuses)
    monkeypatch.setattr(api, "accept_anomaly", _accept)
    return accepted


@pytest.mark.parametrize("request_status", ["accepted", "submitted"])
def test_accept_unblocks_an_anomaly_whose_restore_went_out(monkeypatch, request_status):
    # The restore went out but the scan still sees the change (Amazon re-hosted the
    # image, or edited it again): without this the anomaly stays stuck for ever.
    anomaly, statuses = _linked("restore_requested", request_status)
    accepted = _accept_app(monkeypatch, anomaly, statuses)
    client, db = _client()
    res = client.post(f"/catalog-monitor/anomalies/{anomaly.id}/accept")
    assert res.status_code == 200, res.text
    assert accepted == [anomaly.id] and db.commits == 1


def test_accept_refuses_while_the_restore_is_still_in_the_queue(monkeypatch):
    anomaly, statuses = _linked("restore_requested", "approved")
    accepted = _accept_app(monkeypatch, anomaly, statuses)
    client, _ = _client()
    res = client.post(f"/catalog-monitor/anomalies/{anomaly.id}/accept")
    assert res.status_code == 409 and accepted == []


def test_restore_again_after_the_linked_restore_was_accepted(monkeypatch, known_account):
    stuck, stuck_statuses = _linked("restore_requested", "accepted")
    queued, queued_statuses = _linked("restore_requested", "valid")
    queued.asin = "B0TEST0002"
    created = {}

    async def _by_ids(db, organization_id, ids, lock=False):
        return [stuck, queued]

    async def _statuses(db, ids):
        both = {**stuck_statuses, **queued_statuses}
        return {i: both[i] for i in ids if i in both}

    async def _baselines(db, account_id, asins):
        return {a: _baseline_row(a) for a in ("B0TEST0001", "B0TEST0002")}

    async def _versions(db, account_id, asins):
        return {a: {"sku": f"SKU-{a}", "product_type": "LUGGAGE"} for a in asins}

    async def _products(db, account_id, asins):
        return {}

    class _Svc:
        def __init__(self, db):
            pass

        async def create(self, account, items, user_id, batch_id=None):
            created["anomalies"] = [a.id for item in items for a in item.anomalies]
            return [_req(batch=batch_id)]

        async def validate(self, account, requests):
            pass

    async def _reopen(db, requests):
        pass

    monkeypatch.setattr(api, "_anomalies_by_ids", _by_ids)
    monkeypatch.setattr(api, "_request_statuses", _statuses)
    monkeypatch.setattr(api, "_baselines", _baselines)
    monkeypatch.setattr(api, "_latest_content_dicts", _versions)
    monkeypatch.setattr(api, "_products_by_asin", _products)
    monkeypatch.setattr(api, "_reopen_for_requests", _reopen)
    monkeypatch.setattr(api, "ChangeRequestService", _Svc)
    client, _ = _client()
    res = client.post("/catalog-monitor/anomalies/restore",
                      json={"anomaly_ids": [str(stuck.id), str(queued.id)]})
    assert res.status_code == 200, res.text
    assert created["anomalies"] == [stuck.id]
    assert [(s["asin"], s["reason"]) for s in res.json()["skipped"]] == [
        ("B0TEST0002", "status_restore_requested")
    ]


def test_anomalies_route_returns_the_linked_request_status(monkeypatch, known_account):
    anomaly, statuses = _linked("restore_requested", "accepted")

    async def _list(db, account_id, kind, statuses_filter, search):
        return [(anomaly, "Titolo")]

    async def _statuses(db, ids):
        return {i: statuses[i] for i in ids if i in statuses}

    monkeypatch.setattr(api, "_list_anomalies", _list)
    monkeypatch.setattr(api, "_request_statuses", _statuses)
    client, _ = _client()
    [body] = client.get("/catalog-monitor/anomalies", params={"account_id": str(ACCOUNT_ID)}).json()
    assert (body["status"], body["change_request_status"]) == ("restore_requested", "accepted")


def test_accepting_an_anomaly_requires_admin(monkeypatch):
    # Accepting rewrites the protected baseline, like approving it: admins only.
    anomaly, statuses = _linked("open", None)
    accepted = _accept_app(monkeypatch, anomaly, statuses)
    client, _ = _client(db=_FakeDb(row=(ORG, UserRole.MEMBER)), admin=False)
    res = client.post(f"/catalog-monitor/anomalies/{anomaly.id}/accept")
    assert res.status_code == 403 and accepted == []


# ---- final review: xlsx work off the event loop ----


def _on_event_loop() -> bool:
    import asyncio

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return False
    return True


def _spy(monkeypatch, name):
    """Wrap an api module function; records whether each call ran on the event loop."""
    original = getattr(api, name)
    seen: list[bool] = []

    def wrapper(*args, **kwargs):
        seen.append(_on_event_loop())
        return original(*args, **kwargs)

    monkeypatch.setattr(api, name, wrapper)
    return seen


def test_upload_parsing_runs_off_the_event_loop(monkeypatch, bulk_account):
    _bulk_fakes(monkeypatch, [_product("B0TEST0001")], {"B0TEST0001": _live("B0TEST0001")})
    seen = _spy(monkeypatch, "parse_upload")
    client, _ = _client()
    assert _upload(client, _xlsx(["asin", "title"], [["B0TEST0001", "Nuovo"]])).status_code == 200
    assert seen == [False]


def test_new_item_parsing_and_template_run_off_the_event_loop(monkeypatch, bulk_account):
    _bulk_fakes(monkeypatch, [], {})
    _ptd(monkeypatch, ["brand"])
    parsed = _spy(monkeypatch, "parse_new_items")
    built = _spy(monkeypatch, "build_new_item_template")
    client, _ = _client()
    data = _xlsx(["sku", "product_type", "brand"], [["TEST-NEW-001", "HOME", "TESTBRAND"]])
    assert client.post("/catalog-monitor/new-items/upload", data={"account_id": str(ACCOUNT_ID)},
                       files={"file": ("n.xlsx", data, XLSX)}).status_code == 200
    assert client.get("/catalog-monitor/new-items/template",
                      params={"account_id": str(ACCOUNT_ID), "product_type": "HOME"}).status_code == 200
    assert (parsed, built) == ([False], [False])


def test_quality_export_is_built_off_the_event_loop(monkeypatch, known_account):
    async def _load(db, account_id, search=None, asin=None):
        return [{"asin": "B0TEST0001", "sku": "S", "title": "T", "score": 90,
                 "components": {"state": "green", "score": 90, "results": []}}]

    monkeypatch.setattr(api, "_load_quality_rows", _load)
    seen = _spy(monkeypatch, "build_quality_workbook")
    client, _ = _client()
    res = client.get("/catalog-monitor/quality/export", params={"account_id": str(ACCOUNT_ID)})
    assert res.status_code == 200 and seen == [False]
    ws = load_workbook(io.BytesIO(res.content))["quality"]
    assert [c.value for c in ws[2]][:5] == ["B0TEST0001", "S", "T", "green", 90]


# ---- final review: at most 300 changes per upload ----


def test_upload_over_the_change_cap_is_refused_before_amazon_is_asked(monkeypatch, bulk_account):
    monkeypatch.setattr(api.settings, "CATALOG_UPLOAD_MAX_CHANGES", 3)
    asins = [f"B0TEST000{n}" for n in range(1, 6)]
    products = [_product(a, keyword="vecchia") for a in asins]
    _bulk_fakes(monkeypatch, products, {a: _live(a) for a in asins})
    data = _xlsx(["asin", "title", "main_keyword"],
                 [[a, f"Titolo nuovo {a}", "nuova"] for a in asins])
    client, db = _client()
    res = _upload(client, data)
    assert res.status_code == 422
    assert res.json()["detail"] == (
        "Il file contiene 5 modifiche: il massimo per caricamento è 3. Dividi il file in più parti."
    )
    assert _BatchSvc.created == [] and db.commits == 0  # nothing created, validated or stored
    assert all(p.main_keyword == "vecchia" for p in products)


def test_upload_at_the_change_cap_goes_through(monkeypatch, bulk_account):
    monkeypatch.setattr(api.settings, "CATALOG_UPLOAD_MAX_CHANGES", 3)
    asins = [f"B0TEST000{n}" for n in range(1, 6)]
    _bulk_fakes(monkeypatch, [_product(a) for a in asins], {a: _live(a) for a in asins})
    rows = [[a, f"Titolo nuovo {a}" if n < 3 else "Titolo vecchio"] for n, a in enumerate(asins)]
    client, _ = _client()
    res = _upload(client, _xlsx(["asin", "title"], rows))
    assert res.status_code == 200, res.text
    assert (res.json()["changes"], res.json()["unchanged"]) == (3, 2)


def test_the_change_cap_is_300_by_default():
    from app.config import Settings

    assert Settings.model_fields["CATALOG_UPLOAD_MAX_CHANGES"].default == 300


def test_quality_export_writes_titles_as_text(monkeypatch, known_account):
    async def _load(db, account_id, search=None, asin=None):
        return [{"asin": "B0TEST0001", "sku": "=SKU", "title": "=1+1", "score": 90,
                 "components": {"state": "green", "score": 90, "results": []}}]

    monkeypatch.setattr(api, "_load_quality_rows", _load)
    client, _ = _client()
    res = client.get("/catalog-monitor/quality/export", params={"account_id": str(ACCOUNT_ID)})
    cells = load_workbook(io.BytesIO(res.content))["quality"][2]
    assert [(c.value, c.data_type) for c in cells[1:3]] == [("=SKU", "s"), ("=1+1", "s")]
    assert cells[4].value == 90  # numbers stay numbers


def test_upload_reads_live_content_a_chunk_at_a_time(monkeypatch, bulk_account):
    # Re-uploading a whole export is the documented workflow: thousands of rows,
    # a few changed. Live content (10-30 KB per ASIN) is read 200 rows at a time.
    monkeypatch.setattr(api, "UPLOAD_CHUNK", 2)
    asins = [f"B0TEST000{n}" for n in range(1, 6)]
    _bulk_fakes(monkeypatch, [_product(a) for a in asins], {a: _live(a) for a in asins})
    calls = []
    fake_contents = api._latest_content_dicts

    async def _contents(db, account_id, chunk):
        calls.append(list(chunk))
        return await fake_contents(db, account_id, chunk)

    monkeypatch.setattr(api, "_latest_content_dicts", _contents)
    rows = [[a, "Titolo nuovo" if a == "B0TEST0004" else "Titolo vecchio"] for a in asins]
    rows.append(["B0TEST0001", "Duplicato"])  # same ASIN in a later chunk
    client, _ = _client()
    res = _upload(client, _xlsx(["asin", "title"], rows))
    assert res.status_code == 200, res.text
    body = res.json()
    assert all(len(c) <= 2 for c in calls) and len(calls) == 3
    assert (body["changes"], body["unchanged"]) == (1, 4)
    assert [i.asin for i in _BatchSvc.created] == ["B0TEST0004"]
    assert [(e["row"], e["message"]) for e in body["row_errors"]] == [(7, "ASIN ripetuto nel file")]
