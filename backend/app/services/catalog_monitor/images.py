"""Main-image analysis for the listing-quality rules (R1).

Amazon asks for a pure-white background and a product filling at least 85% of
the frame. ``analyze_main_image`` is pure (bytes in, verdict out);
``get_image_analysis`` adds download and a cache in ``image_checks``.
"""
from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable, Optional

import httpx
from PIL import Image, ImageChops, UnidentifiedImageError
from sqlalchemy import select

from app.models.catalog_monitor import ImageCheck

MAX_DOWNLOAD_BYTES = 10 * 1024 * 1024
MAX_ANALYSIS_SIDE = 1000
ERROR_RETRY_AFTER = timedelta(days=1)
_WHITE_BORDER_SHARE = 0.95


@dataclass(frozen=True)
class ImageAnalysis:
    white_background: bool
    fill_ratio: float
    width: int
    height: int
    error: Optional[str] = None


def url_hash(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def analyze_main_image(
    data: bytes, white_threshold: int = 245, border_ratio: float = 0.02
) -> ImageAnalysis:
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
        rgb = img.convert("RGB")
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        return ImageAnalysis(False, 0.0, 0, 0, error="unreadable")

    width, height = rgb.size
    if width == 0 or height == 0:
        return ImageAnalysis(False, 0.0, 0, 0, error="unreadable")
    if max(width, height) > MAX_ANALYSIS_SIDE:
        scale = MAX_ANALYSIS_SIDE / max(width, height)
        rgb = rgb.resize(
            (max(1, round(width * scale)), max(1, round(height * scale))),
            Image.BILINEAR,
        )
    w, h = rgb.size

    # 255 where any channel is darker than the threshold, i.e. product pixels.
    r, g, b_ = (c.point(lambda v: 255 if v < white_threshold else 0) for c in rgb.split())
    mask = ImageChops.lighter(ImageChops.lighter(r, g), b_)

    band = max(1, round(border_ratio * min(w, h)))
    inner = Image.new("L", (w, h), 0)
    inner.paste(255, (band, band, max(band, w - band), max(band, h - band)))
    border_total = w * h - _count(inner)
    border_product = _count(ImageChops.subtract(mask, inner))
    white = border_total > 0 and (
        (border_total - border_product) / border_total >= _WHITE_BORDER_SHARE
    )

    bbox = mask.getbbox()
    fill = 0.0 if bbox is None else max((bbox[2] - bbox[0]) / w, (bbox[3] - bbox[1]) / h)
    return ImageAnalysis(white, fill, width, height)


def _count(mask: Image.Image) -> int:
    """Number of 255 pixels in an L-mode mask."""
    return mask.histogram()[255]


async def _default_fetch(url: str) -> bytes:
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.content
    if len(data) > MAX_DOWNLOAD_BYTES:
        raise ValueError("image too large")
    return data


def _from_row(row: ImageCheck) -> ImageAnalysis:
    return ImageAnalysis(
        bool(row.white_background),
        float(row.fill_ratio or 0.0),
        row.width or 0,
        row.height or 0,
        row.error,
    )


def _age_exceeds(checked_at: Optional[datetime], limit: timedelta) -> bool:
    if checked_at is None:
        return True
    if checked_at.tzinfo is None:
        checked_at = checked_at.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - checked_at > limit


async def get_image_analysis(
    db, url: str, fetch: Optional[Callable[[str], Awaitable[bytes]]] = None
) -> ImageAnalysis:
    """Cached analysis of ``url``. Does not commit; the caller owns the transaction."""
    key = url_hash(url)
    row = (
        await db.execute(select(ImageCheck).where(ImageCheck.url_hash == key))
    ).scalar_one_or_none()
    if row is not None:
        # Amazon image URLs are immutable, so a good result never expires;
        # failures are retried after a day.
        if row.error is None or not _age_exceeds(row.checked_at, ERROR_RETRY_AFTER):
            return _from_row(row)

    try:
        data = await (fetch or _default_fetch)(url)
        if len(data) > MAX_DOWNLOAD_BYTES:
            raise ValueError("image too large")
        result = analyze_main_image(data)
    except Exception:  # noqa: BLE001 - any download failure is a grey rule, never a crash
        result = ImageAnalysis(False, 0.0, 0, 0, error="download_failed")

    if row is None:
        row = ImageCheck(url_hash=key, url=url)
        db.add(row)
    row.white_background = result.white_background
    row.fill_ratio = result.fill_ratio
    row.width = result.width
    row.height = result.height
    row.error = result.error
    row.checked_at = datetime.now(timezone.utc)
    return result
