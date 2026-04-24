"""Amazon Advertising API client."""
from __future__ import annotations

import functools
import gzip
import json
import logging
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

import httpx

from app.config import settings
from app.core.exceptions import AmazonAPIError

logger = logging.getLogger(__name__)

TOKEN_URL = "https://api.amazon.com/auth/o2/token"

ADS_API_ENDPOINTS: dict[str, str] = {
    "NA": "https://advertising-api.amazon.com",
    "EU": "https://advertising-api-eu.amazon.com",
    "FE": "https://advertising-api-fe.amazon.com",
}

ADS_REGION_BY_COUNTRY: dict[str, str] = {
    "US": "NA",
    "CA": "NA",
    "MX": "NA",
    "BR": "NA",
    "IT": "EU",
    "DE": "EU",
    "FR": "EU",
    "ES": "EU",
    "UK": "EU",
    "GB": "EU",
    "NL": "EU",
    "SE": "EU",
    "PL": "EU",
    "BE": "EU",
    "TR": "EU",
    "JP": "FE",
    "AU": "FE",
    "IN": "FE",
    "SG": "FE",
    "AE": "FE",
}


def resolve_ads_base_url(country_code: str) -> str:
    """Resolve the Ads API endpoint for a marketplace country."""
    if settings.AMAZON_ADS_API_BASE_URL:
        return settings.AMAZON_ADS_API_BASE_URL.rstrip("/")

    region = ADS_REGION_BY_COUNTRY.get(country_code.upper())
    if not region:
        raise AmazonAPIError(
            f"Unsupported Advertising marketplace country code: {country_code}",
            error_code="INVALID_ADS_MARKETPLACE",
        )
    return ADS_API_ENDPOINTS[region]


def with_throttle_retry(max_retries: int = 3, base_delay: float = 2.0):
    """Retry API calls when Amazon Ads returns a throttling response."""

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except AmazonAPIError as exc:
                    if exc.error_code != "THROTTLED":
                        raise
                    last_exc = exc
                    if attempt == max_retries:
                        break
                    backoff = base_delay * (2 ** attempt)
                    retry_after = getattr(exc, "retry_after", None)
                    if retry_after is not None:
                        backoff = max(backoff, retry_after)
                    logger.warning(
                        "Amazon Ads throttled on %s, retrying in %.1fs (%s/%s)",
                        func.__name__,
                        backoff,
                        attempt + 1,
                        max_retries,
                    )
                    time.sleep(backoff)
            raise last_exc or AmazonAPIError(
                f"Amazon Ads throttled after {max_retries} retries on {func.__name__}",
                error_code="THROTTLED",
            )

        return wrapper

    return decorator


@dataclass(frozen=True)
class AdvertisingReportConfig:
    """Normalized configuration for a reporting request."""

    report_type_id: str
    ad_product: str
    group_by: list[str]
    columns: list[str]
    time_unit: str = "DAILY"
    format: str = "GZIP_JSON"


DEFAULT_REPORT_CONFIGS: dict[str, AdvertisingReportConfig] = {
    "sp_campaigns": AdvertisingReportConfig(
        report_type_id="spCampaigns",
        ad_product="SPONSORED_PRODUCTS",
        group_by=["campaign"],
        columns=[
            "date",
            "campaignId",
            "campaignName",
            "campaignStatus",
            "impressions",
            "clicks",
            "cost",
            "sales1d",
            "sales7d",
            "sales14d",
            "sales30d",
            "orders1d",
            "orders7d",
            "orders14d",
            "orders30d",
        ],
    ),
    "sponsored_products_campaigns": AdvertisingReportConfig(
        report_type_id="spCampaigns",
        ad_product="SPONSORED_PRODUCTS",
        group_by=["campaign"],
        columns=[
            "date",
            "campaignId",
            "campaignName",
            "campaignStatus",
            "impressions",
            "clicks",
            "cost",
            "sales1d",
            "sales7d",
            "sales14d",
            "sales30d",
            "orders1d",
            "orders7d",
            "orders14d",
            "orders30d",
        ],
    ),
    "spCampaigns": AdvertisingReportConfig(
        report_type_id="spCampaigns",
        ad_product="SPONSORED_PRODUCTS",
        group_by=["campaign"],
        columns=[
            "date",
            "campaignId",
            "campaignName",
            "campaignStatus",
            "impressions",
            "clicks",
            "cost",
            "sales1d",
            "sales7d",
            "sales14d",
            "sales30d",
            "orders1d",
            "orders7d",
            "orders14d",
            "orders30d",
        ],
    ),
}


