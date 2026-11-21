"""Brand-approved baselines: from live content, from an accepted change or from an upload (R2, R3).

Content protection and broken-variation monitoring compare live content with
these baselines. Pure service functions over ``CatalogMonitorRepository``;
callers commit.
"""
from __future__ import annotations

import re
from dataclasses import replace
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from app.models.catalog_monitor import CatalogAnomaly
from app.services.catalog_monitor.content import (
    ImageRef,
    ListingContent,
    _variant_order,
    content_from_dict,
)

SOURCE_LIVE = "live_snapshot"
SOURCE_UPLOAD = "excel_upload"


async def approve_live_as_baseline(
    repo, account_id: UUID, asins: Optional[list[str]], user_id: Optional[UUID]
) -> int:
    """Make the latest live content the baseline; returns the baselines written."""
    versions = await repo.latest_versions(account_id, asins)
    written = 0
    for asin in sorted(versions):
        content = content_from_dict(versions[asin].content)
        await repo.upsert_baseline(account_id, asin, content, SOURCE_LIVE, user_id)
        written += 1
        if content.child_asins:
            await repo.upsert_family_baseline(
                account_id, asin, content.variation_theme, list(content.child_asins)
            )
    return written


def _positional_images(urls: list[str], known: list[ImageRef]) -> list[ImageRef]:
    by_url = {i.url: i for i in known}
    refs = []
    for pos, url in enumerate(urls):
        variant = "MAIN" if pos == 0 else f"PT{pos:02d}"
        old = by_url.get(url)
        refs.append(ImageRef(variant, url, old.width if old else None, old.height if old else None))
    return refs


async def accept_anomaly(
    repo, anomaly: CatalogAnomaly, user_id: Optional[UUID], now: datetime
) -> None:
    """Accept the live value as approved: update the baseline, resolve the anomaly."""
    if anomaly.kind == "content_changed":
        await _accept_content_change(repo, anomaly, user_id)
    elif anomaly.kind in {"child_detached", "unexpected_child", "family_broken", "theme_changed"}:
        await _refresh_family(repo, anomaly)
    else:
        raise ValueError(f"unknown anomaly kind: {anomaly.kind}")
    await repo.resolve_anomaly(anomaly, now)


async def _accept_content_change(repo, anomaly: CatalogAnomaly, user_id) -> None:
    account_id, asin, name, live = anomaly.account_id, anomaly.asin, anomaly.field, anomaly.live_value
    baseline_row = (await repo.baselines(account_id)).get(asin)
    if baseline_row is None:
        raise ValueError(f"{asin}: no baseline to update")
    content = content_from_dict(baseline_row.content)
    if name == "title":
        content = replace(content, title=live)
    elif name == "description":
        content = replace(content, description=live)
    elif name == "bullets":
        content = replace(content, bullets=list(live or []))
    elif name == "images":
        content = replace(content, images=_positional_images(list(live or []), content.images))
    elif name == "aplus":
        content = replace(content, aplus_module_count=live)
    elif name.startswith("attribute:"):
        key = name.split(":", 1)[1]
        latest = (await repo.latest_versions(account_id, [asin])).get(asin)
        attrs = dict(content.attributes)
        live_attrs = content_from_dict(latest.content).attributes if latest is not None else {}
        if key in live_attrs:
            attrs[key] = live_attrs[key]
        else:
            attrs.pop(key, None)
        content = replace(content, attributes=attrs)
    else:
        raise ValueError(f"unknown content field: {name}")
    await repo.upsert_baseline(account_id, asin, content, baseline_row.source, user_id)


async def _refresh_family(repo, anomaly: CatalogAnomaly) -> None:
    account_id = anomaly.account_id
    parent = anomaly.field.split(":", 1)[1] if ":" in anomaly.field else None
    if not parent:
        raise ValueError(f"variation anomaly without parent field: {anomaly.field!r}")
    latest = (await repo.latest_versions(account_id, [parent])).get(parent)
    if latest is None:
        raise ValueError(f"{parent}: no live content yet")
    live_parent = content_from_dict(latest.content)
    await repo.upsert_family_baseline(
        account_id, parent, live_parent.variation_theme, list(live_parent.child_asins)
    )


def _apply_cells(content: ListingContent, cells: dict[str, Any]) -> ListingContent:
    def given(key: str) -> Optional[str]:
        value = cells.get(key)
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    for key in ("title", "description", "backend_keywords", "item_highlights"):
        if given(key) is not None:
            content = replace(content, **{key: given(key)})

    bullets = list(content.bullets)
    for n in range(1, 6):
        text = given(f"bullet_{n}")
        if text is not None:
            bullets += [""] * (n - len(bullets))
            bullets[n - 1] = text
    content = replace(content, bullets=bullets)

    images = {i.variant: i for i in content.images}
    if given("main_image_url") is not None:
        images["MAIN"] = ImageRef("MAIN", given("main_image_url"))
    for n in range(1, 9):
        if given(f"image_{n}") is not None:
            images[f"PT{n:02d}"] = ImageRef(f"PT{n:02d}", given(f"image_{n}"))
    content = replace(content, images=[images[v] for v in sorted(images, key=_variant_order)])

    attrs = dict(content.attributes)
    for key in cells:
        match = re.fullmatch(r"attr:(.+)", key)
        if match and given(key) is not None:
            attrs[match.group(1)] = [
                {"value": given(key), "marketplace_id": content.marketplace_id}
            ]
    return replace(content, attributes=attrs)


async def import_baseline_rows(
    repo, account_id: UUID, rows: list[tuple[str, dict]], user_id: Optional[UUID]
) -> tuple[int, list[str]]:
    """Approved content from an upload: live content plus the given cells."""
    versions = await repo.latest_versions(account_id, [asin for asin, _ in rows])
    written, errors = 0, []
    for asin, cells in rows:
        version = versions.get(asin)
        if version is None:
            errors.append(f"{asin}: no live content yet")
            continue
        content = _apply_cells(content_from_dict(version.content), cells)
        await repo.upsert_baseline(account_id, asin, content, SOURCE_UPLOAD, user_id)
        written += 1
    return written, errors
