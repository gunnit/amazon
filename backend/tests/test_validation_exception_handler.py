"""Tests for the RequestValidationError exception handler.

Verifies that invalid request bodies yield a clean, serializable 422 (the
PydanticUndefined sentinel in the error context must not crash encoding) and
that unrelated exceptions still surface as 500 via the generic handler.
"""
from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from pydantic import BaseModel
from pydantic_core import PydanticUndefined


class Item(BaseModel):
    name: str


def _build_app() -> FastAPI:
    app = FastAPI()

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        errors = jsonable_encoder(
            exc.errors(),
            custom_encoder={type(PydanticUndefined): lambda _v: None},
        )
        return JSONResponse(status_code=422, content={"detail": errors})

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    @app.post("/items")
    def create_item(item: Item):
        return {"name": item.name}

    @app.get("/boom")
    def boom():
        raise RuntimeError("kaboom")

    return app


def test_invalid_body_returns_clean_422():
    client = TestClient(_build_app(), raise_server_exceptions=False)
    resp = client.post("/items", json={})
    assert resp.status_code == 422
    body = resp.json()
    assert "detail" in body
    # Response must serialize without error and carry no stack trace.
    assert isinstance(body["detail"], list)
    assert "Traceback" not in resp.text
    assert resp.headers["content-type"].startswith("application/json")


def test_malformed_json_returns_422():
    client = TestClient(_build_app(), raise_server_exceptions=False)
    resp = client.post(
        "/items",
        content="{not valid json",
        headers={"content-type": "application/json"},
    )
    assert resp.status_code == 422
    assert "detail" in resp.json()


def test_unrelated_error_still_returns_500():
    client = TestClient(_build_app(), raise_server_exceptions=False)
    resp = client.get("/boom")
    assert resp.status_code == 500
    assert resp.json() == {"detail": "Internal server error"}
