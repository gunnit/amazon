"""Catalog management endpoints."""
from datetime import date
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select

from app.api.deps import CurrentOrganization, CurrentUser, DbSession
from app.core.exceptions import AmazonAPIError
from app.models.amazon_account import AmazonAccount
from app.models.catalog_change_log import CatalogChangeLog
from app.models.product import Product
from app.models.sales_data import SalesData
from app.schemas.catalog import (
    AvailabilityResult,
    AvailabilityUpdateRequest,
    BulkListingUpdateResult,
    BulkPriceUpdateRequest,
    BulkResult,
    CatalogChangeLogEntry,
    ImportResult,
    ListingQualityItem,
    ListingQualityResponse,
    PriceUpdateResult,
)
from app.schemas.report import ProductResponse
from app.services.catalog_service import (
    CatalogOperationError,
    CatalogService,
    import_template_bytes,
)
from app.services.data_extraction import DAILY_TOTAL_ASIN, DataExtractionService
from app.services.image_service import (
    ALLOWED_CONTENT_TYPES,
    ImageService,
    ImageUpload,
    MAX_ALTERNATE_IMAGES,
)

router = APIRouter()


async def _verify_account_in_org(db, organization_id: UUID, account_id: UUID) -> None:
    result = await db.execute(
        select(AmazonAccount.id).where(
            AmazonAccount.id == account_id,
            AmazonAccount.organization_id == organization_id,
        )
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")


@router.get("/products", response_model=List[ProductResponse])
async def list_products(
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
    account_ids: Optional[List[UUID]] = Query(default=None),
    search: Optional[str] = None,
    category: Optional[str] = None,
    active_only: bool = True,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    limit: int = 100,
    offset: int = 0,
):
    """List products from the catalog.

    The catalog lists every synced product regardless of the period. When
    ``date_from``/``date_to`` are supplied each product is flagged with
    ``has_sales_in_period`` instead of being filtered out, so nothing
    visually disappears from the table.
    """
    query = (
        select(Product, AmazonAccount.account_type)
        .join(AmazonAccount, AmazonAccount.id == Product.account_id)
        .where(AmazonAccount.organization_id == organization.id)
        .order_by(Product.updated_at.desc())
        .limit(limit)
        .offset(offset)
    )
    if account_ids:
        query = query.where(AmazonAccount.id.in_(account_ids))

    if active_only:
        query = query.where(Product.is_active == True)  # noqa: E712
    if search:
        query = query.where(
            (Product.asin.ilike(f"%{search}%"))
            | (Product.title.ilike(f"%{search}%"))
            | (Product.sku.ilike(f"%{search}%"))
        )
    if category:
        query = query.where(Product.category == category)

    rows = (await db.execute(query)).all()

    sales_keys: Optional[set] = None
    if date_from is not None and date_to is not None:
        sales_keys = await _asins_with_sales_in_period(
            db, organization.id, date_from, date_to, account_ids
        )

    return [
        ProductResponse.model_validate(
            {
                **product.__dict__,
                "account_type": account_type.value if account_type else None,
                "has_sales_in_period": (
                    (product.account_id, product.asin) in sales_keys
                    if sales_keys is not None
                    else None
                ),
            }
        )
        for product, account_type in rows
    ]


async def _asins_with_sales_in_period(
    db,
    organization_id: UUID,
    date_from: date,
    date_to: date,
    account_ids: Optional[List[UUID]],
) -> set:
    """Distinct (account_id, asin) pairs with sales in the period for the org.

    Keyed per account so an ASIN sold under one account is not flagged on a
    different account that happens to list the same ASIN.
    """
    query = (
        select(SalesData.account_id, SalesData.asin)
        .join(AmazonAccount, AmazonAccount.id == SalesData.account_id)
        .where(
            AmazonAccount.organization_id == organization_id,
            SalesData.asin != DAILY_TOTAL_ASIN,
            SalesData.date >= date_from,
            SalesData.date <= date_to,
        )
        .distinct()
    )
    if account_ids:
        query = query.where(AmazonAccount.id.in_(account_ids))

    rows = (await db.execute(query)).all()
    return {(row[0], row[1]) for row in rows}


@router.get("/products/{asin}", response_model=ProductResponse)
async def get_product(
    asin: str,
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
):
    """Get product details by ASIN."""
    result = await db.execute(
        select(Product, AmazonAccount.account_type)
        .join(AmazonAccount, AmazonAccount.id == Product.account_id)
        .where(
            AmazonAccount.organization_id == organization.id,
            Product.asin == asin,
        )
    )
    row = result.first()

    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    product, account_type = row
    return ProductResponse.model_validate(
        {**product.__dict__, "account_type": account_type.value if account_type else None}
    )


@router.put("/products/{asin}", response_model=ProductResponse)
async def update_product(
    asin: str,
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
    title: Optional[str] = None,
    brand: Optional[str] = None,
    category: Optional[str] = None,
    is_active: Optional[bool] = None,
):
    """Update local product metadata (does not push to Amazon)."""
    accounts_query = select(AmazonAccount.id).where(
        AmazonAccount.organization_id == organization.id
    )

    result = await db.execute(
        select(Product).where(
            Product.account_id.in_(accounts_query),
            Product.asin == asin,
        )
    )
    product = result.scalar_one_or_none()

    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    if title is not None:
        product.title = title
    if brand is not None:
        product.brand = brand
    if category is not None:
        product.category = category
    if is_active is not None:
        product.is_active = is_active

    await db.flush()
    await db.refresh(product)

    return product


@router.post("/backfill-titles")
async def backfill_product_titles(
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
    account_id: UUID = Query(..., description="Account whose missing titles to backfill"),
    limit: Optional[int] = Query(None, ge=1, le=200, description="Max products to look up"),
):
    """Re-query the Amazon catalog to fill in product titles still showing as empty.

    Best-effort: ASINs for which Amazon returns no title are left untouched so the
    UI keeps its honest fallback. Run manually after a sync (no Celery in prod).
    """
    result = await db.execute(
        select(AmazonAccount).where(
            AmazonAccount.id == account_id,
            AmazonAccount.organization_id == organization.id,
        )
    )
    account = result.scalar_one_or_none()
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")

    service = DataExtractionService(db)
    try:
        summary = await service.backfill_missing_product_titles(
            account, organization=organization, limit=limit
        )
    except AmazonAPIError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))

    return {"account_id": str(account_id), **summary}


