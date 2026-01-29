"""Analytics and dashboard schemas."""
from datetime import date
from typing import Optional, List, Dict, Any
from decimal import Decimal
from pydantic import BaseModel


class MetricValue(BaseModel):
    """Single metric with trend."""
    value: float
    previous_value: Optional[float] = None
    change_percent: Optional[float] = None
    trend: str = "stable"  # up, down, stable


class DashboardKPIs(BaseModel):
    """Dashboard KPI overview."""
    total_revenue: MetricValue
    total_units: MetricValue
    total_orders: MetricValue
    average_order_value: MetricValue
    return_rate: MetricValue
    roas: MetricValue
    acos: MetricValue
    ctr: MetricValue
    active_asins: int
    accounts_synced: int
    period_start: date
    period_end: date


class TrendDataPoint(BaseModel):
    """Single data point for trends."""
    date: date
    value: float
    label: Optional[str] = None


class TrendData(BaseModel):
    """Trend data series."""
    metric_name: str
    data_points: List[TrendDataPoint]
    total: float
    average: float
    min_value: float
    max_value: float


class ComparisonData(BaseModel):
    """Period-over-period comparison."""
    metric_name: str
    current_period: Dict[str, Any]
    previous_period: Dict[str, Any]
    change_absolute: float
    change_percent: float


class ProductPerformance(BaseModel):
    """Product performance metrics."""
    asin: str
    title: Optional[str]
    sku: Optional[str]
    total_units: int
    total_revenue: Decimal
    total_orders: int
    avg_price: Optional[Decimal]
    current_bsr: Optional[int]
    bsr_change: Optional[int]
    revenue_share: float


class TopPerformers(BaseModel):
    """Top performing products."""
    by_revenue: List[ProductPerformance]
    by_units: List[ProductPerformance]
    by_growth: List[ProductPerformance]


class CompetitorAnalysis(BaseModel):
    """Competitor analysis data."""
    competitor_asin: str
    competitor_title: Optional[str]
    competitor_brand: Optional[str]
    competitor_price: Optional[Decimal]
    competitor_bsr: Optional[int]
    competitor_reviews: Optional[int]
    competitor_rating: Optional[Decimal]
    price_difference: Optional[Decimal]
    bsr_difference: Optional[int]
    reviews_difference: Optional[int]


class ForecastPrediction(BaseModel):
    """Single forecast prediction."""
    date: date
    predicted_value: float
    lower_bound: float
    upper_bound: float


class ForecastResponse(BaseModel):
    """Forecast response."""
    id: str
    account_id: str
    asin: Optional[str]
    forecast_type: str
    generated_at: str
    horizon_days: int
    model_used: str
    confidence_interval: float
    predictions: List[ForecastPrediction]
    mape: Optional[float]
    rmse: Optional[float]


class AdvertisingInsights(BaseModel):
    """Advertising performance insights."""
    total_spend: Decimal
    total_sales: Decimal
    overall_roas: Decimal
    overall_acos: Decimal
    top_campaigns: List[Dict[str, Any]]
    underperforming_campaigns: List[Dict[str, Any]]
    recommendations: List[str]
