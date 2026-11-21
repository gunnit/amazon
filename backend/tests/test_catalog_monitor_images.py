"""Main image analysis (R1): background, fill ratio, caching."""
import io
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from PIL import Image

from app.models.catalog_monitor import ImageCheck
from app.services.catalog_monitor import images
from app.services.catalog_monitor.images import analyze_main_image, get_image_analysis

URL = "https://example.test/TESTBRAND/B0TEST0001.jpg"


def _png(size, box, bg=(255, 255, 255), fg=(20, 20, 20)) -> bytes:
    img = Image.new("RGB", size, bg)
    if box:
        img.paste(fg, box)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


class FakeResult:
    def __init__(self, row):
        self._row = row

    def scalar_one_or_none(self):
        return self._row


class FakeDb:
    def __init__(self, row=None):
        self.row = row
        self.added = []

    async def execute(self, _stmt):
        return FakeResult(self.row)

    def add(self, obj):
        self.added.append(obj)


def _fetcher(data=None, exc=None):
    calls = []

    async def fetch(url):
        calls.append(url)
        if exc:
            raise exc
        return data

    fetch.calls = calls
    return fetch


def test_white_background_and_90_percent_fill():
    r = analyze_main_image(_png((1000, 1000), (50, 50, 949, 949)))
    assert r.white_background is True
    assert r.fill_ratio == pytest.approx(0.9, abs=0.01)
    assert (r.width, r.height, r.error) == (1000, 1000, None)


def test_small_product_low_fill():
    r = analyze_main_image(_png((1000, 1000), (250, 250, 749, 749)))
    assert r.white_background is True
    assert r.fill_ratio == pytest.approx(0.5, abs=0.01)


def test_grey_background_not_white():
    r = analyze_main_image(_png((1000, 1000), (50, 50, 949, 949), bg=(200, 200, 200)))
    assert r.white_background is False


def test_large_image_reports_original_size():
    r = analyze_main_image(_png((2000, 1500), (100, 100, 1899, 1399)))
    assert (r.width, r.height) == (2000, 1500)
    assert r.white_background is True
    assert r.fill_ratio == pytest.approx(0.9, abs=0.02)


def test_unreadable_bytes_returns_error():
    r = analyze_main_image(b"not an image")
    assert (r.white_background, r.fill_ratio, r.width, r.height) == (False, 0.0, 0, 0)
    assert r.error == "unreadable"


@pytest.mark.asyncio
async def test_download_failure_returns_error_and_caches():
    db = FakeDb()
    r = await get_image_analysis(db, URL, fetch=_fetcher(exc=RuntimeError("boom")))
    assert r.error == "download_failed"
    assert len(db.added) == 1 and db.added[0].error == "download_failed"


@pytest.mark.asyncio
async def test_success_is_cached_and_reused_forever():
    db = FakeDb()
    fetch = _fetcher(_png((1000, 1000), (50, 50, 949, 949)))
    r = await get_image_analysis(db, URL, fetch=fetch)
    assert r.error is None and len(db.added) == 1
    row = db.added[0]
    assert row.url_hash == images.url_hash(URL) and row.url == URL
    row.checked_at = datetime.now(timezone.utc) - timedelta(days=400)
    fetch2 = _fetcher(exc=RuntimeError("must not fetch"))
    r2 = await get_image_analysis(FakeDb(row), URL, fetch=fetch2)
    assert fetch2.calls == [] and r2.white_background is True
    assert r2.fill_ratio == pytest.approx(0.9, abs=0.01)


@pytest.mark.asyncio
async def test_error_row_reused_within_a_day_but_retried_after():
    row = ImageCheck(url_hash=images.url_hash(URL), url=URL, white_background=False,
                     fill_ratio=0.0, width=0, height=0, error="download_failed",
                     checked_at=datetime.now(timezone.utc) - timedelta(hours=2))
    fetch = _fetcher(_png((100, 100), (5, 5, 94, 94)))
    r = await get_image_analysis(FakeDb(row), URL, fetch=fetch)
    assert r.error == "download_failed" and fetch.calls == []

    row.checked_at = datetime.utcnow() - timedelta(days=2)  # naive timestamps too
    db = FakeDb(row)
    r = await get_image_analysis(db, URL, fetch=fetch)
    assert fetch.calls == [URL] and r.error is None
    assert db.added == [] and row.error is None and row.width == 100  # upserted in place
