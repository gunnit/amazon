"""Amazon SP-API client wrapper using python-amazon-sp-api."""
import time
import json
import logging
import functools
from datetime import date, datetime
from decimal import Decimal
from typing import Optional, List, Dict, Any

from sp_api.base import Marketplaces, SellingApiRequestThrottledException
from sp_api.api import (
    Reports,
    Inventories,
    CatalogItems,
    Products,
    Orders,
    VendorOrders,
)

from app.config import settings
from app.core.exceptions import AmazonAPIError

logger = logging.getLogger(__name__)

# Map country codes to SP-API Marketplace enums
MARKETPLACE_MAP: Dict[str, Marketplaces] = {
    "IT": Marketplaces.IT,
    "DE": Marketplaces.DE,
    "FR": Marketplaces.FR,
    "ES": Marketplaces.ES,
    "UK": Marketplaces.UK,
    "GB": Marketplaces.UK,
    "US": Marketplaces.US,
    "CA": Marketplaces.CA,
    "MX": Marketplaces.MX,
    "BR": Marketplaces.BR,
    "JP": Marketplaces.JP,
    "AU": Marketplaces.AU,
    "IN": Marketplaces.IN,
    "AE": Marketplaces.AE,
    "SG": Marketplaces.SG,
    "NL": Marketplaces.NL,
    "SE": Marketplaces.SE,
    "PL": Marketplaces.PL,
    "TR": Marketplaces.TR,
    "BE": Marketplaces.BE,
}


def resolve_marketplace(country_code: str) -> Marketplaces:
    """Convert a country code to an SP-API Marketplaces enum."""
    mp = MARKETPLACE_MAP.get(country_code.upper())
    if not mp:
        raise AmazonAPIError(
            f"Unsupported marketplace country code: {country_code}",
            error_code="INVALID_MARKETPLACE",
        )
    return mp


def with_throttle_retry(max_retries: int = 3, base_delay: float = 2.0):
    """Decorator for retrying on SP-API throttling exceptions with exponential backoff."""

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except SellingApiRequestThrottledException as e:
                    last_exc = e
                    if attempt == max_retries:
                        break
                    backoff = base_delay * (2 ** attempt)
                    # Respect Retry-After header if present
                    headers = getattr(e, "headers", None) or {}
                    retry_after = headers.get("Retry-After") if isinstance(headers, dict) else None
                    if retry_after:
                        try:
                            retry_after = float(retry_after)
                            backoff = max(backoff, retry_after)
                        except (ValueError, TypeError):
                            pass
                    logger.warning(
                        f"SP-API throttled on {func.__name__}, "
                        f"attempt {attempt + 1}/{max_retries}, "
                        f"retrying in {backoff:.1f}s"
                    )
                    time.sleep(backoff)
            raise AmazonAPIError(
                f"SP-API throttled after {max_retries} retries on {func.__name__}: {last_exc}",
                error_code="THROTTLED",
            )

        return wrapper
    return decorator


