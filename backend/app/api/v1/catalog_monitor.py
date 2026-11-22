"""Catalogue monitor API: listing quality, rules, keywords, scan and access check (R1),
content protection, variations and the approval queue (R2, R3).

Every route needs an authenticated user and the account must belong to the user's
organisation (404 otherwise). The admin role is needed to replace the rule overrides,
approve the live content or a file as the baseline, accept an anomaly (it rewrites the
baseline), and approve, submit, mark as uploaded by hand or refresh change requests. All database access sits in small ``_``
helpers so the sorting, filtering and summary logic stays pure.
"""
from __future__ import annotations

import asyncio
import io
import logging
import uuid as uuidlib
from collections import defaultdict
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import delete, func, or_, select

from app.api.deps import (
    AdminOrganization,
    CurrentOrganization,
    CurrentUser,
    DbSession,
    get_admin_organization,
)
from app.models.amazon_account import AmazonAccount
from app.models.catalog_monitor import (
    CatalogAnomaly,
    CatalogApiCapability,
    CatalogChangeRequest,
    ListingContentBaseline,
    ListingQualityRule,
    VariationFamilyBaseline,
)
from app.models.listing_quality import ListingQualitySnapshot
from app.models.product import Product
from app.schemas.catalog_monitor import (
    AccountRequest,
    AnomalyOut,
    AnomalyRestoreRequest,
    BaselineUploadResponse,
    BaselinesRequest,
    BaselinesResponse,
    BaselineStatusResponse,
    BulkUploadResponse,
    CapabilityResponse,
    ChangeActionResponse,
    ChangeBatchResponse,
    ChangeIdsRequest,
    ChangeRequestOut,
    HistoryVersionOut,
    KeywordItem,
    KeywordsUpdateRequest,
    KeywordsUpdateResponse,
    QualityItem,
    QualityItemDetail,
    QualityResponse,
    QualitySummary,
    RefreshFeedRequest,
    RuleConfigOut,
    RuleOverrideIn,
    RuleOverrideOut,
    RulesResponse,
    RowErrorOut,
    RulesUpdateRequest,
    ScanStartResponse,
    ScanStateResponse,
    VariationOut,
    VariationRestoreRequest,
)
from app.services.catalog_monitor.baselines import (
    accept_anomaly,
    approve_live_as_baseline,
    import_baseline_rows,
)
from app.services.catalog_monitor.bulk_io import (
    CatalogExportWriter,
    ParsedRow,
    build_new_item_template,
    export_attribute_names,
    parse_new_items,
    parse_upload,
    row_to_change_item,
    upload_errors,
    validate_new_item,
    wrap_new_item_attributes,
)
from app.services.catalog_monitor.capabilities import check_account_capabilities, listing_seller_id
from app.services.catalog_monitor.clients import default_client_factory, load_organization
from app.services.catalog_monitor.changes import (
    ChangeItem,
    ChangeRequestService,
    build_listings_feed,
    can_approve,
    can_reject,
    is_file_only,
    passed_validation,
    restore_patches,
    variation_patches,
)
from app.services.catalog_monitor.content import content_from_dict
from app.services.catalog_monitor.diff import diff_content
from app.services.catalog_monitor.ptd import ProductTypeDefinitionService
from app.services.catalog_monitor.repository import CatalogMonitorRepository
from app.services.catalog_monitor.rules import DEFAULT_RULES, RULE_KEYS
from app.services.catalog_monitor.scanner import scan_state, start_account_scan

logger = logging.getLogger(__name__)

router = APIRouter()

# The quality list summarises, filters and sorts in memory: it loads one light row
# (no ORM entities) per active product of the account on every request. That is fine
# for catalogues of a few thousand ASINs; above this size move it into SQL.
LARGE_CATALOG_ROWS = 10_000

_STATE_ORDER = {"red": 0, "yellow": 1, "grey": 2, "green": 3}
_STATES = ("green", "yellow", "red", "grey")


# ---- pure helpers ----


def split_scanned(rows: list[dict]) -> tuple[list[dict], int]:
    """Turn product+snapshot rows into quality items; count products with no snapshot."""
    items: list[dict] = []
    unscanned = 0
    for row in rows:
        comp = row.get("components")
        # Legacy snapshots ({component: {earned, max}}) have no "results": not scanned.
        if (
            not isinstance(comp, dict)
            or row.get("score") is None
            or not isinstance(comp.get("results"), list)
        ):
            unscanned += 1
            continue
        results = comp["results"]
        items.append({
            "asin": row["asin"],
            "sku": row.get("sku"),
            "title": row.get("title"),
            "state": comp.get("state") or "grey",
            "score": int(row["score"]),
            "results": results,
        })
    return items, unscanned


def summarize(items: list[dict]) -> dict:
    summary: dict[str, Any] = {s: 0 for s in _STATES}
    per_rule: dict[str, dict[str, int]] = {}
    for item in items:
        if item["state"] in summary:
            summary[item["state"]] += 1
        for r in item["results"]:
            bucket = per_rule.setdefault(r["key"], {})
            bucket[r["state"]] = bucket.get(r["state"], 0) + 1
    summary["per_rule"] = per_rule
    return summary


def filter_items(
    items: list[dict],
    state: Optional[str] = None,
    rule: Optional[str] = None,
    mandatory_only: bool = False,
) -> list[dict]:
    """``state`` alone filters the overall state; with ``rule`` it filters that rule's state;
    ``rule`` alone keeps the items whose result for that rule is not green.

    ``mandatory_only`` trims each item's results to mandatory rules; the state is not recomputed.
    """
    out = []
    for item in items:
        if state and rule:
            if not any(r["key"] == rule and r["state"] == state for r in item["results"]):
                continue
        elif rule:
            if not any(r["key"] == rule and r["state"] != "green" for r in item["results"]):
                continue
        elif state and item["state"] != state:
            continue
        if mandatory_only:
            item = {**item, "results": [r for r in item["results"] if r["mandatory"]]}
        out.append(item)
    return out


def sort_items(items: list[dict]) -> list[dict]:
    return sorted(items, key=lambda i: (_STATE_ORDER.get(i["state"], 2), i["score"], i["asin"]))


def _param_type_ok(default: Any, value: Any) -> bool:
    if isinstance(default, bool):
        return isinstance(value, bool)
    if isinstance(default, int):
        return isinstance(value, int) and not isinstance(value, bool)
    if isinstance(default, float):
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if isinstance(default, list):
        return isinstance(value, list) and all(isinstance(v, str) for v in value)
    return isinstance(value, type(default))


def validate_overrides(overrides: list[RuleOverrideIn]) -> None:
    seen: set[tuple] = set()
    for o in overrides:
        if o.rule_key not in RULE_KEYS:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Unknown rule: {o.rule_key}")
        unknown = set(o.params or {}) - set(DEFAULT_RULES[o.rule_key].params)
        if unknown:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                f"Unknown params for {o.rule_key}: {', '.join(sorted(unknown))}",
            )
        for name, value in (o.params or {}).items():
            if not _param_type_ok(DEFAULT_RULES[o.rule_key].params[name], value):
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    f"Invalid value for {o.rule_key}.{name}",
                )
        scope = (o.marketplace_id or "", o.product_type or "", o.rule_key)
        if scope in seen:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, f"Duplicate override for {o.rule_key}"
            )
        seen.add(scope)


def apply_keywords(products: dict[str, Any], items: list[KeywordItem]) -> tuple[int, list[str]]:
    updated, unknown = 0, []
    for it in items:
        product = products.get(it.asin)
        if product is None:
            unknown.append(it.asin)
            continue
        keyword = it.keyword.strip()
        product.main_keyword = keyword or None
        product.main_keyword_source = "manual" if keyword else None
        updated += 1
    return updated, unknown


