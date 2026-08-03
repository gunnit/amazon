"""Competitor tracking schemas."""
from typing import List, Optional
from pydantic import BaseModel, Field


class CompetitorCreate(BaseModel):
    """Add a competitor ASIN to the tracked list."""
    asin: str = Field(..., min_length=10, max_length=20)
    account_id: str


class CompetitorResponse(BaseModel):
    """A tracked competitor with its latest known metrics."""
    id: str
    asin: str
    marketplace: str
    title: Optional[str] = None
    brand: Optional[str] = None
    current_price: Optional[float] = None
    current_bsr: Optional[int] = None
    review_count: Optional[int] = None
    rating: Optional[float] = None
    is_tracking: bool = True
    created_at: str
    last_snapshot_date: Optional[str] = None


class CompetitorHistoryPoint(BaseModel):
    """One daily snapshot of a tracked competitor."""
    date: str
    price: Optional[float] = None
    bsr: Optional[int] = None
    review_count: Optional[int] = None
    rating: Optional[float] = None


class CompetitorHistoryResponse(BaseModel):
    """Daily history for one tracked competitor, oldest first."""
    competitor_id: str
    asin: str
    points: List[CompetitorHistoryPoint]
