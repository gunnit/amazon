"""Change requests and the approval queue (R2-R4).

Every catalogue write is checked by Amazon with VALIDATION_PREVIEW, approved by an
admin, then submitted per SKU or as one JSON_LISTINGS_FEED. No database, no
network: a fake session records rows, a fake repository serves the account's
Amazon access, and a fake SP-API client records every call.
"""
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.config import settings
from app.core.exceptions import AmazonAPIError
from app.models.amazon_account import AccountType
from app.models.catalog_monitor import (
    CatalogAnomaly,
    CatalogApiCapability,
    CatalogChangeRequest,
    ListingContentBaseline,
)
from app.services.catalog_monitor.changes import (
    LANGUAGE_TAG_BY_MARKETPLACE,
    ChangeItem,
    ChangeRequestService,
    build_listings_feed,
    can_approve,
    can_reject,
    is_file_only,
    patches_from_content,
    restore_patches,
    text_value,
    variation_patches,
)
from app.services.catalog_monitor.content import (
    ImageRef,
    ListingContent,
    content_from_dict,
    content_to_dict,
)
from app.services.catalog_monitor.repository import CatalogMonitorRepository

MKT = "APJ6JRA9NG5V4"
SELLER = "A0TESTSELLER1"
VENDOR_CODE = "TESTV"
ACC, ORG, USER, ADMIN = uuid4(), uuid4(), uuid4(), uuid4()
FEED_ID = "50001"


# ---- fakes ----


class FakeClient:
    """Records calls; answers per SKU from ``responses`` or raises from ``errors``."""

    def __init__(
        self, responses=None, errors=None, feed_status=None, feed_report=None, listings=None,
        listing_errors=None,
    ):
        self.calls: list[tuple] = []
        self.responses = responses or {}
        self.errors = errors or {}
        self.feed_status = feed_status or {"processingStatus": "IN_PROGRESS"}
        self.feed_report = feed_report or {}
        self.listings = dict(listings or {})  # sku -> live listing payload
        self.listing_errors = dict(listing_errors or {})

    def get_listing(self, seller_id, sku, included_data=None):
        self.calls.append(("get_listing", seller_id, sku))
        if sku in self.listing_errors:
            raise self.listing_errors[sku]
        if sku not in self.listings:
            raise AmazonAPIError(f"SP-API error on get_listing: {sku} not found", error_code=404)
        return self.listings[sku]

    def _answer(self, sku, mode):
        if sku in self.errors:
            raise self.errors[sku]
        default = {"status": "VALID" if mode else "ACCEPTED", "issues": [], "submissionId": "s1"}
        return self.responses.get((sku, mode), default)

    def patch_listing(self, seller_id, sku, product_type, patches, mode=None):
        self.calls.append(("patch", seller_id, sku, product_type, patches, mode))
        return self._answer(sku, mode)

    def put_listing(self, seller_id, sku, product_type, attributes, mode=None):
        self.calls.append(("put", seller_id, sku, product_type, attributes, mode))
        return self._answer(sku, mode)

    def submit_json_listings_feed(self, document):
        self.calls.append(("feed", document))
        return FEED_ID

    def get_feed_status(self, feed_id):
        self.calls.append(("feed_status", feed_id))
        return self.feed_status

    def get_feed_result(self, document_id):
        self.calls.append(("feed_result", document_id))
        return self.feed_report

    def writes(self):
        """Calls that would change a live listing (no VALIDATION_PREVIEW)."""
        return [
            c for c in self.calls
            if c[0] == "feed" or (c[0] in ("patch", "put") and c[-1] is None)
        ]

    def previews(self):
        return [c for c in self.calls if c[0] in ("patch", "put") and c[-1] == "VALIDATION_PREVIEW"]


class FakeRepo(CatalogMonitorRepository):
    def __init__(self, vendor_code=None, feed_requests=(), baselines=None):
        super().__init__(db=None)
        self.cap = CatalogApiCapability(account_id=ACC, results={}, vendor_code=vendor_code)
        self.feed_requests = list(feed_requests)
        self.baseline_rows = dict(baselines or {})
        self.upserts: list[tuple] = []

    async def capability(self, account_id):
        return self.cap

    async def baselines(self, account_id, asins=None):
        return {a: r for a, r in self.baseline_rows.items() if asins is None or a in asins}

    async def upsert_baseline(self, account_id, asin, content, source, user_id):
        self.upserts.append((asin, content, source, user_id))
        row = self.baseline_rows[asin]
        row.content, row.source, row.approved_by_user_id = content_to_dict(content), source, user_id
        return row

    async def change_requests_for_feed(self, account_id, feed_id):
        return [
            r for r in self.feed_requests if r.account_id == account_id and r.feed_id == feed_id
        ]


class _Savepoint:
    def __init__(self, db):
        self.db = db

    async def __aenter__(self):
        self.db.savepoints += 1
        return self

    async def __aexit__(self, *exc):
        return False  # a failure inside propagates, as with a real savepoint