def _main_image_from_content(content: Optional[dict]) -> Optional[str]:
    for img in (content or {}).get("images") or []:
        if img.get("variant") == "MAIN" and img.get("url"):
            return img["url"]
    return None


def _as_datetime(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value


def _last_scan_at(rows: list[dict], finished_at: Optional[str]) -> Optional[datetime]:
    candidates = [_as_datetime(r.get("created_at")) for r in rows]
    candidates.append(_as_datetime(finished_at))
    present = [c for c in candidates if c is not None]
    return max(present) if present else None


# ---- data access ----


async def _account_or_404(db, organization_id: UUID, account_id: UUID) -> AmazonAccount:
    account = (
        await db.execute(
            select(AmazonAccount).where(
                AmazonAccount.id == account_id,
                AmazonAccount.organization_id == organization_id,
            )
        )
    ).scalar_one_or_none()
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    return account


async def _load_quality_rows(
    db, account_id: UUID, search: Optional[str] = None, asin: Optional[str] = None
) -> list[dict]:
    """Active products with their latest snapshot (``components`` None when never scanned)."""
    latest = (
        select(
            ListingQualitySnapshot.asin.label("asin"),
            func.max(ListingQualitySnapshot.snapshot_date).label("day"),
        )
        .where(ListingQualitySnapshot.account_id == account_id)
        .group_by(ListingQualitySnapshot.asin)
        .subquery()
    )
    stmt = (
        select(
            Product.asin,
            Product.sku,
            Product.title,
            Product.main_keyword,
            Product.main_keyword_source,
            ListingQualitySnapshot.score,
            ListingQualitySnapshot.components,
            ListingQualitySnapshot.created_at,
        )
        .select_from(Product)
        .outerjoin(latest, latest.c.asin == Product.asin)
        .outerjoin(
            ListingQualitySnapshot,
            (ListingQualitySnapshot.account_id == account_id)
            & (ListingQualitySnapshot.asin == latest.c.asin)
            & (ListingQualitySnapshot.snapshot_date == latest.c.day),
        )
        .where(Product.account_id == account_id, Product.is_active.is_(True))
    )
    if asin:
        stmt = stmt.where(Product.asin == asin)
    if search:
        like = f"%{search.strip()}%"
        stmt = stmt.where(
            or_(Product.asin.ilike(like), Product.sku.ilike(like), Product.title.ilike(like))
        )
    rows = [dict(r._mapping) for r in (await db.execute(stmt)).all()]
    if len(rows) > LARGE_CATALOG_ROWS:
        logger.warning(
            "Quality list for account %s loads %d rows in memory (limit %d)",
            account_id,
            len(rows),
            LARGE_CATALOG_ROWS,
        )
    return rows


async def _main_images(db, account_id: UUID, asins: list[str]) -> dict[str, Optional[str]]:
    versions = await CatalogMonitorRepository(db).latest_versions(account_id, asins)
    return {a: _main_image_from_content(v.content) for a, v in versions.items()}


async def _latest_content(db, account_id: UUID, asin: str) -> Optional[dict]:
    version = (await CatalogMonitorRepository(db).latest_versions(account_id, [asin])).get(asin)
    return version.content if version is not None else None


async def _rule_overrides(db, organization_id: UUID) -> list[ListingQualityRule]:
    return await CatalogMonitorRepository(db).rule_overrides(organization_id)


async def _replace_overrides(
    db, organization_id: UUID, user_id: UUID, overrides: list[RuleOverrideIn]
) -> None:
    await db.execute(
        delete(ListingQualityRule).where(ListingQualityRule.organization_id == organization_id)
    )
    for o in overrides:
        db.add(
            ListingQualityRule(
                organization_id=organization_id,
                marketplace_id=o.marketplace_id or None,
                product_type=o.product_type or None,
                rule_key=o.rule_key,
                enabled=o.enabled,
                mandatory=o.mandatory,
                params=o.params or None,
                updated_by_user_id=user_id,
            )
        )
    await db.flush()


async def _products_by_asin(db, account_id: UUID, asins: list[str]) -> dict[str, Product]:
    result = await db.execute(
        select(Product).where(Product.account_id == account_id, Product.asin.in_(asins))
    )
    return {p.asin: p for p in result.scalars()}


async def _stored_capability(db, account_id: UUID) -> Optional[CatalogApiCapability]:
    return await CatalogMonitorRepository(db).capability(account_id)


def _capability_out(row: CatalogApiCapability) -> CapabilityResponse:
    return CapabilityResponse(
        account_id=row.account_id,
        results=row.results,
        vendor_code=row.vendor_code,
        checked_at=row.checked_at,
    )


# ---- listing quality ----


@router.get("/quality", response_model=QualityResponse)
async def get_quality(
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
    account_id: UUID,
    state: Optional[str] = Query(default=None, pattern="^(green|yellow|red|grey)$"),
    rule: Optional[str] = None,
    mandatory_only: bool = False,
    search: Optional[str] = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
):
    """Latest quality per ASIN, worst first. The summary covers the search, not the filters."""
    await _account_or_404(db, organization.id, account_id)
    rows = await _load_quality_rows(db, account_id, search=search)
    items, unscanned = split_scanned(rows)
    summary = summarize(items)
    selected = sort_items(filter_items(items, state, rule, mandatory_only))
    start = (page - 1) * page_size
    page_items = selected[start : start + page_size]
    images = await _main_images(db, account_id, [i["asin"] for i in page_items])
    for item in page_items:
        item["main_image_url"] = images.get(item["asin"])
    return QualityResponse(
        summary=QualitySummary(**summary),
        items=[QualityItem(**i) for i in page_items],
        total=len(selected),
        unscanned=unscanned,
        page=page,
        page_size=page_size,
        last_scan_at=_last_scan_at(rows, scan_state(account_id).get("finished_at")),
    )


@router.get("/quality/export")
async def export_quality(
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
    account_id: UUID,
):
    """One row per ASIN: overall state and score, then state and code for every rule."""
    from openpyxl import Workbook
    from openpyxl.styles import Font

    await _account_or_404(db, organization.id, account_id)
    items, _ = split_scanned(await _load_quality_rows(db, account_id))
    wb = Workbook()
    ws = wb.active
    ws.title = "quality"
    header = ["asin", "sku", "title", "state", "score"]
    for key in RULE_KEYS:
        header += [f"{key}_state", f"{key}_code"]
    ws.append(header)
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for item in sort_items(items):
        by_key = {r["key"]: r for r in item["results"]}
        row = [item["asin"], item["sku"], item["title"], item["state"], item["score"]]
        for key in RULE_KEYS:
            r = by_key.get(key)
            row += [r["state"], r["code"]] if r else [None, None]
        ws.append(row)
    ws.freeze_panes = "A2"
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="listing_quality.xlsx"'},
    )