@router.get("/bulk-update/template")
async def download_bulk_template(
    current_user: CurrentUser,
    organization: CurrentOrganization,
):
    """Download the Excel template for bulk listing updates."""
    content = CatalogService.generate_template_bytes()
    return StreamingResponse(
        iter([content]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=bulk_listings_template.xlsx"},
    )


@router.post("/bulk-update", response_model=BulkResult[BulkListingUpdateResult])
async def bulk_update_products(
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
    account_id: UUID = Query(...),
    product_type: str = Query("PRODUCT"),
    file: UploadFile = File(...),
):
    """Bulk update product listings on Amazon via Excel upload."""
    if not file.filename or not file.filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be an Excel file (.xlsx or .xls)",
        )

    await _verify_account_in_org(db, organization.id, account_id)

    contents = await file.read()
    service = CatalogService(db, user_id=current_user.id)
    try:
        return await service.bulk_update_from_excel(account_id, contents, product_type=product_type)
    except CatalogOperationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("/import/template")
async def download_import_template(
    current_user: CurrentUser,
    organization: CurrentOrganization,
):
    """Download the CSV template for manual catalog imports."""
    return StreamingResponse(
        iter([import_template_bytes()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=catalog_import_template.csv"},
    )


@router.post("/import", response_model=ImportResult)
async def import_products(
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
    account_id: UUID = Query(...),
    file: UploadFile = File(...),
):
    """Create or update catalog products from a CSV/Excel upload.

    Works for Vendor accounts too: rows are written to the local catalog and are
    never pushed to Amazon.
    """
    if not file.filename or not file.filename.lower().endswith((".csv", ".xlsx", ".xls")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be a CSV or Excel file (.csv, .xlsx or .xls)",
        )

    await _verify_account_in_org(db, organization.id, account_id)

    contents = await file.read()
    service = CatalogService(db, user_id=current_user.id)
    try:
        return await service.import_products_from_file(account_id, contents, file.filename)
    except CatalogOperationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post("/prices", response_model=BulkResult[PriceUpdateResult])
async def update_prices(
    payload: BulkPriceUpdateRequest,
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
):
    """Push SKU prices to Amazon SP-API and mirror them locally."""
    await _verify_account_in_org(db, organization.id, payload.account_id)

    service = CatalogService(db, user_id=current_user.id)
    try:
        return await service.update_prices_bulk(
            payload.account_id,
            payload.updates,
            product_type=payload.product_type,
        )
    except CatalogOperationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.patch("/products/{asin}/availability", response_model=AvailabilityResult)
async def update_availability(
    asin: str,
    payload: AvailabilityUpdateRequest,
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
):
    """Enable or disable a product on Amazon by adjusting its fulfillment quantity."""
    await _verify_account_in_org(db, organization.id, payload.account_id)

    service = CatalogService(db, user_id=current_user.id)
    try:
        return await service.toggle_availability(
            account_id=payload.account_id,
            asin=asin,
            is_available=payload.is_available,
            quantity=payload.quantity,
            product_type=payload.product_type,
        )
    except CatalogOperationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get(
    "/products/{asin}/history",
    response_model=List[CatalogChangeLogEntry],
)
async def get_product_history(
    asin: str,
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
    account_id: UUID = Query(...),
    limit: int = Query(50, ge=1, le=500),
):
    """Return audit-log entries for the given ASIN in chronological reverse order."""
    await _verify_account_in_org(db, organization.id, account_id)

    result = await db.execute(
        select(CatalogChangeLog)
        .where(
            CatalogChangeLog.account_id == account_id,
            CatalogChangeLog.asin == asin,
        )
        .order_by(CatalogChangeLog.created_at.desc())
        .limit(limit)
    )
    return result.scalars().all()


# ---------------------------------------------------------------------
# Image management
# ---------------------------------------------------------------------


@router.get("/products/{asin}/images")
async def list_product_images(
    asin: str,
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
    account_id: UUID = Query(...),
):
    """List images stored in S3 for a given product."""
    await _verify_account_in_org(db, organization.id, account_id)

    service = ImageService(db)
    try:
        return {"asin": asin, "account_id": str(account_id), "images": await service.list_images(account_id, asin)}
    except CatalogOperationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post("/products/{asin}/images", status_code=status.HTTP_201_CREATED)
async def upload_product_images(
    asin: str,
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
    account_id: UUID = Form(...),
    product_type: str = Form("PRODUCT"),
    push_to_amazon: bool = Form(True),
    main_index: Optional[int] = Form(None),
    files: List[UploadFile] = File(...),
):
    """Upload product images to S3 and push them to the Amazon listing.

    * `main_index` (0-based) marks which uploaded file is the primary image.
    * Up to 1 main + 8 alternate images are pushed to SP-API.
    """
    if not files:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No files uploaded")
    if len(files) > MAX_ALTERNATE_IMAGES + 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Too many files (max {MAX_ALTERNATE_IMAGES + 1})",
        )

    await _verify_account_in_org(db, organization.id, account_id)

    uploads: List[ImageUpload] = []
    for idx, file in enumerate(files):
        content_type = (file.content_type or "").lower()
        if content_type not in ALLOWED_CONTENT_TYPES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File {file.filename!r} has unsupported type {content_type!r}",
            )
        data = await file.read()
        uploads.append(
            ImageUpload(
                filename=file.filename or f"image_{idx}",
                content_type=content_type,
                data=data,
                is_main=(main_index == idx),
            )
        )

    service = ImageService(db, user_id=current_user.id)
    try:
        result = await service.upload_images(
            account_id=account_id,
            asin=asin,
            uploads=uploads,
            push_to_amazon=push_to_amazon,
            product_type=product_type,
        )
    except CatalogOperationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    return result


