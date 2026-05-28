"""Catalog write operations against the Amazon SP-API Listings Items API.

Reads from the local Product table, pushes changes through SP-API,
then mirrors the successful change locally and records an audit row.
"""
from __future__ import annotations

import io
import logging
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Sequence
from uuid import UUID

import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AmazonAPIError
from app.models.amazon_account import AmazonAccount, AccountType
from app.models.catalog_change_log import CatalogChangeLog
from app.models.product import Product
from app.schemas.catalog import (
    BulkErrorCode,
    BulkListingUpdateResult,
    BulkResult,
    BulkRowError,
    CatalogChangeField,
    CatalogChangeStatus,
    PriceUpdate,
    PriceUpdateResult,
    AvailabilityResult,
)

logger = logging.getLogger(__name__)

LISTING_TEXT_FIELDS = {
    "title": "item_name",
    "bullet_1": "bullet_point",
    "bullet_2": "bullet_point",
    "bullet_3": "bullet_point",
    "bullet_4": "bullet_point",
    "bullet_5": "bullet_point",
    "description": "product_description",
    "search_terms": "generic_keyword",
}


class CatalogOperationError(Exception):
    """Raised when a catalog write operation cannot be completed."""


class CatalogService:
    """Catalog management service backed by SP-API Listings."""

    def __init__(self, db: AsyncSession, user_id: Optional[UUID] = None):
        self.db = db
        self.user_id = user_id

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    async def _load_organization(self, account: AmazonAccount):
        from app.models.user import Organization
        result = await self.db.execute(
            select(Organization).where(Organization.id == account.organization_id)
        )
        return result.scalar_one_or_none()

    def _create_sp_api_client(self, account: AmazonAccount, organization=None):
        from app.core.amazon.credentials import resolve_credentials
        from app.core.amazon.sp_api_client import SPAPIClient, resolve_marketplace

        credentials = resolve_credentials(account, organization)
        marketplace = resolve_marketplace(account.marketplace_country)
        return SPAPIClient(credentials, marketplace, account_type=account.account_type.value)

    async def _require_seller_account(self, account_id: UUID) -> AmazonAccount:
        result = await self.db.execute(
            select(AmazonAccount).where(AmazonAccount.id == account_id)
        )
        account = result.scalar_one_or_none()
        if not account:
            raise CatalogOperationError(f"Account {account_id} not found")
        if account.account_type != AccountType.SELLER:
            raise CatalogOperationError(
                "Listing writes are only available for Seller Central accounts"
            )
        if not account.seller_id:
            raise CatalogOperationError(
                f"Account {account.account_name} is missing a Seller ID"
            )
        return account

    async def _load_product(self, account_id: UUID, asin: str) -> Optional[Product]:
        result = await self.db.execute(
            select(Product).where(
                Product.account_id == account_id,
                Product.asin == asin,
            )
        )
        return result.scalar_one_or_none()

    def _audit(
        self,
        *,
        organization_id: UUID,
        account_id: UUID,
        asin: Optional[str],
        sku: Optional[str],
        field: CatalogChangeField,
        old_value: Any,
        new_value: Any,
        status: CatalogChangeStatus,
        sp_api_error: Optional[str] = None,
    ) -> None:
        entry = CatalogChangeLog(
            organization_id=organization_id,
            account_id=account_id,
            user_id=self.user_id,
            asin=asin,
            sku=sku,
            field=field.value,
            old_value=old_value,
            new_value=new_value,
            sp_api_status=status.value,
            sp_api_error=sp_api_error,
        )
        self.db.add(entry)

    # ------------------------------------------------------------------
    # Bulk listing updates (title / bullets / description / keywords)
    # ------------------------------------------------------------------

    async def bulk_update_from_excel(
        self,
        account_id: UUID,
        file_bytes: bytes,
        product_type: str = "PRODUCT",
    ) -> BulkResult[BulkListingUpdateResult]:
        """Apply bulk listing content updates from an Excel file.

        Expected columns (all optional except sku): sku, title, bullet_1..5,
        description, search_terms.
        """
        account = await self._require_seller_account(account_id)
        organization = await self._load_organization(account)
        client = self._create_sp_api_client(account, organization)

        try:
            df = pd.read_excel(io.BytesIO(file_bytes))
        except Exception as exc:  # noqa: BLE001
            raise CatalogOperationError(f"Could not parse Excel file: {exc}") from exc

        if "sku" not in df.columns:
            raise CatalogOperationError("Excel must contain a 'sku' column")

        successes: List[BulkListingUpdateResult] = []
        errors: List[BulkRowError] = []

        for row_idx, row in df.iterrows():
            row_number = int(row_idx) + 2  # +1 for 0-based, +1 for header
            sku = str(row.get("sku") or "").strip()
            if not sku:
                continue

            attributes = _row_to_listing_attributes(row)
            if not attributes:
                continue

            old_snapshot = await self._product_snapshot_by_sku(account_id, sku)
            new_snapshot = _row_listing_snapshot(row)

            try:
                client.update_listing_attributes(
                    seller_id=account.seller_id,
                    sku=sku,
                    product_type=product_type,
                    attributes=attributes,
                )
                await self._mirror_local_listing(account_id, sku, row)
                successes.append(
                    BulkListingUpdateResult(sku=sku, fields=list(attributes.keys()))
                )
                self._audit(
                    organization_id=account.organization_id,
                    account_id=account_id,
                    asin=old_snapshot.get("asin") if old_snapshot else None,
                    sku=sku,
                    field=CatalogChangeField.LISTING,
                    old_value=old_snapshot,
                    new_value=new_snapshot,
                    status=CatalogChangeStatus.SUCCESS,
                )
            except AmazonAPIError as exc:
                logger.warning("SP-API listing update failed for %s: %s", sku, exc)
                errors.append(
                    BulkRowError(
                        row=row_number,
                        sku=sku,
                        error=str(exc),
                        code=BulkErrorCode.SP_API_ERROR,
                    )
                )
                self._audit(
                    organization_id=account.organization_id,
                    account_id=account_id,
                    asin=old_snapshot.get("asin") if old_snapshot else None,
                    sku=sku,
                    field=CatalogChangeField.LISTING,
                    old_value=old_snapshot,
                    new_value=new_snapshot,
                    status=CatalogChangeStatus.FAILED,
                    sp_api_error=str(exc),
                )
            except Exception as exc:  # noqa: BLE001
                logger.exception("Unexpected failure updating listing %s", sku)
                errors.append(
                    BulkRowError(
                        row=row_number,
                        sku=sku,
                        error=str(exc),
                        code=BulkErrorCode.UNEXPECTED_ERROR,
                    )
                )

        await self.db.flush()

        return BulkResult[BulkListingUpdateResult](
            account_id=account_id,
            total=int(len(df)),
            succeeded=len(successes),
            failed=len(errors),
            successes=successes,
            errors=errors,
        )

    async def _mirror_local_listing(self, account_id: UUID, sku: str, row: pd.Series) -> None:
        """Reflect the update in the local catalog cache so the UI shows it immediately."""
        result = await self.db.execute(
            select(Product).where(Product.account_id == account_id, Product.sku == sku)
        )
        product = result.scalar_one_or_none()
        if not product:
            return

        if "title" in row and pd.notna(row.get("title")):
            product.title = str(row["title"])
        if "brand" in row and pd.notna(row.get("brand")):
            product.brand = str(row["brand"])
        if "category" in row and pd.notna(row.get("category")):
            product.category = str(row["category"])

    async def _product_snapshot_by_sku(
        self, account_id: UUID, sku: str
    ) -> Optional[Dict[str, Any]]:
        result = await self.db.execute(
            select(Product).where(Product.account_id == account_id, Product.sku == sku)
        )
        product = result.scalar_one_or_none()
        if not product:
            return None
        return {
            "asin": product.asin,
            "sku": product.sku,
            "title": product.title,
            "brand": product.brand,
            "category": product.category,
        }

    # ------------------------------------------------------------------
    # Price management
    # ------------------------------------------------------------------

    async def update_prices_bulk(
        self,
        account_id: UUID,
        updates: Sequence[PriceUpdate],
        product_type: str = "PRODUCT",
    ) -> BulkResult[PriceUpdateResult]:
        """Push a list of price updates to SP-API."""
        account = await self._require_seller_account(account_id)
        organization = await self._load_organization(account)
        client = self._create_sp_api_client(account, organization)

        currency = _marketplace_currency(account.marketplace_country)
        successes: List[PriceUpdateResult] = []
        errors: List[BulkRowError] = []

        for entry in updates:
            asin = entry.asin
            sku = entry.sku
            new_price = entry.price

            product = await self._resolve_product(account_id, asin=asin, sku=sku)
            if not product:
                errors.append(
                    BulkRowError(
                        asin=asin,
                        sku=sku,
                        error="Product not found for this account",
                        code=BulkErrorCode.PRODUCT_NOT_FOUND,
                    )
                )
                continue
            if not product.sku:
                errors.append(
                    BulkRowError(
                        asin=product.asin,
                        sku=sku,
                        error="Product has no SKU; cannot call SP-API",
                        code=BulkErrorCode.MISSING_SKU,
                    )
                )
                continue

            old_price = product.current_price

            try:
                client.update_listing_price(
                    seller_id=account.seller_id,
                    sku=product.sku,
                    product_type=product_type,
                    price=new_price,
                    currency=currency,
                )
                product.current_price = new_price
                successes.append(
                    PriceUpdateResult(asin=product.asin, sku=product.sku, price=new_price)
                )
                self._audit(
                    organization_id=account.organization_id,
                    account_id=account_id,
                    asin=product.asin,
                    sku=product.sku,
                    field=CatalogChangeField.PRICE,
                    old_value={"price": str(old_price) if old_price is not None else None, "currency": currency},
                    new_value={"price": str(new_price), "currency": currency},
                    status=CatalogChangeStatus.SUCCESS,
                )
            except AmazonAPIError as exc:
                errors.append(
                    BulkRowError(
                        asin=product.asin,
                        sku=product.sku,
                        error=str(exc),
                        code=BulkErrorCode.SP_API_ERROR,
                    )
                )
                self._audit(
                    organization_id=account.organization_id,
                    account_id=account_id,
                    asin=product.asin,
                    sku=product.sku,
                    field=CatalogChangeField.PRICE,
                    old_value={"price": str(old_price) if old_price is not None else None, "currency": currency},
                    new_value={"price": str(new_price), "currency": currency},
                    status=CatalogChangeStatus.FAILED,
                    sp_api_error=str(exc),
                )
            except Exception as exc:  # noqa: BLE001
                logger.exception("Unexpected failure updating price for %s", product.sku)
                errors.append(
                    BulkRowError(
                        asin=product.asin,
                        sku=product.sku,
                        error=str(exc),
                        code=BulkErrorCode.UNEXPECTED_ERROR,
                    )
                )

        await self.db.flush()

        return BulkResult[PriceUpdateResult](
            account_id=account_id,
            total=len(updates),
            succeeded=len(successes),
            failed=len(errors),
            successes=successes,
            errors=errors,
        )

    # ------------------------------------------------------------------
    # Availability toggle
    # ------------------------------------------------------------------

    async def toggle_availability(
        self,
        account_id: UUID,
        asin: str,
        is_available: bool,
        quantity: Optional[int] = None,
        product_type: str = "PRODUCT",
    ) -> AvailabilityResult:
        """Enable or disable a product by setting fulfillment quantity."""
        account = await self._require_seller_account(account_id)
        organization = await self._load_organization(account)
        client = self._create_sp_api_client(account, organization)

        product = await self._load_product(account_id, asin)
        if not product:
            raise CatalogOperationError(f"Product {asin} not found for this account")
        if not product.sku:
            raise CatalogOperationError(f"Product {asin} has no SKU")

        effective_quantity = 0 if not is_available else max(1, int(quantity or 1))
        old_value = {
            "is_available": bool(product.is_available),
            "is_active": bool(product.is_active),
        }
        new_value = {
            "is_available": is_available,
            "is_active": bool(is_available),
            "pushed_quantity": effective_quantity,
        }

        try:
            client.set_listing_quantity(
                seller_id=account.seller_id,
                sku=product.sku,
                product_type=product_type,
                quantity=effective_quantity,
            )
        except AmazonAPIError as exc:
            self._audit(
                organization_id=account.organization_id,
                account_id=account_id,
                asin=product.asin,
                sku=product.sku,
                field=CatalogChangeField.AVAILABILITY,
                old_value=old_value,
                new_value=new_value,
                status=CatalogChangeStatus.FAILED,
                sp_api_error=str(exc),
            )
            await self.db.flush()
            raise CatalogOperationError(str(exc)) from exc

        product.is_available = is_available
        product.is_active = bool(is_available)

        self._audit(
            organization_id=account.organization_id,
            account_id=account_id,
            asin=product.asin,
            sku=product.sku,
            field=CatalogChangeField.AVAILABILITY,
            old_value=old_value,
            new_value=new_value,
            status=CatalogChangeStatus.SUCCESS,
        )
        await self.db.flush()

        return AvailabilityResult(
            asin=product.asin,
            sku=product.sku,
            is_available=is_available,
            pushed_quantity=effective_quantity,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _resolve_product(
        self,
        account_id: UUID,
        asin: Optional[str] = None,
        sku: Optional[str] = None,
    ) -> Optional[Product]:
        if not asin and not sku:
            return None
        stmt = select(Product).where(Product.account_id == account_id)
        if asin:
            stmt = stmt.where(Product.asin == asin)
        if sku:
            stmt = stmt.where(Product.sku == sku)
        result = await self.db.execute(stmt)
        return result.scalars().first()

    @staticmethod
    def generate_template_bytes() -> bytes:
        """Return an Excel template for bulk listing updates."""
        columns = ["sku", "asin", "title", "bullet_1", "bullet_2", "bullet_3",
                   "bullet_4", "bullet_5", "description", "search_terms"]
        df = pd.DataFrame(columns=columns)
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="listings")
        return buffer.getvalue()


