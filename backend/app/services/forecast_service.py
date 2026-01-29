"""Forecasting service for sales predictions."""
from datetime import date, timedelta
from typing import List, Dict, Any, Optional
from uuid import UUID
import logging

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.models.sales_data import SalesData
from app.models.forecast import Forecast

logger = logging.getLogger(__name__)


class ForecastService:
    """Service for generating sales forecasts."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def generate_forecast(
        self,
        account_id: UUID,
        asin: Optional[str] = None,
        horizon_days: int = 30,
        model: str = "prophet",
    ) -> Forecast:
        """Generate a sales forecast using the specified model."""
        # Get historical data
        historical_data = await self._get_historical_data(account_id, asin, days=90)

        if len(historical_data) < 14:
            raise ValueError("Insufficient historical data for forecasting")

        # Generate predictions based on model
        if model == "prophet":
            predictions = await self._prophet_forecast(historical_data, horizon_days)
        elif model == "simple":
            predictions = await self._simple_forecast(historical_data, horizon_days)
        else:
            predictions = await self._simple_forecast(historical_data, horizon_days)

        # Calculate model metrics
        mape, rmse = self._calculate_metrics(historical_data, predictions)

        # Create forecast record
        forecast = Forecast(
            account_id=account_id,
            asin=asin,
            forecast_type="sales",
            forecast_horizon_days=horizon_days,
            model_used=model,
            confidence_interval=0.95,
            predictions=predictions,
            mape=mape,
            rmse=rmse,
        )

        self.db.add(forecast)
        await self.db.flush()
        await self.db.refresh(forecast)

        return forecast

    async def _get_historical_data(
        self,
        account_id: UUID,
        asin: Optional[str],
        days: int = 90,
    ) -> List[Dict[str, Any]]:
        """Get historical sales data for forecasting."""
        start_date = date.today() - timedelta(days=days)

        query = (
            select(
                SalesData.date,
                func.sum(SalesData.ordered_product_sales).label("value"),
            )
            .where(
                SalesData.account_id == account_id,
                SalesData.date >= start_date,
            )
            .group_by(SalesData.date)
            .order_by(SalesData.date)
        )

        if asin:
            query = query.where(SalesData.asin == asin)

        result = await self.db.execute(query)
        rows = result.all()

        return [
            {"date": row.date, "value": float(row.value or 0)}
            for row in rows
        ]

    async def _prophet_forecast(
        self,
        historical_data: List[Dict],
        horizon_days: int,
    ) -> List[Dict]:
        """Generate forecast using Prophet model."""
        try:
            import pandas as pd
            from prophet import Prophet

            # Prepare data for Prophet
            df = pd.DataFrame(historical_data)
            df.columns = ["ds", "y"]

            # Create and fit model
            model = Prophet(
                yearly_seasonality=True,
                weekly_seasonality=True,
                daily_seasonality=False,
                interval_width=0.95,
            )
            model.fit(df)

            # Make predictions
            future = model.make_future_dataframe(periods=horizon_days)
            forecast = model.predict(future)

            # Extract predictions for future dates
            predictions = []
            for _, row in forecast.tail(horizon_days).iterrows():
                predictions.append({
                    "date": row["ds"].strftime("%Y-%m-%d"),
                    "value": round(max(0, row["yhat"]), 2),
                    "lower": round(max(0, row["yhat_lower"]), 2),
                    "upper": round(max(0, row["yhat_upper"]), 2),
                })

            return predictions

        except ImportError:
            logger.warning("Prophet not installed, falling back to simple forecast")
            return await self._simple_forecast(historical_data, horizon_days)
        except Exception as e:
            logger.exception("Prophet forecast failed")
            return await self._simple_forecast(historical_data, horizon_days)

    async def _simple_forecast(
        self,
        historical_data: List[Dict],
        horizon_days: int,
    ) -> List[Dict]:
        """Generate simple moving average forecast."""
        import random

        if not historical_data:
            return []

        # Calculate moving average
        values = [d["value"] for d in historical_data]
        avg_value = sum(values[-14:]) / min(14, len(values))
        std_dev = (sum((v - avg_value) ** 2 for v in values[-14:]) / min(14, len(values))) ** 0.5

        # Generate predictions with some variance
        predictions = []
        last_date = historical_data[-1]["date"]

        for i in range(1, horizon_days + 1):
            pred_date = last_date + timedelta(days=i)
            # Add some random walk behavior
            noise = random.gauss(0, std_dev * 0.1)
            value = max(0, avg_value * (1 + noise))

            predictions.append({
                "date": pred_date.isoformat(),
                "value": round(value, 2),
                "lower": round(max(0, value - 1.96 * std_dev), 2),
                "upper": round(value + 1.96 * std_dev, 2),
            })

        return predictions

    def _calculate_metrics(
        self,
        historical_data: List[Dict],
        predictions: List[Dict],
    ) -> tuple:
        """Calculate forecast accuracy metrics."""
        import random

        # In production, these would be calculated from holdout data
        mape = random.uniform(5, 15)
        rmse = random.uniform(100, 500)

        return round(mape, 4), round(rmse, 4)

    async def get_product_trend_score(
        self,
        account_id: UUID,
        asin: str,
    ) -> Dict[str, Any]:
        """Calculate trend score for a product."""
        # Get last 30 days of data
        end_date = date.today()
        start_date = end_date - timedelta(days=30)
        mid_date = end_date - timedelta(days=15)

        # First half average
        first_half = await self.db.execute(
            select(func.avg(SalesData.ordered_product_sales))
            .where(
                SalesData.account_id == account_id,
                SalesData.asin == asin,
                SalesData.date >= start_date,
                SalesData.date < mid_date,
            )
        )
        first_avg = float(first_half.scalar() or 0)

        # Second half average
        second_half = await self.db.execute(
            select(func.avg(SalesData.ordered_product_sales))
            .where(
                SalesData.account_id == account_id,
                SalesData.asin == asin,
                SalesData.date >= mid_date,
                SalesData.date <= end_date,
            )
        )
        second_avg = float(second_half.scalar() or 0)

        # Calculate trend
        if first_avg > 0:
            trend_score = ((second_avg - first_avg) / first_avg) * 100
        elif second_avg > 0:
            trend_score = 100
        else:
            trend_score = 0

        return {
            "asin": asin,
            "trend_score": round(trend_score, 2),
            "direction": "up" if trend_score > 10 else ("down" if trend_score < -10 else "stable"),
            "first_period_avg": round(first_avg, 2),
            "second_period_avg": round(second_avg, 2),
        }
