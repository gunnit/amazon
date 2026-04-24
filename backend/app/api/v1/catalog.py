"""Catalog management endpoints."""
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import CurrentOrganization, CurrentUser, DbSession
from app.models.amazon_account import AmazonAccount
from app.models.product import Product
from app.schemas.report import ProductResponse
from app.services.catalog_service import CatalogOperationError, CatalogService
from app.services.image_service import (
    ALLOWED_CONTENT_TYPES,
    ImageService,
    ImageUpload,
    MAX_ALTERNATE_IMAGES,
)

router = APIRouter()


class PriceUpdate(BaseModel):
    asin: Optional[str] = None
    sku: Optional[str] = None
    price: float


class BulkPriceUpdateRequest(BaseModel):
    account_id: UUID
    updates: List[PriceUpdate] = Field(default_factory=list)
    product_type: str = "PRODUCT"


class AvailabilityUpdateRequest(BaseModel):
    account_id: UUID
    is_available: bool
    quantity: Optional[int] = None
    product_type: str = "PRODUCT"


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
    limit: int = 100,
    offset: int = 0,
):
    """List products from the catalog."""
    accounts_query = select(AmazonAccount.id).where(
        AmazonAccount.organization_id == organization.id
    )
    if account_ids:
        accounts_query = accounts_query.where(AmazonAccount.id.in_(account_ids))

    query = (
        select(Product)
        .where(Product.account_id.in_(accounts_query))
        .order_by(Product.updated_at.desc())
        .limit(limit)
        .offset(offset)
    )

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

    result = await db.execute(query)
    return result.scalars().all()


@router.get("/products/{asin}", response_model=ProductResponse)
async def get_product(
    asin: str,
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
):
    """Get product details by ASIN."""
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

    return product


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


@router.post("/bulk-update")
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
    service = CatalogService(db)
    try:
        return await service.bulk_update_from_excel(account_id, contents, product_type=product_type)
    except CatalogOperationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post("/prices")
async def update_prices(
    payload: BulkPriceUpdateRequest,
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
):
    """Push SKU prices to Amazon SP-API and mirror them locally."""
    await _verify_account_in_org(db, organization.id, payload.account_id)

    service = CatalogService(db)
    try:
        return await service.update_prices_bulk(
            payload.account_id,
            [u.model_dump() for u in payload.updates],
            product_type=payload.product_type,
        )
    except CatalogOperationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.patch("/products/{asin}/availability")
async def update_availability(
    asin: str,
    payload: AvailabilityUpdateRequest,
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
):
    """Enable or disable a product on Amazon by adjusting its fulfillment quantity."""
    await _verify_account_in_org(db, organization.id, payload.account_id)

    service = CatalogService(db)
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

    service = ImageService(db)
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
