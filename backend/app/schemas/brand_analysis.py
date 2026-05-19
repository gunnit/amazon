"""Schemas for Brand Analysis Automation."""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


# Status values produced by the current pipeline. Brand Analysis is now
# autonomous: it uses Inthezon's internal Amazon/SP-API data + Market
# Research enrichment for the main flow, with manual upload of external
# yearly product exports as a fallback. Legacy browser-automation statuses
# still appear in old DB rows; we keep them in the literal so existing
# rows deserialize cleanly.
BrandAnalysisStatus = Literal[
    "pending",
    "capability_checking",
    "preflight_checking",
    "internal_sync_requested",
    "syncing_internal_data",
    "internal_sync_completed",
    "internal_sync_failed",
    "collecting_source_data",
    "enriching_catalog",
    "generating_metrics",
    "generating_narrative",
    "analyzing",
    "generating_pptx",
    "completed",
    "completed_with_limitations",
    "failed",
    "waiting_for_user_action",
    # Legacy statuses retained for backwards compatibility with existing jobs:
    "configuring_market",
    "waiting_for_ready",
    "exporting_2025",
    "exporting_2024",
]


# `internal` is the canonical data-source mode (Inthezon SP-API + Market
# Research). `amazon_sp_api` is kept as a backwards-compatible alias for
# existing DB rows and older clients.
BrandAnalysisMode = Literal[
    "internal",
    "manual",
    # Legacy / backwards-compatible aliases:
    "amazon_sp_api",
]


# Structured codes surfaced to the frontend for actionable error states.
BrandAnalysisErrorCode = Literal[
    "internal_data_missing",
    "missing_2024_data",
    "missing_2025_data",
    "insufficient_yearly_data",
    "catalog_enrichment_partial",
    "analysis_completed_with_missing_optional_fields",
    "connected_account_required",
    "manual_upload_required",
    "internal_sync_failed",
    "capability_missing_permission",
]


class BrandAnalysisCreate(BaseModel):
    """Create a brand analysis job."""

    brand_name: str = Field(..., min_length=1, max_length=255)
    account_id: Optional[str] = None
    language: str = Field(default="en", pattern="^(en|it)$")
    mode: BrandAnalysisMode = "internal"
    market_type: Literal["brand", "asin"] = "brand"
    market_query: Optional[str] = Field(default=None, max_length=500)
    asin_list: Optional[list[str]] = Field(default=None, max_length=500)


class ColumnValidationReport(BaseModel):
    """Result of validating an uploaded source file's columns against canonical aliases."""

    required_found: list[str] = []
    required_missing: list[str] = []
    optional_found: list[str] = []
    optional_missing: list[str] = []
    detected_mapping: dict[str, str] = {}
    available_columns: list[str] = []


class BrandAnalysisSourceFileResponse(BaseModel):
    """Uploaded or fetched source export metadata."""

    id: str
    year: int
    filename: str
    content_type: Optional[str] = None
    file_size: int
    row_count: Optional[int] = None
    columns: list[str] = []
    column_validation: Optional[ColumnValidationReport] = None
    created_at: str


class BrandAnalysisJobResponse(BaseModel):
    """Full brand analysis job response."""

    id: str
    organization_id: str
    created_by_id: Optional[str] = None
    account_id: Optional[str] = None
    brand_name: str
    language: str
    mode: str
    market_type: str
    market_query: Optional[str] = None
    asin_list: Optional[list[str]] = None
    status: str
    progress_step: Optional[str] = None
    progress_pct: int = 0
    error_message: Optional[str] = None
    error_code: Optional[str] = None
    data_source_name: Optional[str] = None
    metrics: Optional[dict[str, Any]] = None
    metric_provenance: Optional[dict[str, Any]] = None
    capability_matrix: Optional[dict[str, Any]] = None
    data_coverage: Optional[dict[str, Any]] = None
    limitations: Optional[dict[str, Any]] = None
    sync_attempt_count: int = 0
    last_sync_error: Optional[str] = None
    next_retry_at: Optional[str] = None
    narrative: Optional[dict[str, Any]] = None
    source_files: list[BrandAnalysisSourceFileResponse] = []
    download_ready: bool = False
    artifact_filename: Optional[str] = None
    created_at: str
    updated_at: Optional[str] = None
    completed_at: Optional[str] = None


class BrandAnalysisListItem(BaseModel):
    """Lightweight list item for previous analyses."""

    id: str
    brand_name: str
    language: str
    mode: str
    market_type: str
    status: str
    progress_pct: int = 0
    error_message: Optional[str] = None
    error_code: Optional[str] = None
    source_years: list[int] = []
    download_ready: bool = False
    created_at: str
    completed_at: Optional[str] = None
