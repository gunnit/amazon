"""Baselines (R2, R3): approve live content, accept an anomaly, import approved rows."""
from datetime import datetime
from uuid import uuid4

import pytest

from app.models.catalog_monitor import CatalogAnomaly, ListingContentBaseline, ListingContentVersion
from app.services.catalog_monitor import baselines
from app.services.catalog_monitor.content import (
    ImageRef,
    ListingContent,
    content_from_dict,
    content_hash,
    content_to_dict,
)
from app.services.catalog_monitor.repository import CatalogMonitorRepository

MKT = "APJ6JRA9NG5V4"
NOW = datetime(2026, 11, 21, 6, 0)
PARENT = "B0TEST0100"


class _Repo(CatalogMonitorRepository):
    def __init__(self):
        super().__init__(db=None)
        self.versions: dict[str, ListingContentVersion] = {}
        self.base: dict[str, ListingContentBaseline] = {}
        self.fams: dict[str, tuple] = {}
        self.resolved: list = []

    def add_live(self, content):
        self.versions[content.asin] = ListingContentVersion(
            account_id=None,
            asin=content.asin,
            content_hash=content_hash(content),
            content=content_to_dict(content),
        )

    async def latest_versions(self, account_id, asins=None):
        self.version_calls = getattr(self, "version_calls", []) + [asins]
        return {a: v for a, v in self.versions.items() if asins is None or a in asins}

    async def version_asins(self, account_id):
        return sorted(self.versions)

    async def baselines(self, account_id, asins=None):
        self.baseline_calls = getattr(self, "baseline_calls", []) + [asins]
        return {a: r for a, r in self.base.items() if asins is None or a in asins}

    async def upsert_baseline(self, account_id, asin, content, source, user_id):
        row = ListingContentBaseline(
            account_id=account_id,
            asin=asin,
            content=content_to_dict(content),
            source=source,
            approved_by_user_id=user_id,
        )
        self.base[asin] = row
        return row

    async def upsert_family_baseline(self, account_id, parent_asin, theme, children):
        self.fams[parent_asin] = (theme, list(children))

    async def resolve_anomaly(self, anomaly, now):
        anomaly.status = "resolved"
        self.resolved.append(anomaly)


def _content(asin, **kw):
    kw.setdefault("title", f"Title {asin}")
    kw.setdefault("bullets", ["b1", "b2", "b3", "b4", "b5"])
    kw.setdefault("images", [ImageRef("MAIN", f"https://x.test/{asin}/m.jpg", 100, 100)])
    return ListingContent(asin=asin, marketplace_id=MKT, **kw)


def _anomaly(asin, kind, field, live):
    return CatalogAnomaly(
        account_id=uuid4(), asin=asin, kind=kind, field=field,
        baseline_value=None, live_value=live, status="open",
    )


ACC, USER = uuid4(), uuid4()


@pytest.mark.asyncio
async def test_approve_all_creates_baselines_and_families():
    repo = _Repo()
    repo.add_live(_content(PARENT, child_asins=["B0TEST0101", "B0TEST0102"], variation_theme="COLOR_NAME"))
    repo.add_live(_content("B0TEST0101", parent_asins=[PARENT]))
    repo.add_live(_content("B0TEST0102", parent_asins=[PARENT]))
    n = await baselines.approve_live_as_baseline(repo, ACC, None, USER)
    assert n == 3
    assert set(repo.base) == {PARENT, "B0TEST0101", "B0TEST0102"}
    assert all(r.source == "live_snapshot" and r.approved_by_user_id == USER for r in repo.base.values())
    assert repo.fams == {PARENT: ("COLOR_NAME", ["B0TEST0101", "B0TEST0102"])}


@pytest.mark.asyncio
async def test_approve_subset_only():
    repo = _Repo()
    repo.add_live(_content("B0TEST0001"))
    repo.add_live(_content("B0TEST0002"))
    assert await baselines.approve_live_as_baseline(repo, ACC, ["B0TEST0001", "B0TEST9999"], USER) == 1
    assert set(repo.base) == {"B0TEST0001"}
    assert repo.fams == {}


