"""Product type requirements (R1, R4).

Amazon's Product Type Definitions API says which attributes a product type
requires. The list feeds the "attributes" traffic light and new-item
validation. Offer attributes are dropped: they are not content. Results are
cached in ``product_type_definitions_cache`` for ``settings.PTD_CACHE_DAYS``.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from sqlalchemy import select

from app.config import settings
from app.core.exceptions import AmazonAPIError
from app.models.catalog_monitor import ProductTypeDefinitionCache
from app.services.catalog_monitor.content import VOLATILE_ATTRIBUTES

logger = logging.getLogger(__name__)

_OFFER_ATTRIBUTES = VOLATILE_ATTRIBUTES | {
    "externally_assigned_product_identifier",
    "merchant_suggested_asin",
}


def required_attributes_from_schema(schema: dict) -> list[str]:
    """Top-level required attributes of a product type schema, minus offer ones."""
    required = (schema or {}).get("required") or []
    return sorted({name for name in required if name not in _OFFER_ATTRIBUTES})


def _is_fresh(fetched_at: Optional[datetime]) -> bool:
    if fetched_at is None:
        return False
    if fetched_at.tzinfo is None:
        fetched_at = fetched_at.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - fetched_at < timedelta(days=settings.PTD_CACHE_DAYS)


class ProductTypeDefinitionService:
    def __init__(self, db):
        self.db = db

    async def required_attributes(
        self,
        client,
        marketplace_id: str,
        product_type: str,
        seller_id: Optional[str] = None,
    ) -> Optional[list[str]]:
        """Required attributes for ``product_type``; ``None`` if unknown.

        Never raises on API failure: falls back to a stale cache row, else None.
        Does not commit; the caller owns the transaction.
        """
        row = (
            await self.db.execute(
                select(ProductTypeDefinitionCache).where(
                    ProductTypeDefinitionCache.marketplace_id == marketplace_id,
                    ProductTypeDefinitionCache.product_type == product_type,
                )
            )
        ).scalar_one_or_none()
        if row is not None and _is_fresh(row.fetched_at):
            return list(row.required_attributes)

        try:
            definition = client.get_product_type_definition(product_type, seller_id=seller_id)
            link = ((definition.get("schema") or {}).get("link") or {}).get("resource")
            if not link:
                raise ValueError("product type definition has no schema link")
            schema = client.fetch_json_schema(link)
        except (AmazonAPIError, httpx.HTTPError, ValueError) as exc:
            logger.warning("Product type definition unavailable for %s: %s", product_type, exc)
            return list(row.required_attributes) if row is not None else None

        required = required_attributes_from_schema(schema)
        names = sorted((schema.get("properties") or {}).keys())
        if row is None:
            row = ProductTypeDefinitionCache(
                marketplace_id=marketplace_id, product_type=product_type
            )
            self.db.add(row)
        row.required_attributes = required
        row.property_names = names
        row.fetched_at = datetime.now(timezone.utc)
        return required