class AdvertisingAPIClient:
    """Synchronous Amazon Advertising API client for worker use."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        refresh_token: str,
        marketplace_country: str,
        *,
        base_url: str | None = None,
        timeout: float = 60.0,
    ):
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        self.base_url = (base_url or resolve_ads_base_url(marketplace_country)).rstrip("/")
        self.timeout = timeout
        self._client = httpx.Client(timeout=self.timeout)
        self._access_token: str | None = None
        self._access_token_expires_at: datetime | None = None

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._client.close()

    def _ensure_access_token(self, force_refresh: bool = False) -> str:
        """Refresh the OAuth access token when needed."""
        now = datetime.utcnow()
        if (
            not force_refresh
            and self._access_token
            and self._access_token_expires_at
            and now < self._access_token_expires_at
        ):
            return self._access_token

        response = self._client.post(
            TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": self.refresh_token,
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"},
        )

        if response.status_code >= 400:
            raise AmazonAPIError(
                f"Advertising OAuth failed ({response.status_code}): {response.text}",
                error_code="ADVERTISING_AUTH_FAILED",
            )

        payload = response.json()
        access_token = payload.get("access_token")
        expires_in = int(payload.get("expires_in", 3600))
        if not access_token:
            raise AmazonAPIError(
                "Advertising OAuth response missing access_token",
                error_code="ADVERTISING_AUTH_FAILED",
            )

        self._access_token = access_token
        self._access_token_expires_at = now + timedelta(seconds=max(expires_in - 60, 60))
        return self._access_token

    def _extract_retry_after(self, response: httpx.Response) -> float | None:
        """Read Retry-After if present."""
        retry_after = response.headers.get("Retry-After")
        if not retry_after:
            return None
        try:
            return float(retry_after)
        except (TypeError, ValueError):
            return None

    def _request(
        self,
        method: str,
        path: str,
        *,
        profile_id: str | None = None,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        absolute_url: bool = False,
        authenticated: bool = True,
    ) -> httpx.Response:
        """Perform a single HTTP request with auth, 401 refresh, and throttle detection."""
        url = path if absolute_url else f"{self.base_url}{path}"
        request_headers = dict(headers or {})
        if authenticated:
            request_headers["Authorization"] = f"Bearer {self._ensure_access_token()}"
            request_headers["Amazon-Advertising-API-ClientId"] = self.client_id
            if profile_id:
                request_headers["Amazon-Advertising-API-Scope"] = str(profile_id)

        response = self._client.request(
            method,
            url,
            params=params,
            json=json_body,
            headers=request_headers,
        )

        if response.status_code == 401 and authenticated:
            request_headers["Authorization"] = f"Bearer {self._ensure_access_token(force_refresh=True)}"
            response = self._client.request(
                method,
                url,
                params=params,
                json=json_body,
                headers=request_headers,
            )

        if response.status_code == 429:
            exc = AmazonAPIError(
                f"Advertising API throttled on {method} {url}",
                error_code="THROTTLED",
            )
            setattr(exc, "retry_after", self._extract_retry_after(response))
            raise exc

        if response.status_code >= 400:
            raise AmazonAPIError(
                f"Advertising API request failed ({response.status_code}) on {method} {url}: {response.text}",
                error_code="ADVERTISING_REQUEST_FAILED",
            )

        return response

    def _campaign_list_payload(self, next_token: str | None = None) -> dict[str, Any]:
        """Build a permissive list payload that returns active and inactive campaigns."""
        payload: dict[str, Any] = {
            "maxResults": 1000,
            "stateFilter": {
                "include": ["ENABLED", "PAUSED", "ARCHIVED"],
            },
        }
        if next_token:
            payload["nextToken"] = next_token
        return payload

    @with_throttle_retry(max_retries=3, base_delay=2.0)
    def list_campaigns(self, profile_id: str) -> list[dict[str, Any]]:
        """Return campaigns across SP, SB, and SD for a profile."""
        campaign_types = {
            "sponsoredProducts": {
                "primary_path": "/sp/campaigns/list",
                "legacy_path": "/v2/sp/campaigns",
            },
            "sponsoredBrands": {
                "primary_path": "/sb/campaigns/list",
                "legacy_path": "/v2/hsa/campaigns",
            },
            "sponsoredDisplay": {
                "primary_path": "/sd/campaigns/list",
                "legacy_path": "/sd/campaigns",
            },
        }
        campaigns: list[dict[str, Any]] = []

        for campaign_type, config in campaign_types.items():
            next_token: str | None = None
            while True:
                try:
                    response = self._request(
                        "POST",
                        config["primary_path"],
                        profile_id=profile_id,
                        json_body=self._campaign_list_payload(next_token),
                    )
                except AmazonAPIError as exc:
                    if exc.error_code != "ADVERTISING_REQUEST_FAILED":
                        raise
                    response = self._request(
                        "GET",
                        config["legacy_path"],
                        profile_id=profile_id,
                    )
                payload = response.json()
                items = payload if isinstance(payload, list) else (
                    payload.get("campaigns")
                    or payload.get("campaignsList")
                    or payload.get("items")
                    or payload.get("content")
                    or []
                )
                for item in items:
                    normalized = dict(item)
                    normalized["campaignType"] = campaign_type
                    campaigns.append(normalized)

                if isinstance(payload, list):
                    break

                next_token = (
                    payload.get("nextToken")
                    or payload.get("nextPageToken")
                    or payload.get("cursorToken")
                )
                if not next_token:
                    break

        return campaigns

    def _normalize_date_range(self, date_range: Any) -> tuple[date, date]:
        """Accept tuple or dict date ranges."""
        if isinstance(date_range, dict):
            start_date = date_range.get("start_date") or date_range.get("startDate")
            end_date = date_range.get("end_date") or date_range.get("endDate")
        elif isinstance(date_range, (list, tuple)) and len(date_range) == 2:
            start_date, end_date = date_range
        else:
            raise AmazonAPIError(
                "date_range must be a dict or a 2-item tuple/list",
                error_code="INVALID_REPORT_RANGE",
            )

        if isinstance(start_date, str):
            start_date = date.fromisoformat(start_date)
        if isinstance(end_date, str):
            end_date = date.fromisoformat(end_date)

        if not isinstance(start_date, date) or not isinstance(end_date, date):
            raise AmazonAPIError(
                "date_range must contain valid dates",
                error_code="INVALID_REPORT_RANGE",
            )

        if start_date > end_date:
            raise AmazonAPIError(
                "Report start_date must be on or before end_date",
                error_code="INVALID_REPORT_RANGE",
            )

        return start_date, end_date

    def _resolve_report_config(self, report_type: str | dict[str, Any]) -> AdvertisingReportConfig:
        """Resolve a supported report type into a reporting configuration."""
        if isinstance(report_type, dict):
            try:
                return AdvertisingReportConfig(
                    report_type_id=report_type["reportTypeId"],
                    ad_product=report_type["adProduct"],
                    group_by=list(report_type["groupBy"]),
                    columns=list(report_type["columns"]),
                    time_unit=report_type.get("timeUnit", "DAILY"),
                    format=report_type.get("format", "GZIP_JSON"),
                )
            except KeyError as exc:
                raise AmazonAPIError(
                    f"Unsupported report config missing {exc.args[0]}",
                    error_code="INVALID_REPORT_TYPE",
                ) from exc

        config = DEFAULT_REPORT_CONFIGS.get(report_type)
        if config:
            return config

        raise AmazonAPIError(
            f"Unsupported Advertising report type: {report_type}",
            error_code="INVALID_REPORT_TYPE",
        )

    @with_throttle_retry(max_retries=3, base_delay=2.0)
    def request_report(self, profile_id: str, report_type: str | dict[str, Any], date_range: Any) -> str:
        """Request an asynchronous report and return the report id."""
        start_date, end_date = self._normalize_date_range(date_range)
        config = self._resolve_report_config(report_type)

        body = {
            "name": f"{config.report_type_id}_{start_date.isoformat()}_{end_date.isoformat()}",
            "startDate": start_date.isoformat(),
            "endDate": end_date.isoformat(),
            "configuration": {
                "adProduct": config.ad_product,
                "groupBy": config.group_by,
                "columns": config.columns,
                "reportTypeId": config.report_type_id,
                "timeUnit": config.time_unit,
                "format": config.format,
            },
        }
        response = self._request(
            "POST",
            "/reporting/reports",
            profile_id=profile_id,
            json_body=body,
        )
        payload = response.json()
        report_id = payload.get("reportId")
        if not report_id:
            raise AmazonAPIError(
                f"Advertising report request did not return reportId: {payload}",
                error_code="REPORT_CREATE_FAILED",
            )
        return str(report_id)

    def _poll_report_location(self, profile_id: str, report_id: str) -> str:
        """Wait for a report to complete and return its download URL."""
        poll_interval = settings.AMAZON_ADS_REPORT_POLL_INTERVAL_SECONDS
        max_attempts = settings.AMAZON_ADS_REPORT_POLL_MAX_ATTEMPTS

        for attempt in range(max_attempts):
            response = self._request(
                "GET",
                f"/reporting/reports/{report_id}",
                profile_id=profile_id,
            )
            payload = response.json()
            status = str(payload.get("status") or payload.get("processingStatus") or "").upper()
            if status in {"COMPLETED", "SUCCESS", "DONE"}:
                location = payload.get("location") or payload.get("url")
                if not location:
                    raise AmazonAPIError(
                        f"Advertising report {report_id} completed without a download location",
                        error_code="REPORT_NO_DOCUMENT",
                    )
                return str(location)

            if status in {"FAILED", "FAILURE", "CANCELLED"}:
                raise AmazonAPIError(
                    f"Advertising report {report_id} ended with status {status}",
                    error_code=f"REPORT_{status}",
                )

            if attempt < max_attempts - 1:
                time.sleep(poll_interval)

        raise AmazonAPIError(
            f"Advertising report {report_id} timed out after {max_attempts * poll_interval}s",
            error_code="REPORT_TIMEOUT",
        )

    def _decode_report_content(self, response: httpx.Response) -> Any:
        """Decode report bytes into JSON."""
        raw = response.content
        content_encoding = response.headers.get("Content-Encoding", "").lower()
        is_gzip = content_encoding == "gzip" or raw[:2] == b"\x1f\x8b"
        if is_gzip:
            raw = gzip.decompress(raw)

        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise AmazonAPIError(
                f"Failed to parse Advertising report payload: {exc}",
                error_code="REPORT_PARSE_FAILED",
            ) from exc

    @with_throttle_retry(max_retries=3, base_delay=2.0)
    def download_report(self, profile_id: str, report_id: str) -> Any:
        """Poll until a report is ready, then download and decode the GZIP JSON payload."""
        location = self._poll_report_location(profile_id, report_id)
        response = self._request(
            "GET",
            location,
            absolute_url=True,
            authenticated=False,
        )
        return self._decode_report_content(response)
