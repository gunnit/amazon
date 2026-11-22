"""Change requests and the approval queue: the only way a catalogue write reaches Amazon (R2-R4).

Bulk updates, content restores, variation restores and new items all become
``CatalogChangeRequest`` rows. Nothing is written to a live listing unless Amazon
first checked it with ``mode="VALIDATION_PREVIEW"`` and an admin approved it:

    create        -> pending, or file_only (no listing seller id / vendor code, or no SKU)
    validate      -> valid | invalid       (pending, valid and invalid requests; a new
                                            item whose SKU already has a listing is invalid)
    approve       -> approved              (valid and file_only requests; admin only)
    reject        -> rejected              (anything not yet sent)
    submit        -> accepted | failed     (fewer than CATALOG_FEED_THRESHOLD: one call per SKU;
                                            a new item whose SKU went live meanwhile fails)
                  -> submitted             (otherwise: one JSON_LISTINGS_FEED)
    refresh_feed  -> accepted | failed     (from the feed's processing report)

An accepted bulk update or new item also updates its ASIN's baseline, so content
protection does not flag the approved change (``baselines.apply_accepted_changes``,
in a savepoint: a failure there is logged and never undoes the submission record).
A request marked as uploaded by hand does not: the next scan shows what went live.

A file-only request is never validated or submitted through the API, also once
approved (``payload["file_only"]`` keeps the mark): ``build_listings_feed`` turns
it into a file for a manual upload; ``submit`` also requires a passed validation.
Patches never erase content: an empty value gives no operation. The only deletes
are image slots past a new image list that the live listing fills, scoped to one
marketplace; Vendor accounts cannot delete attribute values, so ``create`` drops
them and lists them in ``summary["manual_image_removal"]``.
Amazon errors become issues on the request; requests handed to ``validate`` or
``submit`` must belong to the given account. Service methods flush, callers commit.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Literal, Optional
from uuid import UUID

from app.config import settings
from app.core.exceptions import AmazonAPIError
from app.models.amazon_account import AccountType
from app.models.catalog_monitor import CatalogAnomaly, CatalogChangeRequest
from app.services.catalog_monitor.baselines import apply_accepted_changes
from app.services.catalog_monitor.capabilities import listing_seller_id
from app.services.catalog_monitor.clients import (
    ClientFactory,
    default_client_factory,
    load_organization,
)
from app.services.catalog_monitor.content import ListingContent
from app.services.catalog_monitor.repository import CatalogMonitorRepository

logger = logging.getLogger(__name__)

LANGUAGE_TAG_BY_MARKETPLACE: dict[str, str] = {
    "APJ6JRA9NG5V4": "it_IT",  # IT
    "A1PA6795UKMFR9": "de_DE",  # DE
    "A13V1IB3VIYZZH": "fr_FR",  # FR
    "A1RKKUPIHCS9HS": "es_ES",  # ES
    "A1F83G8C2ARO7P": "en_GB",  # UK
    "A1805IZSGTT6HS": "nl_NL",  # NL
    "A2NODRKZP88ZB9": "sv_SE",  # SE
    "A1C3SOZRARQ6R3": "pl_PL",  # PL
    "AMEN7PMS3EDWL": "fr_BE",  # BE
    "ATVPDKIKX0DER": "en_US",  # US
}
DEFAULT_LANGUAGE_TAG = "it_IT"
FEED_ISSUE_LOCALE = "it_IT"
VALIDATION_PREVIEW = "VALIDATION_PREVIEW"
KINDS = frozenset({"bulk_update", "content_restore", "variation_restore", "new_item"})
OTHER_IMAGE_SLOTS = 8  # other_product_image_locator_1..8

_TEXT_ATTRIBUTES = {
    "title": "item_name",
    "description": "product_description",
    "backend_keywords": "generic_keyword",
    "item_highlights": "item_highlights",
}
_ATTRIBUTE_PREFIX = "attribute:"
_IMAGE_SLOT_ATTRIBUTES = frozenset(
    ["main_product_image_locator"]
    + [f"other_product_image_locator_{n}" for n in range(1, OTHER_IMAGE_SLOTS + 1)]
)
# Detected and shown, restored by hand: A+ content cannot be written through Listings Items.
_NOT_RESTORABLE = frozenset({"aplus"})
_VALIDATABLE = frozenset({"pending", "valid", "invalid"})
_APPROVABLE = frozenset({"valid", "file_only"})
_REJECTABLE = frozenset({"pending", "valid", "invalid", "approved", "file_only"})
_FEED_FAILED = frozenset({"FATAL", "CANCELLED"})
_NOT_FOUND_CODES = frozenset({"404", "NOT_FOUND"})


# ---- patch builders (pure) ----


def text_value(value: str, marketplace_id: str) -> list[dict]:
    """A Listings text attribute value in the marketplace's language."""
    tag = LANGUAGE_TAG_BY_MARKETPLACE.get(marketplace_id, DEFAULT_LANGUAGE_TAG)
    return [{"value": value, "language_tag": tag, "marketplace_id": marketplace_id}]