def _row_to_listing_attributes(row: pd.Series) -> Dict[str, List[Dict[str, Any]]]:
    """Translate a spreadsheet row into SP-API attribute patches."""
    attributes: Dict[str, List[Dict[str, Any]]] = {}
    bullet_values: List[str] = []

    for column, attribute in LISTING_TEXT_FIELDS.items():
        value = row.get(column)
        if value is None or (isinstance(value, float) and pd.isna(value)):
            continue
        text = str(value).strip()
        if not text:
            continue

        if attribute == "bullet_point":
            bullet_values.append(text)
            continue

        if attribute == "generic_keyword":
            attributes[attribute] = [{"value": text}]
        else:
            attributes[attribute] = [{"value": text}]

    if bullet_values:
        attributes["bullet_point"] = [{"value": v} for v in bullet_values]

    return attributes


def _row_listing_snapshot(row: pd.Series) -> Dict[str, Any]:
    fields: Dict[str, Any] = {}
    for column in LISTING_TEXT_FIELDS:
        value = row.get(column)
        if value is None or (isinstance(value, float) and pd.isna(value)):
            continue
        fields[column] = str(value)
    return fields


_CURRENCY_BY_MARKETPLACE = {
    "IT": "EUR", "DE": "EUR", "FR": "EUR", "ES": "EUR", "NL": "EUR",
    "BE": "EUR", "PL": "PLN", "SE": "SEK", "TR": "TRY",
    "UK": "GBP", "GB": "GBP",
    "US": "USD", "CA": "CAD", "MX": "MXN", "BR": "BRL",
    "JP": "JPY", "AU": "AUD", "IN": "INR", "AE": "AED", "SG": "SGD",
}


def _marketplace_currency(country_code: str) -> str:
    return _CURRENCY_BY_MARKETPLACE.get((country_code or "").upper(), "EUR")
