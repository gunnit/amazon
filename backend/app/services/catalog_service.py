"""Catalog write operations against the Amazon SP-API Listings Items API.

Reads from the local Product table, pushes changes through SP-API,
then mirrors the successful change locally.
"""
from __future__ import annotations

import io
import logging
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional
from uuid import UUID

import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AmazonAPIError
from app.models.amazon_account import AmazonAccount, AccountType
from app.models.product import Product

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

    def __init__(self, db: AsyncSession):
        self.db = db

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

    # ------------------------------------------------------------------
    # Bulk listing updates (title / bullets / description / keywords)
    # ------------------------------------------------------------------

    async def bulk_update_from_excel(
        self,
        account_id: UUID,
        file_bytes: bytes,
        product_type: str = "PRODUCT",
    ) -> Dict[str, Any]:
        """Apply bulk listing content updates from an Excel file.

        Expected columns (all optional except sku): sku, title, bullet_1..5, description, search_terms.
        """
        account = await self._require_seller_account(account_id)
        organization = await self._load_organization(account)
        client = self._create_sp_api_client(account, organization)

        df = pd.read_excel(io.BytesIO(file_bytes))
        if "sku" not in df.columns:
            raise CatalogOperationError("Excel must contain a 'sku' column")

        successes: List[Dict[str, Any]] = []
        errors: List[Dict[str, Any]] = []

        for _, row in df.iterrows():
            sku = str(row.get("sku") or "").strip()
            if not sku:
                continue

            attributes = _row_to_listing_attributes(row)
            if not attributes:
                continue

            try:
                client.update_listing_attributes(
                    seller_id=account.seller_id,
                    sku=sku,
                    product_type=product_type,
                    attributes=attributes,
                )
                await self._mirror_local_listing(account_id, sku, row)
                successes.append({"sku": sku, "fields": list(attributes.keys())})
            except AmazonAPIError as exc:
                logger.warning("SP-API listing update failed for %s: %s", sku, exc)
                errors.append({"sku": sku, "error": str(exc)})
            except Exception as exc:  # noqa: BLE001
                logger.exception("Unexpected failure updating listing %s", sku)
                errors.append({"sku": sku, "error": str(exc)})

        await self.db.flush()

        return {
            "account_id": str(account_id),
            "total_rows": int(len(df)),
            "updated": len(successes),
            "failed": len(errors),
            "successes": successes,
            "errors": errors,
        }

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

    # ------------------------------------------------------------------
    # Price management
    # ------------------------------------------------------------------

    async def update_prices_bulk(
        self,
        account_id: UUID,
        updates: List[Dict[str, Any]],
        product_type: str = "PRODUCT",
    ) -> Dict[str, Any]:
        """Push a list of {asin|sku, price} updates to SP-API."""
        account = await self._require_seller_account(account_id)
        organization = await self._load_organization(account)
        client = self._create_sp_api_client(account, organization)

        currency = _marketplace_currency(account.marketplace_country)
        successes: List[Dict[str, Any]] = []
        errors: List[Dict[str, Any]] = []

        for entry in updates:
            asin = (entry.get("asin") or "").strip() or None
            sku = (entry.get("sku") or "").strip() or None
            raw_price = entry.get("price")

            try:
                new_price = Decimal(str(raw_price))
            except (InvalidOperation, TypeError):
                errors.append({"asin": asin, "sku": sku, "error": f"Invalid price: {raw_price!r}"})
                continue

            product = await self._resolve_product(account_id, asin=asin, sku=sku)
            if not product:
                errors.append({"asin": asin, "sku": sku, "error": "Product not found"})
                continue
            if not product.sku:
                errors.append({"asin": asin, "sku": sku, "error": "Missing SKU for SP-API call"})
                continue

            try:
                client.update_listing_price(
                    seller_id=account.seller_id,
                    sku=product.sku,
                    product_type=product_type,
                    price=new_price,
                    currency=currency,
                )
                product.current_price = new_price
                successes.append({"asin": product.asin, "sku": product.sku, "price": str(new_price)})
            except AmazonAPIError as exc:
                errors.append({"asin": product.asin, "sku": product.sku, "error": str(exc)})
            except Exception as exc:  # noqa: BLE001
                logger.exception("Unexpected failure updating price for %s", product.sku)
                errors.append({"asin": product.asin, "sku": product.sku, "error": str(exc)})

        await self.db.flush()
        return {
            "account_id": str(account_id),
            "updated": len(successes),
            "failed": len(errors),
            "successes": successes,
            "errors": errors,
        }

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
    ) -> Dict[str, Any]:
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
        client.set_listing_quantity(
            seller_id=account.seller_id,
            sku=product.sku,
            product_type=product_type,
            quantity=effective_quantity,
        )

        product.is_available = is_available
        product.is_active = bool(is_available)
        await self.db.flush()

        return {
            "asin": product.asin,
            "sku": product.sku,
            "is_available": is_available,
            "pushed_quantity": effective_quantity,
        }

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


_CURRENCY_BY_MARKETPLACE = {
    "IT": "EUR", "DE": "EUR", "FR": "EUR", "ES": "EUR", "NL": "EUR",
    "BE": "EUR", "PL": "PLN", "SE": "SEK", "TR": "TRY",
    "UK": "GBP", "GB": "GBP",
    "US": "USD", "CA": "CAD", "MX": "MXN", "BR": "BRL",
    "JP": "JPY", "AU": "AUD", "IN": "INR", "AE": "AED", "SG": "SGD",
}


def _marketplace_currency(country_code: str) -> str:
    return _CURRENCY_BY_MARKETPLACE.get((country_code or "").upper(), "EUR")
