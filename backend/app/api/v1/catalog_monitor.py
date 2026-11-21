"""Catalogue monitor API: listing quality, rules, keywords, scan and access check (R1).

Every route needs an authenticated user and the account must belong to the user's
organisation (404 otherwise). Replacing the rule overrides needs the admin role.
All database access sits in small ``_`` helpers so the sorting, filtering and
summary logic stays pure.
"""
from __future__ import annotations

import io
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import delete, func, or_, select

from app.api.deps import AdminOrganization, CurrentOrganization, CurrentUser, DbSession
from app.models.amazon_account import AmazonAccount
from app.models.catalog_monitor import CatalogApiCapability, ListingQualityRule
from app.models.listing_quality import ListingQualitySnapshot
from app.models.product import Product
from app.schemas.catalog_monitor import (
    AccountRequest,
    CapabilityResponse,
    KeywordItem,
    KeywordsUpdateRequest,
    KeywordsUpdateResponse,
    QualityItem,
    QualityItemDetail,
    QualityResponse,
    QualitySummary,
    RuleConfigOut,
    RuleOverrideIn,
    RuleOverrideOut,
    RulesResponse,
    RulesUpdateRequest,
    ScanStartResponse,
    ScanStateResponse,
)
from app.services.catalog_monitor.capabilities import check_account_capabilities
from app.services.catalog_monitor.repository import CatalogMonitorRepository
from app.services.catalog_monitor.rules import DEFAULT_RULES, RULE_KEYS
from app.services.catalog_monitor.scanner import scan_state, start_account_scan

router = APIRouter()

_STATE_ORDER = {"red": 0, "yellow": 1, "grey": 2, "green": 3}
_STATES = ("green", "yellow", "red", "grey")


# ---- pure helpers ----


def split_scanned(rows: list[dict]) -> tuple[list[dict], int]:
    """Turn product+snapshot rows into quality items; count products with no snapshot."""
    items: list[dict] = []
    unscanned = 0
    for row in rows:
        comp = row.get("components")
        if not isinstance(comp, dict) or row.get("score") is None:
            unscanned += 1
            continue
        results = comp.get("results") if isinstance(comp.get("results"), list) else []
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
    """``state`` alone filters the overall state; with ``rule`` it filters that rule's state.

    ``mandatory_only`` trims each item's results to mandatory rules; the state is not recomputed.
    """
    out = []
    for item in items:
        if state and rule:
            if not any(r["key"] == rule and r["state"] == state for r in item["results"]):
                continue
        elif state and item["state"] != state:
            continue
        if mandatory_only:
            item = {**item, "results": [r for r in item["results"] if r["mandatory"]]}
        out.append(item)
    return out


def sort_items(items: list[dict]) -> list[dict]:
    return sorted(items, key=lambda i: (_STATE_ORDER.get(i["state"], 2), i["score"], i["asin"]))


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
        select(Product, ListingQualitySnapshot)
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
    rows = []
    for product, snap in (await db.execute(stmt)).all():
        rows.append({
            "asin": product.asin,
            "sku": product.sku,
            "title": product.title,
            "main_keyword": product.main_keyword,
            "main_keyword_source": product.main_keyword_source,
            "score": snap.score if snap else None,
            "components": snap.components if snap else None,
            "created_at": snap.created_at if snap else None,
        })
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