class FakeDb:
    def __init__(self):
        self.added: list = []
        self.commits = 0
        self.savepoints = 0

    def begin_nested(self):
        return _Savepoint(self)

    async def execute(self, _stmt):  # load_organization
        return SimpleNamespace(scalar_one_or_none=lambda: None)

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        pass

    async def commit(self):
        self.commits += 1


def _seller():
    return SimpleNamespace(
        id=ACC, organization_id=ORG, account_type=AccountType.SELLER,
        seller_id=SELLER, marketplace_id=MKT, marketplace_country="IT",
    )


def _vendor():
    return SimpleNamespace(
        id=ACC, organization_id=ORG, account_type=AccountType.VENDOR,
        seller_id=None, marketplace_id=MKT, marketplace_country="IT",
    )


def _service(client=None, repo=None):
    client = client or FakeClient()
    db = FakeDb()
    svc = ChangeRequestService(
        db, client_factory=lambda account, org: client, repo=repo or FakeRepo()
    )
    return svc, client, db


def _item(n=1, **kw):
    kw.setdefault("asin", f"B0TEST{n:04d}")
    kw.setdefault("sku", f"TEST-SKU-{n:03d}")
    kw.setdefault("product_type", "HOME")
    kw.setdefault("kind", "bulk_update")
    if kw.get("operation") != "PUT":
        kw.setdefault("patches", patches_from_content({"title": f"Titolo {n}"}, MKT))
    return ChangeItem(**kw)


def _sku(n):
    return f"TEST-SKU-{n:03d}"


async def _approved(svc, account, items):
    rows = await svc.create(account, items, USER)
    await svc.validate(account, rows)
    await svc.approve(rows, ADMIN, is_admin=True)
    return rows


def _content(**kw):
    kw.setdefault("title", "Tazza TESTBRAND")
    return ListingContent(asin="B0TEST0001", marketplace_id=MKT, **kw)


ERROR = {"code": "90220", "message": "item_name obbligatorio", "severity": "ERROR",
         "attributeNames": ["item_name"]}
WARNING = {"code": "18027", "message": "valore insolito", "severity": "WARNING",
           "attributeNames": ["bullet_point"]}


# ---- pure patch builders ----


def test_text_value_carries_language_and_marketplace():
    assert text_value("Tazza", MKT) == [
        {"value": "Tazza", "language_tag": "it_IT", "marketplace_id": MKT}
    ]
    assert text_value("Mug", "A1F83G8C2ARO7P")[0]["language_tag"] == "en_GB"
    assert text_value("Tasse", "A1PA6795UKMFR9")[0]["language_tag"] == "de_DE"
    assert text_value("x", "UNKNOWNMKT")[0] == {
        "value": "x", "language_tag": "it_IT", "marketplace_id": "UNKNOWNMKT"
    }
    assert LANGUAGE_TAG_BY_MARKETPLACE == {
        "APJ6JRA9NG5V4": "it_IT", "A1PA6795UKMFR9": "de_DE", "A13V1IB3VIYZZH": "fr_FR",
        "A1RKKUPIHCS9HS": "es_ES", "A1F83G8C2ARO7P": "en_GB", "A1805IZSGTT6HS": "nl_NL",
        "A2NODRKZP88ZB9": "sv_SE", "A1C3SOZRARQ6R3": "pl_PL", "AMEN7PMS3EDWL": "fr_BE",
        "ATVPDKIKX0DER": "en_US",
    }


URLS = ["https://img.test/m.jpg", "https://img.test/1.jpg", "https://img.test/2.jpg"]


def _deleted_slots(patches):
    return [
        int(p["path"].rsplit("_", 1)[1]) for p in patches if p["op"] == "delete"
    ]


def test_images_patch_deletes_missing_slots():
    """Deletes are scoped to one marketplace, so a pan-EU listing keeps its other images."""
    patches = patches_from_content({"images": URLS}, MKT, existing_image_slots=8)
    by_path = {p["path"]: p for p in patches}

    assert len(patches) == 9
    assert by_path["/attributes/main_product_image_locator"] == {
        "op": "replace",
        "path": "/attributes/main_product_image_locator",
        "value": [{"media_location": URLS[0], "marketplace_id": MKT}],
    }
    for n, url in ((1, URLS[1]), (2, URLS[2])):
        assert by_path[f"/attributes/other_product_image_locator_{n}"]["value"] == [
            {"media_location": url, "marketplace_id": MKT}
        ]
    for n in range(3, 9):
        path = f"/attributes/other_product_image_locator_{n}"
        assert by_path[path] == {
            "op": "delete", "path": path, "value": [{"marketplace_id": MKT}]
        }


def test_no_image_deletes_without_existing_slots():
    patches = patches_from_content({"images": URLS}, MKT)
    assert [p["op"] for p in patches] == ["replace"] * 3
    assert _deleted_slots(patches) == []


def test_image_deletes_only_up_to_existing_slots():
    patches = patches_from_content({"images": URLS}, MKT, existing_image_slots=5)
    assert _deleted_slots(patches) == [3, 4, 5]
    # A new list as long as the live one deletes nothing.
    five = URLS + ["https://img.test/3.jpg", "https://img.test/4.jpg", "https://img.test/5.jpg"]
    assert _deleted_slots(patches_from_content({"images": five}, MKT, 5)) == []


