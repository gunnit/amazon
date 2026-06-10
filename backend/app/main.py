"""Main FastAPI application entry point."""
from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic_core import PydanticUndefined
from sqlalchemy import text

from app.config import settings, validate_production_settings
from app.api.v1.router import api_router
from app.db.session import engine
from app.middleware.request_id import RequestIdMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.observability import configure_logging, init_sentry

# Logging + error tracking must be set up before any other module emits records.
configure_logging("inthezon-api")
init_sentry("inthezon-api")

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Inthezon Platform API (env=%s)", settings.APP_ENV)
    validate_production_settings(settings)

    scheduler = None
    if settings.ENABLE_INPROCESS_SCHEDULER:
        try:
            from apscheduler.schedulers.background import BackgroundScheduler
            from apscheduler.triggers.cron import CronTrigger
            from apscheduler.triggers.interval import IntervalTrigger
            from app.services.extraction_runner import (
                run_daily_sync_all,
                run_recent_seller_sales_sync_all,
            )
            from app.services.scheduled_report_service import run_scheduled_report_scan

            scheduler = BackgroundScheduler(timezone="UTC")
            scheduler.add_job(
                run_daily_sync_all,
                CronTrigger(
                    hour=settings.INPROCESS_SYNC_HOUR_UTC,
                    minute=settings.INPROCESS_SYNC_MINUTE_UTC,
                ),
                id="daily-account-sync",
                max_instances=1,
                coalesce=True,
                misfire_grace_time=3600,
            )
            scheduler.add_job(
                run_recent_seller_sales_sync_all,
                CronTrigger(
                    hour=settings.INPROCESS_SALES_REFRESH_HOURS_UTC,
                    minute=settings.INPROCESS_SALES_REFRESH_MINUTE_UTC,
                ),
                id="recent-seller-sales-refresh",
                max_instances=1,
                coalesce=True,
                misfire_grace_time=3600,
            )
            # Scheduled-report delivery: poll for due schedules and generate +
            # email them in-process. Replaces Celery beat's scan task, so weekly
            # reports work without a separate worker/Redis.
            scheduler.add_job(
                run_scheduled_report_scan,
                IntervalTrigger(minutes=settings.SCHEDULED_REPORT_SCAN_INTERVAL_MINUTES),
                id="scheduled-report-scan",
                max_instances=1,
                coalesce=True,
                misfire_grace_time=600,
            )
            scheduler.start()
            logger.info(
                "In-process scheduler started (daily sync at %02d:%02d UTC, "
                "seller sales refresh at %s:%02d UTC, scheduled-report scan every %d min)",
                settings.INPROCESS_SYNC_HOUR_UTC,
                settings.INPROCESS_SYNC_MINUTE_UTC,
                settings.INPROCESS_SALES_REFRESH_HOURS_UTC,
                settings.INPROCESS_SALES_REFRESH_MINUTE_UTC,
                settings.SCHEDULED_REPORT_SCAN_INTERVAL_MINUTES,
            )
        except Exception:
            logger.exception("Failed to start in-process scheduler")
            scheduler = None

    try:
        yield
    finally:
        logger.info("Shutting down Inthezon Platform API")
        if scheduler is not None:
            try:
                scheduler.shutdown(wait=False)
            except Exception:
                logger.exception("Error shutting down scheduler")
        await engine.dispose()


# Create FastAPI app
app = FastAPI(
    title="Inthezon Platform API",
    description="Multi-tenant SaaS platform for Amazon account management and analytics",
    version="1.0.0",
    docs_url="/api/docs" if settings.APP_DEBUG else None,
    redoc_url="/api/redoc" if settings.APP_DEBUG else None,
    lifespan=lifespan,
)

# Request ID middleware must be added BEFORE CORS so the request_id context
# is set for every dispatched route, including preflight responses.
app.add_middleware(RequestIdMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Exception handlers
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Return a clean 422 for request validation errors.

    FastAPI's default handler crashes when an error context carries the
    PydanticUndefined sentinel, so we encode it explicitly to None.
    """
    errors = jsonable_encoder(
        exc.errors(),
        custom_encoder={type(PydanticUndefined): lambda _v: None},
    )
    return JSONResponse(status_code=422, content={"detail": errors})


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler."""
    logger.exception(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


# Include API router
app.include_router(api_router, prefix="/api/v1")


@app.get("/health")
async def health_check():
    """Liveness probe — returns 200 as long as the process is up.

    Does NOT verify external dependencies; use /health/ready for that.
    """
    return {
        "status": "ok",
        "version": "1.0.0",
        "environment": settings.APP_ENV,
    }


@app.get("/health/ready")
async def readiness_check():
    """Readiness probe — verifies DB and (when configured) Redis are reachable.

    Returns 200 with per-dependency status when all checks pass. Returns 503
    with the same payload (so callers can introspect which dependency is
    failing) when at least one check fails.
    """
    checks: dict[str, dict[str, str]] = {}
    overall_ok = True

    # Database
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        checks["database"] = {"status": "ok"}
    except Exception as exc:  # broad: any failure is a readiness signal
        overall_ok = False
        checks["database"] = {"status": "error", "detail": str(exc)[:200]}

    # Redis (best-effort — skipped if no URL configured)
    redis_url = settings.REDIS_URL or settings.CELERY_BROKER_URL
    if redis_url:
        try:
            import redis.asyncio as redis_asyncio  # lazy import; not in hot path

            redis_client = redis_asyncio.from_url(redis_url, socket_timeout=2.0)
            try:
                await redis_client.ping()
                checks["redis"] = {"status": "ok"}
            finally:
                await redis_client.aclose()
        except Exception as exc:
            overall_ok = False
            checks["redis"] = {"status": "error", "detail": str(exc)[:200]}
    else:
        checks["redis"] = {"status": "skipped", "detail": "no REDIS_URL configured"}

    body = {"status": "ok" if overall_ok else "error", "checks": checks}
    return JSONResponse(status_code=200 if overall_ok else 503, content=body)


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "Inthezon Platform API",
        "docs": "/api/docs",
        "health": "/health",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.APP_DEBUG,
    )
