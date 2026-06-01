"""Forecasting endpoints."""
import logging
from typing import List, Optional
from datetime import date, timedelta
from uuid import UUID
from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import and_, func, select

from app.api.deps import CurrentUser, CurrentOrganization, DbSession
from app.models.amazon_account import AmazonAccount
from app.models.forecast import Forecast
from app.models.product import Product
from app.models.sales_data import SalesData
from app.schemas.analytics import ForecastHistoricalPoint, ForecastProductOption, ForecastResponse, ForecastPrediction
from app.services.data_extraction import DAILY_TOTAL_ASIN
from app.services.forecast_service import ForecastService

logger = logging.getLogger(__name__)

router = APIRouter()


async def _fetch_historical(
    db,
    account_id,
    asin: Optional[str],
    days: int = 30,
) -> List[ForecastHistoricalPoint]:
    """Fetch sales history to display alongside the forecast chart.

    Monthly vendor series store one sparse row per month, so a rolling daily
    window would return nothing; for those we return the full monthly span so
    the chart can compare history against the monthly predictions. Daily
    (seller) series keep the recent-window behaviour.
    """
    query = (
        select(SalesData.date, func.sum(SalesData.ordered_product_sales).label("value"))
        .where(SalesData.account_id == account_id)
        .group_by(SalesData.date)
        .order_by(SalesData.date)
    )
    if asin:
        query = query.where(SalesData.asin == asin)
    else:
        query = query.where(SalesData.asin == DAILY_TOTAL_ASIN)
    rows = (await db.execute(query)).all()

    dates = [row.date for row in rows]
    if not _is_monthly(dates):
        start_date = date.today() - timedelta(days=days)
        rows = [row for row in rows if row.date >= start_date]

    return [
        ForecastHistoricalPoint(date=row.date, value=float(row.value or 0))
        for row in rows
    ]


def _is_monthly(dates: List[date]) -> bool:
    """Detect a monthly cadence from date spacing (mirrors the forecast model)."""
    if len(dates) < 3:
        return False
    ordered = sorted(dates)
    gaps = sorted((ordered[i + 1] - ordered[i]).days for i in range(len(ordered) - 1))
    return gaps[len(gaps) // 2] >= 20


def _build_response(f, historical: List[ForecastHistoricalPoint]) -> ForecastResponse:
    """Build a ForecastResponse from a Forecast model instance."""
    return ForecastResponse(
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
        historical_data=historical,
        mape=float(f.mape) if f.mape is not None else None,
        rmse=float(f.rmse) if f.rmse is not None else None,
        confidence_level=f.confidence_level,
        data_quality_notes=list(f.data_quality_notes) if isinstance(f.data_quality_notes, list) else None,
    )


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

    responses = []
    for f in forecasts:
        historical = await _fetch_historical(db, f.account_id, f.asin)
        responses.append(_build_response(f, historical))
    return responses


@router.get("/available-products", response_model=List[ForecastProductOption])
async def list_forecast_available_products(
    account_id: UUID,
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
    lookback_days: int = Query(default=730, ge=30, le=1825),
    min_history_days: int = Query(default=ForecastService.MIN_HISTORY_DAYS, ge=1, le=30),
    limit: int = Query(default=1000, ge=1, le=5000),
    include_ineligible: bool = Query(
        default=True,
        description=(
            "When true (default), also return ASINs that have any sales in the lookback "
            "window but not enough history to forecast, flagged with is_eligible=false. "
            "The UI uses this to render disabled options with an explanation."
        ),
    ),
):
    """List ASINs the user can pick when generating a forecast.

    By default returns both eligible and ineligible ASINs; ineligible
    ones carry an actionable reason so the UI can disable them with an
    explanation instead of silently hiding them.
    """
    account_result = await db.execute(
        select(AmazonAccount.id).where(
            AmazonAccount.id == account_id,
            AmazonAccount.organization_id == organization.id,
        )
    )
    account = account_result.scalar_one_or_none()

    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account not found",
        )

    start_date = date.today() - timedelta(days=lookback_days)
    distinct_dates = func.count(func.distinct(SalesData.date))
    distinct_months = func.count(func.distinct(func.date_trunc("month", SalesData.date)))
    query = (
        select(
            SalesData.asin,
            func.max(Product.title).label("title"),
            distinct_dates.label("history_days"),
            distinct_months.label("history_months"),
            func.max(SalesData.date).label("last_sale_date"),
        )
        .select_from(SalesData)
        .outerjoin(
            Product,
            and_(
                Product.account_id == SalesData.account_id,
                Product.asin == SalesData.asin,
            ),
        )
        .where(
            SalesData.account_id == account_id,
            SalesData.asin != DAILY_TOTAL_ASIN,
            SalesData.date >= start_date,
        )
        .group_by(SalesData.asin)
        .order_by(func.max(SalesData.date).desc(), SalesData.asin)
        .limit(limit)
    )

    result = await db.execute(query)
    min_points = ForecastService.MIN_HISTORY_POINTS
    options: list[ForecastProductOption] = []
    for row in result.all():
        history_days = int(row.history_days or 0)
        history_months = int(row.history_months or 0)
        # Monthly vendor series store one row per month, so distinct days equal
        # distinct months — gate those on period count, daily series on days.
        is_monthly = history_days == history_months and history_months >= 2
        if is_monthly:
            is_eligible = history_months >= min_points
            reason = None if is_eligible else (
                f"Only {history_months} month{'s' if history_months != 1 else ''} of "
                f"sales history (need at least {min_points})."
            )
        else:
            is_eligible = history_days >= min_history_days
            reason = None if is_eligible else (
                f"Only {history_days} day{'s' if history_days != 1 else ''} of "
                f"sales history in the last {lookback_days} days "
                f"(need at least {min_history_days})."
            )
        options.append(
            ForecastProductOption(
                asin=row.asin,
                title=row.title,
                history_days=history_days,
                last_sale_date=row.last_sale_date,
                is_eligible=is_eligible,
                ineligible_reason=reason,
            )
        )

    if not include_ineligible:
        options = [o for o in options if o.is_eligible]
    options.sort(
        key=lambda o: (o.is_eligible, o.last_sale_date or date.min, o.asin),
        reverse=True,
    )
    return options


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

    historical = await _fetch_historical(db, forecast.account_id, forecast.asin)
    return _build_response(forecast, historical)


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

    historical = await _fetch_historical(db, forecast.account_id, forecast.asin)
    return _build_response(forecast, historical)