def test_patches_from_content_maps_every_field_to_its_attribute():
    color = [{"value": "Rosso", "language_tag": "it_IT", "marketplace_id": MKT}]
    patches = patches_from_content(
        {
            "title": " Tazza TESTBRAND ",
            "bullets": ["Uno", "Due"],
            "description": "Descrizione",
            "backend_keywords": "tazza mug",
            "item_highlights": "In evidenza",
            "attribute:color": color,
        },
        MKT,
    )
    tag = {"language_tag": "it_IT", "marketplace_id": MKT}
    assert patches == [
        {"op": "replace", "path": "/attributes/item_name",
         "value": [{"value": "Tazza TESTBRAND", **tag}]},
        {"op": "replace", "path": "/attributes/bullet_point",
         "value": [{"value": "Uno", **tag}, {"value": "Due", **tag}]},
        {"op": "replace", "path": "/attributes/product_description",
         "value": [{"value": "Descrizione", **tag}]},
        {"op": "replace", "path": "/attributes/generic_keyword",
         "value": [{"value": "tazza mug", **tag}]},
        {"op": "replace", "path": "/attributes/item_highlights",
         "value": [{"value": "In evidenza", **tag}]},
        {"op": "replace", "path": "/attributes/color", "value": color},
    ]


def test_empty_values_never_erase_content():
    assert patches_from_content(
        {"title": "  ", "bullets": ["", " "], "description": None, "images": [],
         "attribute:color": []},
        MKT,
    ) == []
    with pytest.raises(ValueError):
        patches_from_content({"price": "9.99"}, MKT)


def test_bullet_patches_drop_blank_bullets():
    """A stored baseline may hold "" padding (an upload filled bullet_4 only).

    Amazon bullets are gapless, so blank ones never reach a patch.
    """
    baseline = _content(bullets=["Uno", "", "  ", "Quattro"])
    for patches in (
        restore_patches(baseline, ["bullets"]),
        patches_from_content({"bullets": ["Uno", "", "  ", "Quattro"]}, MKT),
    ):
        assert len(patches) == 1
        assert patches[0]["path"] == "/attributes/bullet_point"
        assert [v["value"] for v in patches[0]["value"]] == ["Uno", "Quattro"]


def test_restore_patches_put_back_baseline_values():
    color = [{"value": "Blu", "language_tag": "it_IT", "marketplace_id": MKT}]
    baseline = _content(
        description=None,
        images=[
            ImageRef("MAIN", "https://img.test/m.jpg"),
            ImageRef("PT01", "https://img.test/1.jpg"),
        ],
        attributes={"color": color},
    )
    patches = restore_patches(
        baseline, ["title", "images", "attribute:color", "aplus", "description"]
    )
    by_path = {p["path"]: p for p in patches}

    assert by_path["/attributes/item_name"]["value"][0]["value"] == "Tazza TESTBRAND"
    assert by_path["/attributes/main_product_image_locator"]["value"][0]["media_location"] == (
        "https://img.test/m.jpg"
    )
    assert by_path["/attributes/other_product_image_locator_1"]["value"][0]["media_location"] == (
        "https://img.test/1.jpg"
    )
    assert by_path["/attributes/color"]["value"] == color
    # A+ is restored by hand; a field the baseline lacks gives no patch.
    assert "/attributes/product_description" not in by_path
    assert not any("aplus" in p["path"] for p in patches)
    assert _deleted_slots(patches) == []
    # Live images past the baseline's are deleted only when the caller says they exist.
    assert _deleted_slots(restore_patches(baseline, ["images"], existing_image_slots=3)) == [2, 3]
    with pytest.raises(ValueError):
        restore_patches(baseline, ["shipping"])


def test_variation_patches_shape():
    assert variation_patches("TEST-SKU-PARENT", "SIZE/COLOR", MKT) == [
        {"op": "replace", "path": "/attributes/parentage_level",
         "value": [{"marketplace_id": MKT, "value": "child"}]},
        {"op": "replace", "path": "/attributes/child_parent_sku_relationship",
         "value": [{"marketplace_id": MKT, "child_relationship_type": "variation",
                    "parent_sku": "TEST-SKU-PARENT"}]},
        {"op": "replace", "path": "/attributes/variation_theme",
         "value": [{"name": "SIZE/COLOR"}]},
    ]


# ---- create ----


@pytest.mark.asyncio
async def test_create_without_sku_is_file_only():
    """Review Focus 1: no vendor code or no SKU means "file only", never an exception."""
    svc, client, db = _service(repo=FakeRepo(vendor_code=None))
    rows = await svc.create(_vendor(), [_item(1, sku=None), _item(2)], USER)
    assert [r.status for r in rows] == ["file_only", "file_only"]

    svc, client, db = _service(repo=FakeRepo())
    rows = await svc.create(_seller(), [_item(1, sku=None), _item(2)], USER)
    assert [r.status for r in rows] == ["file_only", "pending"]
    assert [is_file_only(r) for r in rows] == [True, False]
    assert db.added == rows
    assert len({r.batch_id for r in rows}) == 1
    first = rows[0]
    assert (first.organization_id, first.account_id, first.created_by_user_id) == (ORG, ACC, USER)
    assert (first.asin, first.kind, first.operation, first.product_type) == (
        "B0TEST0001", "bulk_update", "PATCH", "HOME"
    )
    assert first.payload["patches"] == _item(1).patches

    # Validation skips file-only requests: no Amazon call, no exception.
    await svc.validate(_seller(), rows)
    assert rows[0].status == "file_only"
    assert [c[2] for c in client.calls] == [_sku(2)]
    assert db.commits == 0


