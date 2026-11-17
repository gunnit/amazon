"""Unit tests for the Helium 10 client and fill-only enrichment (no network)."""
import httpx
import pytest

from app.config import settings
from app.core import helium10


@pytest.fixture
def market_research_fill(monkeypatch):
    monkeypatch.setattr(settings, "HELIUM10_MARKET_RESEARCH_FILL", True)


def test_extract_metrics_from_nested_payload():
    payload = {
        "product": {
            "asin": "B000TEST00",
            "reviews": 1234,
            "rating": "4.3",
            "price": "€24,90",
            "sales": {"estimated_monthly_sales": 850, "monthly_revenue": 21165.0},
        }
    }
    metrics = helium10.extract_metrics(payload)
    assert metrics["review_count"] == 1234
    assert metrics["rating"] == 4.3
    assert metrics["price"] == 24.90
    assert metrics["estimated_monthly_sales"] == 850
    assert metrics["estimated_revenue"] == 21165.0


def test_extract_metrics_matches_key_spelling_variants():
    """Field keys are matched normalized, so casing/separators don't matter."""
    payload = {
        "Monthly Sales": 410,
        "monthlyRevenue": 9020.5,
        "Best Seller Rank": 1875,
        "averageRating": 4.6,
    }
    metrics = helium10.extract_metrics(payload)
    assert metrics["estimated_monthly_sales"] == 410
    assert metrics["estimated_revenue"] == 9020.5
    assert metrics["bsr"] == 1875
    assert metrics["rating"] == 4.6


def test_extract_metrics_rejects_implausible_values():
    metrics = helium10.extract_metrics({"rating": 47, "price": -3, "reviews": 0})
    assert metrics == {}


def test_fill_snapshot_gaps_only_touches_missing_fields(monkeypatch, market_research_fill):
    class FakeClient:
        available = True

        def get_listing_details(self, asin, marketplace):
            return {"rating": 4.1, "reviews": 200, "price": 9.99}

    monkeypatch.setattr(helium10, "get_client", lambda: FakeClient())

    snapshot = {"asin": "B000TEST00", "price": 12.50, "rating": None}
    assert helium10.fill_snapshot_gaps(snapshot, "IT") is True
    assert snapshot["price"] == 12.50  # Amazon value preserved
    assert snapshot["rating"] == 4.1
    assert snapshot["review_count"] == 200
    assert "price" not in snapshot["helium10_fields"]
    assert {"rating", "review_count"} <= set(snapshot["helium10_fields"])


def test_fill_is_noop_when_unconfigured(monkeypatch, market_research_fill):
    monkeypatch.setattr(helium10, "get_client", lambda: None)
    snapshot = {"asin": "B000TEST00"}
    assert helium10.fill_snapshot_gaps(snapshot, "IT") is False
    assert "helium10_fields" not in snapshot
    assert helium10.fill_market_items([snapshot], "IT") == 0


def test_fill_market_items_caps_fresh_calls(monkeypatch, market_research_fill):
    calls = []

    class FakeClient:
        available = True

        def has_cached(self, asin, marketplace):
            return False

        def get_listing_details(self, asin, marketplace):
            calls.append(asin)
            return {"rating": 4.0, "reviews": 10}

    monkeypatch.setattr(helium10, "get_client", lambda: FakeClient())
    items = [{"asin": f"B{i:09d}"} for i in range(helium10.MARKET_SEARCH_CALL_CAP + 5)]
    changed = helium10.fill_market_items(items, "IT")
    assert changed == helium10.MARKET_SEARCH_CALL_CAP
    assert len(calls) == helium10.MARKET_SEARCH_CALL_CAP


def test_marketplace_code_from_sp_api_object():
    class Marketplace:
        code = "IT"
        marketplace_id = "APJ6JRA9NG5V4"

    assert helium10.marketplace_code(Marketplace()) == "IT"
    assert helium10.marketplace_code("it") == "IT"


def test_market_research_fill_is_off_by_default(monkeypatch):
    """Gap-filling spends the monthly quota, so it needs an explicit opt-in."""
    monkeypatch.setattr(settings, "HELIUM10_MARKET_RESEARCH_FILL", False)

    def boom():
        raise AssertionError("client must not be used")

    monkeypatch.setattr(helium10, "get_client", boom)
    assert helium10.fill_snapshot_gaps({"asin": "B000TEST00"}, "IT") is False
    assert helium10.fill_market_items([{"asin": "B000TEST00"}], "IT") == 0


