"""Scheduled report models."""
from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, LargeBinary, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ScheduledReport(Base):
    """Recurring report configuration."""

    __tablename__ = "scheduled_reports"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    created_by_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    frequency: Mapped[str] = mapped_column(String(20), nullable=False)  # weekly, monthly
    format: Mapped[str] = mapped_column(String(20), nullable=False)  # excel, pdf
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC")

    report_types: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    account_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    recipients: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    schedule_config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    parameters: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    last_run_status: Mapped[str] = mapped_column(String(20), nullable=True)
    next_run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )

    organization: Mapped["Organization"] = relationship("Organization")
    created_by: Mapped["User"] = relationship("User")
    runs: Mapped[list["ScheduledReportRun"]] = relationship(
        "ScheduledReportRun",
        back_populates="scheduled_report",
        cascade="all, delete-orphan",
        order_by=lambda: ScheduledReportRun.triggered_at.desc(),
    )


class ScheduledReportRun(Base):
    """Execution record for a scheduled report."""

    __tablename__ = "scheduled_report_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scheduled_report_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("scheduled_reports.id", ondelete="CASCADE"),
        index=True,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    generation_status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    delivery_status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    progress_step: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    triggered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    report_name: Mapped[str] = mapped_column(String(255), nullable=False)
    format: Mapped[str] = mapped_column(String(20), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC")
    recipients_snapshot: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    parameters_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    report_types_snapshot: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)

    artifact_filename: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    artifact_content_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    artifact_data: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)

    scheduled_report: Mapped["ScheduledReport"] = relationship("ScheduledReport", back_populates="runs")
    organization: Mapped["Organization"] = relationship("Organization")


from app.models.user import Organization, User