@pytest.mark.asyncio
async def test_vendor_with_vendor_code_writes_through_listings():
    svc, client, _ = _service(repo=FakeRepo(vendor_code=VENDOR_CODE))
    rows = await svc.create(_vendor(), [_item(1)], USER)
    assert rows[0].status == "pending"
    await svc.validate(_vendor(), rows)
    assert client.calls[0][1] == VENDOR_CODE


@pytest.mark.asyncio
async def test_vendor_create_strips_deletes_and_records_manual_image_removal():
    """Amazon does not let vendors delete attribute values: the deletes become manual work."""
    patches = patches_from_content({"images": URLS}, MKT, existing_image_slots=5)
    paths = [f"/attributes/other_product_image_locator_{n}" for n in (3, 4, 5)]
    item = _item(1, patches=patches, summary={"fields": {"images": {}}})
    text_only = _item(2)

    svc, _, _ = _service(repo=FakeRepo(vendor_code=VENDOR_CODE))
    vendor_rows = await svc.create(_vendor(), [item, text_only], USER)
    assert [p["op"] for p in vendor_rows[0].payload["patches"]] == ["replace"] * 3
    assert vendor_rows[0].summary == {"fields": {"images": {}}, "manual_image_removal": paths}
    assert "manual_image_removal" not in vendor_rows[1].summary

    svc, _, _ = _service()
    [seller_row] = await svc.create(_seller(), [item], USER)
    assert seller_row.payload["patches"] == patches
    assert "manual_image_removal" not in seller_row.summary


@pytest.mark.asyncio
async def test_create_marks_restored_anomalies():
    anomaly = CatalogAnomaly(
        account_id=ACC, asin="B0TEST0001", kind="content_changed", field="title", status="open"
    )
    svc, _, _ = _service()
    batch = uuid4()
    [row] = await svc.create(
        _seller(), [_item(1, kind="content_restore", anomalies=[anomaly])], USER, batch_id=batch
    )
    assert row.batch_id == batch
    assert anomaly.status == "restore_requested"
    assert anomaly.change_request_id == row.id is not None


@pytest.mark.asyncio
async def test_create_rejects_an_empty_or_unknown_change():
    svc, _, _ = _service()
    with pytest.raises(ValueError):
        await svc.create(_seller(), [_item(1, patches=[])], USER)
    with pytest.raises(ValueError):
        await svc.create(_seller(), [_item(1, operation="PUT")], USER)
    with pytest.raises(ValueError):
        await svc.create(_seller(), [_item(1, kind="price_change")], USER)


# ---- validate ----


@pytest.mark.asyncio
async def test_validate_marks_invalid_on_error_issue_even_with_http_200():
    """Review Focus 3: a 200 answer with INVALID (or an ERROR issue) is not a success."""
    client = FakeClient(
        responses={
            (_sku(1), "VALIDATION_PREVIEW"): {"status": "INVALID", "issues": [ERROR]},
            (_sku(2), "VALIDATION_PREVIEW"): {"status": "VALID", "issues": [ERROR, WARNING]},
        }
    )
    svc, client, _ = _service(client)
    rows = await svc.create(_seller(), [_item(1), _item(2)], USER)
    await svc.validate(_seller(), rows)

    assert [r.status for r in rows] == ["invalid", "invalid"]
    assert rows[0].validation_issues == [ERROR]
    assert rows[1].validation_issues == [ERROR, WARNING]
    assert client.previews() == client.calls and len(client.calls) == 2
    assert client.calls[0] == (
        "patch", SELLER, _sku(1), "HOME", _item(1).patches, "VALIDATION_PREVIEW"
    )


@pytest.mark.asyncio
async def test_validate_keeps_warning_as_valid():
    client = FakeClient(
        responses={(_sku(1), "VALIDATION_PREVIEW"): {"status": "VALID", "issues": [WARNING]}}
    )
    svc, _, _ = _service(client)
    rows = await svc.create(_seller(), [_item(1)], USER)
    await svc.validate(_seller(), rows)
    assert rows[0].status == "valid"
    assert rows[0].validation_issues == [WARNING]


@pytest.mark.asyncio
async def test_validate_turns_api_errors_into_issues_and_never_raises():
    client = FakeClient(errors={_sku(1): AmazonAPIError("throttled", error_code="THROTTLED")})
    svc, _, _ = _service(client)
    rows = await svc.create(_seller(), [_item(1), _item(2), _item(3, product_type=None)], USER)
    await svc.validate(_seller(), rows)

    assert [r.status for r in rows] == ["invalid", "valid", "invalid"]
    assert rows[0].validation_issues == [
        {"code": "API_ERROR", "message": "throttled", "severity": "ERROR"}
    ]
    assert rows[2].validation_issues[0]["severity"] == "ERROR"
    assert [c[2] for c in client.calls] == [_sku(1), _sku(2)]  # no product type: no call