@router.delete("/products/{asin}/images")
async def delete_product_image(
    asin: str,
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
    account_id: UUID = Query(...),
    key: str = Query(..., description="S3 object key returned by the upload/list endpoints"),
):
    """Delete a previously uploaded image from S3.

    Does not automatically re-patch the Amazon listing: call the upload
    endpoint again with the remaining set if you need to re-sync slots.
    """
    await _verify_account_in_org(db, organization.id, account_id)

    service = ImageService(db)
    try:
        return await service.delete_image(account_id, asin, key)
    except CatalogOperationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("/listing-quality", response_model=ListingQualityResponse)
async def get_listing_quality(
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
    account_id: UUID = Query(...),
    limit: int = Query(default=100, ge=1, le=500),
):
    """Listing-quality fix list for one account, worst scores first.

    Scores are computed live from warehouse data (no Amazon API calls);
    weekly snapshots in listing_quality_snapshots provide the trend."""
    await _verify_account_in_org(db, organization.id, account_id)

    from app.services.listing_quality_service import ListingQualityService

    scored = await ListingQualityService(db).compute_for_account(account_id)
    scores = [entry["score"] for entry in scored]
    return ListingQualityResponse(
        account_id=account_id,
        product_count=len(scored),
        average_score=round(sum(scores) / len(scores), 1) if scores else None,
        good_count=sum(1 for s in scores if s >= 80),
        fair_count=sum(1 for s in scores if 50 <= s < 80),
        poor_count=sum(1 for s in scores if s < 50),
        products=[ListingQualityItem(**entry) for entry in scored[:limit]],
    )
