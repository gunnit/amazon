"""Analytics and dashboard schemas."""
from datetime import date
from typing import Optional, List, Dict, Any
from decimal import Decimal
from uuid import UUID
from pydantic import BaseModel, Field


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


class ReturnsSummary(BaseModel):
    """High-level summary for returns analytics."""
    total_returns: int
    total_ordered_units: int = 0
    return_rate: Optional[float] = None
    return_rate_available: bool = False
    top_reason: Optional[str] = None
    unique_asins: int = 0


class ReturnsTrendPoint(BaseModel):
    """Daily returns trend with optional rate denominator."""
    date: date
    returned_units: int
    ordered_units: Optional[int] = None
    return_rate: Optional[float] = None


class ReturnReasonBreakdown(BaseModel):
    """Return reason distribution."""
    reason: str
    quantity: int
    share_percent: float


class ReturnAsinMetric(BaseModel):
    """Per-ASIN returns aggregate."""
    asin: str
    sku: Optional[str] = None
    quantity_returned: int
    primary_reason: Optional[str] = None
    disposition: Optional[str] = None
    ordered_units: Optional[int] = None
    return_rate: Optional[float] = None


class ReturnsAnalyticsResponse(BaseModel):
    """Returns analytics payload."""
    summary: ReturnsSummary
    return_rate_over_time: List[ReturnsTrendPoint]
    reason_breakdown: List[ReturnReasonBreakdown]
    top_asins_by_returns: List[ReturnAsinMetric]
    top_asins_by_return_rate: List[ReturnAsinMetric]


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


class ComparisonDailyPoint(BaseModel):
    """Aligned daily revenue point across two comparison periods."""
    day_offset: int
    period_1_date: Optional[date] = None
    period_1_revenue: Optional[float] = None
    period_2_date: Optional[date] = None
    period_2_revenue: Optional[float] = None


class ComparisonResponse(BaseModel):
    """Period-over-period comparison response."""
    preset: Optional[str] = None
    category: Optional[str] = None
    period_1: ComparisonPeriod
    period_2: ComparisonPeriod
    metrics: List[ComparisonMetric]
    daily_series: Optional[List[ComparisonDailyPoint]] = None


class AdsVsOrganicTimeSeriesPoint(BaseModel):
    """Single ads vs organic time-series row."""
    date: date
    total_sales: float
    ad_sales: float
    organic_sales: float
    ad_share_pct: float
    organic_share_pct: float


class AdsVsOrganicSummary(BaseModel):
    """Summary KPI block for ads vs organic analysis."""
    total_sales: MetricValue
    ad_sales: MetricValue
    organic_sales: MetricValue
    ad_share_pct: MetricValue
    organic_share_pct: MetricValue
    period_start: date
    period_end: date
    previous_period_start: Optional[date] = None
    previous_period_end: Optional[date] = None


class AdsVsOrganicAsinBreakdownItem(BaseModel):
    """Sales breakdown by ASIN for the selected period."""
    asin: str
    title: Optional[str] = None
    total_sales: float
    sales_share_pct: float


class AdsVsOrganicResponse(BaseModel):
    """Ads vs organic analytics response."""
    summary: AdsVsOrganicSummary
    time_series: List[AdsVsOrganicTimeSeriesPoint]
    asin_breakdown: Optional[List[AdsVsOrganicAsinBreakdownItem]] = None
    group_by: str = "day"
    asin: Optional[str] = None
    attribution_notes: List[str] = Field(default_factory=list)


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
    historical_data: List[ForecastHistoricalPoint] = Field(default_factory=list)
    mape: Optional[float]
    rmse: Optional[float]
    confidence_level: Optional[str] = None
    data_quality_notes: Optional[List[str]] = None


class AdvertisingInsights(BaseModel):
    """Advertising performance insights."""
    total_spend: Decimal
    total_sales: Decimal
    total_impressions: int
    total_clicks: int
    overall_roas: Decimal
    overall_acos: Decimal
    overall_ctr: Decimal
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


class ProductTrendTimeseriesPoint(BaseModel):
    """Sparkline-friendly recent sales point."""
    date: date
    revenue: float
    units: int


class ProductTrendItem(BaseModel):
    """Single product trend record."""
    asin: str
    account_id: Optional[UUID] = None
    title: Optional[str] = None
    category: Optional[str] = None
    trend_class: str
    trend_score: float
    direction: str
    strength: str
    sales_delta_percent: float
    current_revenue: float
    previous_revenue: float
    current_units: int
    previous_units: int
    revenue_change_percent: float
    units_change_percent: float
    current_bsr: Optional[int] = None
    previous_bsr: Optional[int] = None
    bsr_change_percent: Optional[float] = None
    bsr_position_change: Optional[int] = None
    current_inventory: Optional[int] = None
    previous_inventory: Optional[int] = None
    inventory_days_of_cover: Optional[float] = None
    review_velocity_change_percent: Optional[float] = None
    supporting_signals: List[str] = Field(default_factory=list)
    recent_sales: List[ProductTrendTimeseriesPoint] = Field(default_factory=list)
    data_quality: str
    reason_tags: List[str]


class ProductTrendClassCounts(BaseModel):
    """Counts per trend class."""
    rising_fast: int = 0
    rising: int = 0
    stable: int = 0
    declining: int = 0
    declining_fast: int = 0


class ProductTrendSummary(BaseModel):
    """Aggregate summary for product trends."""
    eligible_products: int
    rising_count: int
    declining_count: int
    stable_count: int
    average_trend_score: float
    trend_class_counts: ProductTrendClassCounts
    strongest_riser: Optional[ProductTrendItem] = None
    strongest_decliner: Optional[ProductTrendItem] = None


class ProductTrendsResponse(BaseModel):
    """Product trends response."""
    summary: ProductTrendSummary
    rising_products: List[ProductTrendItem]
    declining_products: List[ProductTrendItem]
    products: List[ProductTrendItem]
    insights: ProductTrendInsights
    generated_with_ai: bool
    ai_available: bool
