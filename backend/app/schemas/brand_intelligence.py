"""Weekly Brand Intelligence schemas — the API contract the frontend polls."""
from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel


class ReportSummary(BaseModel):
    """One row in the report history list."""

    id: UUID
    account_id: Optional[UUID] = None
    brand_label: str
    period_start: date
    period_end: date
    week_label: str
    status: str
    generated_at: Optional[datetime] = None


class ReportPeriod(BaseModel):
    start: date
    end: date
    previous_start: date
    previous_end: date
    week_label: str
    window_days: int


class KpiCard(BaseModel):
    label: str
    value: str
    delta_percent: Optional[float] = None
    trend: str = "stable"  # up | down | stable


class ExecSummary(BaseModel):
    headline: str
    kpis: List[KpiCard] = []


class SectionItem(BaseModel):
    title: str
    detail: str
    source: str
    confidence: str  # high | medium | low
    evidence: str


class ReportSection(BaseModel):
    key: str
    title: str
    narrative: str
    items: List[SectionItem] = []
    delta: Optional[dict] = None


class ReportDetail(BaseModel):
    """Full persisted report returned by GET /reports/{id}."""

    id: UUID
    account_id: Optional[UUID] = None
    brand_label: str
    period: ReportPeriod
    status: str
    generated_at: Optional[datetime] = None
    model: Optional[str] = None
    coverage_note: Optional[str] = None
    exec_summary: ExecSummary
    sections: List[ReportSection] = []


class GenerateRequest(BaseModel):
    account_id: UUID
    week: Optional[date] = None  # any date inside the target week; defaults to last full week


class GenerateResponse(BaseModel):
    id: UUID
    status: str


class ScheduleConfig(BaseModel):
    account_id: UUID
    is_enabled: bool
    day_of_week: int = 0  # 0 = Monday
    timezone: str = "UTC"
