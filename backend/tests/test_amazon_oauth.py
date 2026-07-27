"""Amazon SP-API OAuth flow: consent URL building + callback code exchange."""
import sys
import types
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import httpx
import pytest
from fastapi import HTTPException
from jose import jwt as jose_jwt

# Reuse the module scaffold (stubs + accounts module) from the summary tests.
import test_accounts_summary as base

accounts = base.accounts
schema = sys.modules["app.schemas.account"]

SECRET = "test-oauth-secret"

_SETTINGS = {
    "JWT_SECRET_KEY": SECRET,
    "JWT_ALGORITHM": "HS256",
    "APP_API_URL": "http://api.test",
    "APP_FRONTEND_URL": "http://front.test",
    "AMAZON_SP_API_APP_ID": "amzn1.sp.solution.test-app",
    "AMAZON_SP_API_CLIENT_ID": "client-id",
    "AMAZON_SP_API_CLIENT_SECRET": "client-secret",
}


@pytest.fixture(autouse=True)
def _oauth_settings(monkeypatch):
    # accounts.py resolves app.config lazily per call; other test modules swap
    # the module in sys.modules, so apply the values at test runtime.
    settings = sys.modules["app.config"].settings
    for key, value in _SETTINGS.items():
        monkeypatch.setattr(settings, key, value, raising=False)

_credentials_stub = types.ModuleType("app.core.amazon.credentials")
_credentials_stub._get_org_sp_api_setting = lambda org, key: None
_amazon_pkg = types.ModuleType("app.core.amazon")
_amazon_pkg.__path__ = []


def _install_lazy_stubs(monkeypatch, sync_calls):
    runner_stub = types.ModuleType("app.services.extraction_runner")
    runner_stub.initial_sync_in_thread = lambda account_id: sync_calls.append(("initial", account_id))
    runner_stub.sync_account_in_thread = lambda account_id: sync_calls.append(("sync", account_id))
    monkeypatch.setitem(sys.modules, "app.core.amazon", _amazon_pkg)
    monkeypatch.setitem(sys.modules, "app.core.amazon.credentials", _credentials_stub)
    monkeypatch.setitem(sys.modules, "app.services.extraction_runner", runner_stub)


class FakeResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class FakeDb:
    """Sequential results for db.execute; records added objects."""

    def __init__(self, results):
        self._results = list(results)
        self.added = []
        self.committed = False

    async def execute(self, _query):
        return FakeResult(self._results.pop(0) if self._results else None)

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.committed = True

    async def refresh(self, obj):
        obj.id = getattr(obj, "id", None) or uuid4()


class FakeAccount:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.id = kwargs.get("id") or uuid4()
        self.last_backfill_status = kwargs.get("last_backfill_status")


class FakeAsyncClient:
    """httpx.AsyncClient stand-in; responses is a list of (status, json)."""

    responses = []
    posts = []

    def __init__(self, **_kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, data=None):
        FakeAsyncClient.posts.append((url, data))
        status, payload = FakeAsyncClient.responses[min(len(FakeAsyncClient.posts) - 1, len(FakeAsyncClient.responses) - 1)]
        return SimpleNamespace(status_code=status, json=lambda: payload)


def _decode_token(token):
    try:
        return jose_jwt.decode(token, SECRET, algorithms=["HS256"])
    except Exception:
        return None


async def _start(account_type="seller", country="IT", marketplace_id="APJ6JRA9NG5V4"):
    oauth_in = schema.AmazonOAuthStartRequest(
        account_type=account_type,
        marketplace_id=marketplace_id,
        marketplace_country=country,
        account_name="Test Account",
    )
    resp = await accounts.start_amazon_oauth(
        oauth_in=oauth_in,
        current_user=SimpleNamespace(id=uuid4()),
        organization=SimpleNamespace(id=uuid4(), settings={}),
        db=FakeDb([]),
    )
    return resp.consent_url


async def _callback(db, state, spapi_oauth_code=None, selling_partner_id=None, error=None):
    # Direct function call: pass every Query(...) parameter explicitly so
    # FastAPI sentinel defaults never leak into the endpoint logic.
    return await accounts.amazon_oauth_callback(
        db=db,
        state=state,
        spapi_oauth_code=spapi_oauth_code,
        selling_partner_id=selling_partner_id,
        error=error,
    )


