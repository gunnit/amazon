"""Tests for the X-Request-ID middleware.

Verifies that the middleware accepts safe IDs from the client, rejects
unsafe inputs (newlines / control chars used in log-injection), and falls
back to a server-generated UUID.
"""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.middleware.request_id import (
    REQUEST_ID_HEADER,
    RequestIdMiddleware,
    get_request_id,
)


def _build_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestIdMiddleware)

    @app.get("/echo")
    def echo():
        return {"request_id": get_request_id()}

    return app


def test_accepts_valid_client_request_id():
    client = TestClient(_build_app())
    resp = client.get("/echo", headers={REQUEST_ID_HEADER: "trace-123_ABC"})
    assert resp.status_code == 200
    assert resp.headers[REQUEST_ID_HEADER] == "trace-123_ABC"
    assert resp.json()["request_id"] == "trace-123_ABC"


def test_rejects_request_id_with_newline():
    client = TestClient(_build_app())
    # Header values can't carry a literal newline, but starlette accepts
    # most printable chars; we still want any unsafe value replaced.
    resp = client.get("/echo", headers={REQUEST_ID_HEADER: "bad;rm -rf /"})
    assert resp.status_code == 200
    returned = resp.headers[REQUEST_ID_HEADER]
    assert returned != "bad;rm -rf /"
    assert len(returned) == 32  # uuid4 hex


def test_rejects_request_id_too_long():
    client = TestClient(_build_app())
    long_value = "a" * 200
    resp = client.get("/echo", headers={REQUEST_ID_HEADER: long_value})
    assert resp.status_code == 200
    returned = resp.headers[REQUEST_ID_HEADER]
    assert returned != long_value
    assert len(returned) == 32


def test_generates_uuid_when_header_absent():
    client = TestClient(_build_app())
    resp = client.get("/echo")
    assert resp.status_code == 200
    returned = resp.headers[REQUEST_ID_HEADER]
    assert len(returned) == 32
    assert all(c in "0123456789abcdef" for c in returned)
