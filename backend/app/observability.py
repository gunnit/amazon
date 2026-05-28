"""Logging + error-tracking configuration.

`configure_logging` is called once at process startup (FastAPI lifespan
for the API, `setup_logging` Celery signal for workers). It installs a
JSON formatter from `python-json-logger` when `LOG_FORMAT=json`, and a
human-readable formatter otherwise. Two filters always run on every
record:

* `request_id` — populated by `app.middleware.request_id` for FastAPI;
  falls back to `'-'` outside an HTTP context (e.g., startup, workers).
* `service` — static, picked from the caller (`inthezon-api` for the API,
  `inthezon-worker` for Celery).

`init_sentry` is the matching error-tracking bootstrap: it is a no-op
when `SENTRY_DSN` is empty, so the same code can ship to environments
that have not (yet) been configured.
"""
from __future__ import annotations

import logging
import logging.config
from typing import Optional

from app.config import settings
from app.middleware.request_id import RequestIdLogFilter


class _ServiceFilter(logging.Filter):
    """Attach a static `service` field (e.g. 'inthezon-api') to every record."""

    def __init__(self, service: str) -> None:
        super().__init__()
        self._service = service

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        record.service = self._service
        return True


def configure_logging(service: str) -> None:
    """Install the JSON (or text) logging config for the given service name."""
    use_json = settings.LOG_FORMAT.strip().lower() == "json"
    level = settings.LOG_LEVEL.strip().upper() or "INFO"

    # The JSON formatter expects all referenced field names to be present
    # on the record. `request_id` and `service` come from filters; the rest
    # come from the standard LogRecord attributes.
    json_format = (
        "%(asctime)s %(levelname)s %(name)s %(message)s "
        "%(request_id)s %(service)s"
    )
    text_format = (
        "%(asctime)s [%(service)s req=%(request_id)s] "
        "%(name)s %(levelname)s - %(message)s"
    )

    formatters = {
        "json": {
            "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
            "format": json_format,
            "rename_fields": {
                "asctime": "timestamp",
                "levelname": "level",
                "name": "logger",
            },
        },
        "text": {"format": text_format},
    }

    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": formatters,
            "filters": {
                "request_id": {"()": RequestIdLogFilter},
                "service": {"()": _ServiceFilter, "service": service},
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "json" if use_json else "text",
                    "filters": ["request_id", "service"],
                },
            },
            "root": {
                "level": level,
                "handlers": ["console"],
            },
        }
    )


def init_sentry(service: str) -> bool:
    """Initialize Sentry if `SENTRY_DSN` is set. Returns True if initialized.

    The lazy import here matters: sentry-sdk pulls in optional integration
    code at import time, so environments without the DSN avoid the cost.
    """
    dsn: Optional[str] = (settings.SENTRY_DSN or "").strip() or None
    if not dsn:
        logging.getLogger(__name__).info(
            "Sentry DSN not set; error tracking disabled",
            extra={"event": "sentry_skipped", "service": service},
        )
        return False

    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.celery import CeleryIntegration

    sentry_sdk.init(
        dsn=dsn,
        environment=settings.APP_ENV,
        traces_sample_rate=float(settings.SENTRY_TRACES_SAMPLE_RATE),
        integrations=[FastApiIntegration(), CeleryIntegration()],
        # Tag every event with the service name so the API and workers are
        # distinguishable in the Sentry UI without manual filtering.
        before_send=lambda event, hint: {**event, "tags": {**(event.get("tags") or {}), "service": service}},
    )
    logging.getLogger(__name__).info(
        "Sentry initialized",
        extra={"event": "sentry_initialized", "service": service},
    )
    return True
