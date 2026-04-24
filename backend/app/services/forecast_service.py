"""Forecasting service for sales predictions."""
from datetime import date, timedelta
from typing import List, Dict, Any, Optional, Tuple
from uuid import UUID
import logging

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.models.sales_data import SalesData
from app.models.forecast import Forecast
from app.services.data_extraction import DAILY_TOTAL_ASIN

logger = logging.getLogger(__name__)


class ForecastService:
    """Service for generating sales forecasts."""

    MIN_HISTORY_DAYS = 14
    MIN_RELIABLE_HISTORY_DAYS = 28
    RECOMMENDED_HISTORY_DAYS = 90

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
        historical_data = await self._get_historical_data(account_id, asin, days=90)

        # Product-level series are often sparse in the most recent 90 days even when
        # the account has enough older data to build a forecast.
        if asin and len(historical_data) < self.MIN_HISTORY_DAYS:
            historical_data = await self._get_historical_data(account_id, asin, days=365)

        if len(historical_data) < self.MIN_HISTORY_DAYS:
            raise ValueError(
                f"Insufficient historical data for forecasting "
                f"(need at least {self.MIN_HISTORY_DAYS} days)"
            )

        # Fill date gaps with zeros for a continuous time series
        historical_data = self._fill_date_gaps(historical_data)
        n_days = len(historical_data)

        # Choose strategy based on data availability
        strategy = self._choose_strategy(n_days)
        chosen_model = strategy["model"] if model == "prophet" else model

        # Cap horizon: strict cap for Prophet, relaxed for simple model
        max_horizon = strategy["max_horizon"]
        effective_horizon = min(horizon_days, max_horizon)
        # Simple model (weighted averages) can safely predict up to 90 days
        simple_horizon = min(horizon_days, 90)

        logger.info(
            f"Forecast strategy: {strategy['label']} | "
            f"{n_days} data points | model={chosen_model} | "
            f"horizon={effective_horizon}d (requested {horizon_days}d)"
        )

        if chosen_model == "prophet":
            predictions = await self._prophet_forecast(
                historical_data, effective_horizon, strategy,
                fallback_horizon=simple_horizon,
            )
        else:
            predictions = self._simple_forecast(historical_data, simple_horizon)

        # Metrics via holdout validation
        mape, rmse = await self._calculate_metrics(historical_data, chosen_model, strategy)
        confidence_level = self._determine_confidence_level(mape)
        data_quality_notes = self._build_data_quality_notes(historical_data, strategy, mape)

        forecast = Forecast(
            account_id=account_id,
            asin=asin,
            forecast_type="sales",
            forecast_horizon_days=len(predictions),
            model_used=chosen_model,
            confidence_interval=0.95,
            predictions=predictions,
            mape=mape,
            rmse=rmse,
            confidence_level=confidence_level,
            data_quality_notes=data_quality_notes or None,
        )

        self.db.add(forecast)
        await self.db.flush()
        await self.db.refresh(forecast)

        return forecast

    # ------------------------------------------------------------------
    # Strategy
    # ------------------------------------------------------------------

    @staticmethod
    def _choose_strategy(n_days: int) -> Dict[str, Any]:
        """Pick model configuration based on how much data we have."""
        if n_days >= 365:
            return {
                "label": "full",
                "model": "prophet",
                "yearly_seasonality": True,
                "weekly_seasonality": True,
                "changepoint_prior_scale": 0.05,
                "max_horizon": 90,
            }
        if n_days >= 90:
            return {
                "label": "medium",
                "model": "prophet",
                "yearly_seasonality": False,
                "weekly_seasonality": True,
                "changepoint_prior_scale": 0.01,
                "max_horizon": 30,
            }
        if n_days >= 28:
            return {
                "label": "limited",
                "model": "prophet",
                "yearly_seasonality": False,
                "weekly_seasonality": True,
                "changepoint_prior_scale": 0.05,
                "seasonality_prior_scale": 1.0,
                "max_horizon": 14,
            }
        # < 28 days — too little for Prophet
        return {
            "label": "minimal",
            "model": "simple",
            "max_horizon": 7,
        }

    # ------------------------------------------------------------------
    # Historical data
    # ------------------------------------------------------------------

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
        else:
            query = query.where(SalesData.asin == DAILY_TOTAL_ASIN)

        result = await self.db.execute(query)
        rows = result.all()

        return [
            {"date": row.date, "value": float(row.value or 0)}
            for row in rows
        ]

    @staticmethod
    def _fill_date_gaps(data: List[Dict]) -> List[Dict]:
        """Fill missing dates with value=0 so models see a continuous series."""
        if len(data) < 2:
            return data

        by_date = {d["date"]: d["value"] for d in data}
        start = data[0]["date"]
        end = data[-1]["date"]
        filled = []
        current = start
        while current <= end:
            filled.append({"date": current, "value": by_date.get(current, 0.0)})
            current += timedelta(days=1)
        return filled

    # ------------------------------------------------------------------
    # Prophet forecast (adaptive)
    # ------------------------------------------------------------------

    async def _prophet_forecast(
        self,
        historical_data: List[Dict],
        horizon_days: int,
        strategy: Dict[str, Any],
        fallback_horizon: Optional[int] = None,
    ) -> List[Dict]:
        """Generate forecast using Prophet with strategy-tuned parameters."""
        fb_horizon = fallback_horizon or horizon_days
        try:
            import pandas as pd
            from prophet import Prophet

            df = pd.DataFrame(historical_data)
            df.columns = ["ds", "y"]
            holidays_df = None
            if strategy.get("label") in {"full", "medium"}:
                holidays_df = self._build_amazon_holidays(
                    pd,
                    start_year=int(df["ds"].min().year),
                    end_year=int((df["ds"].max() + pd.Timedelta(days=horizon_days)).year),
                )

            model = Prophet(
                yearly_seasonality=strategy.get("yearly_seasonality", False),
                weekly_seasonality=strategy.get("weekly_seasonality", True),
                daily_seasonality=False,
                changepoint_prior_scale=strategy.get("changepoint_prior_scale", 0.01),
                seasonality_prior_scale=strategy.get("seasonality_prior_scale", 1.0),
                interval_width=0.95,
                holidays=holidays_df,
            )
            model.fit(df)

            future = model.make_future_dataframe(periods=horizon_days)
            forecast = model.predict(future)

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
            return self._simple_forecast(historical_data, fb_horizon)
        except Exception:
            logger.exception("Prophet forecast failed, falling back to simple")
            return self._simple_forecast(historical_data, fb_horizon)

    # ------------------------------------------------------------------
    # Simple forecast (day-of-week weighted average)
    # ------------------------------------------------------------------

    @staticmethod
    def _simple_forecast(
        historical_data: List[Dict],
        horizon_days: int,
    ) -> List[Dict]:
        """Forecast using day-of-week weighted averages with a light trend."""
        if not historical_data:
            return []

        # Build day-of-week averages from the most recent data
        dow_values: Dict[int, List[float]] = {i: [] for i in range(7)}
        for d in historical_data:
            dow = d["date"].weekday()
            dow_values[dow].append(d["value"])

        dow_avg = {}
        for dow, vals in dow_values.items():
            dow_avg[dow] = sum(vals) / len(vals) if vals else 0.0

        # Overall stats (needed for trend cap and confidence intervals)
        all_values = [d["value"] for d in historical_data]
        mean_val = sum(all_values) / len(all_values) if all_values else 0
        std_dev = (sum((v - mean_val) ** 2 for v in all_values) / len(all_values)) ** 0.5

        # Light linear trend from last 14 days, capped to avoid overshooting
        recent = historical_data[-14:]
        if len(recent) >= 7:
            first_half = sum(d["value"] for d in recent[: len(recent) // 2])
            second_half = sum(d["value"] for d in recent[len(recent) // 2 :])
            first_n = len(recent) // 2
            second_n = len(recent) - first_n
            daily_trend = (second_half / second_n - first_half / first_n) if first_n and second_n else 0
            # Cap trend to ±20% of mean to prevent runaway predictions
            cap = mean_val * 0.2
            daily_trend = max(-cap, min(cap, daily_trend))
        else:
            daily_trend = 0

        last_date = historical_data[-1]["date"]
        predictions = []

        for i in range(1, horizon_days + 1):
            pred_date = last_date + timedelta(days=i)
            dow = pred_date.weekday()
            base = dow_avg.get(dow, mean_val)
            # Apply trend, damped exponentially over time
            dampened_trend = daily_trend * (0.9 ** i)
            value = max(0, base + dampened_trend)

            predictions.append({
                "date": pred_date.isoformat(),
                "value": round(value, 2),
                "lower": round(max(0, value - 1.96 * std_dev), 2),
                "upper": round(value + 1.96 * std_dev, 2),
            })

        return predictions

    # ------------------------------------------------------------------
    # Metrics (holdout cross-validation)
    # ------------------------------------------------------------------

    async def _calculate_metrics(
        self,
        historical_data: List[Dict],
        model: str,
        strategy: Dict[str, Any],
    ) -> Tuple[float, float]:
        """Calculate MAPE/RMSE via holdout: train on all-but-last-7, predict 7, compare."""
        holdout_size = min(7, len(historical_data) // 3)
        if holdout_size < 3:
            return self._variance_metrics(historical_data)

        train = historical_data[:-holdout_size]
        actuals = [d["value"] for d in historical_data[-holdout_size:]]

        if model == "prophet":
            preds_raw = await self._prophet_forecast(
                train,
                holdout_size,
                strategy,
                fallback_horizon=holdout_size,
            )
        else:
            preds_raw = self._simple_forecast(train, holdout_size)
        preds = [p["value"] for p in preds_raw]
        if len(preds) < holdout_size:
            return self._variance_metrics(historical_data)

        # MAPE (skip zero actuals)
        ape_sum = sum(abs(a - p) / a for a, p in zip(actuals, preds) if a != 0)
        non_zero = sum(1 for a in actuals if a != 0)
        mape = (ape_sum / non_zero * 100) if non_zero else 0

        # RMSE
        mse = sum((a - p) ** 2 for a, p in zip(actuals, preds)) / holdout_size
        rmse = mse ** 0.5

        return round(mape, 4), round(rmse, 4)

    @staticmethod
    def _variance_metrics(data: List[Dict]) -> Tuple[float, float]:
        """Fallback metrics from variance when not enough data for holdout."""
        values = [d["value"] for d in data]
        mean_val = sum(values) / len(values) if values else 1
        std_val = (sum((v - mean_val) ** 2 for v in values) / len(values)) ** 0.5 if values else 0
        mape = (std_val / mean_val * 100) if mean_val else 0
        rmse = std_val
        return round(mape, 4), round(rmse, 4)

    @staticmethod
    def _determine_confidence_level(mape: Optional[float]) -> Optional[str]:
        """Map validation error to a confidence label."""
        if mape is None:
            return None
        if mape < 15:
            return "high"
        if mape < 30:
            return "medium"
        return "low"

    def _build_data_quality_notes(
        self,
        historical_data: List[Dict],
        strategy: Dict[str, Any],
        mape: Optional[float],
    ) -> List[str]:
        """Attach practical quality notes that help explain forecast reliability."""
        notes: List[str] = []
        n_days = len(historical_data)
        values = [d["value"] for d in historical_data]
        mean_val = sum(values) / len(values) if values else 0
        std_dev = (sum((v - mean_val) ** 2 for v in values) / len(values)) ** 0.5 if values else 0

        if n_days < self.MIN_RELIABLE_HISTORY_DAYS:
            notes.append("Less than 28 days of data")
        elif n_days < self.RECOMMENDED_HISTORY_DAYS:
            notes.append("Less than 90 days of data")

        if mean_val > 0 and (std_dev / mean_val) >= 1:
            notes.append("High variance detected")

        if strategy.get("label") == "minimal":
            notes.append("Using simplified model due to limited history")

        if mape is not None and mape >= 30:
            notes.append("Historical validation error is high")

        return list(dict.fromkeys(notes))

    @staticmethod
    def _build_amazon_holidays(pd_module, start_year: int, end_year: int):
        """Build a small set of major Amazon demand events for Prophet."""
        holiday_names: List[str] = []
        holiday_dates = []
        for year in range(start_year, end_year + 1):
            black_friday = ForecastService._black_friday(year)
            cyber_monday = black_friday + timedelta(days=3)

            holiday_names.extend(["prime_day", "prime_day", "black_friday", "cyber_monday"])
            holiday_dates.extend(
                [
                    date(year, 7, 12),
                    date(year, 7, 13),
                    black_friday,
                    cyber_monday,
                ]
            )

            holiday_names.extend(["christmas"] * 6)
            holiday_dates.extend(date(year, 12, christmas_day) for christmas_day in range(20, 26))

        if not holiday_names:
            return None

        return pd_module.DataFrame(
            {
                "holiday": holiday_names,
                "ds": pd_module.to_datetime(holiday_dates),
                "lower_window": 0,
                "upper_window": 1,
            }
        )

    @staticmethod
    def _black_friday(year: int) -> date:
        """Return the Friday after US Thanksgiving for the given year."""
        november_first = date(year, 11, 1)
        days_until_thursday = (3 - november_first.weekday()) % 7
        thanksgiving = november_first + timedelta(days=days_until_thursday + 21)
        return thanksgiving + timedelta(days=1)

    # ------------------------------------------------------------------
    # Product trend score
    # ------------------------------------------------------------------

    async def get_product_trend_score(
        self,
        account_id: UUID,
        asin: str,
    ) -> Dict[str, Any]:
        """Calculate trend score for a product."""
        end_date = date.today()
        start_date = end_date - timedelta(days=30)
        mid_date = end_date - timedelta(days=15)

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
