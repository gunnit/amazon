"""Helium 10 client for third-party product metrics.

Helium 10's documented programmatic surface is its MCP server
(https://mcp.helium10.com/mcp, JSON-RPC over HTTP). This module speaks that
protocol directly and exposes a small fill-only API: it populates snapshot
fields the connected account's SP-API structurally cannot return for
non-owned ASINs (rating, review count, sales estimates, fallback price).

Disabled unless ``HELIUM10_API_KEY`` is set. Amazon data always wins: fills
only touch fields that are still ``None``, and every filled field is recorded
in the snapshot's ``helium10_fields`` provenance list because Helium 10
values are modeled estimates refreshed ~daily, not live marketplace data.

Auth caveat (verified against Helium 10's official MCP README, 2026-07):
the server is **OAuth 2.1 only** — "API Token is not supported yet". So
``HELIUM10_API_KEY`` must hold an OAuth *access token* obtained once through
the browser flow, not a self-service API key (none exists). Tokens expire
after extended inactivity; on 401/403 this module trips a circuit breaker and
the platform silently falls back to Amazon-only data until a token is
re-pasted. Swap to stored refresh tokens when H10 ships token auth.
"""

import json
import logging
import threading
import time
from typing import Any, Dict, List, Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

DEFAULT_MCP_URL = "https://mcp.helium10.com/mcp"
CACHE_TTL_SECONDS = 24 * 3600  # matches Helium 10's ~daily refresh
AUTH_FAILURE_BACKOFF_SECONDS = 3600
# Platform-wide quota is 10k calls/month; cap uncached lookups per market
# search so one request can't burn a day's budget.
MARKET_SEARCH_CALL_CAP = 10

# Snapshot fields this integration is allowed to fill, with the payload key
# variants Helium 10 may use for each. Keys are matched *normalized* (lowercase,
# non-alphanumerics stripped), so one entry covers snake_case, camelCase, and
# "Title Case" spellings of the same field.
#
# NOT YET VALIDATED against a live response: Helium 10 publishes no output
# schemas and the MCP server is OAuth-gated, so these names remain informed
# guesses. Extraction is deliberately defensive and never invents values — an
# unmatched field simply stays None. Run scripts/probe_helium10.py once a real
# OAuth token exists and reconcile this table with the printed payload.
_FIELD_KEYS = {
    "rating": ("rating", "averagerating", "reviewrating", "stars"),
    "review_count": (
        "reviewcount", "reviewscount", "ratingstotal", "numberofreviews", "reviews",
    ),
    "price": ("price", "currentprice", "buyboxprice"),
    "estimated_monthly_sales": (
        "estimatedmonthlysales", "monthlysales", "salesestimate",
        "estimatedsales", "monthlyunits", "asinsales",
    ),
    "estimated_revenue": (
        "estimatedrevenue", "monthlyrevenue", "revenueestimate",
        "asinrevenue", "revenue",
    ),
    "bsr": ("bsr", "bestsellerrank", "bestsellersrank", "salesrank"),
}

_INT_FIELDS = {"review_count", "estimated_monthly_sales", "bsr"}


class Helium10Error(Exception):
    pass