@pytest.mark.asyncio
async def test_start_seller_builds_signed_consent_url():
    url = await _start("seller")
    parsed = urlparse(url)
    q = parse_qs(parsed.query)

    assert parsed.scheme == "https"
    assert parsed.netloc == "sellercentral-europe.amazon.com"
    assert parsed.path == "/apps/authorize/consent"
    assert q["application_id"] == ["amzn1.sp.solution.test-app"]
    assert q["version"] == ["beta"]
    assert q["redirect_uri"] == ["http://api.test/api/v1/accounts/oauth/callback"]

    payload = jose_jwt.decode(q["state"][0], SECRET, algorithms=["HS256"])
    assert payload["type"] == "amazon_oauth"
    assert payload["account_type"] == "seller"
    assert payload["marketplace_id"] == "APJ6JRA9NG5V4"


@pytest.mark.asyncio
async def test_start_vendor_uses_country_host_and_rejects_unsupported():
    url = await _start("vendor", country="IT")
    assert urlparse(url).netloc == "vendorcentral.amazon.it"

    with pytest.raises(HTTPException) as exc:
        await _start("vendor", country="US", marketplace_id="ATVPDKIKX0DER")
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_callback_rejects_invalid_state(monkeypatch):
    monkeypatch.setattr(accounts, "decode_token", _decode_token)
    resp = await _callback(FakeDb([]), state="garbage", spapi_oauth_code="x")
    assert resp.headers["location"] == "http://front.test/accounts?amazon_status=error&reason=invalid_state"


@pytest.mark.asyncio
async def test_callback_reports_amazon_error_and_missing_code(monkeypatch):
    monkeypatch.setattr(accounts, "decode_token", _decode_token)
    state = parse_qs(urlparse(await _start()).query)["state"][0]

    resp = await _callback(FakeDb([]), state=state, error="access_denied")
    assert "reason=access_denied" in resp.headers["location"]

    resp = await _callback(FakeDb([]), state=state)
    assert "reason=missing_code" in resp.headers["location"]


@pytest.mark.asyncio
async def test_callback_exchanges_code_and_saves_encrypted_token(monkeypatch):
    sync_calls = []
    _install_lazy_stubs(monkeypatch, sync_calls)
    monkeypatch.setattr(accounts, "decode_token", _decode_token)
    monkeypatch.setattr(accounts, "encrypt_value", lambda v: f"enc({v})")
    monkeypatch.setattr(accounts, "AmazonAccount", FakeAccount)
    monkeypatch.setattr(accounts, "select", lambda *_a, **_k: base.FakeQuery())
    FakeAsyncClient.responses = [(200, {"refresh_token": "Atzr|real-token"})]
    FakeAsyncClient.posts = []
    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)

    state = parse_qs(urlparse(await _start()).query)["state"][0]
    db = FakeDb([SimpleNamespace(id=uuid4(), settings={})])  # org lookup

    resp = await _callback(db, state=state, spapi_oauth_code="oauth-code", selling_partner_id="A2SELLER")

    url, data = FakeAsyncClient.posts[0]
    assert url == accounts.LWA_TOKEN_URL
    assert data["grant_type"] == "authorization_code"
    assert data["code"] == "oauth-code"
    assert data["redirect_uri"] == "http://api.test/api/v1/accounts/oauth/callback"
    assert data["client_id"] == "client-id"
    assert data["client_secret"] == "client-secret"

    assert len(db.added) == 1
    account = db.added[0]
    assert account.sp_api_refresh_token_encrypted == "enc(Atzr|real-token)"
    assert account.seller_id == "A2SELLER"
    assert account.sync_status == base.StubSyncStatus.SYNCING
    assert db.committed
    assert sync_calls == [("initial", account.id)]
    assert "amazon_status=connected" in resp.headers["location"]


@pytest.mark.asyncio
async def test_callback_exchange_failure_tries_both_redirect_uris(monkeypatch):
    sync_calls = []
    _install_lazy_stubs(monkeypatch, sync_calls)
    monkeypatch.setattr(accounts, "decode_token", _decode_token)
    monkeypatch.setattr(accounts, "select", lambda *_a, **_k: base.FakeQuery())
    FakeAsyncClient.responses = [(400, {"error": "invalid_grant"})]
    FakeAsyncClient.posts = []
    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)

    state = parse_qs(urlparse(await _start()).query)["state"][0]
    db = FakeDb([SimpleNamespace(id=uuid4(), settings={})])

    resp = await _callback(db, state=state, spapi_oauth_code="bad-code")

    assert [u for u, _ in FakeAsyncClient.posts] == [accounts.LWA_TOKEN_URL] * 2
    assert FakeAsyncClient.posts[0][1]["redirect_uri"] == "http://api.test/api/v1/accounts/oauth/callback"
    assert FakeAsyncClient.posts[1][1]["redirect_uri"] == "http://front.test/amazon/callback"
    assert "reason=token_exchange_failed" in resp.headers["location"]
    assert db.added == [] and sync_calls == []
