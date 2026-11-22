"""RateLimiter must enforce limits without Redis (in-process fallback)."""
import asyncio
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app.api.deps import RateLimiter


class _Req:
    headers: dict = {}

    class client:
        host = "1.2.3.4"


@patch("app.api.deps._get_redis", return_value=None)
def test_local_fallback_blocks_after_limit(_redis):
    limiter = RateLimiter(max_requests=3, window_seconds=60, scope="test")
    req = _Req()
    for _ in range(3):
        asyncio.run(limiter(req))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(limiter(req))
    assert exc.value.status_code == 429


@patch("app.api.deps._get_redis", return_value=None)
def test_local_window_resets(_redis):
    limiter = RateLimiter(max_requests=2, window_seconds=60, scope="test2")
    req = _Req()
    asyncio.run(limiter(req))
    asyncio.run(limiter(req))
    key = limiter._client_key(req)
    start, count = limiter._local[key]
    limiter._local[key] = (start - 61, count)
    asyncio.run(limiter(req))  # new window, must not raise


@patch("app.api.deps._get_redis", return_value=None)
def test_clients_counted_separately(_redis):
    limiter = RateLimiter(max_requests=1, window_seconds=60, scope="test3")

    class _Other(_Req):
        headers = {"x-forwarded-for": "9.9.9.9"}

    asyncio.run(limiter(_Req()))
    asyncio.run(limiter(_Other()))  # different ip, own budget


def _route_limiters(router, path):
    from fastapi.routing import APIRoute

    route = next(r for r in router.routes if isinstance(r, APIRoute) and r.path == path)
    return [d.call for d in route.dependant.dependencies if isinstance(d.call, RateLimiter)]


def test_refresh_has_its_own_limit_separate_from_login():
    # Parallel 401s after the access token expires each refresh: sharing the
    # login budget (10/min) logged users out mid-session.
    from app.api.v1 import auth

    [refresh] = _route_limiters(auth.router, "/refresh")
    [login] = _route_limiters(auth.router, "/login")
    assert refresh is not login
    assert (refresh.scope, refresh.max_requests, refresh.window_seconds) == ("auth-refresh", 60, 60)
    assert login.scope != refresh.scope


@patch("app.api.deps._get_redis", return_value=None)
def test_exhausted_login_limit_leaves_refresh_open(_redis):
    from app.api.v1 import auth

    class _Ip(_Req):
        class client:
            host = "203.0.113.77"

    req = _Ip()
    [refresh] = _route_limiters(auth.router, "/refresh")
    [login] = _route_limiters(auth.router, "/login")
    try:
        for _ in range(login.max_requests):
            asyncio.run(login(req))
        with pytest.raises(HTTPException):
            asyncio.run(login(req))
        for _ in range(refresh.max_requests):
            asyncio.run(refresh(req))  # its own budget: never blocked by the logins
        with pytest.raises(HTTPException) as exc:
            asyncio.run(refresh(req))
        assert exc.value.status_code == 429
    finally:
        login._local.pop(login._client_key(req), None)
        refresh._local.pop(refresh._client_key(req), None)
