"""Which Amazon APIs an account can use, and its vendor code (R1-R4).

Each check is one cheap read call. A failure is recorded, never raised, so a
Vendor account without Listings access is reported rather than breaking the scan.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.amazon_account import AccountType, AmazonAccount
from app.models.catalog_monitor import CatalogApiCapability
from app.models.product import Product
from app.services.catalog_monitor.clients import (
    ClientFactory,
    default_client_factory,
    load_organization,
)
from app.services.catalog_monitor.repository import CatalogMonitorRepository

CAPABILITY_KEYS = ("catalog_items", "listings_read", "product_type_definitions", "aplus", "feeds")

_FALLBACK_PRODUCT_TYPE = "PRODUCT"


def _error_text(exc: Exception) -> str:
    return f"{type(exc).__name__}: {exc}"[:200]


def _run(check: Callable[[], Any]) -> dict:
    try:
        check()
    except Exception as exc:  # noqa: BLE001 - a probe never raises
        return {"ok": False, "error": _error_text(exc)}
    return {"ok": True, "error": None}


def _skipped(reason: str) -> dict:
    return {"ok": False, "error": reason}


def listing_seller_id(
    account: AmazonAccount, capability: Optional[CatalogApiCapability]
) -> Optional[str]:
    """Seller id for Listings Items calls: the seller id, or a vendor's vendor code."""
    if account.account_type == AccountType.VENDOR:
        return capability.vendor_code if capability else None
    return account.seller_id


def probe_capabilities(
    client: Any, account: AmazonAccount, sample_asin: Optional[str], sample_sku: Optional[str]
) -> tuple[dict, Optional[str]]:
    """Run one read call per API. Returns (results, vendor_code); never raises."""
    vendor_code: Optional[str] = None
    if account.account_type == AccountType.VENDOR:
        try:
            vendor_code = client.resolve_vendor_code()
        except Exception:  # noqa: BLE001
            vendor_code = None
    seller_id = vendor_code if account.account_type == AccountType.VENDOR else account.seller_id

    results: dict = {}
    catalog_payload: dict = {}
    if sample_asin is None:
        results["catalog_items"] = _skipped("no_sample_asin")
    else:

        def _catalog() -> None:
            catalog_payload.update(client.get_catalog_item_full(sample_asin) or {})

        results["catalog_items"] = _run(_catalog)

    if not seller_id or not sample_sku:
        results["listings_read"] = _skipped("no_listing_identity")
    else:
        results["listings_read"] = _run(lambda: client.get_listing(seller_id, sample_sku))

    product_type = _sample_product_type(catalog_payload) or _FALLBACK_PRODUCT_TYPE
    results["product_type_definitions"] = _run(
        lambda: client.get_product_type_definition(product_type)
    )

    if sample_asin is None:
        results["aplus"] = _skipped("no_sample_asin")
    else:
        results["aplus"] = _run(lambda: client.get_aplus_publish_record_count(sample_asin))

    results["feeds"] = _run(lambda: client.list_recent_feeds(page_size=1))
    return results, vendor_code


def _sample_product_type(catalog_payload: dict) -> Optional[str]:
    """Product type of the sample from the Catalog payload, if it reports one."""
    for entry in catalog_payload.get("productTypes") or []:
        if isinstance(entry, dict) and entry.get("productType"):
            return entry["productType"]
    return None


async def _pick_sample(db: AsyncSession, account_id) -> tuple[Optional[str], Optional[str]]:
    result = await db.execute(
        select(Product)
        .where(Product.account_id == account_id, Product.is_active.is_(True), Product.asin.isnot(None))
        .order_by(Product.updated_at.desc())
        .limit(1)
    )
    product = result.scalar_one_or_none()
    if product is None:
        return None, None
    return product.asin, product.sku or None


async def check_account_capabilities(
    db: AsyncSession,
    account: AmazonAccount,
    client_factory: ClientFactory = default_client_factory,
) -> CatalogApiCapability:
    """Probe the account's Amazon APIs and store the result (caller commits)."""
    organization = await load_organization(db, account)
    client = client_factory(account, organization)
    asin, sku = await _pick_sample(db, account.id)
    results, vendor_code = probe_capabilities(client, account, asin, sku)
    return await CatalogMonitorRepository(db).save_capability(
        account.id, results, vendor_code, datetime.now(timezone.utc)
    )