@pytest.mark.asyncio
async def test_accept_anomaly_updates_only_that_field():
    repo = _Repo()
    old = _content("B0TEST0001", title="Old", description="Desc")
    await repo.upsert_baseline(ACC, "B0TEST0001", old, "live_snapshot", USER)
    an = _anomaly("B0TEST0001", "content_changed", "title", "New title")
    await baselines.accept_anomaly(repo, an, USER, NOW)
    got = content_from_dict(repo.base["B0TEST0001"].content)
    assert got.title == "New title"
    assert got.description == "Desc" and got.bullets == old.bullets
    assert an.status == "resolved"


@pytest.mark.asyncio
async def test_accept_images_and_aplus_and_attribute():
    repo = _Repo()
    live_attr = [{"value": "Rosso", "marketplace_id": MKT}]
    repo.add_live(_content("B0TEST0001", attributes={"color": live_attr}))
    await repo.upsert_baseline(
        ACC, "B0TEST0001",
        _content("B0TEST0001", aplus_module_count=1, attributes={"color": [{"value": "Blu"}]}),
        "live_snapshot", USER,
    )
    urls = ["https://x.test/a.jpg", "https://x.test/b.jpg", "https://x.test/c.jpg"]
    await baselines.accept_anomaly(repo, _anomaly("B0TEST0001", "content_changed", "images", urls), USER, NOW)
    await baselines.accept_anomaly(repo, _anomaly("B0TEST0001", "content_changed", "aplus", 4), USER, NOW)
    await baselines.accept_anomaly(
        repo, _anomaly("B0TEST0001", "content_changed", "attribute:color", ["Rosso"]), USER, NOW
    )
    got = content_from_dict(repo.base["B0TEST0001"].content)
    assert [(i.variant, i.url) for i in got.images] == [
        ("MAIN", urls[0]), ("PT01", urls[1]), ("PT02", urls[2])
    ]
    assert got.aplus_module_count == 4
    assert got.attributes["color"] == live_attr


@pytest.mark.asyncio
async def test_accept_variation_anomaly_refreshes_family():
    repo = _Repo()
    repo.add_live(_content(PARENT, child_asins=["B0TEST0101", "B0TEST0103"], variation_theme="SIZE_NAME"))
    for kind, asin in [("theme_changed", PARENT), ("unexpected_child", "B0TEST0103")]:
        an = _anomaly(asin, kind, f"parent:{PARENT}", None)
        await baselines.accept_anomaly(repo, an, USER, NOW)
        assert an.status == "resolved"
    assert repo.fams[PARENT] == ("SIZE_NAME", ["B0TEST0101", "B0TEST0103"])


@pytest.mark.asyncio
async def test_accept_unknown_kind_raises():
    with pytest.raises(ValueError):
        await baselines.accept_anomaly(_Repo(), _anomaly("B0TEST0001", "weird", "x", 1), USER, NOW)


@pytest.mark.asyncio
async def test_import_overrides_only_given_cells():
    repo = _Repo()
    live = _content(
        "B0TEST0001",
        description="Live desc",
        images=[ImageRef("MAIN", "https://x.test/m.jpg"), ImageRef("PT01", "https://x.test/1.jpg"),
                ImageRef("PT02", "https://x.test/2.jpg")],
    )
    repo.add_live(live)
    n, errors = await baselines.import_baseline_rows(
        repo, ACC,
        [
            ("B0TEST0001", {"title": "Approved", "bullet_2": "new b2", "image_2": "https://x.test/new2.jpg",
                            "attr:color": "Verde", "description": ""}),
            ("B0TEST0404", {"title": "x"}),
        ],
        USER,
    )
    assert n == 1 and errors == ["B0TEST0404: no live content yet"]
    row = repo.base["B0TEST0001"]
    assert row.source == "excel_upload"
    got = content_from_dict(row.content)
    assert got.title == "Approved"
    assert got.bullets == ["b1", "new b2", "b3", "b4", "b5"]
    assert got.description == "Live desc"
    assert [i.url for i in got.images] == ["https://x.test/m.jpg", "https://x.test/1.jpg", "https://x.test/new2.jpg"]
    assert got.attributes["color"] == [{"value": "Verde", "marketplace_id": MKT}]


