"""Local stand-in for SP-API: the catalogue monitor's Amazon calls answered from JSON files (R1-R4).

Development only. ``default_client_factory`` returns a ``FixtureClient`` when
``DEV_FIXTURE_AMAZON_DIR`` is set and ``APP_ENV`` is development or test; any other
environment ignores the setting, and production refuses to start with it. ``scripts/dev_seed_catalog_monitor.py`` writes the directory:

    catalog/<ASIN>.json        Catalog Items payload (getCatalogItem, all sections)
    listings/<SKU>.json        Listings Items payload (getListingsItem)
    product_types/<TYPE>.json  product type JSON schema ("required", "properties")
    images/<name>.png          image files, served by the API at /dev-fixtures/images
    client.json                {"vendor_code": str|null, "aplus_modules": {ASIN: int}}
    feeds/<feedId>.json        feeds submitted through this client

Writes behave like Listings Items: ``mode="VALIDATION_PREVIEW"`` answers VALID or
INVALID (a title over 200 characters is an ERROR issue) and changes nothing; a live
call answers ACCEPTED and writes the patch into the catalog and listing files, so the
next scan sees it. Image locator patches move the catalog images, variation patches
move the catalog relationships. Feeds are processed at once.
"""
from __future__ import annotations

import json
import logging
import os
import re
import tempfile
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from app.config import settings
from app.core.exceptions import AmazonAPIError

logger = logging.getLogger(__name__)

VALIDATION_PREVIEW = "VALIDATION_PREVIEW"
IMAGES_ROUTE = "/dev-fixtures/images"  # where the API serves <dir>/images while the seam is on
TITLE_MAX_LENGTH = 200
SCHEMA_SCHEME = "fixture://product_types/"
_IMAGE_SLOT = re.compile(r"other_product_image_locator_(\d+)")
_VARIATION_ATTRIBUTES = frozenset(
    {"parentage_level", "child_parent_sku_relationship", "variation_theme"}
)
_LISTING_ONLY_ATTRIBUTES = frozenset({"generic_keyword"})
_LOCK = threading.Lock()  # scans run in a thread while requests write


FIXTURE_ENVIRONMENTS = frozenset({"development", "test"})


def _fixture_environment() -> bool:
    return (settings.APP_ENV or "").lower() in FIXTURE_ENVIRONMENTS


def active_fixture_dir() -> Optional[str]:
    """The fixture directory when the seam is on: set, and APP_ENV development or test.

    An allowlist on purpose: a staging environment or a mistyped APP_ENV must
    never answer real accounts from local files. Production refuses to start
    with the setting (``validate_production_settings``).
    """
    directory = settings.DEV_FIXTURE_AMAZON_DIR
    if not directory or not _fixture_environment():
        return None
    return directory


def log_fixture_mode(log: logging.Logger = logger) -> None:
    """At startup: a warning when Amazon calls go to fixtures, an error when the setting is ignored."""
    if not settings.DEV_FIXTURE_AMAZON_DIR:
        return
    if not _fixture_environment():
        log.error(
            "DEV_FIXTURE_AMAZON_DIR is set with APP_ENV=%r: ignored, SP-API is used",
            settings.APP_ENV,
        )
    else:
        log.warning(
            "DEV_FIXTURE_AMAZON_DIR is set: catalogue monitor Amazon calls are answered "
            "from local fixtures in %s",
            settings.DEV_FIXTURE_AMAZON_DIR,
        )


def _safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", value)


def _not_found(what: str) -> AmazonAPIError:
    return AmazonAPIError(f"Fixture not found: {what}", error_code="NOT_FOUND")


def _issue(code: str, message: str, attribute: Optional[str] = None) -> dict:
    issue: dict[str, Any] = {"code": code, "message": message, "severity": "ERROR"}
    if attribute:
        issue["attributeNames"] = [attribute]
    return issue