class Helium10Client:
    """Minimal MCP (streamable HTTP) client for the Helium 10 server."""

    def __init__(self, base_url: str, api_key: str, timeout: float = 30.0):
        self.base_url = base_url
        self.api_key = api_key
        self.timeout = timeout
        self._session_id: Optional[str] = None
        self._request_id = 0
        self._lock = threading.Lock()
        self._cache: Dict[tuple, tuple] = {}  # ponytail: in-process cache; move to a DB table if quota gets tight
        self._disabled_until = 0.0

    @property
    def available(self) -> bool:
        return time.time() >= self._disabled_until

    # -- transport -----------------------------------------------------

    def _headers(self) -> Dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        return headers

    def _post(self, payload: dict) -> httpx.Response:
        response = httpx.post(
            self.base_url,
            json=payload,
            headers=self._headers(),
            timeout=self.timeout,
        )
        if response.status_code in (401, 403):
            self._disabled_until = time.time() + AUTH_FAILURE_BACKOFF_SECONDS
            raise Helium10Error(
                f"Helium 10 auth failed ({response.status_code}); "
                f"disabled for {AUTH_FAILURE_BACKOFF_SECONDS // 60} minutes"
            )
        return response

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    @staticmethod
    def _parse_rpc_response(response: httpx.Response, request_id: int) -> dict:
        content_type = response.headers.get("content-type", "")
        if "text/event-stream" in content_type:
            message = None
            for line in response.text.splitlines():
                if not line.startswith("data:"):
                    continue
                try:
                    candidate = json.loads(line[5:].strip())
                except (ValueError, TypeError):
                    continue
                if isinstance(candidate, dict) and candidate.get("id") == request_id:
                    message = candidate
            if message is None:
                raise Helium10Error("No JSON-RPC response in event stream")
            return message
        return response.json()

    def _rpc(self, method: str, params: dict) -> dict:
        request_id = self._next_id()
        response = self._post(
            {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
        )
        response.raise_for_status()
        message = self._parse_rpc_response(response, request_id)
        if message.get("error"):
            raise Helium10Error(f"{method} failed: {message['error']}")
        return message.get("result") or {}

    def _ensure_session(self) -> None:
        if self._session_id is not None:
            return
        request_id = self._next_id()
        response = self._post(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "inthezon", "version": "1.0"},
                },
            }
        )
        response.raise_for_status()
        self._session_id = response.headers.get("mcp-session-id") or response.headers.get("Mcp-Session-Id")
        message = self._parse_rpc_response(response, request_id)
        if message.get("error"):
            raise Helium10Error(f"initialize failed: {message['error']}")
        # Fire-and-forget per MCP spec; some servers require it before tools/call.
        try:
            self._post({"jsonrpc": "2.0", "method": "notifications/initialized"})
        except Exception:
            pass

    # -- tools ---------------------------------------------------------

    def call_tool(self, name: str, arguments: dict) -> Any:
        """Call an MCP tool and return its decoded result payload."""
        if not self.available:
            raise Helium10Error("Helium 10 temporarily disabled after auth failure")
        with self._lock:
            self._ensure_session()
            result = self._rpc("tools/call", {"name": name, "arguments": arguments})
        if result.get("isError"):
            raise Helium10Error(f"tool {name} returned error: {result}")
        if result.get("structuredContent") is not None:
            return result["structuredContent"]
        for block in result.get("content") or []:
            if isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text") or ""
                try:
                    return json.loads(text)
                except (ValueError, TypeError):
                    return text
        return result

    def get_listing_details(self, asin: str, marketplace: str) -> Optional[Any]:
        """Cached per-ASIN listing lookup. Returns None on any failure.

        ``get_listing_details`` is confirmed present in Helium 10's published
        tool reference (Listings toolset); only its argument and response
        shapes are still unverified.
        """
        key = ("get_listing_details", asin.upper(), marketplace.upper())
        cached = self._cache.get(key)
        now = time.time()
        if cached and cached[0] > now:
            return cached[1]
        try:
            payload = self.call_tool(
                "get_listing_details",
                {"asin": asin.upper(), "marketplace": marketplace.upper()},
            )
        except Exception as exc:
            logger.warning("Helium 10 lookup failed for %s/%s: %s", asin, marketplace, exc)
            return None
        self._cache[key] = (now + CACHE_TTL_SECONDS, payload)
        return payload

    def has_cached(self, asin: str, marketplace: str) -> bool:
        key = ("get_listing_details", asin.upper(), marketplace.upper())
        cached = self._cache.get(key)
        return bool(cached and cached[0] > time.time())


_client: Optional[Helium10Client] = None
_client_lock = threading.Lock()


def get_client() -> Optional[Helium10Client]:
    """Singleton client, or None when HELIUM10_API_KEY is not configured."""
    global _client
    if not settings.HELIUM10_API_KEY:
        return None
    if _client is None:
        with _client_lock:
            if _client is None:
                _client = Helium10Client(
                    base_url=settings.HELIUM10_API_BASE_URL or DEFAULT_MCP_URL,
                    api_key=settings.HELIUM10_API_KEY,
                )
    return _client