@router.get("/quality/{asin}", response_model=QualityItemDetail)
async def get_quality_detail(
    asin: str,
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
    account_id: UUID,
):
    await _account_or_404(db, organization.id, account_id)
    row = next(
        (r for r in await _load_quality_rows(db, account_id, asin=asin) if r["asin"] == asin), None
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ASIN not found")
    items, _ = split_scanned([row])
    base = items[0] if items else {
        "asin": asin, "sku": row.get("sku"), "title": row.get("title"),
        "state": "grey", "score": 0, "results": [],
    }
    content = await _latest_content(db, account_id, asin)
    image = _main_image_from_content(content)
    if image is None:
        image = (await _main_images(db, account_id, [asin])).get(asin)
    return QualityItemDetail(
        **base,
        main_image_url=image,
        content=content,
        main_keyword=row.get("main_keyword"),
        main_keyword_source=row.get("main_keyword_source"),
    )


# ---- rules ----


@router.get("/rules", response_model=RulesResponse)
async def get_rules(current_user: CurrentUser, organization: CurrentOrganization, db: DbSession):
    overrides = await _rule_overrides(db, organization.id)
    return RulesResponse(
        defaults={k: RuleConfigOut(**asdict(v)) for k, v in DEFAULT_RULES.items()},
        overrides=[RuleOverrideOut.model_validate(o) for o in overrides],
    )


@router.put("/rules", response_model=RulesResponse)
async def put_rules(
    body: RulesUpdateRequest,
    current_user: CurrentUser,
    organization: AdminOrganization,
    db: DbSession,
):
    """Replace every override of the organisation in a single transaction."""
    validate_overrides(body.overrides)
    await _replace_overrides(db, organization.id, current_user.id, body.overrides)
    await db.commit()
    return await get_rules(current_user, organization, db)


# ---- keywords ----


@router.put("/keywords", response_model=KeywordsUpdateResponse)
async def put_keywords(
    body: KeywordsUpdateRequest,
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
):
    await _account_or_404(db, organization.id, body.account_id)
    products = await _products_by_asin(db, body.account_id, [i.asin for i in body.items])
    updated, unknown = apply_keywords(products, body.items)
    await db.commit()
    return KeywordsUpdateResponse(updated=updated, unknown=unknown)


# ---- scan ----


@router.post("/scan", response_model=ScanStartResponse)
async def start_scan(
    body: AccountRequest,
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
):
    await _account_or_404(db, organization.id, body.account_id)
    return ScanStartResponse(started=start_account_scan(body.account_id))


@router.get("/scan", response_model=ScanStateResponse)
async def get_scan(
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
    account_id: UUID,
):
    await _account_or_404(db, organization.id, account_id)
    return ScanStateResponse(**scan_state(account_id))


# ---- capabilities ----


@router.get("/capabilities", response_model=Optional[CapabilityResponse])
async def get_capabilities(
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
    account_id: UUID,
):
    await _account_or_404(db, organization.id, account_id)
    row = await _stored_capability(db, account_id)
    return _capability_out(row) if row is not None else None


@router.post("/capabilities/check", response_model=CapabilityResponse)
async def check_capabilities(
    body: AccountRequest,
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
):
    account = await _account_or_404(db, organization.id, body.account_id)
    row = await check_account_capabilities(db, account)
    await db.commit()
    return _capability_out(row)


# ---- content protection, variations and approvals (R2, R3) ----

_OPEN_STATUSES = ("open", "acknowledged", "restore_requested")
_RESTORABLE_STATUSES = frozenset({"open", "acknowledged"})
_VARIATION_KINDS = ("child_detached", "unexpected_child", "family_broken", "theme_changed")
_DEAD_RESTORE_STATUSES = frozenset({"rejected", "invalid", "failed"})
# A restore is in progress only while its request can still go out. Once it was
# sent (accepted, submitted) or ended (failed, rejected, invalid), an anomaly still
# marked restore_requested can be accepted or restored again: otherwise a change
# Amazon accepted but the scan still sees would stay stuck.
_LIVE_REQUEST_STATUSES = frozenset({"pending", "valid", "file_only", "approved"})
_MAX_REQUESTS = 500


def _is_empty(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return value == 0
    return value is None or value == "" or value == []


def anomaly_change(kind: str, baseline: Any, live: Any) -> Optional[str]:
    """How a content field changed, by the rule of ``diff_content`` on the stored values.

    missing: the live value is gone (empty text or list, no A+ module); reordered: a
    list of texts (bullets, image URLs) with the same items; otherwise modified.
    Variation anomalies have no change type.
    """
    if kind != "content_changed":
        return None
    if _is_empty(live):
        return "missing"
    if (
        isinstance(baseline, list)
        and isinstance(live, list)
        and all(isinstance(v, str) for v in [*baseline, *live])
        and sorted(baseline) == sorted(live)
    ):
        return "reordered"
    return "modified"


def restore_in_progress(anomaly: Any, request_status: Optional[str]) -> bool:
    """The anomaly waits for a restore request that can still go out."""
    return anomaly.status == "restore_requested" and request_status in _LIVE_REQUEST_STATUSES


def can_restore_again(anomaly: Any, request_status: Optional[str]) -> bool:
    """Open, acknowledged, or restore_requested with a request already sent or ended."""
    if anomaly.status in _RESTORABLE_STATUSES:
        return True
    return anomaly.status == "restore_requested" and not restore_in_progress(
        anomaly, request_status
    )


def anomaly_out(
    anomaly: Any, title: Optional[str] = None, request_status: Optional[str] = None
) -> AnomalyOut:
    return AnomalyOut(
        id=anomaly.id,
        account_id=anomaly.account_id,
        asin=anomaly.asin,
        title=title,
        kind=anomaly.kind,
        field=anomaly.field,
        change=anomaly_change(anomaly.kind, anomaly.baseline_value, anomaly.live_value),
        status=anomaly.status,
        baseline_value=anomaly.baseline_value,
        live_value=anomaly.live_value,
        detected_at=anomaly.detected_at,
        last_seen_at=anomaly.last_seen_at,
        change_request_id=anomaly.change_request_id,
        change_request_status=request_status,
    )


def request_out(row: Any) -> ChangeRequestOut:
    return ChangeRequestOut(
        id=row.id,
        account_id=row.account_id,
        batch_id=row.batch_id,
        asin=row.asin,
        sku=row.sku,
        kind=row.kind,
        operation=row.operation,
        product_type=row.product_type,
        status=row.status,
        file_only=is_file_only(row),
        summary=row.summary,
        validation_issues=row.validation_issues,
        submission_result=row.submission_result,
        feed_id=row.feed_id,
        created_at=row.created_at,
        approved_at=row.approved_at,
        submitted_at=row.submitted_at,
    )


def existing_image_slots(content: Optional[dict]) -> int:
    """Highest filled other-image slot of the live content (PT01..PT08 -> 1..8, none -> 0)."""
    numbers = [
        int(variant[2:])
        for image in (content or {}).get("images") or []
        for variant in [str(image.get("variant") or "")]
        if image.get("url") and variant.startswith("PT") and variant[2:].isdigit()
    ]
    return min(max(numbers, default=0), 8)


def _notice(anomaly: Any, reason: str) -> dict:
    return {"anomaly_id": anomaly.id, "asin": anomaly.asin, "field": anomaly.field, "reason": reason}


def build_restore_items(
    anomalies: list[Any],
    baselines: dict[str, Any],
    versions: dict[str, dict],
    skus: dict[str, str],
) -> tuple[list[ChangeItem], list[dict], list[dict]]:
    """One ``content_restore`` item per ASIN from content_changed anomalies.

    ``baselines`` maps ASIN to a row with ``content``; ``versions`` maps ASIN to its latest
    live content dict (product type and SKU); ``skus`` is the Product.sku fallback.
    A+ fields are listed as ``not_restorable`` (they cannot be written through Listings
    Items); an ASIN without a baseline or with nothing left to write is ``skipped``.
    """
    by_asin: dict[str, list[Any]] = defaultdict(list)
    for anomaly in anomalies:
        by_asin[anomaly.asin].append(anomaly)
    items: list[ChangeItem] = []
    not_restorable: list[dict] = []
    skipped: list[dict] = []
    for asin, group in by_asin.items():
        restorable = [a for a in group if a.field != "aplus"]
        not_restorable += [_notice(a, "not_restorable") for a in group if a.field == "aplus"]
        if not restorable:
            continue
        row = baselines.get(asin)
        if row is None:
            skipped += [_notice(a, "no_baseline") for a in restorable]
            continue
        baseline = content_from_dict(row.content)
        live = versions.get(asin) or {}
        patches = restore_patches(
            baseline, [a.field for a in restorable], existing_image_slots(live)
        )
        if not patches:
            skipped += [_notice(a, "nothing_to_restore") for a in restorable]
            continue
        items.append(
            ChangeItem(
                asin=asin,
                sku=live.get("sku") or skus.get(asin),
                product_type=live.get("product_type"),
                kind="content_restore",
                patches=patches,
                summary={
                    "fields": [a.field for a in restorable],
                    "changes": [
                        {"field": a.field, "from": a.live_value, "to": a.baseline_value}
                        for a in restorable
                    ],
                },
                anomalies=restorable,
            )
        )
    return items, not_restorable, skipped


def build_variation_items(
    parent_asin: str,
    theme: Optional[str],
    marketplace_id: str,
    parent_sku: Optional[str],
    children: list[tuple[str, Optional[str], Optional[str]]],
    anomalies_by_child: dict[str, list[Any]],
) -> tuple[list[ChangeItem], bool]:
    """One ``variation_restore`` item per child (asin, sku, product type).

    Returns the items and whether the parent has no SKU: such a request cannot be
    written through the API, the caller makes it a file-only request.
    """
    patches = variation_patches(parent_sku or parent_asin, theme, marketplace_id)
    items = [
        ChangeItem(
            asin=asin,
            sku=sku,
            product_type=product_type,
            kind="variation_restore",
            patches=[dict(p) for p in patches],
            summary={
                "parent_asin": parent_asin,
                "parent_sku": parent_sku,
                "variation_theme": theme,
                "parent_sku_missing": parent_sku is None,
            },
            anomalies=list(anomalies_by_child.get(asin, [])),
        )
        for asin, sku, product_type in children
    ]
    return items, parent_sku is None


def _family_of(anomaly: Any) -> Optional[str]:
    return anomaly.field.split(":", 1)[1] if ":" in anomaly.field else None


def build_variations(families: list[Any], anomalies: list[Any], known_asins: set[str]) -> list[dict]:
    """Families with their status and child states, from the non-resolved anomalies.

    broken: a family_broken anomaly; partial: a child_detached or unexpected_child one; else ok.
    A child with no live content yet is ``unknown``.
    """
    active = [a for a in anomalies if a.status != "resolved"]
    out = []
    for family in families:
        mine = [a for a in active if _family_of(a) == family.parent_asin]
        detached = {a.asin for a in mine if a.kind == "child_detached"}
        unexpected = sorted({a.asin for a in mine if a.kind == "unexpected_child"})
        children = []
        for asin in [*list(family.child_asins or []), *unexpected]:
            if asin in detached:
                state = "detached"
            elif asin in unexpected:
                state = "unexpected"
            elif asin not in known_asins:
                state = "unknown"
            else:
                state = "ok"
            children.append({"asin": asin, "state": state})
        if any(a.kind == "family_broken" for a in mine):
            family_status = "broken"
        elif detached or unexpected:
            family_status = "partial"
        else:
            family_status = "ok"
        out.append({
            "parent_asin": family.parent_asin,
            "variation_theme": family.variation_theme,
            "status": family_status,
            "children": children,
            "anomaly_ids": [a.id for a in mine],
        })
    return out


def build_history(versions: list[Any]) -> list[dict]:
    """Versions newest first, each with the changes against the next older version."""
    out = []
    for index, version in enumerate(versions):
        changes: list[dict] = []
        if index + 1 < len(versions):
            older = content_from_dict(versions[index + 1].content)
            changes = [asdict(c) for c in diff_content(older, content_from_dict(version.content))]
        out.append({
            "id": version.id,
            "content_hash": version.content_hash,
            "first_seen_at": version.first_seen_at,
            "last_seen_at": version.last_seen_at,
            "changes": changes,
        })
    return out


def reopen_anomalies(anomalies: list[Any]) -> None:
    """A restore that will not happen: its anomalies are open again, unlinked."""
    for anomaly in anomalies:
        if anomaly.status == "restore_requested":
            anomaly.status = "open"
            anomaly.change_request_id = None


def approve_skip_reason(row: Any) -> Optional[str]:
    return None if can_approve(row) else f"status_{row.status}"


def reject_skip_reason(row: Any) -> Optional[str]:
    return None if can_reject(row) else f"status_{row.status}"


def submit_skip_reason(row: Any) -> Optional[str]:
    if row.status != "approved":
        return f"status_{row.status}"
    if is_file_only(row):
        return "file_only"
    return None if passed_validation(row) else "not_validated"


def parent_sku_missing(row: Any) -> bool:
    return bool((row.summary or {}).get("parent_sku_missing"))


def in_feed_file(row: Any) -> bool:
    """What the Vendor Central file may hold: approved file-only requests.

    API requests travel through Amazon's check and the API, never as a file; a
    file-only request waits for an admin's approval like any other. A request
    whose parent SKU is unknown is eligible but left out (``download_feed_file``).
    """
    return row.status == "approved" and is_file_only(row)


def mark_uploaded_skip_reason(row: Any) -> Optional[str]:
    if row.status != "approved":
        return f"status_{row.status}"
    if not is_file_only(row):
        return "not_file_only"
    return "not_in_file" if parent_sku_missing(row) else None


def mark_uploaded(rows: list[Any], user_id: Any, now: datetime) -> None:
    """Approved file-only requests the operator uploaded by hand: submitted, by whom and when."""
    for row in rows:
        row.status = "submitted"
        row.submitted_at = now
        row.submission_result = {
            "manual": True,
            "by": str(user_id) if user_id else None,
            "at": now.isoformat(),
        }


def _split_by_reason(rows: list[Any], reason_of) -> tuple[list[Any], dict[str, str]]:
    todo, skipped = [], {}
    for row in rows:
        reason = reason_of(row)
        if reason:
            skipped[str(row.id)] = reason
        else:
            todo.append(row)
    return todo, skipped


# ---- data access ----


async def _anomalies_by_ids(
    db, organization_id: UUID, ids: list[UUID], lock: bool = False
) -> list[CatalogAnomaly]:
    stmt = (
        select(CatalogAnomaly)
        .join(AmazonAccount, AmazonAccount.id == CatalogAnomaly.account_id)
        .where(AmazonAccount.organization_id == organization_id, CatalogAnomaly.id.in_(ids))
        .order_by(CatalogAnomaly.asin, CatalogAnomaly.field, CatalogAnomaly.id)
    )
    if lock:
        stmt = stmt.with_for_update(of=CatalogAnomaly)
    return list((await db.execute(stmt)).scalars().all())


async def _request_statuses(db, ids: list[UUID]) -> dict[UUID, str]:
    """Status of each change request id (unknown ids are left out)."""
    if not ids:
        return {}
    result = await db.execute(
        select(CatalogChangeRequest.id, CatalogChangeRequest.status).where(
            CatalogChangeRequest.id.in_(ids)
        )
    )
    return {row[0]: row[1] for row in result.all()}


async def _linked_statuses(db, anomalies: list[Any]) -> dict[UUID, str]:
    ids = sorted({a.change_request_id for a in anomalies if a.change_request_id}, key=str)
    return await _request_statuses(db, ids) if ids else {}


async def _list_anomalies(
    db, account_id: UUID, kind: Optional[str], statuses: tuple[str, ...], search: Optional[str]
) -> list[tuple[CatalogAnomaly, Optional[str]]]:
    stmt = (
        select(CatalogAnomaly, Product.title)
        .outerjoin(
            Product,
            (Product.account_id == CatalogAnomaly.account_id) & (Product.asin == CatalogAnomaly.asin),
        )
        .where(CatalogAnomaly.account_id == account_id, CatalogAnomaly.status.in_(statuses))
        .order_by(CatalogAnomaly.detected_at.desc(), CatalogAnomaly.id)
    )
    if kind:
        stmt = stmt.where(CatalogAnomaly.kind == kind)
    if search:
        like = f"%{search.strip()}%"
        stmt = stmt.where(or_(CatalogAnomaly.asin.ilike(like), Product.title.ilike(like)))
    return [(row[0], row[1]) for row in (await db.execute(stmt)).all()]


async def _baselines(db, account_id: UUID, asins: list[str]) -> dict[str, ListingContentBaseline]:
    return await CatalogMonitorRepository(db).baselines(account_id, asins)


async def _latest_content_dicts(db, account_id: UUID, asins: list[str]) -> dict[str, dict]:
    versions = await CatalogMonitorRepository(db).latest_versions(account_id, asins)
    return {asin: v.content for asin, v in versions.items()}


async def _versions(db, account_id: UUID, asin: str) -> list[Any]:
    return await CatalogMonitorRepository(db).versions(account_id, asin)


async def _family_baselines(db, account_id: UUID) -> list[VariationFamilyBaseline]:
    return await CatalogMonitorRepository(db).family_baselines(account_id)


async def _variation_anomalies(
    db, account_id: UUID, lock: bool = False
) -> list[CatalogAnomaly]:
    stmt = (
        select(CatalogAnomaly)
        .where(
            CatalogAnomaly.account_id == account_id,
            CatalogAnomaly.kind.in_(_VARIATION_KINDS),
            CatalogAnomaly.status != "resolved",
        )
        .order_by(CatalogAnomaly.detected_at, CatalogAnomaly.id)
    )
    if lock:
        stmt = stmt.with_for_update()
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def _baseline_counts(db, account_id: UUID) -> tuple[int, int, int]:
    async def count(stmt) -> int:
        return int((await db.execute(stmt)).scalar_one())

    return (
        await count(
            select(func.count()).select_from(ListingContentBaseline).where(
                ListingContentBaseline.account_id == account_id
            )
        ),
        await count(
            select(func.count()).select_from(Product).where(
                Product.account_id == account_id, Product.is_active.is_(True)
            )
        ),
        await count(
            select(func.count()).select_from(VariationFamilyBaseline).where(
                VariationFamilyBaseline.account_id == account_id
            )
        ),
    )


async def _list_requests(
    db,
    organization_id: UUID,
    account_id: UUID,
    batch_id: Optional[UUID],
    request_status: Optional[str],
) -> list[CatalogChangeRequest]:
    stmt = select(CatalogChangeRequest).where(
        CatalogChangeRequest.organization_id == organization_id,
        CatalogChangeRequest.account_id == account_id,
    )
    if batch_id:
        stmt = stmt.where(CatalogChangeRequest.batch_id == batch_id)
    if request_status:
        stmt = stmt.where(CatalogChangeRequest.status == request_status)
    stmt = stmt.order_by(CatalogChangeRequest.created_at.desc()).limit(_MAX_REQUESTS)
    return list((await db.execute(stmt)).scalars().all())


async def _batch_requests(db, organization_id: UUID, batch_id: UUID) -> list[CatalogChangeRequest]:
    result = await db.execute(
        select(CatalogChangeRequest)
        .where(
            CatalogChangeRequest.organization_id == organization_id,
            CatalogChangeRequest.batch_id == batch_id,
        )
        .order_by(CatalogChangeRequest.created_at, CatalogChangeRequest.id)
    )
    return list(result.scalars().all())


async def _requests_for_update(
    db, organization_id: UUID, ids: list[UUID]
) -> list[CatalogChangeRequest]:
    """The organisation's requests with these ids, locked until the transaction ends.

    Ordered by id so two overlapping calls lock in the same order.
    """
    result = await db.execute(
        select(CatalogChangeRequest)
        .where(
            CatalogChangeRequest.organization_id == organization_id,
            CatalogChangeRequest.id.in_(ids),
        )
        .order_by(CatalogChangeRequest.id)
        .with_for_update()
    )
    return list(result.scalars().all())


async def _reopen_for_requests(db, requests: list[CatalogChangeRequest]) -> None:
    """Reopen the anomalies of restore requests that ended rejected, invalid or failed."""
    ids = [r.id for r in requests if r.status in _DEAD_RESTORE_STATUSES]
    if not ids:
        return
    result = await db.execute(
        select(CatalogAnomaly).where(
            CatalogAnomaly.change_request_id.in_(ids), CatalogAnomaly.status == "restore_requested"
        )
    )
    reopen_anomalies(list(result.scalars().all()))


async def _lock_requests(
    db, organization_id: UUID, ids: list[UUID]
) -> tuple[list[CatalogChangeRequest], dict[str, str]]:
    rows = await _requests_for_update(db, organization_id, list(dict.fromkeys(ids)))
    found = {r.id for r in rows}
    return rows, {str(i): "not_found" for i in dict.fromkeys(ids) if i not in found}


def _by_account(rows: list[Any]) -> dict[UUID, list[Any]]:
    groups: dict[UUID, list[Any]] = defaultdict(list)
    for row in rows:
        groups[row.account_id].append(row)
    return groups


# ---- anomalies and restore ----


@router.get("/anomalies", response_model=list[AnomalyOut])
async def list_anomalies(
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
    account_id: UUID,
    kind: Optional[str] = None,
    status_filter: Optional[str] = Query(default=None, alias="status"),
    search: Optional[str] = None,
):
    """Open, acknowledged and restore-requested anomalies unless ``status`` narrows them."""
    await _account_or_404(db, organization.id, account_id)
    statuses = (status_filter,) if status_filter else _OPEN_STATUSES
    rows = await _list_anomalies(db, account_id, kind, statuses, search)
    linked = await _linked_statuses(db, [a for a, _ in rows])
    return [anomaly_out(a, title, linked.get(a.change_request_id)) for a, title in rows]


@router.post("/anomalies/restore", response_model=ChangeBatchResponse)
async def restore_anomalies(
    body: AnomalyRestoreRequest,
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
):
    """Create and validate one restore request per ASIN from the selected content anomalies."""
    anomalies = await _anomalies_by_ids(db, organization.id, list(dict.fromkeys(body.anomaly_ids)), lock=True)
    if not anomalies:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Anomalies not found")
    if len({a.account_id for a in anomalies}) > 1:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Anomalies of one account only")
    account = await _account_or_404(db, organization.id, anomalies[0].account_id)
    linked = await _linked_statuses(db, anomalies)
    skipped: list[dict] = []
    eligible = []
    for anomaly in anomalies:
        if anomaly.kind != "content_changed":
            skipped.append(_notice(anomaly, "not_content_anomaly"))
        elif not can_restore_again(anomaly, linked.get(anomaly.change_request_id)):
            skipped.append(_notice(anomaly, f"status_{anomaly.status}"))
        else:
            eligible.append(anomaly)
    asins = sorted({a.asin for a in eligible})
    items, not_restorable, more_skipped = build_restore_items(
        eligible,
        await _baselines(db, account.id, asins),
        await _latest_content_dicts(db, account.id, asins),
        {asin: p.sku for asin, p in (await _products_by_asin(db, account.id, asins)).items() if p.sku},
    )
    skipped += more_skipped
    if not items:
        return ChangeBatchResponse(requests=[], not_restorable=not_restorable, skipped=skipped)
    service = ChangeRequestService(db)
    batch_id = uuidlib.uuid4()
    rows = await service.create(account, items, current_user.id, batch_id=batch_id)
    await service.validate(account, rows)
    await _reopen_for_requests(db, rows)
    await db.commit()
    return ChangeBatchResponse(
        batch_id=batch_id,
        requests=[request_out(r) for r in rows],
        not_restorable=not_restorable,
        skipped=skipped,
    )


@router.post("/anomalies/{anomaly_id}/accept", response_model=AnomalyOut)
async def accept_anomaly_route(
    anomaly_id: UUID,
    current_user: CurrentUser,
    organization: AdminOrganization,
    db: DbSession,
):
    """Accept the live value: the baseline follows it and the anomaly is resolved; admin only."""
    found = await _anomalies_by_ids(db, organization.id, [anomaly_id], lock=True)
    if not found:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Anomaly not found")
    anomaly = found[0]
    linked = await _linked_statuses(db, [anomaly])
    if anomaly.status == "resolved" or restore_in_progress(
        anomaly, linked.get(anomaly.change_request_id)
    ):
        raise HTTPException(status.HTTP_409_CONFLICT, f"Anomaly is {anomaly.status}")
    try:
        await accept_anomaly(
            CatalogMonitorRepository(db), anomaly, current_user.id, datetime.now(timezone.utc)
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    await db.commit()
    return anomaly_out(anomaly)


# ---- history and baselines ----


@router.get("/history/{asin}", response_model=list[HistoryVersionOut])
async def get_history(
    asin: str,
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
    account_id: UUID,
):
    await _account_or_404(db, organization.id, account_id)
    return build_history(await _versions(db, account_id, asin))


@router.get("/baselines/status", response_model=BaselineStatusResponse)
async def get_baseline_status(
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
    account_id: UUID,
):
    await _account_or_404(db, organization.id, account_id)
    with_baseline, total, families = await _baseline_counts(db, account_id)
    return BaselineStatusResponse(
        asins_with_baseline=with_baseline, asins_total=total, families=families
    )


@router.post("/baselines", response_model=BaselinesResponse)
async def approve_baselines(
    body: BaselinesRequest,
    current_user: CurrentUser,
    organization: AdminOrganization,
    db: DbSession,
):
    """Approve the latest live content as the baseline (all ASINs, or the given ones); admin only."""
    await _account_or_404(db, organization.id, body.account_id)
    count = await approve_live_as_baseline(
        CatalogMonitorRepository(db), body.account_id, body.asins, current_user.id
    )
    await db.commit()
    return BaselinesResponse(count=count)


# ---- variations ----


@router.get("/variations", response_model=list[VariationOut])
async def list_variations(
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
    account_id: UUID,
):
    await _account_or_404(db, organization.id, account_id)
    families = await _family_baselines(db, account_id)
    anomalies = await _variation_anomalies(db, account_id)
    asins = sorted(
        {f.parent_asin for f in families}
        | {c for f in families for c in f.child_asins or []}
        | {a.asin for a in anomalies}
    )
    known = set(await _latest_content_dicts(db, account_id, asins))
    return build_variations(families, anomalies, known)


@router.post("/variations/restore", response_model=ChangeBatchResponse)
async def restore_variation(
    body: VariationRestoreRequest,
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
):
    """Attach children back to their parent: one request per child, created and validated."""
    account = await _account_or_404(db, organization.id, body.account_id)
    family = next(
        (f for f in await _family_baselines(db, account.id) if f.parent_asin == body.parent_asin),
        None,
    )
    if family is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Variation family not found")
    mine = [
        a
        for a in await _variation_anomalies(db, account.id, lock=True)
        if _family_of(a) == family.parent_asin
    ]
    # Open or acknowledged anomalies can be restored, and those whose restore was
    # already sent or ended; a restore still in the queue is not repeated.
    linked = await _linked_statuses(db, mine)
    by_child: dict[str, list[Any]] = defaultdict(list)
    skipped: list[dict] = []
    pending: set[str] = set()
    for anomaly in mine:
        if anomaly.kind != "child_detached":
            continue
        if can_restore_again(anomaly, linked.get(anomaly.change_request_id)):
            by_child[anomaly.asin].append(anomaly)
        else:
            pending.add(anomaly.asin)
            skipped.append(_notice(anomaly, f"status_{anomaly.status}"))
    if body.child_asins is None:
        selected = sorted(by_child)
    else:
        unknown = set(body.child_asins) - set(family.child_asins or [])
        if unknown:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                f"Not children of {family.parent_asin}: {', '.join(sorted(unknown))}",
            )
        selected = [a for a in dict.fromkeys(body.child_asins) if a not in pending]
    if not selected:
        return ChangeBatchResponse(requests=[], skipped=skipped)
    asins = [family.parent_asin, *selected]
    contents = await _latest_content_dicts(db, account.id, asins)
    products = await _products_by_asin(db, account.id, asins)

    def sku_of(asin: str) -> Optional[str]:
        product = products.get(asin)
        return (product.sku if product is not None else None) or (contents.get(asin) or {}).get("sku")

    items, parent_missing = build_variation_items(
        family.parent_asin,
        family.variation_theme,
        account.marketplace_id,
        sku_of(family.parent_asin),
        [(asin, sku_of(asin), (contents.get(asin) or {}).get("product_type")) for asin in selected],
        by_child,
    )
    service = ChangeRequestService(db)
    batch_id = uuidlib.uuid4()
    rows = await service.create(account, items, current_user.id, batch_id=batch_id)
    if parent_missing:
        for row in rows:  # without the parent SKU the patch cannot go through the API
            row.status = "file_only"
            row.payload = {**(row.payload or {}), "file_only": True}
    await service.validate(account, rows)
    await _reopen_for_requests(db, rows)
    await db.commit()
    return ChangeBatchResponse(
        batch_id=batch_id, requests=[request_out(r) for r in rows], skipped=skipped
    )


# ---- approval queue ----


@router.get("/changes", response_model=list[ChangeRequestOut])
async def list_changes(
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
    account_id: UUID,
    batch_id: Optional[UUID] = None,
    status_filter: Optional[str] = Query(default=None, alias="status"),
):
    await _account_or_404(db, organization.id, account_id)
    rows = await _list_requests(db, organization.id, account_id, batch_id, status_filter)
    return [request_out(r) for r in rows]


@router.get("/changes/feed-file")
async def download_feed_file(
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
    batch_id: UUID,
):
    """The batch's approved file-only requests as a JSON_LISTINGS_FEED file.

    Requests the feed cannot hold (no SKU or product type, or an unknown parent
    SKU) are listed in the ``X-Skipped-Requests`` header, comma separated.
    """
    rows = [r for r in await _batch_requests(db, organization.id, batch_id) if in_feed_file(r)]
    if not rows:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No approved file-only requests in batch")
    account = await _account_or_404(db, organization.id, rows[0].account_id)
    seller_id = listing_seller_id(account, await _stored_capability(db, account.id)) or ""
    # A request whose parent SKU is unknown would upload an invalid parent SKU: never in the file.
    unusable = {r.id for r in rows if parent_sku_missing(r)}
    feed = build_listings_feed(
        [r for r in rows if r.account_id == account.id and r.id not in unusable],
        seller_id,
        account.marketplace_id,
    )
    return JSONResponse(
        feed.document,
        headers={
            "Content-Disposition": f'attachment; filename="listings-feed-{batch_id}.json"',
            "X-Skipped-Requests": ",".join(str(i) for i in [*feed.skipped, *sorted(unusable, key=str)]),
        },
    )


@router.post("/changes/approve", response_model=ChangeActionResponse)
async def approve_changes(
    body: ChangeIdsRequest,
    current_user: CurrentUser,
    organization: AdminOrganization,
    db: DbSession,
):
    rows, skipped = await _lock_requests(db, organization.id, body.ids)
    todo, reasons = _split_by_reason(rows, approve_skip_reason)
    await ChangeRequestService(db).approve(todo, current_user.id, True)
    await db.commit()
    return ChangeActionResponse(requests=[request_out(r) for r in rows], skipped={**skipped, **reasons})


@router.post("/changes/reject", response_model=ChangeActionResponse)
async def reject_changes(
    body: ChangeIdsRequest,
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
):
    rows, skipped = await _lock_requests(db, organization.id, body.ids)
    todo, reasons = _split_by_reason(rows, reject_skip_reason)
    await ChangeRequestService(db).reject(todo, current_user.id)
    await _reopen_for_requests(db, todo)
    await db.commit()
    return ChangeActionResponse(requests=[request_out(r) for r in rows], skipped={**skipped, **reasons})


@router.post("/changes/submit", response_model=ChangeActionResponse)
async def submit_changes(
    body: ChangeIdsRequest,
    current_user: CurrentUser,
    organization: AdminOrganization,
    db: DbSession,
):
    """Send approved API requests to Amazon, locked so a retry cannot send them twice."""
    rows, skipped = await _lock_requests(db, organization.id, body.ids)
    todo, reasons = _split_by_reason(rows, submit_skip_reason)
    service = ChangeRequestService(db)
    for account_id, group in _by_account(todo).items():
        account = await _account_or_404(db, organization.id, account_id)
        await service.submit(account, group)
    await _reopen_for_requests(db, todo)
    await db.commit()
    return ChangeActionResponse(requests=[request_out(r) for r in rows], skipped={**skipped, **reasons})


@router.post("/changes/mark-uploaded", response_model=ChangeActionResponse)
async def mark_uploaded_changes(
    body: ChangeIdsRequest,
    current_user: CurrentUser,
    organization: AdminOrganization,
    db: DbSession,
):
    """Approved file-only requests uploaded by hand on Vendor Central become submitted."""
    rows, skipped = await _lock_requests(db, organization.id, body.ids)
    todo, reasons = _split_by_reason(rows, mark_uploaded_skip_reason)
    mark_uploaded(todo, current_user.id, datetime.now(timezone.utc))
    await db.commit()
    return ChangeActionResponse(requests=[request_out(r) for r in rows], skipped={**skipped, **reasons})


@router.post("/changes/refresh-feed", response_model=list[ChangeRequestOut])
async def refresh_feed(
    body: RefreshFeedRequest,
    current_user: CurrentUser,
    organization: AdminOrganization,
    db: DbSession,
):
    """Settle the requests of a submitted feed from Amazon's processing report."""
    account = await _account_or_404(db, organization.id, body.account_id)
    repo = CatalogMonitorRepository(db)
    await ChangeRequestService(db, repo=repo).refresh_feed(account, body.feed_id)
    rows = await repo.change_requests_for_feed(account.id, body.feed_id)
    await _reopen_for_requests(db, rows)
    await db.commit()
    return [request_out(r) for r in rows]


# ---- bulk export, upload and new items (R4) ----

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
EXPORT_CHUNK = 200  # products whose live content is held at once while exporting
_UPLOAD_SUFFIXES = (".xlsx", ".xlsm", ".csv")
_XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_MAX_KEYWORD_LENGTH = 255
_NOT_IN_ACCOUNT = "ASIN non trovato in questo account"
_PTD_UNAVAILABLE = "Definizione del tipo di prodotto non disponibile"
_UNREADABLE_FILE = (
    "Impossibile leggere il file: caricate un file Excel (.xlsx) o CSV esportato da Catalogo."
)


def row_error(row: Any, message: str, asin: Optional[str] = None, sku: Optional[str] = None) -> RowErrorOut:
    return RowErrorOut(row=row, asin=asin, sku=sku, message=message)


def match_upload_rows(
    rows: list[ParsedRow], products: list[Any], live: Optional[dict[str, Any]] = None
) -> tuple[list[tuple[ParsedRow, Any]], list[RowErrorOut]]:
    """Rows that belong to the account (by asin, else sku), plus the errors of the others.

    A row with parse errors, an unknown product or a product already seen in the
    file is reported and skipped. Matched rows get the product's asin and sku.
    ``live`` maps ASIN to its live ``ListingContent``: cells equal to it are not
    checked against the limits, since they become no patch.
    """
    by_asin = {p.asin: p for p in products if p.asin}
    by_sku = {p.sku: p for p in products if p.sku}
    matched: list[tuple[ParsedRow, Any]] = []
    errors: list[RowErrorOut] = []
    seen: set[str] = set()
    for row in rows:
        product = by_asin.get(row.asin) if row.asin else None
        if product is None and row.sku:
            product = by_sku.get(row.sku)
        current = (live or {}).get(product.asin) if product is not None else None
        problems = upload_errors(row, current)
        keyword = row.cells.get("main_keyword") or ""
        if len(keyword) > _MAX_KEYWORD_LENGTH:
            problems.append(f"main_keyword supera {_MAX_KEYWORD_LENGTH} caratteri")
        if problems:
            errors.append(row_error(row.row_number, "; ".join(problems), row.asin, row.sku))
            continue
        if product is None:
            errors.append(row_error(row.row_number, _NOT_IN_ACCOUNT, row.asin, row.sku))
            continue
        if product.asin in seen:
            errors.append(
                row_error(row.row_number, "ASIN ripetuto nel file", product.asin, row.sku)
            )
            continue
        seen.add(product.asin)
        row.asin = product.asin
        row.sku = row.sku or product.sku
        matched.append((row, product))
    return matched, errors


def apply_main_keyword_cells(matched: list[tuple[ParsedRow, Any]]) -> int:
    """Store the ``main_keyword`` cells that differ from the product's keyword; returns how many."""
    changed = [
        KeywordItem(asin=product.asin, keyword=row.cells["main_keyword"])
        for row, product in matched
        if "main_keyword" in row.cells
        and row.cells["main_keyword"].strip() != (product.main_keyword or "")
    ]
    updated, _ = apply_keywords({p.asin: p for _, p in matched}, changed)
    return updated


async def _read_upload(file: UploadFile) -> tuple[bytes, str]:
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            "File troppo grande: il limite e' 10 MB.",
        )
    name = file.filename or ""
    if not name.lower().endswith(_UPLOAD_SUFFIXES):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Formato del file non supportato: usate .xlsx o .csv.",
        )
    return data, name


