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

    def __init__(self, credentials: dict, marketplace: Marketplaces):
        self.marketplace = marketplace
        self.credentials = credentials

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

    def _reports_api(self) -> Reports:
        return Reports(**self._api_kwargs)

    def _inventories_api(self) -> Inventories:
        return Inventories(**self._api_kwargs)

    def _catalog_api(self) -> CatalogItems:
        return CatalogItems(**self._api_kwargs)

    def _products_api(self) -> Products:
        return Products(**self._api_kwargs)

    @with_throttle_retry(max_retries=3, base_delay=2.0)
    def smoke_test(self) -> dict:
        """Validate SP-API authentication with a lightweight call."""
        try:
            api = self._inventories_api()
            api.get_inventory_summary_marketplace(
                details=False,
                granularityType="Marketplace",
                granularityId=self.marketplace.marketplace_id,
            )
            return {
                "status": "ok",
                "marketplace": self.marketplace.name,
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
    def get_sales_report(self, start_date: date, end_date: date) -> List[Dict]:
        """Get sales and traffic report data (by ASIN, daily granularity)."""
        report_data = self.request_and_download_report(
            report_type="GET_SALES_AND_TRAFFIC_REPORT",
            start_date=start_date,
            end_date=end_date,
            report_options={
                "dateGranularity": "DAY",
                "asinGranularity": "CHILD",
            },
        )

        # The downloaded report is a JSON document
        if isinstance(report_data, str):
            report_data = json.loads(report_data)

        # Extract the sales and traffic rows
        rows = []
        sales_traffic = report_data.get("salesAndTrafficByAsin", [])
        for entry in sales_traffic:
            rows.append(entry)

        logger.info(f"Sales report returned {len(rows)} ASIN-day rows")
        return rows

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
                marketplaceIds=[self.marketplace.marketplace_id],
                includedData=["summaries", "salesRanks"],
            )
            return response.payload
        except Exception as e:
            logger.warning(f"Failed to get catalog details for {asin}: {e}")
            return None

    @with_throttle_retry(max_retries=3, base_delay=2.0)
    def get_competitive_pricing(self, asin: str) -> Optional[Decimal]:
        """Get competitive pricing for a product."""
        try:
            api = self._products_api()
            response = api.get_competitive_pricing_for_asins([asin])
            products = response.payload or []
            for product in products:
                prices = product.get("Product", {}).get(
                    "CompetitivePricing", {}
                ).get("CompetitivePrices", [])
                for price_entry in prices:
                    landed = price_entry.get("Price", {}).get("LandedPrice", {})
                    amount = landed.get("Amount")
                    if amount is not None:
                        return Decimal(str(amount))
            return None
        except Exception as e:
            logger.warning(f"Failed to get competitive pricing for {asin}: {e}")
            return None
