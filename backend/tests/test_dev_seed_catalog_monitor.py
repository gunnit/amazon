"""The local demo seed (scripts/dev_seed_catalog_monitor.py): safety guard and fixture realism.

No database: the guard, the fixture files, the generated main images and the
third-party changes the seed makes before its second scan.
"""
import asyncio
import importlib.util
import sys
from pathlib import Path

import pytest

from app.services.catalog_monitor.content import content_from_catalog
from app.services.catalog_monitor.diff import diff_content
from app.services.catalog_monitor.images import analyze_main_image

SEED_PATH = Path(__file__).resolve().parents[1] / "scripts" / "dev_seed_catalog_monitor.py"


def _load_seed():
    name = "dev_seed_catalog_monitor"
    if name not in sys.modules:  # registered first: its dataclasses look themselves up
        spec = importlib.util.spec_from_file_location(name, SEED_PATH)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return sys.modules[name]


seed = _load_seed()


@pytest.mark.parametrize("url", [
    "postgresql+asyncpg://postgres@db.example.com:5432/inthezon",
    "postgresql+asyncpg://user:pw@10.0.0.5/inthezon",
    "postgresql+asyncpg:///inthezon",
])
def test_refuses_any_database_not_on_localhost(url):
    with pytest.raises(SystemExit):
        seed.refuse_non_local(url)


@pytest.mark.parametrize("host", ["localhost", "127.0.0.1"])
def test_accepts_localhost(host):
    seed.refuse_non_local(f"postgresql+asyncpg://postgres@{host}:5455/inthezon_dev")


def test_main_refuses_before_connecting(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://postgres@db.example.com/inthezon")

    def never(*args, **kwargs):
        raise AssertionError("connected to a remote database")

    monkeypatch.setattr(seed, "create_async_engine", never)
    with pytest.raises(SystemExit, match="not localhost"):
        asyncio.run(seed.main(["--email", "demo@example.com", "--password", "x" * 12,
                               "--fixtures-dir", str(tmp_path)]))
    assert not any(tmp_path.iterdir())  # nothing written either


@pytest.fixture
def fixtures(tmp_path):
    config = seed.SeedConfig(admin_email="demo@example.com", admin_password="x" * 12,
                             fixture_dir=tmp_path, image_base_url="http://img.test")
    seed.write_fixtures(config)
    return tmp_path


def _content(directory: Path, asin: str):
    client = seed.FixtureClient(str(directory), seed.MP)
    return content_from_catalog(client.get_catalog_item_full(asin), seed.MP)


def test_fixtures_hold_every_product_and_its_listing(fixtures):
    assert sorted(p.stem for p in (fixtures / "catalog").glob("*.json")) == [
        f"B0TEST{n:04d}" for n in range(1, 13)
    ]
    listings = sorted(p.stem for p in (fixtures / "listings").glob("*.json"))
    assert len(listings) == 12 + 3  # the seller's, and the vendor's with a SKU
    assert {"TEST-VSKU-001", "TEST-VSKU-002", "TEST-VSKU-003"} <= set(listings)
    vendor = seed.FixtureClient(str(fixtures), seed.MP, account_type="vendor")
    assert vendor.resolve_vendor_code() == "TESTVENDOR"
    assert vendor.get_listing("TESTVENDOR", "TEST-VSKU-002")["summaries"][0]["asin"] == "B0TEST0002"
    child = _content(fixtures, "B0TEST0012")
    assert (child.parent_asins, child.variation_theme) == (["B0TEST0010"], "COLOR")
    assert _content(fixtures, "B0TEST0010").child_asins == ["B0TEST0011", "B0TEST0012"]


def test_main_images_cover_green_yellow_and_red(fixtures):
    def analysis(asin):
        return analyze_main_image((fixtures / "images" / f"{asin}-main.png").read_bytes())

    green = analysis("B0TEST0001")
    assert green.white_background and green.fill_ratio >= 0.85
    small = analysis("B0TEST0005")
    assert small.white_background and abs(small.fill_ratio - 0.6) < 0.01
    assert not analysis("B0TEST0006").white_background


def test_mutations_are_the_four_expected_changes(fixtures):
    before = {asin: _content(fixtures, asin) for asin in seed.PRODUCT_BY_ASIN}
    seed.mutate_fixtures(fixtures)
    changes = {
        asin: [(c.field, c.change) for c in diff_content(before[asin], _content(fixtures, asin))]
        for asin in seed.PRODUCT_BY_ASIN
    }
    assert {asin: c for asin, c in changes.items() if c} == {
        "B0TEST0002": [("title", "modified")],
        "B0TEST0003": [("bullets", "modified")],
        "B0TEST0004": [("images", "reordered")],
    }
    assert _content(fixtures, "B0TEST0012").parent_asins == []
    assert _content(fixtures, "B0TEST0010").child_asins == ["B0TEST0011"]
