"""Request ID propagation.

The middleware reads the inbound `X-Request-ID` header (or generates a
UUID4 hex if absent), stores it in a ContextVar so log records can pick
it up, and echoes it back on the response so callers can correlate.

The accompanying log filter is registered in the dictConfig built by
`app.observability.configure_logging`.
"""
from __future__ import annotations

import contextvars
import logging
import uuid
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


REQUEST_ID_HEADER = "X-Request-ID"
_REQUEST_ID_CTX: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "inthezon_request_id", default=None
)


def get_request_id() -> Optional[str]:
    """Return the current request's correlation ID, if any."""
    return _REQUEST_ID_CTX.get()


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        incoming = request.headers.get(REQUEST_ID_HEADER)
        request_id = incoming or uuid.uuid4().hex
        token = _REQUEST_ID_CTX.set(request_id)
        try:
            response: Response = await call_next(request)
        finally:
            _REQUEST_ID_CTX.reset(token)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response


class RequestIdLogFilter(logging.Filter):
    """Attach the current request_id (or '-' outside a request) to log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = _REQUEST_ID_CTX.get() or "-"
        return True
