"""Google Sheets integration schemas."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

GoogleSheetsDataType = Literal["sales", "inventory", "advertising", "forecasts", "analytics"]
GoogleSheetsFrequency = Literal["daily", "weekly"]
GoogleSheetsSyncMode = Literal["overwrite", "append"]


class DailyScheduleConfig(BaseModel):
    """Daily sync schedule settings."""

    hour: int = Field(..., ge=0, le=23)
    minute: int = Field(..., ge=0, le=59)


class WeeklyScheduleConfig(DailyScheduleConfig):
    """Weekly sync schedule settings."""

    weekday: int = Field(..., ge=0, le=6)


class GoogleSheetsConnectionResponse(BaseModel):
    """Read model for a Google Sheets OAuth connection.

    Always returned with HTTP 200. When no connection exists, ``connected`` is
    ``False`` and the connection fields are ``None`` so the client can probe the
    state without a noisy 404 on every page load.
    """

    connected: bool = True
    id: Optional[UUID] = None
    google_email: Optional[str] = None
    is_active: Optional[bool] = None
    connected_at: Optional[datetime] = None
    scopes: list[str] = Field(default_factory=list)

    class Config:
        from_attributes = True


class GoogleSheetsExportRequest(BaseModel):
    """Manual export request for Google Sheets."""

    data_types: list[GoogleSheetsDataType] = Field(..., min_length=1)
    start_date: date
    end_date: date
    account_ids: Optional[list[UUID]] = None
    spreadsheet_id: Optional[str] = Field(default=None, max_length=255)
    name: Optional[str] = Field(default=None, max_length=255)
    language: Literal["en", "it"] = "en"
    group_by: Literal["day", "week", "month"] = "day"
    parameters: dict[str, Any] = Field(default_factory=dict)

    @field_validator("data_types")
    @classmethod
    def validate_data_types(cls, value: list[GoogleSheetsDataType]) -> list[GoogleSheetsDataType]:
        if not value:
            raise ValueError("At least one data type is required")
        return list(dict.fromkeys(value))

    @model_validator(mode="after")
    def validate_dates(self) -> "GoogleSheetsExportRequest":
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        merged_parameters = dict(self.parameters)
        merged_parameters.setdefault("language", self.language)
        merged_parameters.setdefault("group_by", self.group_by)
        self.parameters = merged_parameters
        return self


class GoogleSheetsExportResponse(BaseModel):
    """Manual export response."""

    spreadsheet_id: str
    spreadsheet_url: str
    sheets_created: list[str]


class GoogleSheetsSyncCreate(BaseModel):
    """Create payload for a scheduled Google Sheets sync."""

    name: str = Field(..., min_length=1, max_length=255)
    data_types: list[GoogleSheetsDataType] = Field(..., min_length=1)
    frequency: GoogleSheetsFrequency
    sync_mode: GoogleSheetsSyncMode
    account_ids: list[UUID] = Field(default_factory=list)
    parameters: dict[str, Any] = Field(default_factory=dict)
    schedule_config: dict[str, Any]
    timezone: str = Field(default="UTC", min_length=1, max_length=64)

    @field_validator("data_types")
    @classmethod
    def validate_unique_data_types(cls, value: list[GoogleSheetsDataType]) -> list[GoogleSheetsDataType]:
        if not value:
            raise ValueError("At least one data type is required")
        return list(dict.fromkeys(value))

    @model_validator(mode="after")
    def validate_schedule_config(self) -> "GoogleSheetsSyncCreate":
        if self.frequency == "daily":
            DailyScheduleConfig(**self.schedule_config)
        else:
            WeeklyScheduleConfig(**self.schedule_config)
        return self


class GoogleSheetsSyncUpdate(BaseModel):
    """Update payload for a scheduled Google Sheets sync."""

    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    data_types: Optional[list[GoogleSheetsDataType]] = None
    frequency: Optional[GoogleSheetsFrequency] = None
    sync_mode: Optional[GoogleSheetsSyncMode] = None
    account_ids: Optional[list[UUID]] = None
    parameters: Optional[dict[str, Any]] = None
    schedule_config: Optional[dict[str, Any]] = None
    timezone: Optional[str] = Field(default=None, min_length=1, max_length=64)
    is_enabled: Optional[bool] = None


class GoogleSheetsSyncResponse(BaseModel):
    """Read model for a Google Sheets sync configuration."""

    id: UUID
    name: str
    spreadsheet_id: Optional[str]
    spreadsheet_url: Optional[str]
    frequency: GoogleSheetsFrequency
    sync_mode: GoogleSheetsSyncMode
    data_types: list[GoogleSheetsDataType]
    account_ids: list[str]
    parameters: dict[str, Any]
    schedule_config: dict[str, Any]
    timezone: str
    is_enabled: bool
    last_run_at: Optional[datetime]
    last_run_status: Optional[str]
    next_run_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class GoogleSheetsSyncRunResponse(BaseModel):
    """Read model for a Google Sheets sync execution."""

    id: UUID
    sync_id: UUID
    status: str
    progress_step: Optional[str]
    error_message: Optional[str]
    triggered_at: datetime
    completed_at: Optional[datetime]
    rows_written: Optional[int]
    spreadsheet_url: Optional[str]
    data_types_snapshot: list[GoogleSheetsDataType]

    class Config:
        from_attributes = True
