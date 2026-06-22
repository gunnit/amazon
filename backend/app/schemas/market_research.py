"""Market research schemas."""
from typing import List, Literal, Optional
from pydantic import BaseModel, Field


class MarketSearchSeedSnapshot(BaseModel):
    """Market Tracker result snapshot used to seed report generation.

    Values are never invented: they come from the just-completed market-search
    response and are used only as fallback when the report re-fetch misses a
    field that was already available.
    """
    asin: str
    title: Optional[str] = None
    brand: Optional[str] = None
    category: Optional[str] = None
    price: Optional[float] = None
    bsr: Optional[int] = None
    review_count: Optional[int] = None
    rating: Optional[float] = None
    price_unreliable: Optional[bool] = None


class MarketResearchCreate(BaseModel):
    """Request to create a market research report.

    The system automatically discovers competitors via SP-API catalog search.
    Optionally, extra ASINs can be provided to include in the analysis.

    For Market Tracker 360: provide search_query + search_type instead of source_asin.
    """
    source_asin: Optional[str] = Field(default=None, max_length=20)
    account_id: str
    language: str = Field(default="en", pattern="^(en|it)$")
    extra_competitor_asins: Optional[List[str]] = Field(default=None, max_length=5)
    market_competitor_asins: Optional[List[str]] = Field(default=None, max_length=15)
    search_query: Optional[str] = Field(default=None, max_length=200)
    search_type: Optional[str] = Field(default=None, pattern="^(keyword|brand|asin)$")
    market_search_results: Optional[List[MarketSearchSeedSnapshot]] = Field(default=None, max_length=20)


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
    fetch_errors: Optional[List[str]] = None
    # True when the price is a repeated placeholder/sentinel detected at
    # persist time; the UI must not present it as a real market price.
    price_unreliable: Optional[bool] = None


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
    source_asin: Optional[str] = None
    marketplace: Optional[str] = None
    language: str
    title: Optional[str] = None
    status: str
    progress_step: Optional[str] = None
    progress_pct: Optional[int] = 0
    error_message: Optional[str] = None
    product_snapshot: Optional[ProductSnapshot] = None
    competitor_data: Optional[List[CompetitorSnapshot]] = None
    ai_analysis: Optional[AIAnalysis] = None
    # "ok" | "unavailable" (AI call failed) | "unconfigured" (no API key);
    # None while the report is not completed.
    ai_status: Optional[Literal["ok", "unavailable", "unconfigured"]] = None
    created_at: str
    completed_at: Optional[str] = None
    last_refreshed_at: Optional[str] = None


class MarketResearchListItem(BaseModel):
    """Lightweight list item for market research reports."""
    id: str
    title: Optional[str] = None
    source_asin: str
    status: str
    language: str
    created_at: str
    competitor_count: int = 0


class ComparisonDimension(BaseModel):
    """Competitive comparison metrics for a single dimension."""
    name: Literal["price", "bsr", "reviews", "rating"]
    client_value: Optional[float] = None
    competitor_avg: Optional[float] = None
    competitor_min: Optional[float] = None
    competitor_max: Optional[float] = None
    competitor_best: Optional[float] = None
    competitor_best_name: Optional[str] = None
    client_rank: Optional[int] = None
    total_competitors: int = 0
    competitors_with_data: int = 0
    gap_percent: Optional[float] = None


class ComparisonMatrixResponse(BaseModel):
    """Detailed client-vs-competitor comparison matrix.

    ``overall_score`` is ``None`` when no dimension had enough comparable
    competitor data to score the client.
    """
    dimensions: List[ComparisonDimension]
    overall_score: Optional[float] = Field(default=None, ge=0, le=100)
    opportunities: List[Literal["price", "bsr", "reviews", "rating"]]


# ── Market Tracker 360 schemas ──

class MarketSearchRequest(BaseModel):
    """Request to search the market by keyword, brand, or ASIN."""
    account_id: str
    search_type: str = Field(..., pattern="^(keyword|brand|asin)$")
    query: str = Field(..., min_length=1, max_length=200)
    language: str = Field(default="en", pattern="^(en|it)$")


class MarketSearchResult(BaseModel):
    """A single product found in the market search.

    Fields can be ``None`` when SP-API does not surface them. Callers
    should consult ``missing_data`` to render explicit N/A markers
    instead of inventing values.
    """
    asin: str
    title: Optional[str] = None
    brand: Optional[str] = None
    category: Optional[str] = None
    price: Optional[float] = None
    bsr: Optional[int] = None
    review_count: Optional[int] = None
    rating: Optional[float] = None
    missing_data: Optional[List[str]] = None
    price_unreliable: Optional[bool] = None
    price_unavailable_reason: Optional[
        Literal[
            "api_no_price",
            "pricing_forbidden",
            "pricing_unsupported_account_type",
            "pricing_throttled",
            "pricing_failed",
            "price_unreliable",
            "invalid_price",
        ]
    ] = None


class MarketSearchResponse(BaseModel):
    """Response from a market search."""
    results: List[MarketSearchResult]
    total_found: int
    query: str
    search_type: str