class _FakeHttp:
    """Records token and MCP posts; answers like the Helium 10 servers."""

    def __init__(self, *, mcp_statuses=None, token_status=200, rotate=False):
        self.token_calls = []
        self.mcp_auth = []
        self.mcp_statuses = list(mcp_statuses or [])
        self.token_status = token_status
        self.rotate = rotate
        self.issued = 0

    def post(self, url, json=None, data=None, headers=None, timeout=None):
        request = httpx.Request("POST", url)
        if url == helium10.DEFAULT_TOKEN_URL:
            self.token_calls.append(dict(data))
            if self.token_status != 200:
                return httpx.Response(self.token_status, json={"error": "invalid_grant"}, request=request)
            self.issued += 1
            body = {"access_token": f"access-{self.issued}", "expires_in": 1079, "token_type": "Bearer"}
            if self.rotate:
                body["refresh_token"] = f"refresh-{self.issued}"
            return httpx.Response(200, json=body, request=request)
        self.mcp_auth.append(headers["Authorization"])
        status = self.mcp_statuses.pop(0) if self.mcp_statuses else 200
        return httpx.Response(
            status,
            json={"jsonrpc": "2.0", "id": json.get("id"), "result": {}},
            headers={"mcp-session-id": "s1"},
            request=request,
        )


def _refreshing_client():
    return helium10.Helium10Client(
        helium10.DEFAULT_MCP_URL, client_id="client-test", refresh_token="refresh-test"
    )


def test_client_renews_access_token_from_refresh_token(monkeypatch):
    fake = _FakeHttp()
    monkeypatch.setattr(helium10.httpx, "post", fake.post)
    client = _refreshing_client()

    client._post({"jsonrpc": "2.0", "id": 1, "method": "ping"})
    client._post({"jsonrpc": "2.0", "id": 2, "method": "ping"})

    assert len(fake.token_calls) == 1  # reused until it nears expiry
    assert fake.token_calls[0]["grant_type"] == "refresh_token"
    assert fake.token_calls[0]["client_id"] == "client-test"
    assert fake.mcp_auth == ["Bearer access-1", "Bearer access-1"]

    client._access_expires_at = 0  # expired
    client._post({"jsonrpc": "2.0", "id": 3, "method": "ping"})
    assert len(fake.token_calls) == 2
    assert fake.mcp_auth[-1] == "Bearer access-2"


def test_client_retries_once_after_401_with_a_new_token(monkeypatch):
    fake = _FakeHttp(mcp_statuses=[401, 200])
    monkeypatch.setattr(helium10.httpx, "post", fake.post)
    client = _refreshing_client()

    response = client._post({"jsonrpc": "2.0", "id": 1, "method": "ping"})

    assert response.status_code == 200
    assert fake.mcp_auth == ["Bearer access-1", "Bearer access-2"]
    assert client.available


def test_failed_renewal_trips_the_breaker(monkeypatch):
    fake = _FakeHttp(token_status=400)
    monkeypatch.setattr(helium10.httpx, "post", fake.post)
    client = _refreshing_client()

    with pytest.raises(helium10.Helium10Error, match="connect_helium10"):
        client._post({"jsonrpc": "2.0", "id": 1, "method": "ping"})
    assert not client.available
    assert fake.mcp_auth == []


def test_rotated_refresh_token_is_kept(monkeypatch):
    fake = _FakeHttp(rotate=True)
    monkeypatch.setattr(helium10.httpx, "post", fake.post)
    client = _refreshing_client()

    client._post({"jsonrpc": "2.0", "id": 1, "method": "ping"})
    assert client.refresh_token == "refresh-1"


def test_get_client_prefers_refresh_credentials(monkeypatch):
    monkeypatch.setattr(helium10, "_client", None)
    monkeypatch.setattr(settings, "HELIUM10_API_KEY", None)
    monkeypatch.setattr(settings, "HELIUM10_CLIENT_ID", None)
    monkeypatch.setattr(settings, "HELIUM10_REFRESH_TOKEN", None)
    assert helium10.get_client() is None

    monkeypatch.setattr(settings, "HELIUM10_CLIENT_ID", "client-test")
    monkeypatch.setattr(settings, "HELIUM10_REFRESH_TOKEN", "refresh-test")
    client = helium10.get_client()
    assert client is not None and client._can_refresh
    monkeypatch.setattr(helium10, "_client", None)


def test_market_products_follows_last_page_and_stops_on_empty(monkeypatch):
    pages = {
        # has_more and last_page disagree on real responses; both are honoured.
        1: {"data": [{"asin": "B0TEST0001", "totalRevenue": 10.0}], "has_more": False, "last_page": 2},
        2: {"data": [{"asin": "B0TEST0002", "totalRevenue": 0}], "has_more": False, "last_page": 2},
    }
    calls = []
    client = helium10.Helium10Client(helium10.DEFAULT_MCP_URL, api_key="token-test")

    def fake_call(name, arguments):
        calls.append(arguments["page"])
        return {"data": pages.get(arguments["page"], {"data": []}), "error": None}

    monkeypatch.setattr(client, "call_tool", fake_call)
    rows = client.market_products(1, "2025-01-01", "2025-12-31")
    assert [r["asin"] for r in rows] == ["B0TEST0001", "B0TEST0002"]
    assert calls == [1, 2]


def test_market_tool_error_is_raised(monkeypatch):
    client = helium10.Helium10Client(helium10.DEFAULT_MCP_URL, api_key="token-test")
    monkeypatch.setattr(client, "call_tool", lambda name, arguments: {"data": None, "error": "Wrong Params"})
    with pytest.raises(helium10.Helium10Error, match="Wrong Params"):
        client.list_markets()
