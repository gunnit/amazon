"""Schemas for async export jobs."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class ForecastExportCreate(BaseModel):
    """Request to create a forecast export package."""

    forecast_id: str
    template: str = Field(default="corporate", pattern="^(clean|corporate|executive)$")
    language: str = Field(default="en", pattern="^(en|it)$")
    include_insights: bool = False


class ForecastExportJobResponse(BaseModel):
    """Async forecast export job status response."""

    id: str
    forecast_id: str
    status: str
    progress_step: Optional[str] = None
    progress_pct: int = 0
    error_message: Optional[str] = None
    include_insights: bool
    template: str
    language: str
    download_ready: bool = False
    created_at: str
    completed_at: Optional[str] = None