@pytest.mark.asyncio
async def test_validate_treats_a_preview_answering_accepted_as_invalid():
    client = FakeClient(
        responses={(_sku(1), "VALIDATION_PREVIEW"): {"status": "ACCEPTED", "issues": []}}
    )
    svc, _, _ = _service(client)
    rows = await svc.create(_seller(), [_item(1)], USER)
    await svc.validate(_seller(), rows)
    assert rows[0].status == "invalid"
    assert [(i["code"], i["severity"]) for i in rows[0].validation_issues] == [
        ("UNEXPECTED_STATUS", "ERROR")
    ]


@pytest.mark.asyncio
async def test_validate_refuses_a_blank_sku_without_calling_amazon():
    svc, client, _ = _service()
    rows = await svc.create(_seller(), [_item(1, sku="   "), _item(2, product_type=" ")], USER)
    await svc.validate(_seller(), rows)
    assert [r.status for r in rows] == ["invalid", "invalid"]
    assert all(r.validation_issues[0]["severity"] == "ERROR" for r in rows)
    assert client.calls == []


@pytest.mark.asyncio
async def test_validate_put_uses_validation_preview():
    attrs = {"item_name": text_value("Nuovo", MKT)}
    svc, client, _ = _service()
    rows = await svc.create(
        _seller(), [_item(1, kind="new_item", operation="PUT", attributes=attrs)], USER
    )
    await svc.validate(_seller(), rows)
    assert rows[0].status == "valid"
    assert client.calls == [
        ("get_listing", SELLER, _sku(1)),  # a new item must not exist yet
        ("put", SELLER, _sku(1), "HOME", attrs, "VALIDATION_PREVIEW"),
    ]


# ---- approve / reject ----


@pytest.mark.asyncio
async def test_approve_requires_admin():
    client = FakeClient(
        responses={(_sku(2), "VALIDATION_PREVIEW"): {"status": "INVALID", "issues": [ERROR]}}
    )
    svc, _, _ = _service(client)
    rows = await svc.create(_seller(), [_item(1), _item(2), _item(3, sku=None), _item(4)], USER)
    await svc.validate(_seller(), rows[:3])  # the 4th stays pending

    with pytest.raises(PermissionError):
        await svc.approve(rows, USER, is_admin=False)
    assert [r.status for r in rows] == ["valid", "invalid", "file_only", "pending"]

    await svc.approve(rows, ADMIN, is_admin=True)
    assert [r.status for r in rows] == ["approved", "invalid", "approved", "pending"]
    assert rows[0].approved_by_user_id == ADMIN and rows[0].approved_at is not None
    assert rows[1].approved_by_user_id is None
    # An approved file-only request stays file only: it is exported, never sent.
    assert is_file_only(rows[2]) and not is_file_only(rows[0])


def test_can_approve_and_can_reject():
    def row(status):
        return CatalogChangeRequest(status=status)

    approvable = {"valid", "file_only"}
    rejectable = {"pending", "valid", "invalid", "approved", "file_only"}
    for status in (
        "pending", "valid", "invalid", "approved", "rejected", "submitted", "accepted",
        "failed", "file_only",
    ):
        assert can_approve(row(status)) is (status in approvable)
        assert can_reject(row(status)) is (status in rejectable)


@pytest.mark.asyncio
async def test_reject_stops_a_request_before_it_is_sent():
    svc, client, _ = _service()
    rows = await svc.create(_seller(), [_item(1)], USER)
    await svc.validate(_seller(), rows)
    await svc.reject(rows, USER)
    assert rows[0].status == "rejected"
    await svc.approve(rows, ADMIN, is_admin=True)
    await svc.submit(_seller(), rows)
    assert rows[0].status == "rejected"
    assert client.writes() == []


# ---- submit ----


@pytest.mark.asyncio
async def test_submit_small_batch_patches_each():
    client = FakeClient(
        responses={(_sku(2), None): {"status": "INVALID", "issues": [ERROR], "submissionId": "s2"}},
    )
    svc, client, db = _service(client)
    rows = await _approved(svc, _seller(), [_item(1), _item(2), _item(3), _item(4, sku=None)])
    pending = (await svc.create(_seller(), [_item(5)], USER))[0]
    client.errors = {_sku(3): AmazonAPIError("server error", error_code="SP_API_ERROR")}

    await svc.submit(_seller(), rows + [pending])

    assert [r.status for r in rows] == ["accepted", "failed", "failed", "approved"]
    assert pending.status == "pending"
    assert rows[0].submission_result == {"status": "ACCEPTED", "submissionId": "s1", "issues": []}
    assert rows[1].submission_result["issues"] == [ERROR]
    assert rows[2].submission_result["issues"][0]["code"] == "API_ERROR"
    assert all(r.submitted_at is not None for r in rows[:3])
    # One live write per approved API request, without VALIDATION_PREVIEW; none for
    # the file-only or the unapproved one.
    assert [(c[0], c[2], c[-1]) for c in client.writes()] == [
        ("patch", _sku(1), None), ("patch", _sku(2), None), ("patch", _sku(3), None)
    ]
    assert db.commits == 0


