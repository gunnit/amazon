"""Brand Pulse schemas."""
from datetime import date
from typing import Dict, List, Optional

from pydantic import BaseModel


class PulsePeriod(BaseModel):
    start: date
    end: date
    previous_start: date
    previous_end: date
    window_days: int
    cadence: str = "unknown"
    awaiting_data: bool = False


class PulsePeriodMetrics(BaseModel):
    revenue: float
    units: int
    orders: int
    average_order_value: float
    active_asins: int


class PulseMetricChange(BaseModel):
    absolute: float
    percent: float
    trend: str  # up, down, stable


class PulseOverview(BaseModel):
    current: PulsePeriodMetrics
    previous: PulsePeriodMetrics
    changes: Dict[str, PulseMetricChange]


class PulseAsin(BaseModel):
    asin: str
    title: Optional[str] = None
    revenue: float
    previous_revenue: float
    change_percent: float


class PulseDecliningAsin(PulseAsin):
    trend_class: str  # declining, declining_fast


class PulseAds(BaseModel):
    is_available: bool
    unavailable_reason: Optional[str] = None
    spend: Optional[float] = None
    ad_sales: Optional[float] = None
    acos: Optional[float] = None
    tacos: Optional[float] = None
    roas: Optional[float] = None
    attribution_window: Optional[str] = None


class PulseRecommendation(BaseModel):
    """Evidence-backed recommendation. Populated by the recommendation layer;
    the list stays empty until then."""
    title: str
    priority: str
    confidence: str
    source: str
    evidence: str
    rationale: Optional[str] = None


class PulseResponse(BaseModel):
    period: PulsePeriod
    overview: PulseOverview
    top_asins: List[PulseAsin]
    declining_asins: List[PulseDecliningAsin]
    ads: PulseAds
    recommendations: List[PulseRecommendation] = []
