"""Catalog management endpoints."""
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, HTTPException, status, UploadFile, File
from sqlalchemy import select

from app.api.deps import CurrentUser, CurrentOrganization, DbSession
from app.models.amazon_account import AmazonAccount
from app.models.product import Product
from app.schemas.report import ProductResponse

router = APIRouter()


@router.get("/products", response_model=List[ProductResponse])
async def list_products(
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
    account_ids: Optional[List[UUID]] = None,
    search: Optional[str] = None,
    category: Optional[str] = None,
    active_only: bool = True,
    limit: int = 100,
    offset: int = 0,
):
    """List products from catalog."""
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
        query = query.where(Product.is_active == True)
    if search:
        query = query.where(
            (Product.asin.ilike(f"%{search}%")) |
            (Product.title.ilike(f"%{search}%")) |
            (Product.sku.ilike(f"%{search}%"))
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
        select(Product)
        .where(
            Product.account_id.in_(accounts_query),
            Product.asin == asin,
        )
    )
    product = result.scalar_one_or_none()

    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found"
        )

    return product


@router.put("/products/{asin}", response_model=ProductResponse)
async def update_product(
    asin: str,
    title: Optional[str] = None,
    brand: Optional[str] = None,
    category: Optional[str] = None,
    is_active: Optional[bool] = None,
    current_user: CurrentUser = None,
    organization: CurrentOrganization = None,
    db: DbSession = None,
):
    """Update product information."""
    accounts_query = select(AmazonAccount.id).where(
        AmazonAccount.organization_id == organization.id
    )

    result = await db.execute(
        select(Product)
        .where(
            Product.account_id.in_(accounts_query),
            Product.asin == asin,
        )
    )
    product = result.scalar_one_or_none()

    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found"
        )

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


@router.post("/bulk-update")
async def bulk_update_products(
    file: UploadFile = File(...),
    current_user: CurrentUser = None,
    organization: CurrentOrganization = None,
    db: DbSession = None,
):
    """Bulk update products via Excel upload."""
    if not file.filename.endswith(('.xlsx', '.xls')):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be an Excel file (.xlsx or .xls)"
        )

    # Read and process Excel file
    import pandas as pd
    import io

    contents = await file.read()
    df = pd.read_excel(io.BytesIO(contents))

    required_columns = ['asin']
    if not all(col in df.columns for col in required_columns):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Excel file must contain columns: {required_columns}"
        )

    accounts_query = select(AmazonAccount.id).where(
        AmazonAccount.organization_id == organization.id
    )

    updated = 0
    errors = []

    for _, row in df.iterrows():
        asin = row['asin']
        result = await db.execute(
            select(Product)
            .where(
                Product.account_id.in_(accounts_query),
                Product.asin == asin,
            )
        )
        product = result.scalar_one_or_none()

        if not product:
            errors.append(f"Product {asin} not found")
            continue

        if 'title' in row and pd.notna(row['title']):
            product.title = row['title']
        if 'brand' in row and pd.notna(row['brand']):
            product.brand = row['brand']
        if 'category' in row and pd.notna(row['category']):
            product.category = row['category']

        updated += 1

    await db.flush()

    return {
        "updated": updated,
        "errors": errors,
        "total_rows": len(df),
    }


@router.post("/prices")
async def update_prices(
    price_updates: List[dict],
    current_user: CurrentUser = None,
    organization: CurrentOrganization = None,
    db: DbSession = None,
):
    """Bulk update product prices."""
    accounts_query = select(AmazonAccount.id).where(
        AmazonAccount.organization_id == organization.id
    )

    updated = 0
    errors = []

    for update in price_updates:
        asin = update.get('asin')
        new_price = update.get('price')

        if not asin or new_price is None:
            errors.append(f"Invalid update: {update}")
            continue

        result = await db.execute(
            select(Product)
            .where(
                Product.account_id.in_(accounts_query),
                Product.asin == asin,
            )
        )
        product = result.scalar_one_or_none()

        if not product:
            errors.append(f"Product {asin} not found")
            continue

        product.current_price = new_price
        updated += 1

    await db.flush()

    return {
        "updated": updated,
        "errors": errors,
    }