def _parse_file(parser, data: bytes, name: str):
    try:
        return parser(data, name)
    except Exception as exc:  # noqa: BLE001 - corrupt xlsx, bad encoding, odd csv: all 422
        logger.warning("Unreadable bulk upload %r: %s", name, type(exc).__name__)
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, _UNREADABLE_FILE) from exc


async def _account_products(db, account_id: UUID) -> list[Product]:
    result = await db.execute(select(Product).where(Product.account_id == account_id))
    return list(result.scalars().all())


async def _export_products(db, account_id: UUID) -> list[Any]:
    """Light rows (asin, sku, title, main_keyword) of the active products, by ASIN."""
    result = await db.execute(
        select(Product.asin, Product.sku, Product.title, Product.main_keyword)
        .where(
            Product.account_id == account_id,
            Product.is_active.is_(True),
            Product.asin.isnot(None),
        )
        .order_by(Product.asin)
    )
    return list(result.all())


async def _export_contents(db, account_id: UUID, asins: list[str]) -> dict[str, Any]:
    """Latest live content of these ASINs (one export chunk)."""
    versions = await CatalogMonitorRepository(db).latest_versions(account_id, asins)
    return {asin: content_from_dict(v.content) for asin, v in versions.items()}


async def build_catalog_export(db, account_id: UUID) -> bytes:
    """The catalogue export, ``EXPORT_CHUNK`` products at a time, built off the event loop.

    Live content (10-30 KB per ASIN) is read twice, a chunk at a time: once for
    the ``attr:`` columns the header needs, once to write the rows into a
    streamed (write-only) workbook.
    """
    products = await _export_products(db, account_id)
    chunks = [products[i : i + EXPORT_CHUNK] for i in range(0, len(products), EXPORT_CHUNK)]
    names: set[str] = set()
    for chunk in chunks:
        contents = await _export_contents(db, account_id, [p.asin for p in chunk])
        names |= export_attribute_names(contents.values())
    writer = await asyncio.to_thread(CatalogExportWriter, sorted(names))
    for chunk in chunks:
        contents = await _export_contents(db, account_id, [p.asin for p in chunk])
        await asyncio.to_thread(writer.add, [(p, contents.get(p.asin)) for p in chunk])
    return await asyncio.to_thread(writer.finish)