# ---- accepted changes become the baseline (found in the end-to-end run) ----


def _accepted(asin, kind="bulk_update", operation="PATCH", **payload):
    from app.models.catalog_monitor import CatalogChangeRequest

    return CatalogChangeRequest(
        account_id=ACC, asin=asin, sku="TEST-SKU-001", kind=kind, operation=operation,
        product_type="HOME", payload=payload, status="accepted", approved_by_user_id=USER,
    )


def test_baseline_after_change_applies_every_changed_field():
    from app.services.catalog_monitor.changes import patches_from_content, text_value

    base = _content(
        "B0TEST0001",
        images=[ImageRef("MAIN", "https://x.test/m.jpg"), ImageRef("PT01", "https://x.test/1.jpg"),
                ImageRef("PT02", "https://x.test/2.jpg")],
        attributes={"color": text_value("Rosso", MKT), "item_highlights": text_value("Vecchia", MKT)},
    )
    patches = patches_from_content({
        "title": "Titolo nuovo",
        "bullets": ["b1", "b2 nuovo", "b3", "b4", "b5"],
        "description": "Descrizione nuova",
        "backend_keywords": "alfa beta",
        "item_highlights": "Nuova evidenza",
        "image_slots": {"main_product_image_locator": "https://x.test/m2.jpg",
                        "other_product_image_locator_3": "https://x.test/3.jpg"},
        "attribute:color": text_value("Blu", MKT),
    }, MKT)
    after = baselines.baseline_after_change(base, _accepted("B0TEST0001", patches=patches))
    assert (after.title, after.description, after.backend_keywords, after.item_highlights) == (
        "Titolo nuovo", "Descrizione nuova", "alfa beta", "Nuova evidenza"
    )
    assert after.bullets == ["b1", "b2 nuovo", "b3", "b4", "b5"]
    assert [(i.variant, i.url) for i in after.images] == [
        ("MAIN", "https://x.test/m2.jpg"), ("PT01", "https://x.test/1.jpg"),
        ("PT02", "https://x.test/2.jpg"), ("PT03", "https://x.test/3.jpg"),
    ]
    assert after.attributes["color"] == text_value("Blu", MKT)
    assert after.attributes["item_highlights"] == text_value("Nuova evidenza", MKT)
    assert base.title == "Title B0TEST0001"  # the input is not mutated


def test_baseline_after_change_reads_put_attributes_and_image_deletes():
    from app.services.catalog_monitor.changes import text_value

    base = _content("B0TEST0001", images=[ImageRef("MAIN", "https://x.test/m.jpg"),
                                          ImageRef("PT01", "https://x.test/1.jpg")])
    put = _accepted("B0TEST0001", kind="new_item", operation="PUT",
                    attributes={"item_name": text_value("Nuovo articolo", MKT),
                                "material": text_value("Vetro", MKT)})
    after = baselines.baseline_after_change(base, put)
    assert after.title == "Nuovo articolo" and after.attributes["material"] == text_value("Vetro", MKT)
    delete = _accepted("B0TEST0001", patches=[{
        "op": "delete", "path": "/attributes/other_product_image_locator_1",
        "value": [{"marketplace_id": MKT}],
    }])
    assert [i.variant for i in baselines.baseline_after_change(base, delete).images] == ["MAIN"]