class SPAPIClient:
    """Synchronous SP-API client for use in Celery workers."""

    def __init__(self, credentials: dict, marketplace: Marketplaces, account_type: str = "seller"):
        self.marketplace = marketplace
        self.credentials = credentials
        self.account_type = account_type  # "seller" or "vendor"

        # Build kwargs for SP-API constructors
        self._api_kwargs: Dict[str, Any] = {
            "marketplace": self.marketplace,
            "refresh_token": credentials["refresh_token"],
            "credentials": {
                "lwa_app_id": credentials.get("lwa_app_id"),
                "lwa_client_secret": credentials.get("lwa_client_secret"),
            },
        }

        # Add AWS credentials only if provided
        aws_access = credentials.get("aws_access_key")
        aws_secret = credentials.get("aws_secret_key")
        role_arn = credentials.get("role_arn")
        if aws_access and aws_secret and role_arn:
            self._api_kwargs["credentials"]["aws_access_key"] = aws_access
            self._api_kwargs["credentials"]["aws_secret_key"] = aws_secret
            self._api_kwargs["credentials"]["role_arn"] = role_arn

    @property
    def is_vendor(self) -> bool:
        return self.account_type == "vendor"

    def _reports_api(self) -> Reports:
        return Reports(**self._api_kwargs)

    def _inventories_api(self) -> Inventories:
        return Inventories(**self._api_kwargs)

    def _catalog_api(self, version: str = "2022-04-01") -> CatalogItems:
        return CatalogItems(**self._api_kwargs, version=version)

    def _products_api(self) -> Products:
        return Products(**self._api_kwargs)

    def _orders_api(self) -> Orders:
        return Orders(**self._api_kwargs)

    def _vendor_orders_api(self) -> VendorOrders:
        return VendorOrders(**self._api_kwargs)

    @with_throttle_retry(max_retries=3, base_delay=2.0)
    def smoke_test(self) -> dict:
        """Validate SP-API authentication with a lightweight call."""
        try:
            if self.is_vendor:
                api = self._vendor_orders_api()
                api.get_purchase_orders(
                    createdAfter=(datetime.utcnow()).isoformat(),
                )
            else:
                api = self._orders_api()
                api.get_orders(
                    CreatedAfter=(datetime.utcnow()).isoformat(),
                )
            return {
                "status": "ok",
                "marketplace": self.marketplace.name,
                "account_type": self.account_type,
                "timestamp": datetime.utcnow().isoformat(),
            }
        except SellingApiRequestThrottledException:
            raise  # Let the retry decorator handle it
        except Exception as e:
            raise AmazonAPIError(
                f"SP-API authentication failed: {e}",
                error_code="AUTH_FAILED",
            ) from e

    def request_and_download_report(
        self,
        report_type: str,
        start_date: date,
        end_date: date,
        report_options: Optional[dict] = None,
    ) -> dict:
        """Request a report, poll until done, and download the result."""
        api = self._reports_api()

        create_params = {
            "reportType": report_type,
            "dataStartTime": start_date.isoformat(),
            "dataEndTime": end_date.isoformat(),
            "marketplaceIds": [self.marketplace.marketplace_id],
        }
        if report_options:
            create_params["reportOptions"] = report_options

        # Create report
        logger.info(f"Creating report {report_type} for {start_date} to {end_date}")
        create_response = api.create_report(**create_params)
        report_id = create_response.payload.get("reportId")
        if not report_id:
            raise AmazonAPIError(
                f"No reportId returned when creating {report_type}",
                error_code="REPORT_CREATE_FAILED",
            )

        # Poll for completion
        poll_interval = settings.SP_API_REPORT_POLL_INTERVAL_SECONDS
        max_attempts = settings.SP_API_REPORT_POLL_MAX_ATTEMPTS
        for attempt in range(max_attempts):
            time.sleep(poll_interval)
            status_response = api.get_report(report_id)
            status = status_response.payload.get("processingStatus")
            logger.debug(
                f"Report {report_id} status: {status} (attempt {attempt + 1}/{max_attempts})"
            )

            if status == "DONE":
                doc_id = status_response.payload.get("reportDocumentId")
                if not doc_id:
                    raise AmazonAPIError(
                        f"Report {report_id} DONE but no reportDocumentId",
                        error_code="REPORT_NO_DOCUMENT",
                    )
                # Download the report document
                doc_response = api.get_report_document(doc_id, download=True)
                return doc_response.payload
            elif status in ("FATAL", "CANCELLED"):
                raise AmazonAPIError(
                    f"Report {report_id} ended with status {status}",
                    error_code=f"REPORT_{status}",
                )

        raise AmazonAPIError(
            f"Report {report_id} timed out after {max_attempts * poll_interval}s",
            error_code="REPORT_TIMEOUT",
        )

    @with_throttle_retry(max_retries=3, base_delay=2.0)
    def get_sales_report(self, start_date: date, end_date: date) -> Dict[str, List[Dict]]:
        """Get sales and traffic report data (by date and by ASIN)."""
        report_data = self.request_and_download_report(
            report_type="GET_SALES_AND_TRAFFIC_REPORT",
            start_date=start_date,
            end_date=end_date,
            report_options={
                "dateGranularity": "DAY",
                "asinGranularity": "CHILD",
            },
        )

        # The downloaded report may be:
        # 1) raw JSON string
        # 2) metadata dict with JSON payload inside "document"
        if isinstance(report_data, str):
            report_data = json.loads(report_data)
        elif isinstance(report_data, dict) and "document" in report_data:
            document = report_data.get("document")
            if isinstance(document, (bytes, bytearray)):
                document = document.decode("utf-8")
            if isinstance(document, str):
                report_data = json.loads(document)
            elif isinstance(document, dict):
                report_data = document

        by_date = report_data.get("salesAndTrafficByDate", [])
        by_asin = report_data.get("salesAndTrafficByAsin", [])

        logger.info(
            f"Sales report returned {len(by_date)} daily rows and {len(by_asin)} ASIN rows"
        )
        return {"by_date": by_date, "by_asin": by_asin}

    @with_throttle_retry(max_retries=3, base_delay=2.0)
    def get_inventory_summaries(self) -> List[Dict]:
        """Get FBA inventory summaries with pagination."""
        api = self._inventories_api()
        all_items = []
        next_token = None

        while True:
            kwargs = {
                "details": True,
                "granularityType": "Marketplace",
                "granularityId": self.marketplace.marketplace_id,
            }
            if next_token:
                kwargs["nextToken"] = next_token

            response = api.get_inventory_summary_marketplace(**kwargs)
            payload = response.payload

            items = payload.get("inventorySummaries", [])
            all_items.extend(items)

            next_token = payload.get("nextToken")
            if not next_token:
                break

        logger.info(f"Inventory returned {len(all_items)} items")
        return all_items

    @with_throttle_retry(max_retries=3, base_delay=2.0)
    def get_catalog_item_details(self, asin: str) -> Optional[Dict]:
        """Get catalog item details including title, brand, category, and BSR."""
        try:
            api = self._catalog_api()
            response = api.get_catalog_item(
                asin=asin,
                marketplaceIds=self.marketplace.marketplace_id,
                includedData=["summaries", "salesRanks", "classifications"],
            )
            return response.payload
        except Exception as e:
            logger.warning(f"Failed to get catalog details for {asin}: {e}")
            return None

    @with_throttle_retry(max_retries=3, base_delay=2.0)
    def get_competitive_pricing(self, asin: str) -> Optional[Decimal]:
        """Get competitive pricing for a product."""
        try:
            if self.is_vendor:
                logger.debug(
                    "Skipping pricing lookup for %s because Product Pricing API is seller-only",
                    asin,
                )
                return None

            api = self._products_api()
            response = api.get_competitive_pricing_for_asins([asin])
            price = self._extract_price_amount(response.payload)
            if price is not None:
                return price

            # Fallback: lowest offers by ASIN often contain pricing when
            # competitive pricing does not expose it in CompetitivePrices.
            offers_response = api.get_item_offers(asin=asin, item_condition="New")
            return self._extract_price_amount(offers_response.payload)
        except Exception as e:
            logger.warning(f"Failed to get competitive pricing for {asin}: {e}")
            return None

    def _extract_price_amount(self, payload: Any) -> Optional[Decimal]:
        """Extract a representative price from Product Pricing payloads."""
        candidates: List[Decimal] = []

        def add_amount(container: Optional[Dict[str, Any]]):
            if not isinstance(container, dict):
                return
            amount = container.get("Amount")
            if amount is None:
                return
            try:
                candidates.append(Decimal(str(amount)))
            except Exception:
                return

        def add_price_node(node: Any):
            if not isinstance(node, dict):
                return

            # Prefer landed price when present, then listing/buying price.
            add_amount(node.get("LandedPrice"))
            add_amount(node.get("ListingPrice"))
            add_amount(node.get("BuyingPrice"))
            add_amount(node.get("price"))

            price_node = node.get("Price")
            if isinstance(price_node, dict):
                add_amount(price_node.get("LandedPrice"))
                add_amount(price_node.get("ListingPrice"))
                if price_node.get("Amount") is not None:
                    add_amount({"Amount": price_node.get("Amount")})

            shipping = node.get("Shipping")
            listing = node.get("ListingPrice")
            if isinstance(listing, dict) and isinstance(shipping, dict):
                listing_amount = listing.get("Amount")
                shipping_amount = shipping.get("Amount")
                if listing_amount is not None and shipping_amount is not None:
                    try:
                        candidates.append(
                            Decimal(str(listing_amount)) + Decimal(str(shipping_amount))
                        )
                    except Exception:
                        pass

        def walk(node: Any):
            if isinstance(node, list):
                for item in node:
                    walk(item)
                return
            if not isinstance(node, dict):
                return

            add_price_node(node)

            for key in (
                "CompetitivePrices",
                "LowestPrices",
                "BuyBoxPrices",
                "Offers",
                "price",
                "Price",
            ):
                value = node.get(key)
                if value is not None:
                    walk(value)

            product = node.get("Product")
            if isinstance(product, dict):
                walk(product)

            competitive = node.get("CompetitivePricing")
            if isinstance(competitive, dict):
                walk(competitive)

            summary = node.get("Summary")
            if isinstance(summary, dict):
                walk(summary)

        walk(payload)
        return candidates[0] if candidates else None

    @with_throttle_retry(max_retries=3, base_delay=3.0)
    def search_competitor_asins(
        self,
        keywords: str,
        source_asin: str,
        source_brand: Optional[str] = None,
        max_results: int = 10,
    ) -> List[Dict]:
        """Search catalog for competitor products, excluding the source ASIN.

        Returns list of dicts with: asin, title, brand, classifications.
        """
        try:
            api = self._catalog_api()
            response = api.search_catalog_items(
                keywords=keywords,
                marketplaceIds=self.marketplace.marketplace_id,
                includedData=["summaries", "salesRanks", "classifications"],
                pageSize=min(max_results + 5, 20),  # fetch extra to filter
            )
            items = response.payload.get("items", [])
            results = []
            for item in items:
                asin = item.get("asin", "")
                if asin == source_asin:
                    continue  # skip the source product

                summaries = item.get("summaries", [])
                summary = summaries[0] if summaries else {}
                brand = summary.get("brand", "")

                # Optionally skip same-brand products
                if source_brand and brand and brand.lower() == source_brand.lower():
                    continue

                result = {
                    "asin": asin,
                    "title": summary.get("itemName"),
                    "brand": brand or None,
                    "classifications": item.get("classifications", []),
                    "salesRanks": item.get("salesRanks", []),
                }
                results.append(result)

                if len(results) >= max_results:
                    break

            logger.info(
                f"Competitor search for '{keywords[:50]}' returned "
                f"{len(results)} results (source={source_asin})"
            )
            return results
        except SellingApiRequestThrottledException:
            raise
        except AmazonAPIError:
            raise
        except Exception as e:
            logger.exception(f"Catalog search failed for '{keywords[:50]}': {e}")
            raise AmazonAPIError(
                f"Catalog search failed: {e}",
                error_code="CATALOG_SEARCH_FAILED",
            )

    @with_throttle_retry(max_retries=3, base_delay=3.0)
    def search_catalog_by_keyword(
        self,
        keywords: str,
        max_results: int = 20,
    ) -> List[Dict]:
        """Search catalog by keyword/brand and return products with metrics.

        Unlike search_competitor_asins, this does NOT filter out any
        specific ASIN or brand — it returns all matching products.
        Used by Market Tracker 360.
        """
        try:
            api = self._catalog_api()
            response = api.search_catalog_items(
                keywords=keywords,
                marketplaceIds=self.marketplace.marketplace_id,
                includedData=["summaries", "salesRanks", "classifications"],
                pageSize=min(max_results, 20),
            )
            items = response.payload.get("items", [])
            results = []
            for item in items:
                asin = item.get("asin", "")
                summaries = item.get("summaries", [])
                summary = summaries[0] if summaries else {}

                # Extract BSR
                bsr = None
                sales_ranks = item.get("salesRanks", [])
                for rank_list in sales_ranks:
                    for rank in rank_list.get("ranks", []):
                        if rank.get("link") is None:
                            bsr = rank.get("value")
                            break
                    if bsr is not None:
                        break

                # Extract category
                category = None
                classifications = item.get("classifications", [])
                if classifications:
                    category = classifications[0].get("displayName")

                result = {
                    "asin": asin,
                    "title": summary.get("itemName"),
                    "brand": summary.get("brand") or None,
                    "category": category,
                    "bsr": bsr,
                }
                results.append(result)

                if len(results) >= max_results:
                    break

            logger.info(
                f"Market search for '{keywords[:50]}' returned {len(results)} results"
            )
            return results
        except SellingApiRequestThrottledException:
            raise
        except AmazonAPIError:
            raise
        except Exception as e:
            logger.exception(f"Market search failed for '{keywords[:50]}': {e}")
            raise AmazonAPIError(
                f"Market search failed: {e}",
                error_code="MARKET_SEARCH_FAILED",
            )

    # ---- Vendor-specific methods ----

    @with_throttle_retry(max_retries=3, base_delay=2.0)
    def get_vendor_purchase_orders(
        self,
        start_date: date,
        end_date: date,
    ) -> List[Dict]:
        """Get vendor purchase orders for the given date range."""
        api = self._vendor_orders_api()
        all_orders = []
        next_token = None

        while True:
            kwargs = {
                "createdAfter": datetime.combine(start_date, datetime.min.time()).isoformat(),
                "createdBefore": datetime.combine(end_date, datetime.max.time()).isoformat(),
            }
            if next_token:
                kwargs["nextToken"] = next_token

            response = api.get_purchase_orders(**kwargs)
            payload = response.payload or {}

            orders = payload.get("orders", [])
            all_orders.extend(orders)

            pagination = payload.get("pagination", {})
            next_token = pagination.get("nextToken")
            if not next_token:
                break

        logger.info(f"Vendor purchase orders returned {len(all_orders)} orders")
        return all_orders

    @with_throttle_retry(max_retries=3, base_delay=2.0)
    def get_vendor_sales_report(self, start_date: date, end_date: date) -> Dict[str, Any]:
        """Get vendor sales data via Reports API with vendor-specific report type."""
        report_data = self.request_and_download_report(
            report_type="GET_VENDOR_SALES_DIAGNOSTIC_REPORT",
            start_date=start_date,
            end_date=end_date,
            report_options={
                "reportPeriod": "DAY",
                "sellingProgram": "RETAIL",
            },
        )

        if isinstance(report_data, str):
            report_data = json.loads(report_data)
        elif isinstance(report_data, dict) and "document" in report_data:
            document = report_data.get("document")
            if isinstance(document, (bytes, bytearray)):
                document = document.decode("utf-8")
            if isinstance(document, str):
                report_data = json.loads(document)
            elif isinstance(document, dict):
                report_data = document

        logger.info(f"Vendor sales report returned data keys: {list(report_data.keys()) if isinstance(report_data, dict) else 'non-dict'}")
        return report_data if isinstance(report_data, dict) else {}