async def _live_skus(db, account_id: UUID) -> set[str]:
    """SKUs of the latest listing content: Product.sku can be empty (vendor, catalogue-only).

    Read in SQL: no content payload is loaded.
    """
    return await CatalogMonitorRepository(db).latest_skus(account_id)


async def _product_type_required(db, account: Any, product_type: str) -> Optional[list[str]]:
    """Required attributes of the product type for the account's marketplace; None if unknown."""
    try:
        client = default_client_factory(account, await load_organization(db, account))
        seller_id = listing_seller_id(account, await _stored_capability(db, account.id))
        return await ProductTypeDefinitionService(db).required_attributes(
            client, account.marketplace_id, product_type, seller_id
        )
    except Exception as exc:  # noqa: BLE001 - an unreachable definition is "unavailable"
        logger.warning("Product type %s definition failed: %s", product_type, type(exc).__name__)
        return None


def _xlsx_response(content: bytes, filename: str) -> StreamingResponse:
    return StreamingResponse(
        iter([content]),
        media_type=_XLSX_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/export")
async def export_catalog(
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
    account_id: UUID,
):
    """The account's catalogue as an Excel file: it is also the upload template."""
    await _account_or_404(db, organization.id, account_id)
    content = await build_catalog_export(db, account_id)
    return _xlsx_response(content, f"catalogo-{account_id}.xlsx")


@router.post("/bulk/upload", response_model=BulkUploadResponse | BaselineUploadResponse)
async def upload_bulk(
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
    account_id: UUID = Form(...),
    mode: str = Form("update"),
    file: UploadFile = File(...),
):
    """Edited export: ``update`` makes validated change requests of the changed cells,
    ``baseline`` (admin only) makes the file the approved content to protect.
    """
    if mode not in ("update", "baseline"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "mode must be update or baseline")
    if mode == "baseline":
        await get_admin_organization(current_user, db)
    account = await _account_or_404(db, organization.id, account_id)
    data, name = await _read_upload(file)
    parsed = _parse_file(parse_upload, data, name)
    products = await _account_products(db, account.id)
    skus = {row.sku for row in parsed if row.sku}
    named = {row.asin for row in parsed if row.asin} | {p.asin for p in products if p.sku in skus}
    live = {
        asin: content_from_dict(content)
        for asin, content in (
            await _latest_content_dicts(db, account.id, sorted(a for a in named if a))
        ).items()
    }
    matched, errors = match_upload_rows(parsed, products, live)
    keywords_updated = apply_main_keyword_cells(matched)

    if mode == "baseline":
        written, import_errors = await import_baseline_rows(
            CatalogMonitorRepository(db),
            account.id,
            [
                (row.asin, {k: v for k, v in row.cells.items() if k != "main_keyword"})
                for row, _ in matched
            ],
            current_user.id,
        )
        await db.commit()
        return BaselineUploadResponse(
            updated=written,
            keywords_updated=keywords_updated,
            row_errors=[*errors, *(row_error(None, message) for message in import_errors)],
        )

    items: list[ChangeItem] = []
    for row, _ in matched:
        item = row_to_change_item(row, live.get(row.asin), account.marketplace_id)
        if item is not None:
            items.append(item)
    batch_id, requests = None, []
    if items:
        service = ChangeRequestService(db)
        batch_id = uuidlib.uuid4()
        requests = await service.create(account, items, current_user.id, batch_id=batch_id)
        await service.validate(account, requests)
    await db.commit()
    return BulkUploadResponse(
        batch_id=batch_id,
        rows=len(parsed),
        changes=len(items),
        unchanged=len(matched) - len(items),
        keywords_updated=keywords_updated,
        row_errors=errors,
        requests=[request_out(r) for r in requests],
    )


@router.get("/new-items/template")
async def new_items_template(
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
    account_id: UUID,
    product_type: str = Query(min_length=1),
):
    """Empty new-item sheet for a product type: sku, product_type, required, recommended."""
    account = await _account_or_404(db, organization.id, account_id)
    required = await _product_type_required(db, account, product_type)
    if required is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, _PTD_UNAVAILABLE)
    await db.commit()  # keeps the definition cache row
    recommended = list(DEFAULT_RULES["attributes"].params["recommended_attributes"])
    content = build_new_item_template(product_type, required, recommended)
    return _xlsx_response(content, f"nuovi-articoli-{product_type}.xlsx")


