"""Amazon SP-API client wrapper using python-amazon-sp-api."""
from __future__ import annotations

import csv
import functools
import io
import json
import logging
import re
import time
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional, List, Dict, Any
from urllib.parse import quote, unquote

from sp_api.base import Marketplaces, SellingApiRequestThrottledException
from sp_api.api import (
    Reports,
    Inventories,
    CatalogItems,
    Products,
    Orders,
    VendorOrders,
    ListingsItems,
)

from app.config import settings
from app.core.exceptions import AmazonAPIError

logger = logging.getLogger(__name__)

RETURN_REASON_ALIASES: Dict[str, str] = {
    "damaged": "Damaged",
    "damaged by carrier": "Damaged",
    "defective": "Defective",
    "customer damaged": "Customer Damaged",
    "wrong item": "Wrong Item",
    "wrong item sent": "Wrong Item",
    "not as described": "Not As Described",
    "arrived too late": "Arrived Late",
    "late delivery": "Arrived Late",
    "no longer needed": "No Longer Needed",
    "unwanted item": "No Longer Needed",
    "better price available": "Better Price Available",
    "performance or quality not adequate": "Performance Or Quality Not Adequate",
    "missing parts or accessories": "Missing Parts Or Accessories",
}

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

    def _listings_api(self) -> ListingsItems:
        return ListingsItems(**self._api_kwargs)

    @staticmethod
    def _format_datetime(value: date | datetime | str) -> str:
        """Format a date-like value for SP-API request parameters."""
        if isinstance(value, date) and not isinstance(value, datetime):
            value = datetime.combine(value, datetime.min.time())
        if isinstance(value, datetime):
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            else:
                value = value.astimezone(timezone.utc)
            return value.isoformat().replace("+00:00", "Z")
        return str(value)

    @with_throttle_retry(max_retries=3, base_delay=2.0)
    def _create_report_request(self, api: Reports, **create_params) -> Dict[str, Any]:
        """Create a report and return the raw payload."""
        return api.create_report(**create_params).payload

    @with_throttle_retry(max_retries=3, base_delay=2.0)
    def _get_report_status(self, api: Reports, report_id: str) -> Dict[str, Any]:
        """Fetch the current processing status for a report."""
        return api.get_report(report_id).payload

    @with_throttle_retry(max_retries=3, base_delay=2.0)
    def _download_report_document(self, api: Reports, document_id: str) -> Dict[str, Any]:
        """Download a report document and return the raw payload."""
        return api.get_report_document(document_id, download=True).payload

    @staticmethod
    def _normalize_report_key(value: Optional[str]) -> str:
        """Normalize report headers for easier lookups."""
        cleaned = (value or "").strip().lstrip("\ufeff").lower()
        return re.sub(r"[^a-z0-9]+", "-", cleaned).strip("-")

    @classmethod
    def _pick_report_value(cls, row: Dict[str, Any], *keys: str) -> Any:
        """Return the first populated value for a set of possible report keys."""
        for key in keys:
            value = row.get(cls._normalize_report_key(key))
            if value not in (None, ""):
                return value
        return None

    @staticmethod
    def _parse_int(value: Any) -> int:
        """Parse an integer-like report value, defaulting blanks to zero."""
        if value in (None, ""):
            return 0
        try:
            return int(Decimal(str(value).strip()))
        except Exception:
            return 0

    @staticmethod
    def _normalize_text_label(value: Any) -> Optional[str]:
        """Normalize free-form text from reports while preserving meaning."""
        if value in (None, ""):
            return None
        cleaned = re.sub(r"\s+", " ", str(value).strip())
        return cleaned or None

    @classmethod
    def _normalize_asin(cls, value: Any) -> Optional[str]:
        """Normalize ASIN-like identifiers for consistent storage."""
        label = cls._normalize_text_label(value)
        if not label:
            return None
        return label.upper()

    @classmethod
    def _normalize_return_reason(cls, value: Any) -> Optional[str]:
        """Canonicalize common return-reason variants for analytics."""
        label = cls._normalize_text_label(value)
        if not label:
            return None

        lookup_key = re.sub(r"[^a-z0-9]+", " ", label.lower()).strip()
        if lookup_key in RETURN_REASON_ALIASES:
            return RETURN_REASON_ALIASES[lookup_key]

        if label.isupper() or label.islower():
            return label.replace("_", " ").replace("-", " ").title()
        return label

    @staticmethod
    def _parse_report_date(value: Any) -> Optional[date]:
        """Parse a date from delimited report content."""
        if value in (None, ""):
            return None
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value

        text = str(value).strip()
        if not text:
            return None

        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
        except ValueError:
            pass

        iso_candidate = text[:10]
        try:
            return date.fromisoformat(iso_candidate)
        except ValueError:
            pass

        for fmt in (
            "%m/%d/%Y",
            "%m/%d/%Y %H:%M:%S",
            "%d/%m/%Y",
            "%d/%m/%Y %H:%M:%S",
            "%d-%m-%Y",
            "%d-%m-%Y %H:%M:%S",
            "%Y/%m/%d",
            "%Y/%m/%d %H:%M:%S",
        ):
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                continue
        return None

    def _extract_report_document_text(self, report_data: Any) -> str:
        """Extract report text from a downloaded document payload."""
        document = report_data
        if isinstance(report_data, dict):
            document = report_data.get("document", report_data)

        if isinstance(document, str):
            return document

        if isinstance(document, (bytes, bytearray)):
            for encoding in ("utf-8-sig", "utf-8", "iso-8859-1"):
                try:
                    return document.decode(encoding)
                except Exception:
                    continue

        raise AmazonAPIError(
            f"Unsupported report document payload type: {type(document).__name__}",
            error_code="REPORT_PARSE_FAILED",
        )

    def _parse_delimited_report_rows(self, document_text: str) -> List[Dict[str, str]]:
        """Parse TSV/CSV report contents into normalized dict rows."""
        sample = document_text[:4096]
        delimiter = "\t" if "\t" in sample else ","
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters="\t,;")
            delimiter = dialect.delimiter
        except csv.Error:
            pass

        reader = csv.DictReader(io.StringIO(document_text), delimiter=delimiter)
        if not reader.fieldnames:
            return []

        rows: List[Dict[str, str]] = []
        for raw_row in reader:
            row = {
                self._normalize_report_key(key): (value.strip() if isinstance(value, str) else value)
                for key, value in raw_row.items()
                if key
            }
            if any(value not in (None, "") for value in row.values()):
                rows.append(row)
        return rows

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
        create_payload = self._create_report_request(api, **create_params)
        report_id = create_payload.get("reportId")
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
            status_payload = self._get_report_status(api, report_id)
            status = status_payload.get("processingStatus")
            logger.debug(
                f"Report {report_id} status: {status} (attempt {attempt + 1}/{max_attempts})"
            )

            if status == "DONE":
                doc_id = status_payload.get("reportDocumentId")
                if not doc_id:
                    raise AmazonAPIError(
                        f"Report {report_id} DONE but no reportDocumentId",
                        error_code="REPORT_NO_DOCUMENT",
                    )
                # Download the report document
                return self._download_report_document(api, doc_id)
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
    def fetch_orders(
        self,
        created_after: datetime,
        created_before: datetime,
    ) -> List[Dict[str, Any]]:
        """Fetch seller orders with pagination."""
        if self.is_vendor:
            raise AmazonAPIError(
                "Orders API is only available for seller accounts",
                error_code="UNSUPPORTED_ACCOUNT_TYPE",
            )

        api = self._orders_api()
        all_orders: List[Dict[str, Any]] = []
        next_token = None

        while True:
            if next_token:
                response = api.get_orders(NextToken=next_token)
            else:
                response = api.get_orders(
                    CreatedAfter=self._format_datetime(created_after),
                    CreatedBefore=self._format_datetime(created_before),
                    MarketplaceIds=[self.marketplace.marketplace_id],
                )

            payload = response.payload or {}
            orders = payload.get("Orders") or payload.get("orders") or []
            all_orders.extend(orders)

            next_token = payload.get("NextToken") or payload.get("nextToken")
            if not next_token:
                break

        logger.info("Orders API returned %s orders", len(all_orders))
        return all_orders

    @with_throttle_retry(max_retries=3, base_delay=2.0)
    def fetch_order_items(self, order_id: str) -> List[Dict[str, Any]]:
        """Fetch seller order items with pagination."""
        if self.is_vendor:
            raise AmazonAPIError(
                "Orders API is only available for seller accounts",
                error_code="UNSUPPORTED_ACCOUNT_TYPE",
            )

        api = self._orders_api()
        all_items: List[Dict[str, Any]] = []
        next_token = None

        while True:
            if next_token:
                response = api.get_order_items(order_id, NextToken=next_token)
            else:
                response = api.get_order_items(order_id)

            payload = response.payload or {}
            items = (
                payload.get("OrderItems")
                or payload.get("orderItems")
                or payload.get("order_items")
                or []
            )
            all_items.extend(items)

            next_token = payload.get("NextToken") or payload.get("nextToken")
            if not next_token:
                break

        logger.debug("Orders API returned %s items for %s", len(all_items), order_id)
        return all_items

    def fetch_inventory_report(self) -> List[Dict[str, Any]]:
        """Fetch and parse the FBA inventory report via the Reports API."""
        api = self._reports_api()
        report_type = "GET_FBA_MYI_ALL_INVENTORY_DATA"

        logger.info("Creating inventory report %s", report_type)
        create_payload = self._create_report_request(
            api,
            reportType=report_type,
            marketplaceIds=[self.marketplace.marketplace_id],
        )
        report_id = create_payload.get("reportId")
        if not report_id:
            raise AmazonAPIError(
                f"No reportId returned when creating {report_type}",
                error_code="REPORT_CREATE_FAILED",
            )

        delay_seconds = 2.0
        max_delay_seconds = float(max(settings.SP_API_REPORT_POLL_INTERVAL_SECONDS, 2))
        max_attempts = settings.SP_API_REPORT_POLL_MAX_ATTEMPTS

        for attempt in range(max_attempts):
            time.sleep(delay_seconds)
            status_payload = self._get_report_status(api, report_id)
            status = status_payload.get("processingStatus")
            logger.debug(
                "Inventory report %s status: %s (attempt %s/%s)",
                report_id,
                status,
                attempt + 1,
                max_attempts,
            )

            if status == "DONE":
                document_id = status_payload.get("reportDocumentId")
                if not document_id:
                    raise AmazonAPIError(
                        f"Inventory report {report_id} completed without a document ID",
                        error_code="REPORT_NO_DOCUMENT",
                    )
                report_payload = self._download_report_document(api, document_id)
                document_text = self._extract_report_document_text(report_payload)
                rows = self._parse_delimited_report_rows(document_text)

                items: List[Dict[str, Any]] = []
                for row in rows:
                    asin = (row.get("asin") or "").strip()
                    if not asin:
                        continue

                    working_inbound = self._parse_int(row.get("afn-inbound-working-quantity"))
                    shipped_inbound = self._parse_int(row.get("afn-inbound-shipped-quantity"))
                    receiving_inbound = self._parse_int(row.get("afn-inbound-receiving-quantity"))
                    inbound_quantity = (
                        self._parse_int(row.get("inbound-quantity"))
                        if row.get("inbound-quantity") not in (None, "")
                        else working_inbound + shipped_inbound + receiving_inbound
                    )

                    items.append(
                        {
                            "asin": asin,
                            "sku": row.get("sku") or row.get("seller-sku"),
                            "fnsku": row.get("fnsku") or row.get("fn-sku"),
                            "fulfillment_channel": row.get("fulfillment-channel") or "AFN",
                            "quantity": self._parse_int(
                                row.get("afn-fulfillable-quantity") or row.get("quantity")
                            ),
                            "reserved_quantity": self._parse_int(
                                row.get("afn-reserved-quantity") or row.get("reserved-quantity")
                            ),
                            "inbound_working_quantity": working_inbound + receiving_inbound,
                            "inbound_shipped_quantity": shipped_inbound,
                            "inbound_quantity": inbound_quantity,
                        }
                    )

                logger.info("Inventory report returned %d rows", len(items))
                return items

            if status == "DONE_NO_DATA":
                logger.info("Inventory report %s completed with no data", report_id)
                return []

            if status in ("FATAL", "CANCELLED"):
                raise AmazonAPIError(
                    (
                        "Amazon did not generate the FBA inventory report "
                        f"GET_FBA_MYI_ALL_INVENTORY_DATA for marketplace {self.marketplace.marketplace_id}. "
                        f"Report {report_id} ended with status {status}."
                    ),
                    error_code=f"INVENTORY_REPORT_{status}",
                )

            delay_seconds = min(delay_seconds * 2, max_delay_seconds)

        raise AmazonAPIError(
            f"Inventory report {report_id} timed out after {max_attempts} polling attempts",
            error_code="REPORT_TIMEOUT",
        )

    def fetch_returns_report(self) -> List[Dict[str, Any]]:
        """Fetch and parse the FBA customer returns report via the Reports API."""
        if self.is_vendor:
            raise AmazonAPIError(
                "Returns report is only available for seller accounts",
                error_code="UNSUPPORTED_ACCOUNT_TYPE",
            )

        api = self._reports_api()
        report_type = "GET_FBA_FULFILLMENT_CUSTOMER_RETURNS_DATA"

        logger.info("Creating returns report %s", report_type)
        create_payload = self._create_report_request(
            api,
            reportType=report_type,
            marketplaceIds=[self.marketplace.marketplace_id],
        )
        report_id = create_payload.get("reportId")
        if not report_id:
            raise AmazonAPIError(
                f"No reportId returned when creating {report_type}",
                error_code="REPORT_CREATE_FAILED",
            )

        delay_seconds = 2.0
        max_delay_seconds = float(max(settings.SP_API_REPORT_POLL_INTERVAL_SECONDS, 2))
        max_attempts = settings.SP_API_REPORT_POLL_MAX_ATTEMPTS

        for attempt in range(max_attempts):
            time.sleep(delay_seconds)
            status_payload = self._get_report_status(api, report_id)
            status = status_payload.get("processingStatus")
            logger.debug(
                "Returns report %s status: %s (attempt %s/%s)",
                report_id,
                status,
                attempt + 1,
                max_attempts,
            )

            if status == "DONE":
                document_id = status_payload.get("reportDocumentId")
                if not document_id:
                    raise AmazonAPIError(
                        f"Returns report {report_id} completed without a document ID",
                        error_code="REPORT_NO_DOCUMENT",
                    )

                report_payload = self._download_report_document(api, document_id)
                document_text = self._extract_report_document_text(report_payload)
                rows = self._parse_delimited_report_rows(document_text)

                returns: List[Dict[str, Any]] = []
                for row in rows:
                    return_date = self._parse_report_date(
                        self._pick_report_value(
                            row,
                            "return-date",
                            "return-request-date",
                            "return date",
                        )
                    )
                    if return_date is None:
                        logger.debug("Skipping return row without return date: %s", row)
                        continue

                    returns.append(
                        {
                            "amazon_order_id": self._normalize_text_label(
                                self._pick_report_value(row, "amazon-order-id", "order-id", "order id")
                            ),
                            "asin": self._normalize_asin(self._pick_report_value(row, "asin")),
                            "sku": self._normalize_text_label(self._pick_report_value(row, "sku", "seller-sku")),
                            "return_date": return_date,
                            "quantity": self._parse_int(
                                self._pick_report_value(row, "quantity", "quantity-returned")
                            ),
                            "reason": self._normalize_return_reason(
                                self._pick_report_value(row, "reason", "return-reason")
                            ),
                            "disposition": self._normalize_text_label(
                                self._pick_report_value(row, "disposition", "status")
                            ),
                            "detailed_disposition": self._normalize_text_label(
                                self._pick_report_value(
                                    row,
                                    "detailed-disposition",
                                    "detailed disposition",
                                )
                            ),
                        }
                    )

                logger.info("Returns report returned %d normalized rows", len(returns))
                return returns

            if status == "DONE_NO_DATA":
                logger.info("Returns report %s completed with no data", report_id)
                return []

            if status in ("FATAL", "CANCELLED"):
                raise AmazonAPIError(
                    f"Returns report {report_id} ended with status {status}",
                    error_code=f"REPORT_{status}",
                )

            delay_seconds = min(delay_seconds * 2, max_delay_seconds)

        raise AmazonAPIError(
            f"Returns report {report_id} timed out after {max_attempts} polling attempts",
            error_code="REPORT_TIMEOUT",
        )

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
                includedData=["summaries", "salesRanks", "classifications", "attributes"],
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
                catalog_payload = self.get_catalog_item_details(asin)
                if catalog_payload:
                    return self._extract_catalog_price_amount(catalog_payload)
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
            price = self._extract_price_amount(offers_response.payload)
            if price is not None:
                return price

            catalog_payload = self.get_catalog_item_details(asin)
            if catalog_payload:
                return self._extract_catalog_price_amount(catalog_payload)
            return None
        except SellingApiRequestThrottledException:
            raise
        except AmazonAPIError:
            raise
        except Exception as e:
            logger.warning(f"Failed to get competitive pricing for {asin}: {e}")
            catalog_payload = self.get_catalog_item_details(asin)
            if catalog_payload:
                return self._extract_catalog_price_amount(catalog_payload)
            return None

    @staticmethod
    def _extract_asin_from_payload(payload: Any) -> Optional[str]:
        """Extract an ASIN from Product Pricing or batch-offers payload fragments."""
        if not isinstance(payload, dict):
            return None

        for key in ("ASIN", "asin", "Asin"):
            asin = payload.get(key)
            if isinstance(asin, str) and asin.strip():
                return asin.strip().upper()

        identifiers = payload.get("Identifiers")
        if isinstance(identifiers, dict):
            marketplace_asin = (
                identifiers.get("MarketplaceASIN")
                or identifiers.get("MarketplaceAsin")
                or identifiers.get("marketplaceAsin")
            )
            if isinstance(marketplace_asin, dict):
                asin = marketplace_asin.get("ASIN") or marketplace_asin.get("asin")
                if isinstance(asin, str) and asin.strip():
                    return asin.strip().upper()

        identifier = payload.get("Identifier")
        if isinstance(identifier, dict):
            asin = SPAPIClient._extract_asin_from_payload(identifier)
            if asin:
                return asin

        product = payload.get("Product")
        if isinstance(product, dict):
            asin = SPAPIClient._extract_asin_from_payload(product)
            if asin:
                return asin

        return None

    @staticmethod
    def _extract_asin_from_uri(uri: Optional[str]) -> Optional[str]:
        """Parse an ASIN from a Product Pricing item-offers URI."""
        if not uri:
            return None

        marker = "/items/"
        if marker not in uri:
            return None

        tail = uri.split(marker, 1)[1]
        asin = tail.split("/", 1)[0]
        asin = unquote(asin).strip()
        return asin.upper() if asin else None

    @staticmethod
    def _chunk_values(values: List[str], size: int = 20) -> List[List[str]]:
        """Split a list into fixed-size chunks."""
        return [values[index:index + size] for index in range(0, len(values), size)]

    @with_throttle_retry(max_retries=3, base_delay=2.0)
    def _get_competitive_pricing_batch_payload(self, asins: List[str]) -> Any:
        """Fetch competitive pricing for a batch of ASINs."""
        api = self._products_api()
        response = api.get_competitive_pricing_for_asins(asins)
        return response.payload or []

    @with_throttle_retry(max_retries=3, base_delay=2.0)
    def _get_item_offers_batch_payload(self, asins: List[str]) -> Any:
        """Fetch item offers for a batch of ASINs."""
        requests_ = [
            {
                "uri": f"/products/pricing/v0/items/{quote(asin, safe='')}/offers",
                "method": "GET",
                "MarketplaceId": self.marketplace.marketplace_id,
                "ItemCondition": "New",
                "CustomerType": "Consumer",
            }
            for asin in asins
        ]
        api = self._products_api()
        response = api.get_item_offers_batch(requests_=requests_)
        return response.payload or {}

    def get_market_prices_for_asins(self, asins: List[str]) -> Dict[str, Decimal]:
        """Resolve market prices for many ASINs with batched Pricing API calls."""
        if self.is_vendor:
            return {}

        normalized_asins = list(dict.fromkeys(str(asin).strip().upper() for asin in asins if asin))
        if not normalized_asins:
            return {}

        prices: Dict[str, Decimal] = {}

        for chunk in self._chunk_values(normalized_asins, size=20):
            competitive_payload = self._get_competitive_pricing_batch_payload(chunk)
            competitive_entries = (
                competitive_payload
                if isinstance(competitive_payload, list)
                else competitive_payload.get("payload", [])
            )

            for entry in competitive_entries:
                asin = self._extract_asin_from_payload(entry)
                price = self._extract_price_amount(entry)
                if asin and price is not None:
                    prices[asin] = price

            unresolved = [asin for asin in chunk if asin not in prices]
            if not unresolved:
                continue

            offers_payload = self._get_item_offers_batch_payload(unresolved)
            offer_responses = (
                offers_payload.get("responses")
                if isinstance(offers_payload, dict)
                else None
            ) or []

            for response_entry in offer_responses:
                status = response_entry.get("status") or {}
                status_code = status.get("statusCode") or status.get("StatusCode") or 0
                if status_code and int(status_code) >= 400:
                    continue

                body = response_entry.get("body") or {}
                body_payload = body.get("payload") or body
                asin = (
                    self._extract_asin_from_payload(body_payload)
                    or self._extract_asin_from_payload(response_entry.get("request"))
                    or self._extract_asin_from_uri((response_entry.get("request") or {}).get("uri"))
                )
                price = self._extract_price_amount(body_payload)
                if asin and price is not None:
                    prices[asin] = price

        return prices

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

    def _extract_catalog_price_amount(self, payload: Any) -> Optional[Decimal]:
        """Extract a representative price from Catalog Items attributes."""
        candidates: List[Decimal] = []

        def add_candidate(raw_value: Any):
            if raw_value is None:
                return

            normalized = raw_value
            if isinstance(raw_value, str):
                normalized = raw_value.strip()
                if not normalized:
                    return
                if normalized.count(",") == 1 and normalized.count(".") == 0:
                    normalized = normalized.replace(",", ".")
                normalized = re.sub(r"[^0-9.\-]", "", normalized)
                if normalized in {"", "-", ".", "-.", ".-"}:
                    return

            try:
                amount = Decimal(str(normalized))
            except Exception:
                return

            if amount <= 0:
                return
            candidates.append(amount)

        def walk(node: Any, *, price_context: bool = False):
            if isinstance(node, list):
                for item in node:
                    walk(item, price_context=price_context)
                return

            if isinstance(node, dict):
                if price_context:
                    add_candidate(node.get("value_with_tax"))
                    add_candidate(node.get("value"))
                    add_candidate(node.get("amount"))
                    add_candidate(node.get("Amount"))

                for key, value in node.items():
                    normalized_key = str(key).lower().replace("-", "_")
                    walk(value, price_context=price_context or ("price" in normalized_key))
                return

            if price_context:
                add_candidate(node)

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
            results = []
            seen_asins = set()
            page_token = None
            max_pages = max(1, min(5, ((max_results - 1) // 20) + 2))

            for _ in range(max_pages):
                request_kwargs = {
                    "keywords": keywords,
                    "marketplaceIds": self.marketplace.marketplace_id,
                    "includedData": ["summaries", "salesRanks", "classifications", "attributes"],
                    "pageSize": min(max_results, 20),
                }
                if page_token:
                    request_kwargs["pageToken"] = page_token

                response = api.search_catalog_items(**request_kwargs)
                payload = response.payload or {}
                items = payload.get("items", [])
                if not items:
                    break

                for item in items:
                    asin = item.get("asin", "")
                    if not asin or asin in seen_asins:
                        continue
                    seen_asins.add(asin)

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

                    price = self._extract_catalog_price_amount(item)
                    result = {
                        "asin": asin,
                        "title": summary.get("itemName"),
                        "brand": summary.get("brand") or None,
                        "category": category,
                        "price": float(price) if price is not None else None,
                        "bsr": bsr,
                    }
                    results.append(result)

                    if len(results) >= max_results:
                        break

                if len(results) >= max_results:
                    break

                pagination = payload.get("pagination") or {}
                page_token = (
                    pagination.get("nextToken")
                    or payload.get("nextToken")
                    or payload.get("pageToken")
                )
                if not page_token:
                    break

            logger.info(
                "Market search for '%s' returned %s results",
                keywords[:50],
                len(results),
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

    # ------------------------------------------------------------------
    # Listings Items API — write operations
    # ------------------------------------------------------------------

    @with_throttle_retry(max_retries=3, base_delay=2.0)
    def get_listing(self, seller_id: str, sku: str, included_data: Optional[List[str]] = None) -> Dict[str, Any]:
        """Fetch a listing item, including attributes, for a given SKU."""
        api = self._listings_api()
        kwargs: Dict[str, Any] = {
            "marketplaceIds": [self.marketplace.marketplace_id],
            "includedData": included_data or ["summaries", "attributes", "issues", "offers"],
        }
        response = api.get_listings_item(sellerId=seller_id, sku=sku, **kwargs)
        return response.payload or {}

    @with_throttle_retry(max_retries=3, base_delay=2.0)
    def patch_listing(
        self,
        seller_id: str,
        sku: str,
        product_type: str,
        patches: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Partially update a listing via JSON-patch operations on top-level attributes."""
        if not patches:
            raise AmazonAPIError("No patches supplied", error_code="INVALID_PATCH")

        api = self._listings_api()
        body = {
            "productType": product_type,
            "patches": patches,
        }
        response = api.patch_listings_item(
            sellerId=seller_id,
            sku=sku,
            marketplaceIds=[self.marketplace.marketplace_id],
            body=body,
        )
        return response.payload or {}

    def update_listing_attributes(
        self,
        seller_id: str,
        sku: str,
        product_type: str,
        attributes: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Replace top-level listing attributes (title, bullet points, description, keywords, ...)."""
        patches = [
            {"op": "replace", "path": f"/attributes/{name}", "value": value if isinstance(value, list) else [value]}
            for name, value in attributes.items()
        ]
        return self.patch_listing(seller_id, sku, product_type, patches)

    def update_listing_price(
        self,
        seller_id: str,
        sku: str,
        product_type: str,
        price: Decimal | float,
        currency: str,
    ) -> Dict[str, Any]:
        """Set the purchasable offer price on a listing."""
        marketplace_id = self.marketplace.marketplace_id
        offer_value = [
            {
                "marketplace_id": marketplace_id,
                "currency": currency,
                "our_price": [{"schedule": [{"value_with_tax": str(price)}]}],
            }
        ]
        patches = [
            {"op": "replace", "path": "/attributes/purchasable_offer", "value": offer_value}
        ]
        return self.patch_listing(seller_id, sku, product_type, patches)

    def set_listing_quantity(
        self,
        seller_id: str,
        sku: str,
        product_type: str,
        quantity: int,
        fulfillment_channel_code: str = "DEFAULT",
    ) -> Dict[str, Any]:
        """Set merchant-fulfilled stock quantity (0 = effectively inactive)."""
        marketplace_id = self.marketplace.marketplace_id
        availability = [
            {
                "marketplace_id": marketplace_id,
                "fulfillment_channel_code": fulfillment_channel_code,
                "quantity": max(0, int(quantity)),
            }
        ]
        patches = [
            {"op": "replace", "path": "/attributes/fulfillment_availability", "value": availability}
        ]
        return self.patch_listing(seller_id, sku, product_type, patches)

    def update_listing_images(
        self,
        seller_id: str,
        sku: str,
        product_type: str,
        main_image_url: Optional[str],
        other_image_urls: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Patch the listing's main and alternate product images.

        Amazon accepts up to 8 alternate images (`other_product_image_locator_1`..`_8`).
        Each URL must be a publicly reachable HTTPS URL pointing to JPG/PNG.
        """
        patches: List[Dict[str, Any]] = []
        if main_image_url:
            patches.append({
                "op": "replace",
                "path": "/attributes/main_product_image_locator",
                "value": [{"media_location": main_image_url}],
            })

        for idx, url in enumerate((other_image_urls or [])[:8], start=1):
            patches.append({
                "op": "replace",
                "path": f"/attributes/other_product_image_locator_{idx}",
                "value": [{"media_location": url}],
            })

        if not patches:
            raise AmazonAPIError("No image URLs supplied", error_code="INVALID_PATCH")

        return self.patch_listing(seller_id, sku, product_type, patches)

    @with_throttle_retry(max_retries=3, base_delay=2.0)
    def delete_listing(self, seller_id: str, sku: str) -> Dict[str, Any]:
        """Remove a listing (hard-delete from Amazon catalogue for this seller)."""
        api = self._listings_api()
        response = api.delete_listings_item(
            sellerId=seller_id,
            sku=sku,
            marketplaceIds=[self.marketplace.marketplace_id],
        )
        return response.payload or {}