@pytest.mark.asyncio
async def test_accepted_changes_update_the_baseline_of_their_asin_only():
    from app.services.catalog_monitor.changes import patches_from_content

    repo = _Repo()
    repo.base["B0TEST0001"] = ListingContentBaseline(
        account_id=ACC, asin="B0TEST0001", content=content_to_dict(_content("B0TEST0001")),
        source=baselines.SOURCE_UPLOAD,
    )
    title = patches_from_content({"title": "Nuovo"}, MKT)
    requests = [
        _accepted("B0TEST0001", patches=title),
        _accepted("B0TEST0002", patches=title),  # no baseline: nothing to update
        _accepted("B0TEST0001", kind="content_restore", patches=patches_from_content({"title": "Altro"}, MKT)),
        _accepted("B0TEST0001", kind="variation_restore", patches=title),
    ]
    assert await baselines.apply_accepted_changes(repo, ACC, requests) == 1
    row = repo.base["B0TEST0001"]
    assert content_from_dict(row.content).title == "Nuovo"
    assert (row.source, row.approved_by_user_id) == (baselines.SOURCE_UPLOAD, USER)
    assert set(repo.base) == {"B0TEST0001"}



# ---- memory at scale (final review) ----


@pytest.mark.asyncio
async def test_approving_every_asin_reads_the_versions_in_chunks(monkeypatch):
    monkeypatch.setattr(baselines, "BASELINE_CHUNK", 2)
    repo = _Repo()
    for n in range(1, 6):
        repo.add_live(_content(f"B0TEST000{n}"))
    assert await baselines.approve_live_as_baseline(repo, ACC, None, USER) == 5
    assert set(repo.base) == {f"B0TEST000{n}" for n in range(1, 6)}
    assert repo.version_calls == [
        ["B0TEST0001", "B0TEST0002"], ["B0TEST0003", "B0TEST0004"], ["B0TEST0005"]
    ]


@pytest.mark.asyncio
async def test_accepted_changes_read_only_the_baselines_of_their_asins():
    from app.services.catalog_monitor.changes import patches_from_content

    repo = _Repo()
    for asin in ("B0TEST0001", "B0TEST0002", "B0TEST0003"):
        repo.base[asin] = ListingContentBaseline(
            account_id=ACC, asin=asin, content=content_to_dict(_content(asin)), source="live_snapshot",
        )
    title = patches_from_content({"title": "Nuovo"}, MKT)
    requests = [_accepted("B0TEST0002", patches=title), _accepted("B0TEST0003", patches=title)]
    assert await baselines.apply_accepted_changes(repo, ACC, requests) == 2
    assert repo.baseline_calls == [["B0TEST0002", "B0TEST0003"]]


@pytest.mark.asyncio
async def test_accepting_an_anomaly_reads_only_its_baseline():
    repo = _Repo()
    await repo.upsert_baseline(ACC, "B0TEST0001", _content("B0TEST0001"), "live_snapshot", USER)
    await repo.upsert_baseline(ACC, "B0TEST0002", _content("B0TEST0002"), "live_snapshot", USER)
    await baselines.accept_anomaly(
        repo, _anomaly("B0TEST0001", "content_changed", "title", "Nuovo"), USER, NOW
    )
    assert repo.baseline_calls == [["B0TEST0001"]]


@pytest.mark.asyncio
async def test_baseline_upload_reads_the_versions_in_chunks(monkeypatch):
    monkeypatch.setattr(baselines, "BASELINE_CHUNK", 2)
    repo = _Repo()
    for n in range(1, 4):
        repo.add_live(_content(f"B0TEST000{n}"))
    rows = [(f"B0TEST000{n}", {"title": f"Approvato {n}"}) for n in range(1, 4)]
    assert await baselines.import_baseline_rows(repo, ACC, rows, USER) == (3, [])
    assert repo.version_calls == [["B0TEST0001", "B0TEST0002"], ["B0TEST0003"]]
    assert content_from_dict(repo.base["B0TEST0003"].content).title == "Approvato 3"
