"""Main FastAPI application entry point."""
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import logging

from app.config import settings
from app.api.v1.router import api_router
from app.db.session import engine

logging.basicConfig(
    level=logging.DEBUG if settings.APP_DEBUG else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Inthezon Platform API (env=%s)", settings.APP_ENV)

    scheduler = None
    if settings.ENABLE_INPROCESS_SCHEDULER:
        try:
            from apscheduler.schedulers.background import BackgroundScheduler
            from apscheduler.triggers.cron import CronTrigger
            from app.services.extraction_runner import run_daily_sync_all

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
            scheduler.start()
            logger.info(
                "In-process scheduler started (daily sync at %02d:%02d UTC)",
                settings.INPROCESS_SYNC_HOUR_UTC,
                settings.INPROCESS_SYNC_MINUTE_UTC,
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

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Exception handlers
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


# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "version": "1.0.0",
        "environment": settings.APP_ENV,
    }


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
