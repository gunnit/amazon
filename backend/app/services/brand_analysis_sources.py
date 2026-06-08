"""Data source adapters for the Brand Analysis pipeline.

The Brand Analysis pipeline (metrics → narrative → PPTX) is fed by a
:class:`ParsedBrandExport` per year. The adapters here all produce that
same dataclass so the downstream code does not care whether the data
came from Inthezon's internal SP-API + Market Research path or from
manually uploaded external yearly exports.

Adapters:

* :class:`AmazonAccountDataSource` — the canonical production path.
  Aggregates Inthezon ``sales_data`` for a connected Amazon account by
  ASIN and year, then enriches catalog fields (title, brand,
  subcategory, rating, reviews, images, sellers, Buy Box) via Market
  Research's :func:`_fetch_product_data` helper. Per-ASIN catalog
  results are cached for the lifetime of the adapter so the 2024 and
  2025 years share the same lookup.
* :class:`ManualUploadDataSource` — fallback for when internal data is
  incomplete. Wraps the generic :func:`parse_brand_export` parser.
* :class:`Helium10ApiDataSource` — deprecated. Kept only as a
  forward-compatible boundary for a hypothetical future official API.
  The processor no longer selects it.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Optional, Protocol
from uuid import UUID

import pandas as pd
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.amazon_account import AmazonAccount
from app.models.brand_analysis import AsinOfferSnapshot
from app.models.product import Product
from app.models.sales_data import SalesData
from app.services.data_extraction import DAILY_TOTAL_ASIN
from app.services.sales_metrics import display_revenue_expr, display_units_expr
from app.services.brand_analysis_service import (
    InsufficientDataError,
    ParsedBrandExport,
    brand_matches,
    normalize_brand_text,
    parse_brand_export,
)
logger = logging.getLogger(__name__)


class BrandDataSource(Protocol):
    """Adapter contract for delivering one year of Brand Analysis source data."""

    source_name: str

    async def fetch_year(self, year: int) -> ParsedBrandExport: ...

    def describe(self) -> dict: ...


@dataclass
class AmazonAccountDataSource:
    """Adapter that builds a :class:`ParsedBrandExport` from Inthezon's
    internal Amazon data.

    This is the canonical production path for Brand Analysis. For each
    requested calendar year it:

    1. Aggregates ``sales_data`` (per-day per-ASIN totals already synced
       from SP-API) into per-ASIN revenue and units.
    2. Optionally filters by an explicit ``asin_list`` (ASIN-list mode)
       and/or by brand name (the catalog ``brand`` field, case-insensitive).
    3. Enriches each surviving ASIN with catalog metadata through Market
       Research's :func:`_fetch_product_data` helper. Per-ASIN catalog
       results are cached for the lifetime of the adapter so 2024 and
       2025 share one set of catalog lookups.

    No field is fabricated when SP-API does not surface it — missing
    catalog values stay ``None`` and the downstream metric layer handles
    them as N/A. Counts of ASINs whose enrichment failed are tracked so
    the processor can mark the job with a
    ``catalog_enrichment_partial`` code if a significant fraction of
    ASINs lack catalog data.
    """

    db: AsyncSession
    account_id: UUID
    organization_id: UUID
    brand_filter: Optional[str] = None
    asin_list: Optional[list[str]] = None
    source_name: str = "internal"
    _catalog_cache: dict[str, dict] = field(default_factory=dict)
    enrichment_failed_asins: set[str] = field(default_factory=set)
    enrichment_attempted: int = 0
    discovered_asins: set[str] = field(default_factory=set)
    discovery_errors: list[str] = field(default_factory=list)
    year_diagnostics: dict[int, dict[str, Any]] = field(default_factory=dict)
    _scope_asins_cache: Optional[set[str]] = None
    _account_marketplace_id_cache: Optional[str] = None

    async def fetch_year(self, year: int) -> ParsedBrandExport:
        start = date(year, 1, 1)
        end = date(year, 12, 31)
        scope_asins = await self._resolve_scope_asins()
        account_summary = await self._year_sales_summary(year)

        units_expr = (
            func.coalesce(func.sum(display_units_expr()), 0)
            + func.coalesce(func.sum(SalesData.units_ordered_b2b), 0)
        )
        revenue_expr = (
            func.coalesce(func.sum(display_revenue_expr()), 0)
            + func.coalesce(func.sum(SalesData.ordered_product_sales_b2b), 0)
        )
        stmt = (
            select(
                SalesData.asin.label("asin"),
                units_expr.label("units"),
                revenue_expr.label("revenue"),
            )
            .where(
                and_(
                    SalesData.account_id == self.account_id,
                    SalesData.date >= start,
                    SalesData.date <= end,
                    SalesData.asin != DAILY_TOTAL_ASIN,
                )
            )
            .group_by(SalesData.asin)
        )
        if scope_asins:
            stmt = stmt.where(SalesData.asin.in_(sorted(scope_asins)))

        result = await self.db.execute(stmt)
        rows = result.all()
        if scope_asins:
            rows = [row for row in rows if str(row[0] or "").upper() in scope_asins]
        sales_by_asin = {
            str(asin or "").upper(): {
                "units": float(units or 0) if units is not None else None,
                "revenue": float(revenue or 0),
            }
            for asin, units, revenue in rows
            if asin
        }

        if not rows and not scope_asins and not account_summary["has_sales"]:
            raise InsufficientDataError(
                year=year,
                source_name=self.source_name,
                detail=self._year_gap_detail(year, account_summary),
            )

        if scope_asins and not account_summary["has_sales"]:
            raise InsufficientDataError(
                year=year,
                source_name=self.source_name,
                detail=self._year_gap_detail(year, account_summary, scoped_asins=len(scope_asins)),
            )

        candidate_asins = sorted(scope_asins | set(sales_by_asin)) if scope_asins else sorted(sales_by_asin)
        if not candidate_asins:
            # The account has other sales in this year, but none for the scoped
            # brand/ASIN set. Return discovered ASINs as zero-revenue rows when
            # possible; otherwise surface a recovery path.
            if scope_asins:
                candidate_asins = sorted(scope_asins)
            else:
                raise InsufficientDataError(
                    year=year,
                    source_name=self.source_name,
                    detail=(
                        f"No ASIN could be resolved for '{self.brand_filter or 'the requested scope'}'. "
                        "Provide an explicit ASIN list, sync the catalog, or upload external yearly exports."
                    ),
                )

        enriched_rows: list[dict[str, Any]] = []
        matched_sales_count = 0
        for asin in candidate_asins:
            sales = sales_by_asin.get(asin, {"units": 0, "revenue": 0})
            units = sales.get("units")
            revenue = float(sales.get("revenue") or 0)
            if asin in sales_by_asin:
                matched_sales_count += 1
            catalog = await self._get_catalog(asin)
            if not self._catalog_matches_scope(catalog, explicit_asin=bool(self.asin_list)):
                continue
            title = catalog.get("title") or asin
            category = catalog.get("category")
            subcategory = catalog.get("subcategory") or category or "Uncategorized"
            sellers_count = catalog.get("sellers_count")
            offer_count = catalog.get("offer_count") or sellers_count
            buy_box_owner = catalog.get("buy_box_owner")
            await self._save_offer_snapshot(asin, catalog)
            # Brand Analysis uses the process rule from the legacy prompt:
            # zero-revenue ASINs are considered inactive for the performance
            # audit, even if the current catalog listing is technically live.
            status = "active" if revenue > 0 else "inactive"
            enriched_rows.append(
                {
                    "asin": asin,
                    "title": title,
                    "product_name": title,
                    "brand": catalog.get("brand"),
                    "category": category,
                    "subcategory": subcategory,
                    "revenue": float(revenue or 0),
                    "units": float(units or 0) if units is not None else None,
                    "price": catalog.get("price"),
                    "rating": catalog.get("rating"),
                    "reviews": catalog.get("review_count"),
                    "images": catalog.get("images_count"),
                    "image_count": catalog.get("images_count"),
                    "sellers": sellers_count,
                    "seller_count": sellers_count,
                    "reseller_count": sellers_count,
                    "offer_count": offer_count,
                    "buy_box_owner": buy_box_owner,
                    "buy_box_seller": buy_box_owner,
                    "bsr": catalog.get("bsr"),
                    "status": status,
                    "bullets": catalog.get("bullets"),
                    "bullet_count": catalog.get("bullet_count"),
                    "description": catalog.get("description"),
                    "aplus_content": catalog.get("aplus_content"),
                    "has_aplus_content": catalog.get("has_aplus_content"),
                    "aplus_module_count": catalog.get("aplus_module_count"),
                    "text_module_count": catalog.get("text_module_count"),
                    "image_module_count": catalog.get("image_module_count"),
                    "aplus_source": catalog.get("aplus_source"),
                    "aplus_limitation": catalog.get("aplus_limitation"),
                    "fulfillment": catalog.get("fulfillment"),
                    "fba_fees": catalog.get("fba_fees"),
                    "actual_fba_fees": catalog.get("actual_fba_fees"),
                    "estimated_fba_fees": catalog.get("estimated_fba_fees"),
                    "fee_source": catalog.get("fee_source"),
                    "fee_confidence": catalog.get("fee_confidence"),
                    "fee_limitation": catalog.get("fee_limitation"),
                }
            )

        self.year_diagnostics[year] = {
            **account_summary,
            "scope_asins_count": len(scope_asins),
            "discovered_asins_count": len(self.discovered_asins),
            "scoped_sales_asins_count": matched_sales_count,
            "zero_revenue_asins_count": max(len(enriched_rows) - matched_sales_count, 0),
            "scope_source": "asin_list" if self.asin_list else "brand_discovery",
            "discovery_errors": list(self.discovery_errors),
        }

        if not enriched_rows:
            raise InsufficientDataError(
                year=year,
                source_name=self.source_name,
                detail=(
                    f"No ASIN matched brand filter '{self.brand_filter}' "
                    f"with sales in {year}. Try providing an ASIN list "
                    "explicitly, or upload an external yearly export."
                ),
            )

        df = pd.DataFrame(enriched_rows)
        columns = [
            "asin",
            "title",
            "product_name",
            "brand",
            "category",
            "subcategory",
            "revenue",
            "units",
            "price",
            "rating",
            "reviews",
            "images",
            "image_count",
            "sellers",
            "seller_count",
            "reseller_count",
            "offer_count",
            "buy_box_owner",
            "buy_box_seller",
            "bsr",
            "status",
            "bullets",
            "bullet_count",
            "description",
            "aplus_content",
            "has_aplus_content",
            "aplus_module_count",
            "text_module_count",
            "image_module_count",
            "aplus_source",
            "aplus_limitation",
            "fulfillment",
            "fba_fees",
            "actual_fba_fees",
            "estimated_fba_fees",
            "fee_source",
            "fee_confidence",
            "fee_limitation",
        ]
        return ParsedBrandExport(
            rows=df,
            columns=columns,
            row_count=len(enriched_rows),
            source_name=self.source_name,
            year=year,
            validation=None,
        )

    @property
    def enrichment_partial(self) -> bool:
        """True if a non-trivial fraction of ASIN catalog lookups failed."""
        if self.enrichment_attempted == 0:
            return False
        return len(self.enrichment_failed_asins) / max(self.enrichment_attempted, 1) >= 0.2

    async def _resolve_scope_asins(self) -> set[str]:
        """Resolve the ASIN universe for this analysis before loading yearly revenue.

        ASIN-list jobs are deterministic: use the provided list. Brand jobs
        combine local catalog matches with SP-API catalog search results via
        the Market Research client. The resulting scope is cached so 2024 and
        2025 use the same product universe and zero-revenue ASINs can be
        represented consistently.
        """
        if self._scope_asins_cache is not None:
            return set(self._scope_asins_cache)

        explicit = {
            asin.strip().upper()
            for asin in (self.asin_list or [])
            if asin and asin.strip()
        }
        if explicit:
            self._scope_asins_cache = explicit
            return set(explicit)

        scope: set[str] = set()
        scope.update(await self._discover_asins_from_local_products())
        scope.update(await self._discover_asins_via_market_research())

        self.discovered_asins = set(scope)
        self._scope_asins_cache = set(scope)
        return set(scope)

    async def _discover_asins_from_local_products(self) -> set[str]:
        if not self.brand_filter:
            return set()

        result = await self.db.execute(
            select(Product).where(Product.account_id == self.account_id)
        )
        products = list(result.scalars().all())
        discovered: set[str] = set()
        for product in products:
            asin = str(getattr(product, "asin", "") or "").upper()
            if not asin:
                continue
            title = getattr(product, "title", None)
            brand = getattr(product, "brand", None)
            title_matches = normalize_brand_text(self.brand_filter) in normalize_brand_text(title)
            if brand_matches(brand, self.brand_filter) or title_matches:
                discovered.add(asin)
                self._catalog_cache.setdefault(
                    asin,
                    {
                        "asin": asin,
                        "title": title,
                        "brand": brand,
                        "category": getattr(product, "category", None),
                        "subcategory": getattr(product, "subcategory", None),
                        "price": float(product.current_price) if getattr(product, "current_price", None) is not None else None,
                        "bsr": int(product.current_bsr) if getattr(product, "current_bsr", None) is not None else None,
                        "review_count": int(product.review_count) if getattr(product, "review_count", None) is not None else None,
                        "rating": float(product.rating) if getattr(product, "rating", None) is not None else None,
                        "status": (
                            "active"
                            if bool(getattr(product, "is_active", False) and getattr(product, "is_available", False))
                            else "inactive"
                        ),
                        "_discovery_snapshot": True,
                    },
                )
        return discovered

    async def _discover_asins_via_market_research(self) -> set[str]:
        if not self.brand_filter:
            return set()

        try:
            client = await self._build_sp_api_client()
            if client is None:
                return set()
            raw_results = client.search_catalog_by_keyword(self.brand_filter, max_results=80)
        except Exception as exc:
            logger.warning("Brand Analysis market discovery failed for %s: %s", self.brand_filter, exc)
            self.discovery_errors.append(str(exc)[:200])
            return set()

        discovered: set[str] = set()
        target_norm = normalize_brand_text(self.brand_filter)
        for item in raw_results or []:
            asin = str(item.get("asin") or "").upper()
            if not asin:
                continue
            item_brand = item.get("brand")
            item_title = item.get("title")
            title_matches = bool(target_norm and target_norm in normalize_brand_text(item_title))
            if not (brand_matches(item_brand, self.brand_filter) or title_matches):
                continue
            discovered.add(asin)
            self._catalog_cache.setdefault(
                asin,
                {
                    "asin": asin,
                    "title": item_title,
                    "brand": item_brand,
                    "category": item.get("category"),
                    "subcategory": item.get("subcategory") or item.get("category"),
                    "price": item.get("price"),
                    "bsr": item.get("bsr"),
                    "review_count": item.get("review_count"),
                    "rating": item.get("rating"),
                    "_discovery_snapshot": True,
                },
            )
        return discovered

    async def _year_sales_summary(self, year: int) -> dict[str, Any]:
        start = date(year, 1, 1)
        end = date(year, 12, 31)
        result = await self.db.execute(
            select(
                func.count(SalesData.id),
                func.count(func.distinct(SalesData.asin)),
                func.min(SalesData.date),
                func.max(SalesData.date),
            ).where(
                and_(
                    SalesData.account_id == self.account_id,
                    SalesData.date >= start,
                    SalesData.date <= end,
                    SalesData.asin != DAILY_TOTAL_ASIN,
                )
            )
        )
        row = result.one()
        row_count = int(row[0] or 0)
        first_date = row[2]
        last_date = row[3]
        complete_year = bool(row_count and first_date and last_date and first_date <= start and last_date >= end)
        missing_periods: list[str] = []
        if row_count and first_date and first_date > start:
            missing_periods.append(f"{start.isoformat()} to {(first_date).isoformat()}")
        if row_count and last_date and last_date < end:
            missing_periods.append(f"{(last_date).isoformat()} to {end.isoformat()}")
        return {
            "year": year,
            "has_sales": row_count > 0,
            "account_sales_rows": row_count,
            "account_sales_asins": int(row[1] or 0),
            "first_sales_date": first_date.isoformat() if first_date else None,
            "last_sales_date": last_date.isoformat() if last_date else None,
            "complete_year": complete_year,
            "missing_periods": missing_periods,
        }

    def _year_gap_detail(self, year: int, summary: dict[str, Any], scoped_asins: int = 0) -> str:
        asin_clause = f" Scope currently contains {scoped_asins} ASINs." if scoped_asins else ""
        return (
            f"Inthezon has no synced sales_data rows for this account in {year}."
            f"{asin_clause} Sync the Amazon account for {year}, check the account connection, "
            "provide an explicit ASIN list if the brand query is too broad, or upload an external yearly product export."
        )

    def _catalog_matches_scope(self, catalog: dict[str, Any], *, explicit_asin: bool = False) -> bool:
        if explicit_asin or not self.brand_filter:
            return True
        brand = catalog.get("brand")
        title = catalog.get("title")
        if brand and brand_matches(brand, self.brand_filter):
            return True
        if title and normalize_brand_text(self.brand_filter) in normalize_brand_text(title):
            return True
        # If discovery gave us the ASIN but SP-API does not expose brand/title
        # on enrichment, keep it and mark catalog enrichment as partial rather
        # than silently dropping a potentially valid zero-revenue ASIN.
        return not (brand or title)

    async def _get_catalog(self, asin: str) -> dict:
        cached = self._catalog_cache.get(asin)
        if cached and cached.get("_fully_enriched"):
            return cached

        self.enrichment_attempted += 1
        catalog: dict[str, Any] = dict(cached or {})
        if not catalog:
            catalog = await self._fetch_catalog_from_local_products(asin)
        try:
            remote_catalog = await self._fetch_catalog_via_market_research(asin)
            if remote_catalog:
                catalog.update({key: value for key, value in remote_catalog.items() if value is not None})
            if not catalog or not (catalog.get("title") or catalog.get("brand") or catalog.get("category")):
                self.enrichment_failed_asins.add(asin)
        except Exception:
            logger.exception("Catalog enrichment failed for %s; falling back to empty snapshot", asin)
            if not catalog:
                catalog = {"asin": asin}
                self.enrichment_failed_asins.add(asin)
        catalog["_fully_enriched"] = True
        self._catalog_cache[asin] = catalog
        return catalog

    async def _fetch_catalog_from_local_products(self, asin: str) -> dict:
        """Use the locally synced products table before making SP-API calls."""
        result = await self.db.execute(
            select(Product).where(
                Product.account_id == self.account_id,
                Product.asin == asin,
            )
        )
        product = result.scalar_one_or_none()
        if not product:
            return {}

        status = "active" if bool(product.is_active and product.is_available) else "inactive"
        return {
            "asin": asin,
            "title": product.title,
            "brand": product.brand,
            "category": product.category,
            "subcategory": product.subcategory,
            "price": float(product.current_price) if product.current_price is not None else None,
            "bsr": int(product.current_bsr) if product.current_bsr is not None else None,
            "review_count": int(product.review_count) if product.review_count is not None else None,
            "rating": float(product.rating) if product.rating is not None else None,
            "status": status,
        }

    async def _build_sp_api_client(self):
        from app.core.amazon.credentials import resolve_credentials
        from app.core.amazon.sp_api_client import SPAPIClient, resolve_marketplace
        from app.models.user import Organization

        account_result = await self.db.execute(
            select(AmazonAccount).where(
                AmazonAccount.id == self.account_id,
                AmazonAccount.organization_id == self.organization_id,
            )
        )
        account = account_result.scalar_one_or_none()
        if not account:
            return None

        org_result = await self.db.execute(
            select(Organization).where(Organization.id == self.organization_id)
        )
        organization = org_result.scalar_one_or_none()
        credentials = resolve_credentials(account, organization)
        marketplace = resolve_marketplace(account.marketplace_country)
        client = SPAPIClient(
            credentials,
            marketplace,
            account_type=account.account_type.value,
        )
        self._account_marketplace_id_cache = account.marketplace_id
        return client

    async def _fetch_catalog_via_market_research(self, asin: str) -> dict:
        """Use Market Research's SP-API client to enrich one ASIN's catalog fields."""
        from app.services.market_research_service import _fetch_product_data

        client = await self._build_sp_api_client()
        if client is None:
            return {"asin": asin}
        # _fetch_product_data is synchronous; we run it inline. With a small
        # number of ASINs per analysis this is acceptable; for larger sets a
        # bounded thread pool can be added later without changing this API.
        catalog = _fetch_product_data(client, asin)
        if catalog.get("price") is not None:
            try:
                fee = client.estimate_fba_fee_for_asin(asin, float(catalog["price"]))
                if fee is not None:
                    catalog["estimated_fba_fees"] = float(fee)
                    catalog["fee_source"] = "product_fees_api"
                    catalog["fee_confidence"] = "estimated"
                else:
                    catalog["fee_source"] = "unavailable"
                    catalog["fee_confidence"] = "unavailable"
                    catalog["fee_limitation"] = "Product Fees API did not return a usable fee estimate."
            except Exception as exc:
                logger.info("FBA fee estimate unavailable for %s: %s", asin, exc)
                catalog["fee_source"] = "unavailable"
                catalog["fee_confidence"] = "unavailable"
                catalog["fee_limitation"] = str(exc)[:300]
        else:
            catalog["fee_source"] = "unavailable"
            catalog["fee_confidence"] = "unavailable"
            catalog["fee_limitation"] = "Current price is unavailable, so Product Fees API estimates cannot be requested."
        try:
            aplus = client.get_aplus_content_for_asin(asin)
            catalog.update({key: value for key, value in aplus.items() if key != "raw_payload"})
        except Exception as exc:
            logger.info("A+ content lookup unavailable for %s: %s", asin, exc)
            catalog.setdefault("has_aplus_content", None)
            catalog.setdefault("aplus_source", "unavailable")
            catalog.setdefault("aplus_limitation", str(exc)[:300])
        return catalog

    async def _save_offer_snapshot(self, asin: str, catalog: dict[str, Any]) -> None:
        """Persist current offer metadata when Product Pricing returned it."""
        if not self.db or not hasattr(self.db, "add"):
            return
        offer_snapshot = catalog.get("offer_snapshot") or {}
        has_offer_fields = any(
            catalog.get(key) is not None
            for key in ("sellers_count", "offer_count", "buy_box_owner", "price")
        ) or bool(offer_snapshot)
        if not has_offer_fields:
            return
        try:
            marketplace_id = self._account_marketplace_id_cache
            if marketplace_id is None:
                account_result = await self.db.execute(
                    select(AmazonAccount.marketplace_id).where(AmazonAccount.id == self.account_id)
                )
                marketplace_id = account_result.scalar_one_or_none()
                self._account_marketplace_id_cache = marketplace_id
            if not marketplace_id:
                return

            price = (
                offer_snapshot.get("buy_box_price")
                if offer_snapshot.get("buy_box_price") is not None
                else catalog.get("price")
            )
            snapshot = AsinOfferSnapshot(
                organization_id=self.organization_id,
                account_id=self.account_id,
                marketplace_id=marketplace_id,
                asin=asin,
                observed_at=datetime.utcnow(),
                seller_count=offer_snapshot.get("seller_count") or catalog.get("sellers_count"),
                offer_count=offer_snapshot.get("offer_count") or catalog.get("offer_count") or catalog.get("sellers_count"),
                buy_box_owner_name=offer_snapshot.get("buy_box_owner_name") or catalog.get("buy_box_owner"),
                buy_box_seller_id=offer_snapshot.get("buy_box_seller_id"),
                buy_box_price=price,
                fulfillment_channel=offer_snapshot.get("fulfillment_channel") or catalog.get("fulfillment"),
                is_fba=offer_snapshot.get("is_fba"),
                source="product_pricing_snapshot",
                raw_payload=offer_snapshot.get("raw_payload") or offer_snapshot or None,
            )
            self.db.add(snapshot)
            await self.db.flush()
        except Exception as exc:
            logger.info("Failed to persist offer snapshot for %s: %s", asin, exc)

    def describe_readiness(self) -> dict[str, Any]:
        return {
            "years": self.year_diagnostics,
            "discovered_asins": sorted(self.discovered_asins),
            "discovered_asins_count": len(self.discovered_asins),
            "catalog_enrichment": {
                "attempted": self.enrichment_attempted,
                "failed_asins": sorted(self.enrichment_failed_asins),
                "partial": self.enrichment_partial,
            },
            "discovery_errors": list(self.discovery_errors),
        }

    def describe(self) -> dict:
        return {
            "name": self.source_name,
            "details": {
                "account_id": str(self.account_id),
                "brand_filter": self.brand_filter,
                "asin_filter_count": len(self.asin_list or []),
                "discovered_asins_count": len(self.discovered_asins),
            },
        }


@dataclass
class ManualUploadDataSource:
    """Adapter backed by user-uploaded external yearly product exports.

    Supports any CSV/XLSX export keyed by ASIN with revenue columns.
    Column-alias detection lives in :func:`parse_brand_export`.
    """

    source_files: dict[int, tuple[bytes, str]]  # year -> (data, filename)
    source_name: str = "manual_upload"

    async def fetch_year(self, year: int) -> ParsedBrandExport:
        if year not in self.source_files:
            raise InsufficientDataError(
                year=year,
                source_name=self.source_name,
                detail=f"no external export uploaded for {year}",
            )
        data, filename = self.source_files[year]
        return parse_brand_export(data, filename, year=year)

    def describe(self) -> dict:
        return {
            "name": self.source_name,
            "details": {"years": sorted(self.source_files.keys())},
        }


@dataclass
class Helium10ApiDataSource:
    """Deprecated. Forward-compatible boundary for a hypothetical future
    official Helium10 Enterprise API.

    The processor no longer selects this adapter — Brand Analysis is
    autonomous and Helium10 is not a required dependency. The class
    stays here so any legacy job rows or tests that reference it still
    raise cleanly via :class:`Helium10UnavailableError`.
    """

    market_id: Optional[str] = None
    source_name: str = "helium10_api"

    async def fetch_year(self, year: int) -> ParsedBrandExport:
        from app.services.helium10_service import Helium10Service, Helium10UnavailableError

        service = Helium10Service()
        service.fetch_products_for_year(market_id=self.market_id, year=year)
        raise Helium10UnavailableError("Unreachable: Helium10Service should have raised")

    def describe(self) -> dict:
        return {
            "name": self.source_name,
            "details": {"market_id": self.market_id, "deprecated": True},
        }