@router.post("/new-items/upload", response_model=BulkUploadResponse)
async def upload_new_items(
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
    account_id: UUID = Form(...),
    file: UploadFile = File(...),
):
    """New items: one validated PUT request per row that fills the required attributes."""
    account = await _account_or_404(db, organization.id, account_id)
    data, name = await _read_upload(file)
    parsed = _parse_file(parse_new_items, data, name)
    existing_skus = {p.sku for p in await _account_products(db, account.id) if p.sku}
    existing_skus |= await _live_skus(db, account.id)
    required_by_type: dict[str, Optional[list[str]]] = {}
    seen: set[str] = set()
    items: list[ChangeItem] = []
    errors: list[RowErrorOut] = []
    for row in parsed:
        if row.errors:
            errors.append(row_error(row.row_number, "; ".join(row.errors), sku=row.sku or None))
            continue
        if row.sku in existing_skus:
            errors.append(row_error(
                row.row_number, "SKU già presente: usate l'aggiornamento massivo", sku=row.sku
            ))
            continue
        if row.sku in seen:
            errors.append(row_error(row.row_number, "SKU ripetuto nel file", sku=row.sku))
            continue
        seen.add(row.sku)
        if row.product_type not in required_by_type:
            required_by_type[row.product_type] = await _product_type_required(
                db, account, row.product_type
            )
        required = required_by_type[row.product_type]
        if required is None:
            errors.append(row_error(
                row.row_number, f"{_PTD_UNAVAILABLE}: {row.product_type}", sku=row.sku
            ))
            continue
        missing = validate_new_item(row, required)
        if missing or not row.attributes:
            errors.append(row_error(
                row.row_number, "; ".join(missing) or "nessun attributo compilato", sku=row.sku
            ))
            continue
        items.append(ChangeItem(
            asin=None,
            sku=row.sku,
            product_type=row.product_type,
            kind="new_item",
            operation="PUT",
            attributes=wrap_new_item_attributes(row.attributes, account.marketplace_id),
            summary={"fields": {k: {"before": None, "after": v} for k, v in row.attributes.items()}},
        ))
    batch_id, requests = None, []
    if items:
        service = ChangeRequestService(db)
        batch_id = uuidlib.uuid4()
        requests = await service.create(account, items, current_user.id, batch_id=batch_id)
        await service.validate(account, requests)
    await db.commit()
    return BulkUploadResponse(
        batch_id=batch_id,
        rows=len(parsed),
        changes=len(items),
        row_errors=errors,
        requests=[request_out(r) for r in requests],
    )
