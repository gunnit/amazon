"""Main API router."""
from fastapi import APIRouter

from app.api.v1 import (
    accounts,
    alerts,
    analytics,
    auth,
    catalog,
    exports,
    forecasts,
    google_sheets,
    market_research,
    recommendations,
    reports,
)

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(accounts.router, prefix="/accounts", tags=["Amazon Accounts"])
api_router.include_router(reports.router, prefix="/reports", tags=["Reports & Data"])
api_router.include_router(analytics.router, prefix="/analytics", tags=["Analytics"])
api_router.include_router(catalog.router, prefix="/catalog", tags=["Catalog Management"])
api_router.include_router(forecasts.router, prefix="/forecasts", tags=["Forecasting"])
api_router.include_router(exports.router, prefix="/exports", tags=["Exports"])
api_router.include_router(google_sheets.router, prefix="/google-sheets", tags=["Google Sheets"])
api_router.include_router(alerts.router, prefix="/alerts", tags=["Alerts"])
api_router.include_router(market_research.router, prefix="/market-research", tags=["Market Research"])
api_router.include_router(recommendations.router, prefix="/recommendations", tags=["Strategic Recommendations"])
