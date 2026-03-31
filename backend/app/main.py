"""Main FastAPI application entry point."""
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import logging

from app.config import settings
from app.api.v1.router import api_router
from sqlalchemy import text as sa_text
from app.db.session import engine
from app.db.base import Base

# Configure logging
logging.basicConfig(
    level=logging.DEBUG if settings.APP_DEBUG else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup
    logger.info("Starting Inthezon Platform API")
    logger.info(f"Environment: {settings.APP_ENV}")

    # Run migrations and ensure schema is up to date
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Add columns that create_all can't add to existing tables
        for statement in [
            "ALTER TABLE market_research_reports ADD COLUMN IF NOT EXISTS progress_step VARCHAR(100)",
            "ALTER TABLE market_research_reports ADD COLUMN IF NOT EXISTS progress_pct INTEGER DEFAULT 0",
        ]:
            try:
                await conn.execute(sa_text(statement))
            except Exception:
                pass  # Column already exists or table doesn't exist yet
    logger.info("Database tables created/verified")

    yield

    # Shutdown
    logger.info("Shutting down Inthezon Platform API")
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