@pytest.mark.asyncio
async def test_submit_fails_a_live_answer_that_is_not_accepted():
    client = FakeClient(responses={(_sku(1), None): {"status": "VALID", "issues": []}})
    svc, client, _ = _service(client)
    rows = await _approved(svc, _seller(), [_item(1)])
    await svc.submit(_seller(), rows)
    assert rows[0].status == "failed"
    assert [i["code"] for i in rows[0].submission_result["issues"]] == ["UNEXPECTED_STATUS"]


@pytest.mark.asyncio
async def test_submit_refuses_an_approved_request_that_did_not_pass_validation():
    svc, client, _ = _service()
    never_checked, with_error = await svc.create(_seller(), [_item(1), _item(2)], USER)
    never_checked.status = "approved"  # validation_issues is None
    with_error.status, with_error.validation_issues = "approved", [ERROR]

    await svc.submit(_seller(), [never_checked, with_error])

    assert client.writes() == []
    assert [never_checked.status, with_error.status] == ["approved", "approved"]


@pytest.mark.asyncio
async def test_submit_large_batch_uses_feed():
    n = settings.CATALOG_FEED_THRESHOLD
    svc, client, _ = _service()
    rows = await _approved(svc, _seller(), [_item(i) for i in range(1, n + 1)])

    await svc.submit(_seller(), rows)

    [feed_call] = client.writes()
    assert feed_call[0] == "feed"
    document = feed_call[1]
    assert len(document["messages"]) == n
    assert all(r.status == "submitted" and r.feed_id == FEED_ID for r in rows)
    assert [r.submission_result["messageId"] for r in rows] == list(range(1, n + 1))
    assert [m["sku"] for m in document["messages"]] == [r.sku for r in rows]


@pytest.mark.asyncio
async def test_submit_below_threshold_does_not_use_feed():
    n = settings.CATALOG_FEED_THRESHOLD - 1
    svc, client, _ = _service()
    rows = await _approved(svc, _seller(), [_item(i) for i in range(1, n + 1)])
    await svc.submit(_seller(), rows)
    assert len(client.writes()) == n
    assert {c[0] for c in client.writes()} == {"patch"}


@pytest.mark.asyncio
async def test_submit_refuses_requests_of_another_account():
    svc, client, _ = _service()
    rows = await _approved(svc, _seller(), [_item(1)])
    other = SimpleNamespace(**{**vars(_seller()), "id": uuid4()})
    with pytest.raises(ValueError):
        await svc.submit(other, rows)
    assert client.writes() == []


# ---- feed ----


def _request(n, operation="PATCH", sku="default", product_type="HOME", **payload):
    payload = payload or (
        {"patches": _item(n).patches} if operation == "PATCH" else {"attributes": {}}
    )
    return CatalogChangeRequest(
        id=uuid4(), organization_id=ORG, account_id=ACC, batch_id=uuid4(),
        asin=f"B0TEST{n:04d}", sku=_sku(n) if sku == "default" else sku, kind="bulk_update",
        operation=operation, product_type=product_type, payload=payload, status="approved",
    )


def test_feed_document_shape():
    attrs = {"item_name": text_value("Nuovo", MKT)}
    patch = _request(1)
    put = _request(2, operation="PUT", attributes=attrs)
    no_sku = _request(3, sku=None)
    no_type = _request(4, product_type=None)

    feed = build_listings_feed([patch, no_sku, put, no_type], SELLER, MKT)

    assert feed.document == {
        "header": {"sellerId": SELLER, "version": "2.0", "issueLocale": "it_IT"},
        "messages": [
            {"messageId": 1, "sku": _sku(1), "operationType": "PATCH", "productType": "HOME",
             "patches": patch.payload["patches"]},
            {"messageId": 2, "sku": _sku(2), "operationType": "UPDATE", "productType": "HOME",
             "attributes": attrs},
        ],
    }
    assert feed.message_ids == {patch.id: 1, put.id: 2}
    assert feed.skipped == {no_sku.id: "no_sku", no_type.id: "no_product_type"}
    assert feed.marketplace_id == MKT


def _submitted(n):
    row = _request(n)
    row.status, row.feed_id, row.submission_result = "submitted", FEED_ID, {"messageId": n}
    return row