def _replace(name: str, value: Any) -> dict:
    return {"op": "replace", "path": f"/attributes/{name}", "value": value}


def _clean(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _image_patches(
    urls: Iterable[Any], marketplace_id: str, existing_image_slots: int
) -> list[dict]:
    """Main image plus up to 8 others, in order.

    A slot past the new list is deleted only when the live listing fills it
    (``existing_image_slots`` other images), and only for this marketplace.
    Listings Items holds nine images, so URLs past the ninth are ignored.
    """
    clean = [url for url in (_clean(u) for u in urls or []) if url]
    if not clean:
        return []

    def locator(url: str) -> list[dict]:
        return [{"media_location": url, "marketplace_id": marketplace_id}]

    patches = [_replace("main_product_image_locator", locator(clean[0]))]
    others = clean[1 : OTHER_IMAGE_SLOTS + 1]
    for n in range(1, OTHER_IMAGE_SLOTS + 1):
        name = f"other_product_image_locator_{n}"
        if n <= len(others):
            patches.append(_replace(name, locator(others[n - 1])))
        elif n <= existing_image_slots:
            patches.append(
                {
                    "op": "delete",
                    "path": f"/attributes/{name}",
                    "value": [{"marketplace_id": marketplace_id}],
                }
            )
    return patches


def patches_from_content(
    fields: dict[str, Any], marketplace_id: str, existing_image_slots: int = 0
) -> list[dict]:
    """``replace`` operations for the given content fields, in the given order.

    Keys: title, bullets (list), description, backend_keywords, item_highlights,
    images (URLs, main first), ``image_slots`` (attribute name -> URL, replaced in
    place, never deleted) and ``attribute:<name>`` (the raw Amazon value list).
    Empty values give no operation; blank bullets are dropped. Unknown keys raise
    ``ValueError``. ``existing_image_slots`` is how many other images the live
    listing has: only those slots past the new image list are deleted (none by
    default).
    """
    patches: list[dict] = []
    for key, value in fields.items():
        if key in _TEXT_ATTRIBUTES:
            text = _clean(value)
            if text:
                patches.append(_replace(_TEXT_ATTRIBUTES[key], text_value(text, marketplace_id)))
        elif key == "bullets":
            bullets = [b for b in (_clean(v) for v in value or []) if b]
            if bullets:
                patches.append(
                    _replace("bullet_point", [text_value(b, marketplace_id)[0] for b in bullets])
                )
        elif key == "images":
            patches += _image_patches(value, marketplace_id, existing_image_slots)
        elif key == "image_slots":
            # Slot by slot, no compaction and no deletes: only the named slots change.
            for name, url in (value or {}).items():
                if name not in _IMAGE_SLOT_ATTRIBUTES:
                    raise ValueError(f"unknown image slot: {name!r}")
                clean = _clean(url)
                if clean:
                    patches.append(
                        _replace(name, [{"media_location": clean, "marketplace_id": marketplace_id}])
                    )
        elif key.startswith(_ATTRIBUTE_PREFIX) and len(key) > len(_ATTRIBUTE_PREFIX):
            if not value:
                continue
            if not isinstance(value, list):
                raise ValueError(f"{key}: expected the Amazon attribute value list")
            patches.append(_replace(key[len(_ATTRIBUTE_PREFIX) :], value))
        else:
            raise ValueError(f"unknown content field: {key!r}")
    return patches


def restore_patches(
    baseline: ListingContent, fields: list[str], existing_image_slots: int = 0
) -> list[dict]:
    """Patches that put the baseline value of each field back.

    ``fields`` are anomaly fields (title, bullets, description, images,
    backend_keywords, item_highlights, attribute:<name>). A+ is skipped (restored
    by hand); a field the baseline does not hold gives no patch.
    ``existing_image_slots`` as in ``patches_from_content``.
    """
    values: dict[str, Any] = {}
    for name in fields:
        if name in _NOT_RESTORABLE:
            continue
        if name in _TEXT_ATTRIBUTES:
            values[name] = getattr(baseline, name)
        elif name == "bullets":
            values[name] = list(baseline.bullets)
        elif name == "images":
            values[name] = [image.url for image in baseline.images]
        elif name.startswith(_ATTRIBUTE_PREFIX):
            values[name] = baseline.attributes.get(name[len(_ATTRIBUTE_PREFIX) :])
        else:
            raise ValueError(f"cannot restore field {name!r}")
    return patches_from_content(values, baseline.marketplace_id, existing_image_slots)


def variation_patches(parent_sku: str, theme: Optional[str], marketplace_id: str) -> list[dict]:
    """Attach a child SKU to its parent SKU (the theme is left out when unknown)."""
    patches = [
        _replace("parentage_level", [{"marketplace_id": marketplace_id, "value": "child"}]),
        _replace(
            "child_parent_sku_relationship",
            [
                {
                    "marketplace_id": marketplace_id,
                    "child_relationship_type": "variation",
                    "parent_sku": parent_sku,
                }
            ],
        ),
    ]
    if theme:
        patches.append(_replace("variation_theme", [{"name": theme}]))
    return patches


# ---- requests ----


@dataclass
class ChangeItem:
    """One proposed write, before it becomes a ``CatalogChangeRequest``."""

    asin: Optional[str]
    sku: Optional[str]
    product_type: Optional[str]
    kind: str  # bulk_update|content_restore|variation_restore|new_item
    operation: Literal["PATCH", "PUT"] = "PATCH"
    patches: list[dict] = field(default_factory=list)
    attributes: Optional[dict] = None  # PUT only
    summary: dict = field(default_factory=dict)  # before/after shown to the operator
    # Anomalies this request restores: marked restore_requested and linked on create;
    # the next scan resolves them once live content matches the baseline again.
    anomalies: list[CatalogAnomaly] = field(default_factory=list)


def is_file_only(request: CatalogChangeRequest) -> bool:
    """True when the request can only travel as a feed file, never through the API."""
    return request.status == "file_only" or bool((request.payload or {}).get("file_only"))


def can_approve(request: CatalogChangeRequest) -> bool:
    """Valid and file-only requests can be approved."""
    return request.status in _APPROVABLE


def can_reject(request: CatalogChangeRequest) -> bool:
    """Anything not yet sent to Amazon can be rejected."""
    return request.status in _REJECTABLE


def passed_validation(request: CatalogChangeRequest) -> bool:
    """Amazon checked the request with VALIDATION_PREVIEW and found no error."""
    issues = request.validation_issues
    return isinstance(issues, list) and not _has_error(issues)


@dataclass
class ListingsFeed:
    document: dict  # JSON_LISTINGS_FEED body: upload as is, or offer as a download
    message_ids: dict[UUID, int]  # request id -> messageId
    skipped: dict[UUID, str]  # request id -> "no_sku" | "no_product_type"
    marketplace_id: str  # the marketplace the feed must be created for


def build_listings_feed(
    requests: Iterable[CatalogChangeRequest], seller_id: str, marketplace_id: str
) -> ListingsFeed:
    """One JSON_LISTINGS_FEED message per request; a message needs a SKU and a product type."""
    messages: list[dict] = []
    message_ids: dict[UUID, int] = {}
    skipped: dict[UUID, str] = {}
    for request in requests:
        if not _clean(request.sku):
            skipped[request.id] = "no_sku"
            continue
        if not _clean(request.product_type):
            skipped[request.id] = "no_product_type"
            continue
        payload = request.payload or {}
        put = request.operation == "PUT"
        message: dict[str, Any] = {
            "messageId": len(messages) + 1,
            "sku": request.sku,
            "operationType": "UPDATE" if put else "PATCH",
            "productType": request.product_type,
        }
        if put:
            message["attributes"] = payload.get("attributes") or {}
        else:
            message["patches"] = list(payload.get("patches") or [])
        messages.append(message)
        message_ids[request.id] = message["messageId"]
    document = {
        "header": {"sellerId": seller_id, "version": "2.0", "issueLocale": FEED_ISSUE_LOCALE},
        "messages": messages,
    }
    return ListingsFeed(document, message_ids, skipped, marketplace_id)


# ---- issues ----


def _issue(code: str, message: str) -> dict:
    return {"code": code, "message": message, "severity": "ERROR"}


def _no_listing_access() -> dict:
    return _issue("NO_LISTING_ACCESS", "No seller id or vendor code for Listings Items")


def _api_error(exc: Exception) -> dict:
    return _issue("API_ERROR", (str(exc) or type(exc).__name__)[:500])


def _issues(response: dict) -> list[dict]:
    return [dict(i) for i in response.get("issues") or [] if isinstance(i, dict)]


def _has_error(issues: list[dict]) -> bool:
    return any(str(i.get("severity") or "").upper() == "ERROR" for i in issues)


def _message_key(value: Any) -> Any:
    try:
        return int(value)
    except (TypeError, ValueError):
        return value


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _send(client: Any, seller_id: str, request: CatalogChangeRequest, mode: Optional[str]) -> dict:
    if not _clean(request.sku):
        raise ValueError("The request has no SKU")
    if not _clean(request.product_type):
        raise ValueError("The request has no product type")
    payload = request.payload or {}
    if request.operation == "PUT":
        response = client.put_listing(
            seller_id, request.sku, request.product_type, payload.get("attributes") or {}, mode=mode
        )
    else:
        response = client.patch_listing(
            seller_id, request.sku, request.product_type, list(payload.get("patches") or []),
            mode=mode,
        )
    return response or {}


def _is_not_found(exc: Exception) -> bool:
    """Amazon's 404 for a listing (SP-API client: error_code 404; fixtures: NOT_FOUND)."""
    return isinstance(exc, AmazonAPIError) and str(exc.error_code) in _NOT_FOUND_CODES


def existing_listing_issue(client: Any, seller_id: str, sku: str) -> Optional[dict]:
    """None when the SKU has no listing yet; otherwise the ERROR issue that stops a PUT.

    A PUT replaces the whole listing, so a new item may only go out for a SKU
    Amazon answers 404 for. A live listing is ``SKU_EXISTS``; any other answer
    (an error, an empty payload) is ``SKU_CHECK_FAILED``: when in doubt, nothing
    is replaced.
    """
    try:
        listing = client.get_listing(seller_id, sku)
    except Exception as exc:  # noqa: BLE001 - only a 404 lets the PUT through
        if _is_not_found(exc):
            return None
        return _issue("SKU_CHECK_FAILED", f"Could not check whether SKU {sku} exists: {exc}"[:500])
    if listing:
        return _issue("SKU_EXISTS", f"SKU {sku} already has a listing: a new item would replace it")
    return _issue("SKU_CHECK_FAILED", f"Amazon did not say whether SKU {sku} exists")


def _check_item(item: ChangeItem) -> None:
    if item.kind not in KINDS:
        raise ValueError(f"unknown change kind: {item.kind!r}")
    if item.operation not in ("PATCH", "PUT"):
        raise ValueError(f"unknown operation: {item.operation!r}")
    if item.operation == "PATCH" and not item.patches:
        raise ValueError("a PATCH change needs at least one patch")
    if item.operation == "PUT" and not item.attributes:
        raise ValueError("a PUT change needs attributes")


def _check_account(account: Any, requests: list[CatalogChangeRequest]) -> None:
    if any(r.account_id != account.id for r in requests):
        raise ValueError("change requests belong to another account")


def _fail(requests: list[CatalogChangeRequest], issue: dict, now: datetime) -> None:
    for request in requests:
        request.status = "failed"
        request.submission_result = {"status": None, "issues": [issue]}
        request.submitted_at = now


class ChangeRequestService:
    def __init__(
        self,
        db,
        client_factory: ClientFactory = default_client_factory,
        repo: Optional[CatalogMonitorRepository] = None,
    ):
        self.db = db
        self.client_factory = client_factory
        self.repo = repo or CatalogMonitorRepository(db)

    async def _seller_id(self, account) -> Optional[str]:
        return listing_seller_id(account, await self.repo.capability(account.id))

    async def _client(self, account) -> Any:
        organization = await load_organization(self.db, account)
        return self.client_factory(account, organization)

    async def create(
        self,
        account,
        items: list[ChangeItem],
        user_id: Optional[UUID],
        batch_id: Optional[UUID] = None,
    ) -> list[CatalogChangeRequest]:
        """One pending (or file-only) request per item, all in one batch.

        Vendor accounts cannot delete attribute values: their ``delete`` ops are
        dropped and listed in ``summary["manual_image_removal"]``.
        """
        for item in items:
            _check_item(item)
        batch_id = batch_id or uuid.uuid4()
        seller_id = await self._seller_id(account)
        vendor = account.account_type == AccountType.VENDOR
        rows: list[CatalogChangeRequest] = []
        for item in items:
            file_only = not seller_id or not item.sku
            summary = dict(item.summary)
            if item.operation == "PUT":
                payload: dict[str, Any] = {"attributes": dict(item.attributes or {})}
            else:
                patches = list(item.patches)
                if vendor:
                    removed = [p.get("path") for p in patches if p.get("op") == "delete"]
                    patches = [p for p in patches if p.get("op") != "delete"]
                    if removed:
                        summary["manual_image_removal"] = removed
                payload = {"patches": patches}
            payload["file_only"] = file_only
            row = CatalogChangeRequest(
                id=uuid.uuid4(),
                organization_id=account.organization_id,
                account_id=account.id,
                batch_id=batch_id,
                asin=item.asin,
                sku=item.sku,
                kind=item.kind,
                operation=item.operation,
                product_type=item.product_type,
                payload=payload,
                summary=summary,
                status="file_only" if file_only else "pending",
                created_by_user_id=user_id,
            )
            self.db.add(row)
            for anomaly in item.anomalies:
                anomaly.status = "restore_requested"
                anomaly.change_request_id = row.id
            rows.append(row)
        if rows:
            await self.db.flush()
        return rows

    async def validate(self, account, requests: list[CatalogChangeRequest]) -> None:
        """Check each request with VALIDATION_PREVIEW; never raises for Amazon errors.

        ``INVALID``, any other non-success status, or any ERROR issue makes the
        request ``invalid``; WARNING issues are kept on a ``valid`` request.
        """
        todo = [r for r in requests if r.status in _VALIDATABLE and not is_file_only(r)]
        if not todo:
            return
        _check_account(account, todo)
        seller_id = await self._seller_id(account)
        client: Any = None
        client_error: Optional[dict] = None
        try:
            client = await self._client(account)
        except Exception as exc:  # noqa: BLE001 - recorded on every request
            client_error = _api_error(exc)
        for request in todo:
            if client_error is not None:
                issues, ok = [client_error], False
            else:
                issues, ok = await self._preview(client, seller_id, request)
            request.validation_issues = issues
            request.status = "valid" if ok else "invalid"
        await self.db.flush()

    async def _preview(
        self, client: Any, seller_id: Optional[str], request: CatalogChangeRequest
    ) -> tuple[list[dict], bool]:
        if not seller_id:
            return [_no_listing_access()], False
        if not _clean(request.product_type):
            return [_issue("MISSING_PRODUCT_TYPE", "The product type is unknown")], False
        if request.operation == "PUT" and _clean(request.sku):
            exists = await asyncio.to_thread(existing_listing_issue, client, seller_id, request.sku)
            if exists is not None:
                return [exists], False
        try:
            response = await asyncio.to_thread(
                _send, client, seller_id, request, VALIDATION_PREVIEW
            )
        except Exception as exc:  # noqa: BLE001 - an Amazon error is an issue
            return [_api_error(exc)], False
        issues = _issues(response)
        status = response.get("status")
        # A preview answers VALID or INVALID; anything else (ACCEPTED included) is an error.
        ok = status == "VALID" and not _has_error(issues)
        if status not in ("VALID", "INVALID") or (not ok and not _has_error(issues)):
            issues.append(_issue("UNEXPECTED_STATUS", f"Amazon answered status {status!r}"))
        return issues, ok

    async def approve(
        self, requests: list[CatalogChangeRequest], user_id: Optional[UUID], is_admin: bool
    ) -> None:
        """Approve valid and file-only requests; other statuses are left as they are."""
        if not is_admin:
            raise PermissionError("Only an admin can approve catalogue changes")
        now = _now()
        for request in requests:
            if can_approve(request):
                request.status = "approved"
                request.approved_by_user_id = user_id
                request.approved_at = now
        await self.db.flush()

    async def reject(self, requests: list[CatalogChangeRequest], user_id: Optional[UUID]) -> None:
        """Reject requests not yet sent to Amazon; who and when go in ``submission_result``."""
        now = _now()
        for request in requests:
            if can_reject(request):
                request.status = "rejected"
                request.submission_result = {
                    "rejected_by": str(user_id) if user_id else None,
                    "rejected_at": now.isoformat(),
                }
        await self.db.flush()

    async def submit(self, account, requests: list[CatalogChangeRequest]) -> None:
        """Send approved API requests that passed validation.

        Never raises for Amazon errors: they fail the request.
        """
        todo = [
            r for r in requests
            if r.status == "approved" and not is_file_only(r) and passed_validation(r)
        ]
        if not todo:
            return
        _check_account(account, todo)
        now = _now()
        seller_id = await self._seller_id(account)
        if not seller_id:
            _fail(todo, _no_listing_access(), now)
        else:
            try:
                client = await self._client(account)
            except Exception as exc:  # noqa: BLE001
                _fail(todo, _api_error(exc), now)
            else:
                sendable = await self._without_live_skus(client, seller_id, todo, now)
                if len(sendable) < settings.CATALOG_FEED_THRESHOLD:
                    await self._submit_each(client, seller_id, sendable, now)
                else:
                    await self._submit_feed(client, seller_id, account.marketplace_id, sendable, now)
        await self._update_baselines(account.id, todo)
        await self.db.flush()

    async def _update_baselines(self, account_id, requests: list[CatalogChangeRequest]) -> None:
        """Accepted changes into their baselines, in a savepoint: Amazon already applied
        them, so a failure here is logged and never undoes the submission record."""
        try:
            async with self.db.begin_nested():
                await apply_accepted_changes(self.repo, account_id, requests)
        except Exception:  # noqa: BLE001 - the next scan shows the change as an anomaly
            logger.exception("Baseline update after accepted changes failed for account %s", account_id)

    async def _without_live_skus(
        self, client: Any, seller_id: str, requests: list[CatalogChangeRequest], now: datetime
    ) -> list[CatalogChangeRequest]:
        """Fail the new items (PUT) whose SKU has a listing by now; return the others.

        Checked again at submit: a listing created by hand after validation would
        otherwise be replaced by the new item.
        """
        sendable = []
        for request in requests:
            if request.operation == "PUT" and _clean(request.sku):
                issue = await asyncio.to_thread(
                    existing_listing_issue, client, seller_id, request.sku
                )
                if issue is not None:
                    _fail([request], issue, now)
                    continue
            sendable.append(request)
        return sendable

    async def _submit_each(
        self, client: Any, seller_id: str, requests: list[CatalogChangeRequest], now: datetime
    ) -> None:
        for request in requests:
            request.submitted_at = now
            try:
                response = await asyncio.to_thread(_send, client, seller_id, request, None)
            except Exception as exc:  # noqa: BLE001 - one failure never stops the others
                _fail([request], _api_error(exc), now)
                continue
            issues = _issues(response)
            status = response.get("status")
            ok = status == "ACCEPTED" and not _has_error(issues)
            if not ok and not _has_error(issues):
                issues.append(_issue("UNEXPECTED_STATUS", f"Amazon answered status {status!r}"))
            request.submission_result = {
                "status": status,
                "submissionId": response.get("submissionId"),
                "issues": issues,
            }
            request.status = "accepted" if ok else "failed"

    async def _submit_feed(
        self,
        client: Any,
        seller_id: str,
        marketplace_id: str,
        requests: list[CatalogChangeRequest],
        now: datetime,
    ) -> None:
        feed = build_listings_feed(requests, seller_id, marketplace_id)
        for request in requests:
            reason = feed.skipped.get(request.id)
            if reason:
                _fail([request], _issue("NOT_IN_FEED", reason), now)
        included = [r for r in requests if r.id in feed.message_ids]
        if not included:
            return
        try:
            feed_id = await asyncio.to_thread(client.submit_json_listings_feed, feed.document)
        except Exception as exc:  # noqa: BLE001
            _fail(included, _api_error(exc), now)
            return
        for request in included:
            request.status = "submitted"
            request.feed_id = feed_id
            request.submission_result = {"messageId": feed.message_ids[request.id]}
            request.submitted_at = now

    async def refresh_feed(self, account, feed_id: str) -> None:
        """Settle the feed's submitted requests once Amazon has processed it.

        DONE: a request whose message has an ERROR issue fails, the others are
        accepted. FATAL or CANCELLED: all fail. Otherwise nothing changes. Amazon
        errors propagate: nothing is recorded, the caller may retry.
        """
        requests = [
            r for r in await self.repo.change_requests_for_feed(account.id, feed_id)
            if r.status == "submitted"
        ]
        if not requests:
            return
        client = await self._client(account)
        status = await asyncio.to_thread(client.get_feed_status, feed_id) or {}
        processing = status.get("processingStatus")
        if processing in _FEED_FAILED:
            issue = _issue(f"FEED_{processing}", f"Amazon ended the feed with {processing}")
            for request in requests:
                request.status = "failed"
                request.submission_result = {
                    **(request.submission_result or {}),
                    "processingStatus": processing,
                    "issues": [issue],
                }
        elif processing == "DONE" and status.get("resultFeedDocumentId"):
            report = await asyncio.to_thread(
                client.get_feed_result, status["resultFeedDocumentId"]
            ) or {}
            by_message: dict[Any, list[dict]] = defaultdict(list)
            for issue in report.get("issues") or []:
                if isinstance(issue, dict):
                    by_message[_message_key(issue.get("messageId"))].append(dict(issue))
            for request in requests:
                message_id = (request.submission_result or {}).get("messageId")
                issues = by_message.get(_message_key(message_id), [])
                request.status = "failed" if _has_error(issues) else "accepted"
                request.submission_result = {
                    "messageId": message_id,
                    "processingStatus": processing,
                    "issues": issues,
                }
            await self._update_baselines(account.id, requests)
        else:
            return
        await self.db.flush()
