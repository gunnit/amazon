"""Helium10 Market Tracker 360 service boundary.

This module is intentionally an **API-shaped** boundary. Browser automation
(Playwright, selectors, CAPTCHA/MFA handling) has been removed. When the
official Helium10 Enterprise API becomes available, the methods below will
be implemented as HTTP calls against ``HELIUM10_API_BASE_URL`` using
``HELIUM10_API_KEY`` as a bearer token, mirroring the patterns in
``app.core.amazon.sp_api_client``.

Until then every method raises :class:`Helium10UnavailableError`. Brand
Analysis does not use this service for its normal workflow; it uses
internal Amazon data + Market Research, with generic external yearly
exports as an optional fallback.

Per-organization credentials are not implemented in this iteration. The
intended future pattern is to store them in
``Organization.settings["helium10"] = {"api_key_enc": ...}`` and decrypt
through ``app.core.security.encrypt_value`` / ``decrypt_value`` (Fernet),
mirroring ``app/core/amazon/credentials.py``.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.config import settings


class Helium10UnavailableError(RuntimeError):
    """Raised when Helium10 data cannot be retrieved from the current environment."""


@dataclass
class Helium10Export:
    """Downloaded Helium10 Products export payload for a single year."""

    year: int
    filename: str
    content_type: str
    data: bytes


@dataclass
class Helium10MarketResult:
    """Configured or selected Market Tracker 360 slot."""

    market_id: Optional[str]
    slot: Optional[int]
    status: str


_UNAVAILABLE_MESSAGE = (
    "Helium10 Enterprise API is not yet configured. "
    "Brand Analysis runs on internal Amazon data; use generic external yearly uploads only as fallback."
)


class Helium10Service:
    """Thin API-shaped wrapper for Helium10 Market Tracker 360.

    All methods raise :class:`Helium10UnavailableError` today. The shape is
    preserved so the Brand Analysis pipeline can plug a real implementation
    in without changes to call sites.
    """

    def __init__(self) -> None:
        self.username = settings.HELIUM10_USERNAME
        self.password = settings.HELIUM10_PASSWORD
        self.api_base_url = settings.HELIUM10_API_BASE_URL
        self.api_key = settings.HELIUM10_API_KEY
        self.enabled = settings.HELIUM10_AUTOMATION_ENABLED

    def ensure_available(self) -> None:
        """Raise unless an API client could be constructed for the current env.

        When the Enterprise API is available this becomes a real check
        (``HELIUM10_API_BASE_URL`` and ``HELIUM10_API_KEY`` set). For now it
        always raises so call sites must route through the manual fallback.
        """
        raise Helium10UnavailableError(_UNAVAILABLE_MESSAGE)

    def list_markets(self) -> list[Helium10MarketResult]:
        """Return the configured Market Tracker 360 slots for the account."""
        self.ensure_available()
        raise Helium10UnavailableError(_UNAVAILABLE_MESSAGE)

    def configure_market(
        self,
        *,
        brand_name: str,
        market_type: str,
        market_query: Optional[str],
        asin_list: Optional[list[str]],
        slot: Optional[int],
    ) -> Helium10MarketResult:
        """Create or update a Market Tracker 360 slot.

        Future API call: ``POST {HELIUM10_API_BASE_URL}/market-tracker/markets``
        with body describing slot, brand or ASIN list, and date range.
        """
        self.ensure_available()
        raise Helium10UnavailableError(_UNAVAILABLE_MESSAGE)

    def check_market_status(self, market_id: Optional[str]) -> str:
        """Return ``"ready" | "loading" | "failed" | "unknown"`` for a market."""
        self.ensure_available()
        raise Helium10UnavailableError(_UNAVAILABLE_MESSAGE)

    def fetch_products_for_year(
        self,
        *,
        market_id: Optional[str],
        year: int,
    ) -> Helium10Export:
        """Download the Products export for the given calendar year.

        Future API call: ``GET {HELIUM10_API_BASE_URL}/market-tracker/markets/
        {market_id}/products/export?from=YYYY-01-01&to=YYYY-12-31``.
        """
        self.ensure_available()
        raise Helium10UnavailableError(_UNAVAILABLE_MESSAGE)
