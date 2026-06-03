"""Strategic recommendation schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


CATEGORY_PATTERN = r"^(pricing|advertising|inventory|content)$"
STATUS_PATTERN = r"^(pending|implemented|dismissed)$"
PRIORITY_PATTERN = r"^(high|medium|low)$"


class StrategicRecommendationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    account_id: Optional[UUID] = None
    created_by_id: Optional[UUID] = None

    category: str
    priority: str
    priority_score: int
    confidence: str
    title: str
    rationale: str
    expected_impact: Optional[str] = None
    context: Optional[Dict[str, Any]] = None

    status: str
    implemented_at: Optional[datetime] = None
    dismissed_at: Optional[datetime] = None
    outcome_notes: Optional[str] = None

    generated_by: str
    generated_at: datetime
    created_at: datetime
    updated_at: datetime


class StrategicRecommendationStatusUpdate(BaseModel):
    status: str = Field(pattern=STATUS_PATTERN)
    outcome_notes: Optional[str] = Field(default=None, max_length=2000)


class StrategicRecommendationGenerateRequest(BaseModel):
    # `auto` lets the service pick a window that matches the account cadence
    # (daily seller vs monthly vendor); an explicit value overrides it.
    lookback_days: Optional[int] = Field(default=None, ge=7, le=400)
    language: str = Field(default="en", pattern="^(en|it)$")
    account_id: Optional[UUID] = None
    asin: Optional[str] = Field(default=None, min_length=1, max_length=20)


class StrategicRecommendationGenerateResponse(BaseModel):
    created_count: int
    recommendations: List[StrategicRecommendationOut]
