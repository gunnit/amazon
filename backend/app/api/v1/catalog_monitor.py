"""Catalogue monitor API: listing quality, rules, keywords, scan and access check (R1),
content protection, variations and the approval queue (R2, R3).

Every route needs an authenticated user and the account must belong to the user's
organisation (404 otherwise). Replacing the rule overrides needs the admin role.
All database access sits in small ``_`` helpers so the sorting, filtering and
summary logic stays pure.
"""
from __future__ import annotations

import io
import logging
import uuid as uuidlib
from collections import defaultdict
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import delete, func, or_, select

from app.api.deps import AdminOrganization, CurrentOrganization, CurrentUser, DbSession
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
    BaselinesRequest,
    BaselinesResponse,
    BaselineStatusResponse,
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
    RulesUpdateRequest,
    ScanStartResponse,
    ScanStateResponse,
    VariationOut,
    VariationRestoreRequest,
)
from app.services.catalog_monitor.baselines import accept_anomaly, approve_live_as_baseline
from app.services.catalog_monitor.capabilities import check_account_capabilities, listing_seller_id
from app.services.catalog_monitor.changes import (
    _APPROVABLE,
    _REJECTABLE,
    ChangeItem,
    ChangeRequestService,
    build_listings_feed,
    is_file_only,
    restore_patches,
    variation_patches,
)
from app.services.catalog_monitor.content import content_from_dict
from app.services.catalog_monitor.diff import diff_content
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
_FEED_STATUSES = ("approved", "file_only")
_MAX_REQUESTS = 500


def anomaly_out(anomaly: Any, title: Optional[str] = None) -> AnomalyOut:
    return AnomalyOut(
        id=anomaly.id,
        account_id=anomaly.account_id,
        asin=anomaly.asin,
        title=title,
        kind=anomaly.kind,
        field=anomaly.field,
        status=anomaly.status,
        baseline_value=anomaly.baseline_value,
        live_value=anomaly.live_value,
        detected_at=anomaly.detected_at,
        last_seen_at=anomaly.last_seen_at,
        change_request_id=anomaly.change_request_id,
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
        patches = restore_patches(baseline, [a.field for a in restorable])
        if not patches:
            skipped += [_notice(a, "nothing_to_restore") for a in restorable]
            continue
        live = versions.get(asin) or {}
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
    return None if row.status in _APPROVABLE else f"status_{row.status}"


def reject_skip_reason(row: Any) -> Optional[str]:
    return None if row.status in _REJECTABLE else f"status_{row.status}"


def submit_skip_reason(row: Any) -> Optional[str]:
    if row.status != "approved":
        return f"status_{row.status}"
    return "file_only" if is_file_only(row) else None


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


async def _baselines(db, account_id: UUID) -> dict[str, ListingContentBaseline]:
    return await CatalogMonitorRepository(db).baselines(account_id)


async def _latest_content_dicts(db, account_id: UUID, asins: list[str]) -> dict[str, dict]:
    versions = await CatalogMonitorRepository(db).latest_versions(account_id, asins)
    return {asin: v.content for asin, v in versions.items()}


async def _versions(db, account_id: UUID, asin: str) -> list[Any]:
    return await CatalogMonitorRepository(db).versions(account_id, asin)


async def _family_baselines(db, account_id: UUID) -> list[VariationFamilyBaseline]:
    return await CatalogMonitorRepository(db).family_baselines(account_id)


async def _variation_anomalies(db, account_id: UUID) -> list[CatalogAnomaly]:
    result = await db.execute(
        select(CatalogAnomaly)
        .where(
            CatalogAnomaly.account_id == account_id,
            CatalogAnomaly.kind.in_(_VARIATION_KINDS),
            CatalogAnomaly.status != "resolved",
        )
        .order_by(CatalogAnomaly.detected_at, CatalogAnomaly.id)
    )
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
    return [anomaly_out(a, title) for a, title in rows]


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
    skipped: list[dict] = []
    eligible = []
    for anomaly in anomalies:
        if anomaly.kind != "content_changed":
            skipped.append(_notice(anomaly, "not_content_anomaly"))
        elif anomaly.status not in _RESTORABLE_STATUSES:
            skipped.append(_notice(anomaly, f"status_{anomaly.status}"))
        else:
            eligible.append(anomaly)
    asins = sorted({a.asin for a in eligible})
    items, not_restorable, more_skipped = build_restore_items(
        eligible,
        await _baselines(db, account.id),
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
    organization: CurrentOrganization,
    db: DbSession,
):
    """Accept the live value: the baseline follows it and the anomaly is resolved."""
    found = await _anomalies_by_ids(db, organization.id, [anomaly_id], lock=True)
    if not found:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Anomaly not found")
    anomaly = found[0]
    if anomaly.status in ("resolved", "restore_requested"):
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
    organization: CurrentOrganization,
    db: DbSession,
):
    """Approve the latest live content as the baseline (all ASINs, or the given ones)."""
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
        a for a in await _variation_anomalies(db, account.id) if _family_of(a) == family.parent_asin
    ]
    by_child: dict[str, list[Any]] = defaultdict(list)
    for anomaly in mine:
        if anomaly.kind == "child_detached":
            by_child[anomaly.asin].append(anomaly)
    if body.child_asins is None:
        selected = sorted(by_child)
    else:
        unknown = set(body.child_asins) - set(family.child_asins or [])
        if unknown:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                f"Not children of {family.parent_asin}: {', '.join(sorted(unknown))}",
            )
        selected = list(dict.fromkeys(body.child_asins))
    if not selected:
        return ChangeBatchResponse(requests=[])
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
    return ChangeBatchResponse(batch_id=batch_id, requests=[request_out(r) for r in rows])


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
    """The batch's approved and file-only requests as a JSON_LISTINGS_FEED file.

    Requests the feed cannot hold (no SKU or product type) are listed in the
    ``X-Skipped-Requests`` header, comma separated.
    """
    rows = [r for r in await _batch_requests(db, organization.id, batch_id) if r.status in _FEED_STATUSES]
    if not rows:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No approved or file-only requests in batch")
    account = await _account_or_404(db, organization.id, rows[0].account_id)
    seller_id = listing_seller_id(account, await _stored_capability(db, account.id)) or ""
    feed = build_listings_feed([r for r in rows if r.account_id == account.id], seller_id, account.marketplace_id)
    return JSONResponse(
        feed.document,
        headers={
            "Content-Disposition": f'attachment; filename="listings-feed-{batch_id}.json"',
            "X-Skipped-Requests": ",".join(str(i) for i in feed.skipped),
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
