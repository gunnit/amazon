"""Market research schemas."""
from typing import List, Optional
from pydantic import BaseModel, Field


class MarketResearchCreate(BaseModel):
    """Request to create a market research report.

    The system automatically discovers competitors via SP-API catalog search.
    Optionally, extra ASINs can be provided to include in the analysis.
    """
    source_asin: str = Field(..., max_length=20)
    account_id: str
    language: str = Field(default="en", pattern="^(en|it)$")
    extra_competitor_asins: Optional[List[str]] = Field(default=None, max_length=5)


class ProductSnapshot(BaseModel):
    """Snapshot of a product's metrics."""
    asin: str
    title: Optional[str] = None
    brand: Optional[str] = None
    category: Optional[str] = None
    price: Optional[float] = None
    bsr: Optional[int] = None
    review_count: Optional[int] = None
    rating: Optional[float] = None


class CompetitorSnapshot(ProductSnapshot):
    """Snapshot of a competitor product's metrics."""
    pass


class AIRecommendation(BaseModel):
    """A single AI recommendation."""
    area: str
    priority: str  # high, medium, low
    action: str
    expected_impact: str


class AIAnalysis(BaseModel):
    """AI-generated analysis results."""
    strengths: List[str]
    weaknesses: List[str]
    recommendations: List[AIRecommendation]
    overall_score: int = Field(ge=1, le=100)
    summary: str


class MarketResearchResponse(BaseModel):
    """Full market research report response."""
    id: str
    organization_id: str
    account_id: str
    source_asin: str
    marketplace: Optional[str] = None
    language: str
    title: Optional[str] = None
    status: str
    error_message: Optional[str] = None
    product_snapshot: Optional[ProductSnapshot] = None
    competitor_data: Optional[List[CompetitorSnapshot]] = None
    ai_analysis: Optional[AIAnalysis] = None
    created_at: str
    completed_at: Optional[str] = None


class MarketResearchListItem(BaseModel):
    """Lightweight list item for market research reports."""
    id: str
    title: Optional[str] = None
    source_asin: str
    status: str
    language: str
    created_at: str
    competitor_count: int = 0
