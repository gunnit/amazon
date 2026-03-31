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
    is_available: bool = True
    unavailable_reason: Optional[str] = None


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


class CategorySalesData(BaseModel):
    """Sales aggregates by category."""
    category: str
    total_revenue: float
    total_units: int
    total_orders: int


class HourlyOrdersData(BaseModel):
    """Orders count by hour of day (0-23, UTC)."""
    hour: int
    orders: int


class ComparisonPeriod(BaseModel):
    """Date range used in period comparison."""
    start: date
    end: date


class ComparisonMetric(BaseModel):
    """Single metric in a period-over-period comparison."""
    metric_name: str
    label: str
    current_value: Optional[float] = None
    previous_value: Optional[float] = None
    change_percent: Optional[float] = None
    trend: str = "stable"
    format: str = "number"
    is_available: bool = True
    unavailable_reason: Optional[str] = None


class ComparisonResponse(BaseModel):
    """Period-over-period comparison response."""
    preset: Optional[str] = None
    category: Optional[str] = None
    period_1: ComparisonPeriod
    period_2: ComparisonPeriod
    metrics: List[ComparisonMetric]


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


class ForecastHistoricalPoint(BaseModel):
    """Single historical data point for chart context."""
    date: date
    value: float


class ForecastProductOption(BaseModel):
    """ASIN option that has enough history for forecasting."""
    asin: str
    title: Optional[str] = None
    history_days: int
    last_sale_date: Optional[date] = None


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
    historical_data: List[ForecastHistoricalPoint] = []
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


class ProductTrendRecommendation(BaseModel):
    """Actionable recommendation for trend insights."""
    priority: str
    action: str
    rationale: str
    expected_impact: str


class ProductTrendInsights(BaseModel):
    """Structured insight block for trends."""
    summary: str
    key_trends: List[str]
    risks: List[str]
    opportunities: List[str]
    recommendations: List[ProductTrendRecommendation]


class ProductTrendItem(BaseModel):
    """Single product trend record."""
    asin: str
    title: Optional[str] = None
    category: Optional[str] = None
    trend_score: float
    direction: str
    strength: str
    current_revenue: float
    previous_revenue: float
    current_units: int
    previous_units: int
    revenue_change_percent: float
    units_change_percent: float
    current_bsr: Optional[int] = None
    previous_bsr: Optional[int] = None
    bsr_change_percent: Optional[float] = None
    data_quality: str
    reason_tags: List[str]


class ProductTrendSummary(BaseModel):
    """Aggregate summary for product trends."""
    eligible_products: int
    rising_count: int
    declining_count: int
    stable_count: int
    average_trend_score: float
    strongest_riser: Optional[ProductTrendItem] = None
    strongest_decliner: Optional[ProductTrendItem] = None


class ProductTrendsResponse(BaseModel):
    """Product trends response."""
    summary: ProductTrendSummary
    rising_products: List[ProductTrendItem]
    declining_products: List[ProductTrendItem]
    insights: ProductTrendInsights
    generated_with_ai: bool
    ai_available: bool