@pytest.mark.asyncio
async def test_refresh_feed_maps_the_processing_report_per_message():
    rows = [_submitted(1), _submitted(2), _submitted(3)]
    client = FakeClient(
        feed_status={"processingStatus": "DONE", "resultFeedDocumentId": "doc-1"},
        feed_report={
            "header": {"sellerId": SELLER, "version": "2.0", "feedId": FEED_ID},
            "issues": [{**ERROR, "messageId": 2}, {**WARNING, "messageId": 3}],
            "summary": {"messagesProcessed": 3, "messagesAccepted": 2, "messagesInvalid": 1},
        },
    )
    svc, client, _ = _service(client, FakeRepo(feed_requests=rows))

    await svc.refresh_feed(_seller(), FEED_ID)

    assert [r.status for r in rows] == ["accepted", "failed", "accepted"]
    assert rows[1].submission_result["issues"] == [{**ERROR, "messageId": 2}]
    assert rows[2].submission_result["issues"] == [{**WARNING, "messageId": 3}]
    assert rows[0].submission_result["messageId"] == 1
    assert ("feed_result", "doc-1") in client.calls


@pytest.mark.asyncio
async def test_refresh_feed_fails_every_request_of_a_fatal_feed():
    rows = [_submitted(1), _submitted(2)]
    client = FakeClient(feed_status={"processingStatus": "FATAL"})
    svc, _, _ = _service(client, FakeRepo(feed_requests=rows))
    await svc.refresh_feed(_seller(), FEED_ID)
    assert [r.status for r in rows] == ["failed", "failed"]
    assert rows[0].submission_result["issues"][0]["severity"] == "ERROR"


@pytest.mark.asyncio
async def test_refresh_feed_waits_while_amazon_is_processing():
    rows = [_submitted(1)]
    svc, client, _ = _service(FakeClient(), FakeRepo(feed_requests=rows))
    await svc.refresh_feed(_seller(), FEED_ID)
    assert rows[0].status == "submitted"
    assert not any(c[0] == "feed_result" for c in client.calls)


def test_image_slots_patch_replaces_only_named_slots():
    patches = patches_from_content(
        {"image_slots": {"other_product_image_locator_3": "https://img.test/3.jpg", "main_product_image_locator": " "}},
        MKT,
    )
    assert patches == [
        {
            "op": "replace",
            "path": "/attributes/other_product_image_locator_3",
            "value": [{"media_location": "https://img.test/3.jpg", "marketplace_id": MKT}],
        }
    ]
    with pytest.raises(ValueError):
        patches_from_content({"image_slots": {"title": "https://img.test/x.jpg"}}, MKT)


# ---- accepted changes become the protected baseline (found in the end-to-end run) ----


def _baseline_rows(*asins):
    return {
        asin: ListingContentBaseline(
            account_id=ACC, asin=asin, source="live_snapshot",
            content=content_to_dict(ListingContent(asin=asin, marketplace_id=MKT, title="Vecchio")),
        )
        for asin in asins
    }


@pytest.mark.asyncio
async def test_an_accepted_bulk_update_updates_the_baseline_and_a_failed_one_does_not():
    client = FakeClient(
        responses={(_sku(2), None): {"status": "INVALID", "issues": [ERROR], "submissionId": "s2"}},
    )
    repo = FakeRepo(baselines=_baseline_rows("B0TEST0001", "B0TEST0002"))
    svc, client, _ = _service(client, repo)
    rows = await _approved(svc, _seller(), [_item(1), _item(2)])

    await svc.submit(_seller(), rows)

    assert [r.status for r in rows] == ["accepted", "failed"]
    assert [(asin, c.title, source, user) for asin, c, source, user in repo.upserts] == [
        ("B0TEST0001", "Titolo 1", "live_snapshot", ADMIN)
    ]
    assert content_from_dict(repo.baseline_rows["B0TEST0002"].content).title == "Vecchio"


@pytest.mark.asyncio
async def test_an_accepted_restore_leaves_the_baseline_alone():
    repo = FakeRepo(baselines=_baseline_rows("B0TEST0001"))
    svc, _, _ = _service(repo=repo)
    rows = await _approved(svc, _seller(), [_item(1, kind="content_restore")])
    await svc.submit(_seller(), rows)
    assert rows[0].status == "accepted" and repo.upserts == []


@pytest.mark.asyncio
async def test_refresh_feed_puts_accepted_bulk_updates_into_the_baseline():
    rows = [_submitted(1), _submitted(2)]
    for row in rows:
        row.approved_by_user_id = ADMIN
    client = FakeClient(
        feed_status={"processingStatus": "DONE", "resultFeedDocumentId": "doc-1"},
        feed_report={"issues": [{**ERROR, "messageId": 2}]},
    )
    repo = FakeRepo(feed_requests=rows, baselines=_baseline_rows("B0TEST0001", "B0TEST0002"))
    svc, _, _ = _service(client, repo)

    await svc.refresh_feed(_seller(), FEED_ID)

    assert [r.status for r in rows] == ["accepted", "failed"]
    assert [(asin, c.title, user) for asin, c, _, user in repo.upserts] == [("B0TEST0001", "Titolo 1", ADMIN)]


# ---- a new item never replaces a live listing ----

LIVE_LISTING = {"sku": "TEST-SKU-001", "summaries": [{"marketplaceId": MKT, "asin": "B0TEST0001"}]}


def _new_item(n=1):
    return _item(n, asin=None, kind="new_item", operation="PUT",
                 attributes={"item_name": text_value(f"Nuovo {n}", MKT)})


