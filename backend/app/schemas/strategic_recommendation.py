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
    lookback_days: int = Field(default=28, ge=7, le=180)
    language: str = Field(default="en", pattern="^(en|it)$")
    account_id: Optional[UUID] = None
    asin: Optional[str] = Field(default=None, min_length=1, max_length=20)


class StrategicRecommendationGenerateResponse(BaseModel):
    created_count: int
    recommendations: List[StrategicRecommendationOut]
