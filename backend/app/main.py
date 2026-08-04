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
                run_asin_economics_sync_all,
                run_backfill_recovery_sweep,
                run_brand_analysis_recovery,
                run_brand_search_terms_sync_all,
                run_competitor_tracking_all,
                run_daily_sync_all,
                run_listing_quality_snapshot_all,
                run_market_snapshot_all,
                run_recent_orders_sync_all,
                run_recent_seller_sales_sync_all,
                run_sales_gap_repair_all,
            )
            from app.services.alert_check_service import run_alert_check, run_daily_digest
            from app.services.brand_intelligence_service import (
                run_brand_intelligence_recovery,
                run_brand_intelligence_scan,
            )
            from app.services.db_maintenance import run_partition_ensure
            from app.services.forecast_service import run_weekly_forecast_generation
            from app.services.google_sheets_service import run_google_sheets_scan
            from app.services.scheduled_report_service import (
                run_scheduled_report_recovery,
                run_scheduled_report_scan,
            )
            from app.services.strategic_recommendations_service import (
                run_weekly_recommendations,
            )

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
            # Backfills interrupted by a process restart stay `running` forever
            # without this sweep.
            scheduler.add_job(
                run_backfill_recovery_sweep,
                IntervalTrigger(hours=1),
                id="backfill-recovery-sweep",
                max_instances=1,
                coalesce=True,
                misfire_grace_time=600,
            )
            # Re-pull sales dates missing from the warehouse (a failed window
            # older than the 30-day rolling refresh never heals otherwise).
            scheduler.add_job(
                run_sales_gap_repair_all,
                CronTrigger(hour=4, minute=30),
                id="sales-gap-repair",
                max_instances=1,
                coalesce=True,
                misfire_grace_time=3600,
            )
            # Near-real-time orders for the "today" dashboard metrics. Orders
            # API quota, independent of the report-based syncs.
            scheduler.add_job(
                run_recent_orders_sync_all,
                CronTrigger(minute=45),
                id="recent-orders-refresh",
                max_instances=1,
                coalesce=True,
                misfire_grace_time=900,
            )
            # Per-ASIN profitability from the Data Kiosk economics dataset.
            scheduler.add_job(
                run_asin_economics_sync_all,
                CronTrigger(hour=5, minute=30),
                id="asin-economics-sync",
                max_instances=1,
                coalesce=True,
                misfire_grace_time=3600,
            )
            # Fee estimates + price/Buy Box snapshots (Pricing/Fees quotas).
            scheduler.add_job(
                run_market_snapshot_all,
                CronTrigger(hour=6, minute=30),
                id="market-snapshot",
                max_instances=1,
                coalesce=True,
                misfire_grace_time=3600,
            )
            # Daily tracked-competitor snapshots (Catalog/Pricing quotas,
            # after the market snapshot so the two don't overlap on Pricing).
            scheduler.add_job(
                run_competitor_tracking_all,
                CronTrigger(hour=7, minute=15),
                id="competitor-tracking",
                max_instances=1,
                coalesce=True,
                misfire_grace_time=3600,
            )
            # Weekly Brand Analytics search terms (published a few days after
            # the Sun-Sat reporting week closes; Wednesday is safely after).
            scheduler.add_job(
                run_brand_search_terms_sync_all,
                CronTrigger(day_of_week="wed", hour=7, minute=0),
                id="brand-search-terms-sync",
                max_instances=1,
                coalesce=True,
                misfire_grace_time=3600,
            )
            # Weekly listing-quality snapshots for trend lines (DB only).
            scheduler.add_job(
                run_listing_quality_snapshot_all,
                CronTrigger(day_of_week="sun", hour=7, minute=30),
                id="listing-quality-snapshot",
                max_instances=1,
                coalesce=True,
                misfire_grace_time=3600,
            )
            # Finalize brand-analysis jobs whose in-process thread was lost to a
            # web-process restart (deploy mid-run). Without this, such jobs hang
            # at "In preparazione" forever since there is no Celery beat in prod.
            scheduler.add_job(
                run_brand_analysis_recovery,
                IntervalTrigger(minutes=settings.BRAND_ANALYSIS_RECOVERY_INTERVAL_MINUTES),
                id="brand-analysis-recovery",
                max_instances=1,
                coalesce=True,
                misfire_grace_time=600,
            )
            # ---- Jobs below existed only in Celery beat; without them the
            # weekly artifacts silently go stale in worker-less deployments.
            # Configurable alert rules (low_stock/price_change/bsr_drop/
            # sync_failure) are only evaluated here.
            scheduler.add_job(
                run_alert_check,
                CronTrigger(minute=5),
                id="hourly-alert-check",
                max_instances=1,
                coalesce=True,
                misfire_grace_time=900,
            )
            scheduler.add_job(
                run_daily_digest,
                CronTrigger(hour=8, minute=0),
                id="daily-digest",
                max_instances=1,
                coalesce=True,
                misfire_grace_time=3600,
            )
            scheduler.add_job(
                run_weekly_forecast_generation,
                CronTrigger(day_of_week="sun", hour=3, minute=0),
                id="weekly-forecasts",
                max_instances=1,
                coalesce=True,
                misfire_grace_time=3600,
            )
            scheduler.add_job(
                run_weekly_recommendations,
                CronTrigger(day_of_week="mon", hour=6, minute=0),
                id="weekly-strategic-recommendations",
                max_instances=1,
                coalesce=True,
                misfire_grace_time=3600,
            )
            scheduler.add_job(
                run_brand_intelligence_scan,
                IntervalTrigger(minutes=15),
                id="brand-intelligence-scan",
                max_instances=1,
                coalesce=True,
                misfire_grace_time=600,
            )
            scheduler.add_job(
                run_brand_intelligence_recovery,
                IntervalTrigger(minutes=30),
                id="brand-intelligence-recovery",
                max_instances=1,
                coalesce=True,
                misfire_grace_time=600,
            )
            scheduler.add_job(
                run_scheduled_report_recovery,
                IntervalTrigger(minutes=15),
                id="scheduled-report-recovery",
                max_instances=1,
                coalesce=True,
                misfire_grace_time=600,
            )
            scheduler.add_job(
                run_google_sheets_scan,
                IntervalTrigger(minutes=5),
                id="google-sheets-sync-scan",
                max_instances=1,
                coalesce=True,
                misfire_grace_time=300,
            )
            # Creation-only: never drops partitions (see db_maintenance.py).
            scheduler.add_job(
                run_partition_ensure,
                CronTrigger(hour=3, minute=30),
                id="partition-ensure",
                max_instances=1,
                coalesce=True,
                misfire_grace_time=3600,
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
    # Disabling docs_url alone still leaves /openapi.json public, which hands
    # out the full endpoint/schema inventory. Nothing consumes it in prod.
    openapi_url="/openapi.json" if settings.APP_DEBUG else None,
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


def _readiness_detail(exc: Exception) -> str:
    """Readiness is unauthenticated, so never echo the driver's error text.

    Connection errors routinely embed host, port, database name and sometimes
    credentials. The full traceback goes to the logs instead.
    """
    if settings.is_production:
        return type(exc).__name__
    return str(exc)[:200]


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
        logger.warning("Readiness: database check failed", exc_info=True)
        checks["database"] = {"status": "error", "detail": _readiness_detail(exc)}

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
            logger.warning("Readiness: redis check failed", exc_info=True)
            checks["redis"] = {"status": "error", "detail": _readiness_detail(exc)}
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