@pytest.mark.asyncio
async def test_validate_refuses_a_new_item_whose_sku_is_already_live():
    client = FakeClient(listings={_sku(1): LIVE_LISTING})
    svc, client, _ = _service(client)
    rows = await svc.create(_seller(), [_new_item(1), _new_item(2)], USER)
    await svc.validate(_seller(), rows)
    assert [r.status for r in rows] == ["invalid", "valid"]
    [issue] = rows[0].validation_issues
    assert (issue["code"], issue["severity"]) == ("SKU_EXISTS", "ERROR")
    assert [c[2] for c in client.previews()] == [_sku(2)]  # no PUT preview for the live SKU


@pytest.mark.asyncio
async def test_validate_refuses_a_new_item_when_the_sku_check_fails():
    client = FakeClient(listing_errors={_sku(1): AmazonAPIError("throttled", error_code="THROTTLED")})
    svc, client, _ = _service(client)
    rows = await svc.create(_seller(), [_new_item(1)], USER)
    await svc.validate(_seller(), rows)
    assert rows[0].status == "invalid"
    assert [i["code"] for i in rows[0].validation_issues] == ["SKU_CHECK_FAILED"]
    assert client.previews() == []


@pytest.mark.asyncio
async def test_submit_fails_a_new_item_whose_sku_went_live_after_validation():
    client = FakeClient()
    svc, client, _ = _service(client)
    rows = await _approved(svc, _seller(), [_new_item(1), _new_item(2)])
    assert [r.status for r in rows] == ["approved", "approved"]
    client.listings[_sku(1)] = LIVE_LISTING  # created by hand meanwhile

    await svc.submit(_seller(), rows)

    assert [r.status for r in rows] == ["failed", "accepted"]
    assert [i["code"] for i in rows[0].submission_result["issues"]] == ["SKU_EXISTS"]
    assert [c[2] for c in client.writes()] == [_sku(2)]


@pytest.mark.asyncio
async def test_submit_by_feed_leaves_out_a_new_item_whose_sku_is_live(monkeypatch):
    monkeypatch.setattr(settings, "CATALOG_FEED_THRESHOLD", 2)
    client = FakeClient()
    svc, client, _ = _service(client)
    rows = await _approved(svc, _seller(), [_new_item(1), _new_item(2), _new_item(3)])
    client.listings[_sku(2)] = LIVE_LISTING

    await svc.submit(_seller(), rows)

    assert [r.status for r in rows] == ["submitted", "failed", "submitted"]
    [feed] = [c[1] for c in client.calls if c[0] == "feed"]
    assert [m["sku"] for m in feed["messages"]] == [_sku(1), _sku(3)]


@pytest.mark.asyncio
async def test_patch_requests_do_not_check_the_sku():
    svc, client, _ = _service()
    rows = await _approved(svc, _seller(), [_item(1)])
    await svc.submit(_seller(), rows)
    assert rows[0].status == "accepted"
    assert not [c for c in client.calls if c[0] == "get_listing"]


@pytest.mark.asyncio
async def test_new_item_sku_check_with_the_fixture_client(tmp_path):
    from app.services.catalog_monitor.fixture_client import FixtureClient

    listing = tmp_path / "listings" / f"{_sku(1)}.json"
    listing.parent.mkdir(parents=True)
    listing.write_text('{"sku": "TEST-SKU-001", "summaries": [], "attributes": {}}')
    svc, _, _ = _service(FixtureClient(str(tmp_path), MKT))
    rows = await svc.create(_seller(), [_new_item(1), _new_item(2)], USER)
    await svc.validate(_seller(), rows)
    assert [r.status for r in rows] == ["invalid", "valid"]  # unknown SKU: not found, proceed
    assert rows[0].validation_issues[0]["code"] == "SKU_EXISTS"



# ---- the submission record survives a failed baseline update (final review) ----


class _BrokenBaselines(FakeRepo):
    async def upsert_baseline(self, account_id, asin, content, source, user_id):
        raise RuntimeError("baseline write failed")


@pytest.mark.asyncio
async def test_a_failed_baseline_update_keeps_the_accepted_submission(caplog):
    repo = _BrokenBaselines(baselines=_baseline_rows("B0TEST0001"))
    svc, client, db = _service(repo=repo)
    rows = await _approved(svc, _seller(), [_item(1)])

    await svc.submit(_seller(), rows)  # never raises: Amazon already accepted the change

    assert rows[0].status == "accepted" and rows[0].submission_result["status"] == "ACCEPTED"
    assert db.savepoints == 1 and len(client.writes()) == 1
    assert "baseline" in caplog.text.lower()


@pytest.mark.asyncio
async def test_a_failed_baseline_update_keeps_the_settled_feed():
    rows = [_submitted(1)]
    client = FakeClient(feed_status={"processingStatus": "DONE", "resultFeedDocumentId": "doc-1"},
                        feed_report={"issues": []})
    repo = _BrokenBaselines(feed_requests=rows, baselines=_baseline_rows("B0TEST0001"))
    svc, _, db = _service(client, repo)
    await svc.refresh_feed(_seller(), FEED_ID)
    assert rows[0].status == "accepted" and db.savepoints == 1
