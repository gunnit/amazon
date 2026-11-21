"""Normalised listing content shared by quality rules, diffing, scans and export (R1-R3).

Pure module: no database, no network. Builds one ``ListingContent`` from a
Catalog Items v2022-04-01 payload (works for Vendor and Seller accounts) and
optionally enriches it from a Listings Items v2021-08-01 payload (Seller only).
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field, fields, replace
from typing import Any, Optional

# Attributes that change with offers, stock or shipping rather than with the
# content a shopper reads; keeping them would raise false change alerts.
VOLATILE_ATTRIBUTES: frozenset[str] = frozenset(
    {
        "purchasable_offer",
        "list_price",
        "fulfillment_availability",
        "merchant_shipping_group",
        "condition_type",
        "max_order_quantity",
        "skip_offer",
        "merchant_release_date",
        "supplier_declared_dg_hz_regulation",
        "batteries_required",
    }
)

_HIGHLIGHT_KEYS = ("item_highlights", "item_highlight", "highlights")
_IGNORED_IMAGE_VARIANTS = {"SWCH"}
_HASH_EXCLUDED = ("listing_status", "listing_issues")


@dataclass(frozen=True)
class ImageRef:
    variant: str
    url: str
    width: Optional[int] = None
    height: Optional[int] = None


@dataclass
class ListingContent:
    asin: str
    marketplace_id: str
    sku: Optional[str] = None
    title: Optional[str] = None
    brand: Optional[str] = None
    bullets: list[str] = field(default_factory=list)
    description: Optional[str] = None
    item_highlights: Optional[str] = None
    backend_keywords: Optional[str] = None
    backend_keywords_readable: bool = False
    images: list[ImageRef] = field(default_factory=list)
    has_video: Optional[bool] = None
    aplus_module_count: Optional[int] = None
    aplus_available: bool = False
    attributes: dict = field(default_factory=dict)
    product_type: Optional[str] = None
    classification_path: list[str] = field(default_factory=list)
    browse_node_id: Optional[str] = None
    parent_asins: list[str] = field(default_factory=list)
    child_asins: list[str] = field(default_factory=list)
    variation_theme: Optional[str] = None
    listing_status: Optional[list[str]] = None
    listing_issues: list[dict] = field(default_factory=list)


def attribute_text(
    attributes: dict, name: str, marketplace_id: Optional[str] = None
) -> list[str]:
    """Text values of an attribute, in order, for one marketplace (or all)."""
    out: list[str] = []
    for item in attributes.get(name) or []:
        if not isinstance(item, dict):
            continue
        mp = item.get("marketplace_id")
        if marketplace_id and mp and mp != marketplace_id:
            continue
        value = item.get("value")
        if isinstance(value, str) and value.strip():
            out.append(value)
    return out


def _first_text(attributes: dict, name: str, marketplace_id: str) -> Optional[str]:
    values = attribute_text(attributes, name, marketplace_id)
    return values[0] if values else None


def _for_marketplace(entries: Any, marketplace_id: str) -> Optional[dict]:
    for entry in entries or []:
        if isinstance(entry, dict) and entry.get("marketplaceId") == marketplace_id:
            return entry
    return None


def _strip_volatile(attributes: dict) -> dict:
    return {k: v for k, v in (attributes or {}).items() if k not in VOLATILE_ATTRIBUTES}


def _variant_order(variant: str) -> tuple[int, int, str]:
    if variant == "MAIN":
        return (0, 0, variant)
    match = re.fullmatch(r"PT(\d+)", variant)
    if match:
        return (1, int(match.group(1)), variant)
    return (2, 0, variant)


def _images(payload: dict, marketplace_id: str) -> list[ImageRef]:
    block = _for_marketplace(payload.get("images"), marketplace_id) or {}
    best: dict[str, ImageRef] = {}
    for raw in block.get("images") or []:
        variant = raw.get("variant")
        link = raw.get("link")
        if not variant or not link or variant in _IGNORED_IMAGE_VARIANTS:
            continue
        ref = ImageRef(variant, link, raw.get("width"), raw.get("height"))
        current = best.get(variant)
        if current is None or (ref.width or 0) > (current.width or 0):
            best[variant] = ref
    return [best[v] for v in sorted(best, key=_variant_order)]


def _classification(payload: dict, marketplace_id: str) -> tuple[list[str], Optional[str]]:
    block = _for_marketplace(payload.get("classifications"), marketplace_id) or {}
    items = block.get("classifications") or []
    if not items:
        return [], None
    first = items[0]
    names: list[str] = []
    node = first
    while isinstance(node, dict):
        if node.get("displayName"):
            names.append(node["displayName"])
        node = node.get("parent")
    names.reverse()
    node_id = first.get("classificationId")
    return names, str(node_id) if node_id is not None else None


def content_from_catalog(payload: dict, marketplace_id: str) -> ListingContent:
    """Build content from a Catalog Items v2022-04-01 ``getCatalogItem`` payload."""
    attrs = payload.get("attributes") or {}
    summary = _for_marketplace(payload.get("summaries"), marketplace_id) or {}

    highlights = None
    for key in _HIGHLIGHT_KEYS:
        values = attribute_text(attrs, key, marketplace_id)
        if values:
            highlights = "\n".join(values)
            break

    product_type = (_for_marketplace(payload.get("productTypes"), marketplace_id) or {}).get(
        "productType"
    )
    path, node_id = _classification(payload, marketplace_id)

    parents: list[str] = []
    children: list[str] = []
    theme: Optional[str] = None
    rel_block = _for_marketplace(payload.get("relationships"), marketplace_id) or {}
    for rel in rel_block.get("relationships") or []:
        if rel.get("type") != "VARIATION":
            continue
        parents.extend(a for a in rel.get("parentAsins") or [] if a not in parents)
        children.extend(a for a in rel.get("childAsins") or [] if a not in children)
        theme = theme or (rel.get("variationTheme") or {}).get("theme")

    return ListingContent(
        asin=payload.get("asin", ""),
        marketplace_id=marketplace_id,
        title=_first_text(attrs, "item_name", marketplace_id) or summary.get("itemName"),
        brand=_first_text(attrs, "brand", marketplace_id) or summary.get("brand"),
        bullets=attribute_text(attrs, "bullet_point", marketplace_id),
        description=_first_text(attrs, "product_description", marketplace_id),
        item_highlights=highlights,
        images=_images(payload, marketplace_id),
        attributes=_strip_volatile(attrs),
        product_type=product_type,
        classification_path=path,
        browse_node_id=node_id,
        parent_asins=parents,
        child_asins=children,
        variation_theme=theme,
    )


def merge_listing(content: ListingContent, listing_payload: dict) -> ListingContent:
    """Add Listings Items data (SKU, backend keywords, status, issues).

    The catalogue wins for shopper-visible text; the input is not mutated.
    """
    lattrs = listing_payload.get("attributes") or {}
    mp = content.marketplace_id
    summary = _for_marketplace(listing_payload.get("summaries"), mp) or {}
    merged_attrs = {**_strip_volatile(lattrs), **content.attributes}
    keywords = attribute_text(lattrs, "generic_keyword", mp)
    status = summary.get("status")
    return replace(
        content,
        sku=listing_payload.get("sku") or content.sku,
        backend_keywords=" ".join(keywords) if keywords else None,
        backend_keywords_readable=True,
        listing_status=list(status) if status is not None else [],
        listing_issues=[dict(i) for i in listing_payload.get("issues") or []],
        attributes=merged_attrs,
        product_type=content.product_type or summary.get("productType"),
    )


def with_aplus(
    content: ListingContent, module_count: Optional[int], available: bool
) -> ListingContent:
    return replace(content, aplus_module_count=module_count, aplus_available=available)


def carry_forward(
    content: ListingContent,
    previous: Optional[ListingContent],
    listing_fetched: bool,
    aplus_fetched: bool,
) -> ListingContent:
    """Fill fields an Amazon call could not supply today from the previous version.

    Keeps the content hash stable when the Listings or A+ call fails; fresh
    values always win. Inputs are not mutated.
    """
    if previous is None:
        return content
    result = content
    if not listing_fetched:
        extra = {
            k: v for k, v in previous.attributes.items() if k not in content.attributes
        }
        result = replace(
            result,
            sku=previous.sku,
            backend_keywords=previous.backend_keywords,
            backend_keywords_readable=previous.backend_keywords_readable,
            listing_status=previous.listing_status,
            listing_issues=[dict(i) for i in previous.listing_issues],
            attributes={**content.attributes, **extra},
        )
    if not aplus_fetched:
        result = replace(
            result,
            aplus_available=previous.aplus_available,
            aplus_module_count=previous.aplus_module_count,
        )
    return result


def content_to_dict(content: ListingContent) -> dict:
    return asdict(content)


def content_from_dict(data: dict) -> ListingContent:
    names = {f.name for f in fields(ListingContent)}
    data = {k: v for k, v in data.items() if k in names}
    data["images"] = [ImageRef(**i) for i in data.get("images") or []]
    return ListingContent(**data)


def content_hash(content: ListingContent) -> str:
    """sha256 of canonical JSON, excluding listing status and issues."""
    data = content_to_dict(content)
    for key in _HASH_EXCLUDED:
        data.pop(key, None)
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
