"""Capability detection for Brand Analysis source selection."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Optional

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.exceptions import AmazonAPIError
from app.models.amazon_account import AmazonAccount
from app.models.brand_analysis import BrandAnalysisCapability
from app.models.product import Product
from app.models.sales_data import SalesData

logger = logging.getLogger(__name__)


CAPABILITY_KEYS = (
    "sales_and_traffic_available",
    "data_kiosk_available",
    "brand_analytics_available",
    "brand_registry_available_or_inferred",
    "product_pricing_available",
    "product_fees_available",
    "aplus_available",
    "finance_reports_available",
    "settlement_reports_available",
    "catalog_items_available",
    "listings_available",
)

# Capabilities whose data the Brand Analysis pipeline actually consumes (not just
# probes). Everything else is detected-only: the probe confirms the role/access
# but no metric reads it yet. Keeping this explicit lets the UI matrix show
# "detected vs integrated" honestly instead of implying probe == coverage.
INTEGRATED_CAPABILITIES = frozenset(
    {
        "sales_and_traffic_available",
        "brand_analytics_available",
        "product_pricing_available",
        "product_fees_available",
        "aplus_available",
        "catalog_items_available",
    }
)


@dataclass
class CapabilityProbeResult:
    """Normalized capability matrix and diagnostics."""

    organization_id: str
    account_id: str
    marketplace_id: str
    checked_at: datetime
    capabilities: dict[str, bool] = field(default_factory=lambda: {key: False for key in CAPABILITY_KEYS})
    missing_roles: list[str] = field(default_factory=list)
    last_error_by_capability: dict[str, str] = field(default_factory=dict)
    raw_diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        # The flat ``**self.capabilities`` booleans below are the existing shape
        # the frontend reads and mean "detected" (probe succeeded). The new
        # ``integrated``/``capability_status`` fields are additive: they expose
        # whether the pipeline actually consumes each detected source, so the UI
        # can distinguish "probed only" from "actually used".
        integrated = {
            key: bool(self.capabilities.get(key)) and key in INTEGRATED_CAPABILITIES
            for key in CAPABILITY_KEYS
        }
        capability_status = {
            key: {
                "detected": bool(self.capabilities.get(key)),
                "integrated": integrated[key],
            }
            for key in CAPABILITY_KEYS
        }
        return {
            "organization_id": self.organization_id,
            "account_id": self.account_id,
            "marketplace_id": self.marketplace_id,
            "checked_at": self.checked_at.isoformat(),
            **self.capabilities,
            "integrated_capabilities": integrated,
            "capability_status": capability_status,
            "missing_roles": list(dict.fromkeys(self.missing_roles)),
            "last_error_by_capability": dict(self.last_error_by_capability),
            "raw_diagnostics": dict(self.raw_diagnostics),
        }


def _error_text(exc: Exception) -> str:
    if isinstance(exc, AmazonAPIError):
        return f"{exc.error_code or 'AMAZON_API_ERROR'}: {exc.message}"
    return str(exc) or exc.__class__.__name__


def _is_permission_error(exc: Exception) -> bool:
    text = _error_text(exc).lower()
    name = exc.__class__.__name__.lower()
    return any(
        marker in text or marker in name
        for marker in (
            "forbidden",
            "unauthorized",
            "not authorized",
            "access denied",
            "accessdenied",
            "missing role",
            "restricted",
            "403",
            "401",
        )
    )


def _role_reason(capability: str, exc: Exception) -> str:
    reason = _error_text(exc).strip()
    if not reason:
        reason = exc.__class__.__name__
    return f"{capability}: {reason[:300]}"


async def _sample_product(db: AsyncSession, account_id) -> tuple[Optional[str], Optional[str], Optional[float]]:
    result = await db.execute(
        select(Product.asin, Product.sku, Product.current_price)
        .where(Product.account_id == account_id)
        .limit(1)
    )
    row = result.first()
    if row:
        price = float(row.current_price) if row.current_price is not None else None
        return row.asin, row.sku, price

    result = await db.execute(
        select(SalesData.asin)
        .where(SalesData.account_id == account_id)
        .where(SalesData.asin != "__DAILY_TOTAL__")
        .limit(1)
    )
    asin = result.scalar_one_or_none()
    return asin, None, None


async def _has_sales_data(db: AsyncSession, account_id) -> bool:
    result = await db.execute(
        select(func.count(SalesData.id)).where(SalesData.account_id == account_id)
    )
    return bool(result.scalar_one() or 0)


async def detect_brand_analysis_capabilities(
    db: AsyncSession,
    account: AmazonAccount,
    *,
    organization: Any = None,
    client_factory: Optional[Callable[[AmazonAccount, Any], Any]] = None,
    sample_asin: Optional[str] = None,
    sample_sku: Optional[str] = None,
    sample_price: Optional[float] = None,
    now: Optional[datetime] = None,
    persist: bool = True,
    force_refresh: bool = False,
) -> CapabilityProbeResult:
    """Detect Brand Analysis capabilities without requiring reauthorization.

    Existing warehouse data is counted as available even when a remote probe is
    not possible. Remote probes are deliberately small list/read calls; failures
    are recorded per capability and do not block the analysis job.
    """

    checked_at = now or datetime.utcnow()
    marketplace_id = account.marketplace_id

    if not force_refresh:
        cached_result = await db.execute(
            select(BrandAnalysisCapability)
            .where(
                BrandAnalysisCapability.organization_id == account.organization_id,
                BrandAnalysisCapability.account_id == account.id,
                BrandAnalysisCapability.marketplace_id == marketplace_id,
            )
        )
        cached = cached_result.scalar_one_or_none()
        ttl = timedelta(hours=settings.BRAND_ANALYSIS_CAPABILITY_CACHE_TTL_HOURS)
        if cached and cached.checked_at and checked_at - cached.checked_at < ttl:
            return CapabilityProbeResult(
                organization_id=str(account.organization_id),
                account_id=str(account.id),
                marketplace_id=marketplace_id,
                checked_at=cached.checked_at,
                capabilities={key: bool(getattr(cached, key)) for key in CAPABILITY_KEYS},
                missing_roles=list(cached.missing_roles or []),
                last_error_by_capability=dict(cached.last_error_by_capability or {}),
                raw_diagnostics=dict(cached.raw_diagnostics or {}),
            )

    if sample_asin is None or sample_sku is None or sample_price is None:
        discovered_asin, discovered_sku, discovered_price = await _sample_product(db, account.id)
        sample_asin = sample_asin or discovered_asin
        sample_sku = sample_sku or discovered_sku
        sample_price = sample_price if sample_price is not None else discovered_price

    result = CapabilityProbeResult(
        organization_id=str(account.organization_id),
        account_id=str(account.id),
        marketplace_id=marketplace_id,
        checked_at=checked_at,
        raw_diagnostics={
            "sample_asin": sample_asin,
            "sample_sku_present": bool(sample_sku),
            "sample_price_present": sample_price is not None,
            "account_type": getattr(getattr(account, "account_type", None), "value", account.account_type),
        },
    )

    if await _has_sales_data(db, account.id):
        result.capabilities["sales_and_traffic_available"] = True
        result.raw_diagnostics["sales_and_traffic_source"] = "internal_sales_data"

    try:
        if client_factory is not None:
            client = client_factory(account, organization)
        else:
            from app.services.data_extraction import DataExtractionService

            client = DataExtractionService(db)._create_sp_api_client(account, organization)
    except Exception as exc:
        reason = _role_reason("sp_api_credentials", exc)
        result.last_error_by_capability["sp_api_credentials"] = reason
        result.missing_roles.append(reason)
        if persist:
            await persist_brand_analysis_capabilities(db, result)
        return result

    def probe(capability: str, operation: Callable[[], Any], *, role_name: Optional[str] = None) -> None:
        try:
            payload = operation()
            result.capabilities[capability] = True
            result.raw_diagnostics[f"{capability}_probe"] = _summarize_payload(payload)
        except Exception as exc:
            reason = _role_reason(role_name or capability, exc)
            result.last_error_by_capability[capability] = reason
            if _is_permission_error(exc):
                result.missing_roles.append(reason)
            logger.info("Brand Analysis capability %s unavailable for account %s: %s", capability, account.id, reason)

    def reports_get(report_type: str) -> Any:
        api = client._reports_api()
        return api.get_reports(
            reportTypes=[report_type],
            marketplaceIds=[client.marketplace.marketplace_id],
            pageSize=1,
        ).payload

    if not result.capabilities["sales_and_traffic_available"]:
        probe(
            "sales_and_traffic_available",
            lambda: reports_get("GET_SALES_AND_TRAFFIC_REPORT"),
            role_name="Reports/Sales and Traffic",
        )
    else:
        # Still probe Reports permissions when possible so missing role reasons
        # are visible even if warehouse rows already exist.
        probe(
            "sales_and_traffic_available",
            lambda: reports_get("GET_SALES_AND_TRAFFIC_REPORT"),
            role_name="Reports/Sales and Traffic",
        )
        result.capabilities["sales_and_traffic_available"] = True

    probe(
        "brand_analytics_available",
        lambda: reports_get("GET_BRAND_ANALYTICS_SEARCH_TERMS_REPORT"),
        role_name="Brand Analytics",
    )
    probe(
        "settlement_reports_available",
        lambda: reports_get("GET_V2_SETTLEMENT_REPORT_DATA_FLAT_FILE"),
        role_name="Settlement Reports",
    )
    probe(
        "finance_reports_available",
        lambda: client._finances_api().list_financial_event_groups(MaxResultsPerPage=1).payload,
        role_name="Finances",
    )
    probe(
        "data_kiosk_available",
        lambda: client._data_kiosk_api().get_queries(pageSize=1).payload,
        role_name="Data Kiosk",
    )

    if sample_asin:
        probe(
            "catalog_items_available",
            lambda: client._catalog_api().get_catalog_item(
                asin=sample_asin,
                marketplaceIds=client.marketplace.marketplace_id,
                includedData=["summaries"],
            ).payload,
            role_name="Catalog Items",
        )
        if not getattr(client, "is_vendor", False):
            probe(
                "product_pricing_available",
                lambda: client._products_api().get_item_offers(asin=sample_asin, item_condition="New").payload,
                role_name="Product Pricing",
            )
        else:
            result.last_error_by_capability["product_pricing_available"] = "Product Pricing: seller-only SP-API endpoint"
    else:
        result.last_error_by_capability["catalog_items_available"] = "Catalog Items: no sample ASIN available for a safe probe"
        result.last_error_by_capability["product_pricing_available"] = "Product Pricing: no sample ASIN available for a safe probe"

    if sample_asin and sample_price is not None and not getattr(client, "is_vendor", False):
        probe(
            "product_fees_available",
            lambda: client._product_fees_api().get_product_fees_estimate_for_asin(
                sample_asin,
                price=float(sample_price),
                currency="EUR",
                marketplace_id=client.marketplace.marketplace_id,
                is_fba=True,
            ).payload,
            role_name="Product Fees",
        )
    else:
        result.last_error_by_capability["product_fees_available"] = (
            "Product Fees: no sample ASIN/price available for a safe estimate"
        )

    probe(
        "aplus_available",
        lambda: client._aplus_content_api().search_content_documents(
            marketplaceId=client.marketplace.marketplace_id,
            pageSize=1,
        ).payload,
        role_name="A+ Content / Brand Registry",
    )
    result.capabilities["brand_registry_available_or_inferred"] = result.capabilities["aplus_available"]
    if not result.capabilities["aplus_available"] and "aplus_available" in result.last_error_by_capability:
        result.last_error_by_capability["brand_registry_available_or_inferred"] = result.last_error_by_capability["aplus_available"]

    if sample_sku and account.seller_id:
        probe(
            "listings_available",
            lambda: client._listings_api().get_listings_item(
                sellerId=account.seller_id,
                sku=sample_sku,
                marketplaceIds=[client.marketplace.marketplace_id],
                includedData=["summaries"],
            ).payload,
            role_name="Listings Items",
        )
    else:
        result.last_error_by_capability["listings_available"] = "Listings Items: no seller_id/SKU available for a safe probe"

    if persist:
        await persist_brand_analysis_capabilities(db, result)
    return result


def _summarize_payload(payload: Any) -> dict[str, Any]:
    if payload is None:
        return {"payload": None}
    if isinstance(payload, dict):
        return {"type": "dict", "keys": sorted(str(key) for key in payload.keys())[:20]}
    if isinstance(payload, list):
        return {"type": "list", "length": len(payload)}
    return {"type": type(payload).__name__}


async def persist_brand_analysis_capabilities(db: AsyncSession, result: CapabilityProbeResult) -> None:
    values = {
        "organization_id": result.organization_id,
        "account_id": result.account_id,
        "marketplace_id": result.marketplace_id,
        "checked_at": result.checked_at,
        **result.capabilities,
        "missing_roles": list(dict.fromkeys(result.missing_roles)),
        "last_error_by_capability": result.last_error_by_capability,
        "raw_diagnostics": result.raw_diagnostics,
    }
    stmt = pg_insert(BrandAnalysisCapability).values(**values)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_brand_analysis_capabilities_org_account_marketplace",
        set_={key: stmt.excluded[key] for key in values if key != "id"},
    )
    await db.execute(stmt)
    await db.flush()
