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
