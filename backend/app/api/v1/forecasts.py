"""Forecasting endpoints."""
import logging
from typing import List, Optional
from datetime import date, timedelta
from uuid import UUID
from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import CurrentUser, CurrentOrganization, DbSession
from app.models.amazon_account import AmazonAccount
from app.models.forecast import Forecast
from app.schemas.analytics import ForecastResponse, ForecastPrediction
from app.services.forecast_service import ForecastService

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("", response_model=List[ForecastResponse])
async def list_forecasts(
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
    account_ids: Optional[List[UUID]] = None,
    forecast_type: Optional[str] = None,
    limit: int = 20,
):
    """List available forecasts."""
    accounts_query = select(AmazonAccount.id).where(
        AmazonAccount.organization_id == organization.id
    )
    if account_ids:
        accounts_query = accounts_query.where(AmazonAccount.id.in_(account_ids))

    query = (
        select(Forecast)
        .where(Forecast.account_id.in_(accounts_query))
        .order_by(Forecast.generated_at.desc())
        .limit(limit)
    )

    if forecast_type:
        query = query.where(Forecast.forecast_type == forecast_type)

    result = await db.execute(query)
    forecasts = result.scalars().all()

    return [
        ForecastResponse(
            id=str(f.id),
            account_id=str(f.account_id),
            asin=f.asin,
            forecast_type=f.forecast_type or "sales",
            generated_at=f.generated_at.isoformat() if f.generated_at else "",
            horizon_days=f.forecast_horizon_days or 30,
            model_used=f.model_used or "prophet",
            confidence_interval=float(f.confidence_interval or 0.95),
            predictions=[
                ForecastPrediction(
                    date=date.fromisoformat(p["date"]) if isinstance(p["date"], str) else p["date"],
                    predicted_value=p["value"],
                    lower_bound=p.get("lower", p["value"] * 0.8),
                    upper_bound=p.get("upper", p["value"] * 1.2),
                )
                for p in (f.predictions or [])
            ],
            mape=float(f.mape) if f.mape else None,
            rmse=float(f.rmse) if f.rmse else None,
        )
        for f in forecasts
    ]


@router.post("/generate", response_model=dict)
async def generate_forecast(
    account_id: UUID,
    current_user: CurrentUser = None,
    organization: CurrentOrganization = None,
    db: DbSession = None,
    forecast_type: str = "sales",
    horizon_days: int = 30,
    asin: Optional[str] = None,
):
    """Generate a new forecast."""
    # Verify account belongs to organization
    result = await db.execute(
        select(AmazonAccount)
        .where(
            AmazonAccount.id == account_id,
            AmazonAccount.organization_id == organization.id,
        )
    )
    account = result.scalar_one_or_none()

    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account not found"
        )

    service = ForecastService(db)
    try:
        forecast = await service.generate_forecast(
            account_id=account_id,
            asin=asin or None,
            horizon_days=horizon_days,
            model="prophet",
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )

    return {
        "id": str(forecast.id),
        "status": "completed",
        "message": f"Forecast generated for {horizon_days} days",
        "model_used": forecast.model_used,
    }


@router.get("/{forecast_id}", response_model=ForecastResponse)
async def get_forecast(
    forecast_id: UUID,
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
):
    """Get forecast details."""
    accounts_query = select(AmazonAccount.id).where(
        AmazonAccount.organization_id == organization.id
    )

    result = await db.execute(
        select(Forecast)
        .where(
            Forecast.id == forecast_id,
            Forecast.account_id.in_(accounts_query),
        )
    )
    forecast = result.scalar_one_or_none()

    if not forecast:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Forecast not found"
        )

    return ForecastResponse(
        id=str(forecast.id),
        account_id=str(forecast.account_id),
        asin=forecast.asin,
        forecast_type=forecast.forecast_type or "sales",
        generated_at=forecast.generated_at.isoformat() if forecast.generated_at else "",
        horizon_days=forecast.forecast_horizon_days or 30,
        model_used=forecast.model_used or "prophet",
        confidence_interval=float(forecast.confidence_interval or 0.95),
        predictions=[
            ForecastPrediction(
                date=date.fromisoformat(p["date"]) if isinstance(p["date"], str) else p["date"],
                predicted_value=p["value"],
                lower_bound=p.get("lower", p["value"] * 0.8),
                upper_bound=p.get("upper", p["value"] * 1.2),
            )
            for p in (forecast.predictions or [])
        ],
        mape=float(forecast.mape) if forecast.mape else None,
        rmse=float(forecast.rmse) if forecast.rmse else None,
    )


@router.get("/products/{asin}", response_model=ForecastResponse)
async def get_product_forecast(
    asin: str,
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
):
    """Get latest forecast for a specific product."""
    accounts_query = select(AmazonAccount.id).where(
        AmazonAccount.organization_id == organization.id
    )

    result = await db.execute(
        select(Forecast)
        .where(
            Forecast.account_id.in_(accounts_query),
            Forecast.asin == asin,
        )
        .order_by(Forecast.generated_at.desc())
        .limit(1)
    )
    forecast = result.scalar_one_or_none()

    if not forecast:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No forecast found for ASIN {asin}"
        )

    return ForecastResponse(
        id=str(forecast.id),
        account_id=str(forecast.account_id),
        asin=forecast.asin,
        forecast_type=forecast.forecast_type or "sales",
        generated_at=forecast.generated_at.isoformat() if forecast.generated_at else "",
        horizon_days=forecast.forecast_horizon_days or 30,
        model_used=forecast.model_used or "prophet",
        confidence_interval=float(forecast.confidence_interval or 0.95),
        predictions=[
            ForecastPrediction(
                date=date.fromisoformat(p["date"]) if isinstance(p["date"], str) else p["date"],
                predicted_value=p["value"],
                lower_bound=p.get("lower", p["value"] * 0.8),
                upper_bound=p.get("upper", p["value"] * 1.2),
            )
            for p in (forecast.predictions or [])
        ],
        mape=float(forecast.mape) if forecast.mape else None,
        rmse=float(forecast.rmse) if forecast.rmse else None,
    )
