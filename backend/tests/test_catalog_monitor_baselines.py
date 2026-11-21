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
        return {a: v for a, v in self.versions.items() if asins is None or a in asins}

    async def baselines(self, account_id):
        return dict(self.base)

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