def _for_marketplace(entries: list, marketplace_id: str) -> Optional[dict]:
    for entry in entries:
        if isinstance(entry, dict) and entry.get("marketplaceId") == marketplace_id:
            return entry
    return None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class FixtureClient:
    """The SP-API methods the catalogue monitor and its change requests use, over local files."""

    def __init__(self, directory: str, marketplace_id: str, account_type: str = "seller"):
        self.root = Path(directory)
        self.marketplace_id = marketplace_id
        self.account_type = account_type

    @property
    def is_vendor(self) -> bool:
        return self.account_type == "vendor"

    # ---- files ----

    def _path(self, folder: str, name: str) -> Path:
        return self.root / folder / f"{_safe_name(name)}.json"

    def _read(self, path: Path) -> Optional[dict]:
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def _write(self, path: Path, data: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, path)

    def _settings(self) -> dict:
        return self._read(self.root / "client.json") or {}

    def _listing_files(self) -> list[dict]:
        folder = self.root / "listings"
        if not folder.is_dir():
            return []
        return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(folder.glob("*.json"))]

    def _asin_of(self, listing: Optional[dict]) -> Optional[str]:
        summary = _for_marketplace((listing or {}).get("summaries") or [], self.marketplace_id)
        return (summary or {}).get("asin")

    def _asin_for_sku(self, sku: str) -> Optional[str]:
        return self._asin_of(self._read(self._path("listings", sku)))

    # ---- reads ----

    def get_catalog_item_full(self, asin: str) -> Optional[dict]:
        payload = self._read(self._path("catalog", asin))
        if payload is None:
            raise _not_found(f"catalog item {asin}")
        return payload

    def get_listing(
        self, seller_id: str, sku: str, included_data: Optional[list[str]] = None
    ) -> dict:
        payload = self._read(self._path("listings", sku))
        if payload is None:
            raise _not_found(f"listing {sku}")
        return payload

    def search_listings_by_asins(self, seller_id: str, asins: list[str]) -> list[dict]:
        wanted = set(asins)
        return [
            {"sku": item.get("sku"), "summaries": item.get("summaries") or [],
             "issues": item.get("issues") or []}
            for item in self._listing_files()
            if self._asin_of(item) in wanted
        ]

    def get_product_type_definition(
        self, product_type: str, seller_id: Optional[str] = None, locale: str = "it_IT"
    ) -> dict:
        if not self._path("product_types", product_type).is_file():
            raise _not_found(f"product type {product_type}")
        return {
            "productType": product_type,
            "requirements": "LISTING",
            "schema": {"link": {"resource": f"{SCHEMA_SCHEME}{product_type}", "verb": "GET"}},
        }

    def fetch_json_schema(self, url: str) -> dict:
        if not url.startswith(SCHEMA_SCHEME):
            raise ValueError(f"not a fixture schema link: {url}")
        schema = self._read(self._path("product_types", url[len(SCHEMA_SCHEME):]))
        if schema is None:
            raise ValueError(f"fixture schema missing: {url}")
        return schema

    def get_aplus_publish_record_count(self, asin: str) -> int:
        return int((self._settings().get("aplus_modules") or {}).get(asin, 0))

    def get_aplus_content_for_asin(self, asin):
        count = self.get_aplus_publish_record_count(asin)
        return {"aplus_module_count": count, "publish_record_count": count}

    def resolve_vendor_code(self) -> Optional[str]:
        if not self.is_vendor:
            return None
        return self._settings().get("vendor_code")

    # ---- writes ----

    def _validate(self, sku: str, attributes: dict, must_exist: bool) -> list[dict]:
        issues: list[dict] = []
        if must_exist and self._read(self._path("listings", sku)) is None:
            issues.append(_issue("4000004", f"SKU {sku} non trovato per questo venditore"))
        for entry in attributes.get("item_name") or []:
            value = entry.get("value") if isinstance(entry, dict) else None
            if isinstance(value, str) and len(value) > TITLE_MAX_LENGTH:
                issues.append(_issue(
                    "90220",
                    f"'item_name' supera la lunghezza massima di {TITLE_MAX_LENGTH} caratteri",
                    "item_name",
                ))
        return issues

    def _answer(self, sku: str, issues: list[dict], mode: Optional[str]) -> dict:
        if issues:
            status = "INVALID"
        else:
            status = "VALID" if mode == VALIDATION_PREVIEW else "ACCEPTED"
        return {"sku": sku, "status": status, "submissionId": uuid.uuid4().hex, "issues": issues}

    def patch_listing(
        self,
        seller_id: str,
        sku: str,
        product_type: str,
        patches: list[dict],
        mode: Optional[str] = None,
    ) -> dict:
        if not patches:
            raise AmazonAPIError("No patches supplied", error_code="INVALID_PATCH")
        replaced = {
            p["path"].rsplit("/", 1)[-1]: p.get("value")
            for p in patches if p.get("op") == "replace"
        }
        issues = self._validate(sku, replaced, must_exist=True)
        answer = self._answer(sku, issues, mode)
        if answer["status"] == "ACCEPTED":
            with _LOCK:
                self._apply_patches(sku, patches)
        return answer

    def put_listing(
        self,
        seller_id: str,
        sku: str,
        product_type: str,
        attributes: dict,
        mode: Optional[str] = None,
        requirements: str = "LISTING",
    ) -> dict:
        answer = self._answer(sku, self._validate(sku, attributes, must_exist=False), mode)
        if answer["status"] == "ACCEPTED":
            with _LOCK:
                self._write(self._path("listings", sku), {
                    "sku": sku,
                    "summaries": [{
                        "marketplaceId": self.marketplace_id,
                        "productType": product_type,
                        "status": ["DISCOVERABLE"],
                        "createdDate": _now_iso(),
                    }],
                    "attributes": attributes,
                    "issues": [],
                })
        return answer

    def _apply_patches(self, sku: str, patches: list[dict]) -> None:
        listing_path = self._path("listings", sku)
        listing = self._read(listing_path) or {"sku": sku, "attributes": {}}
        asin = self._asin_of(listing)
        catalog = self._read(self._path("catalog", asin)) if asin else None
        for patch in patches:
            name = patch["path"].rsplit("/", 1)[-1]
            value = patch.get("value")
            delete = patch.get("op") == "delete"
            if name == "main_product_image_locator" or _IMAGE_SLOT.fullmatch(name):
                if catalog is not None:
                    self._set_image(catalog, name, None if delete else value)
            elif name in _VARIATION_ATTRIBUTES:
                if name == "child_parent_sku_relationship" and catalog is not None and not delete:
                    self._attach_child(asin, catalog, value)
            else:
                self._set_attribute(listing.setdefault("attributes", {}), name, value, delete)
                if catalog is not None and name not in _LISTING_ONLY_ATTRIBUTES:
                    self._set_attribute(catalog.setdefault("attributes", {}), name, value, delete)
                    if name == "item_name" and not delete:
                        self._set_summary_title(catalog, value)
        self._write(listing_path, listing)
        if catalog is not None:
            self._write(self._path("catalog", asin), catalog)

    @staticmethod
    def _set_attribute(attributes: dict, name: str, value: Any, delete: bool) -> None:
        if delete:
            attributes.pop(name, None)
        else:
            attributes[name] = value

    def _set_summary_title(self, catalog: dict, value: Any) -> None:
        summary = _for_marketplace(catalog.get("summaries") or [], self.marketplace_id)
        texts = [v.get("value") for v in value or [] if isinstance(v, dict)]
        if summary is not None and texts:
            summary["itemName"] = texts[0]

    def _image_block(self, catalog: dict) -> dict:
        blocks = catalog.setdefault("images", [])
        block = _for_marketplace(blocks, self.marketplace_id)
        if block is None:
            block = {"marketplaceId": self.marketplace_id, "images": []}
            blocks.append(block)
        return block

    def _set_image(self, catalog: dict, name: str, value: Any) -> None:
        match = _IMAGE_SLOT.fullmatch(name)
        variant = f"PT{int(match.group(1)):02d}" if match else "MAIN"
        block = self._image_block(catalog)
        images = [i for i in block.get("images") or [] if i.get("variant") != variant]
        urls = [v.get("media_location") for v in value or [] if isinstance(v, dict)]
        if urls and urls[0]:
            images.append({"variant": variant, "link": urls[0], "width": 1000, "height": 1000})
        block["images"] = images

    def _variation(self, catalog: dict) -> dict:
        blocks = catalog.setdefault("relationships", [])
        block = _for_marketplace(blocks, self.marketplace_id)
        if block is None:
            block = {"marketplaceId": self.marketplace_id, "relationships": []}
            blocks.append(block)
        for rel in block.setdefault("relationships", []):
            if rel.get("type") == "VARIATION":
                return rel
        rel = {"type": "VARIATION"}
        block["relationships"].append(rel)
        return rel

    def _attach_child(self, child_asin: str, child: dict, value: Any) -> None:
        """Name the parent on the child (written by the caller) and the child on the parent."""
        parent_skus = [v.get("parent_sku") for v in value or [] if isinstance(v, dict)]
        parent_asin = self._asin_for_sku(parent_skus[0]) if parent_skus and parent_skus[0] else None
        parent = self._read(self._path("catalog", parent_asin)) if parent_asin else None
        if parent is None:
            return
        parent_rel = self._variation(parent)
        children = parent_rel.setdefault("childAsins", [])
        if child_asin not in children:
            children.append(child_asin)
        child_rel = self._variation(child)
        child_rel["parentAsins"] = [parent_asin]
        if parent_rel.get("variationTheme"):
            child_rel["variationTheme"] = parent_rel["variationTheme"]
        self._write(self._path("catalog", parent_asin), parent)

    # ---- feeds ----

    def submit_json_listings_feed(self, document: dict) -> str:
        feed_id = f"FIXTURE{uuid.uuid4().hex[:10].upper()}"
        issues: list[dict] = []
        for message in document.get("messages") or []:
            sku = message.get("sku") or ""
            if message.get("operationType") == "PATCH":
                answer = self.patch_listing("", sku, message.get("productType") or "",
                                            list(message.get("patches") or []))
            else:
                answer = self.put_listing("", sku, message.get("productType") or "",
                                          message.get("attributes") or {})
            issues += [{**issue, "messageId": message.get("messageId")} for issue in answer["issues"]]
        accepted = len(document.get("messages") or []) - len({i["messageId"] for i in issues})
        with _LOCK:
            self._write(self._path("feeds", feed_id), {
                "feedId": feed_id,
                "feedType": "JSON_LISTINGS_FEED",
                "processingStatus": "DONE",
                "createdTime": _now_iso(),
                "resultFeedDocumentId": f"{feed_id}-RESULT",
                "result": {
                    "header": {"sellerId": (document.get("header") or {}).get("sellerId"),
                               "version": "2.0", "feedId": feed_id},
                    "issues": issues,
                    "summary": {"errors": len(issues), "warnings": 0,
                                "messagesProcessed": len(document.get("messages") or []),
                                "messagesAccepted": accepted,
                                "messagesInvalid": len({i["messageId"] for i in issues})},
                },
            })
        return feed_id

    def _feed(self, feed_id: str) -> dict:
        feed = self._read(self._path("feeds", feed_id))
        if feed is None:
            raise _not_found(f"feed {feed_id}")
        return feed

    def get_feed_status(self, feed_id: str) -> dict:
        feed = self._feed(feed_id)
        return {
            "processingStatus": feed["processingStatus"],
            "resultFeedDocumentId": feed.get("resultFeedDocumentId"),
        }

    def get_feed_result(self, document_id: str) -> dict:
        return self._feed(document_id.removesuffix("-RESULT"))["result"]

    def list_recent_feeds(self, page_size: int = 1) -> list[dict]:
        folder = self.root / "feeds"
        feeds = [
            json.loads(p.read_text(encoding="utf-8")) for p in folder.glob("*.json")
        ] if folder.is_dir() else []
        feeds.sort(key=lambda f: f.get("createdTime") or "", reverse=True)
        return [
            {k: f.get(k) for k in ("feedId", "feedType", "processingStatus", "createdTime")}
            for f in feeds[:page_size]
        ]