# -- extraction / fill ----------------------------------------------------


def _normalize_key(key: str) -> str:
    """`Monthly Sales` / `monthly_sales` / `monthlySales` -> `monthlysales`."""
    return "".join(ch for ch in str(key).lower() if ch.isalnum())


def _coerce(field: str, value: Any) -> Optional[float]:
    if isinstance(value, str):
        text = value.strip().lstrip("$€£").strip()
        # One comma and no dot = European decimal comma; otherwise thousands.
        if text.count(",") == 1 and text.count(".") == 0:
            text = text.replace(",", ".")
        else:
            text = text.replace(",", "")
        value = text
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number <= 0:
        return None
    if field == "rating" and number > 5:
        return None
    return number


def extract_metrics(payload: Any) -> Dict[str, float]:
    """Pull known metric fields out of an arbitrarily shaped H10 payload.

    Walks nested dicts/lists; the shallowest match per field wins. Returns
    only positive, plausible values — never defaults.
    """
    found: Dict[str, float] = {}

    def walk(node: Any) -> None:
        if isinstance(node, list):
            for item in node:
                walk(item)
            return
        if not isinstance(node, dict):
            return
        scalars: Dict[str, Any] = {}
        for key, value in node.items():
            if not isinstance(value, (dict, list)):
                scalars.setdefault(_normalize_key(key), value)
        for field, keys in _FIELD_KEYS.items():
            if field in found:
                continue
            for key in keys:
                if key in scalars:
                    value = _coerce(field, scalars[key])
                    if value is not None:
                        found[field] = value
                        break
        for value in node.values():
            if isinstance(value, (dict, list)):
                walk(value)

    walk(payload)
    return {
        field: int(value) if field in _INT_FIELDS else value
        for field, value in found.items()
    }


def marketplace_code(marketplace: Any) -> str:
    """Country code from an SP-API marketplace object or plain string."""
    if isinstance(marketplace, str):
        return marketplace.upper()
    return str(
        getattr(marketplace, "code", None) or getattr(marketplace, "name", "") or ""
    ).upper()


def fill_snapshot_gaps(snapshot: dict, marketplace: Any) -> bool:
    """Fill missing snapshot fields from Helium 10. Mutates in place.

    Only fields currently ``None``/absent are touched; filled field names are
    appended to ``snapshot["helium10_fields"]``. Returns True if anything
    was filled. No-op (False) when the integration is not configured.
    """
    client = get_client()
    asin = snapshot.get("asin")
    country = marketplace_code(marketplace)
    if client is None or not client.available or not asin or not country:
        return False

    wanted = [f for f in _FIELD_KEYS if snapshot.get(f) is None]
    if not wanted:
        return False

    payload = client.get_listing_details(str(asin), country)
    if payload is None:
        return False
    metrics = extract_metrics(payload)

    filled = []
    for field in wanted:
        if metrics.get(field) is not None:
            snapshot[field] = metrics[field]
            filled.append(field)
    if filled:
        snapshot["helium10_fields"] = sorted(
            set(snapshot.get("helium10_fields") or []) | set(filled)
        )
    return bool(filled)


def fill_market_items(items: List[dict], marketplace: Any) -> int:
    """Fill gaps across market-search result rows. Returns rows changed.

    Caps uncached Helium 10 calls at MARKET_SEARCH_CALL_CAP per invocation
    to protect the monthly quota and keep request latency bounded.
    """
    # ponytail: per-ASIN calls capped; switch to a batch tool (compare_listings)
    # once its live schema is verified for amazon.it.
    client = get_client()
    country = marketplace_code(marketplace)
    if client is None or not client.available or not country:
        return 0

    changed = 0
    fresh_calls = 0
    for item in items:
        asin = item.get("asin")
        if not asin:
            continue
        if not client.has_cached(str(asin), country):
            if fresh_calls >= MARKET_SEARCH_CALL_CAP:
                continue
            fresh_calls += 1
        if fill_snapshot_gaps(item, country):
            changed += 1
    return changed
