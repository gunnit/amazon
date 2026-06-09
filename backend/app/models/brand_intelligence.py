"""Weekly Brand Intelligence models.

A persisted, diff-based, LLM-synthesized weekly brand report. Unlike the
request-time Brand Pulse, every run is stored so the next week can compute
"what changed since last week" against the previous snapshot. The shape mirrors
``ScheduledReportRun`` (status machine + period + JSONB payloads) and the weekly
automation reuses the scheduled-reports beat scanner.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

# Status machine for a report run. Kept here so the model, the service and the
# recovery task share one definition instead of triplicating literals.
STATUS_PENDING = "pending"
STATUS_GENERATING = "generating"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"

RUNNING_STATUSES = (STATUS_PENDING, STATUS_GENERATING)
TERMINAL_STATUSES = (STATUS_COMPLETED, STATUS_FAILED)


class BrandIntelligenceReport(Base):
    """A single weekly brand-intelligence report for one account."""

    __tablename__ = "brand_intelligence_reports"
    __table_args__ = (
        UniqueConstraint(
            "account_id", "period_start", "period_end", name="uq_bir_account_period"
        ),
        Index("ix_bir_account_period_end", "account_id", "period_end"),
        Index("ix_bir_status_heartbeat", "status", "heartbeat_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    account_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("amazon_accounts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    brand_label: Mapped[str] = mapped_column(String(255), nullable=False, default="Brand")
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    previous_start: Mapped[date] = mapped_column(Date, nullable=False)
    previous_end: Mapped[date] = mapped_column(Date, nullable=False)
    window_days: Mapped[int] = mapped_column(default=7, nullable=False)
    week_label: Mapped[str] = mapped_column(String(64), nullable=False, default="")

    status: Mapped[str] = mapped_column(String(20), nullable=False, default=STATUS_PENDING, index=True)
    generated_by: Mapped[str] = mapped_column(String(20), nullable=False, default="manual")  # manual | scheduler
    model: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    coverage_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Deterministic metrics for THIS period and the previous one.
    snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # Week-over-week deltas derived from the two snapshots.
    diff: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # LLM (or fallback) output: exec_summary + sections.
    intelligence: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    generated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    heartbeat_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    organization: Mapped["Organization"] = relationship("Organization")


class BrandIntelligenceSchedule(Base):
    """Opt-in weekly automation config, one row per account."""

    __tablename__ = "brand_intelligence_schedules"
    __table_args__ = (
        UniqueConstraint("account_id", name="uq_bis_account"),
        Index("ix_bis_enabled_next_run", "is_enabled", "next_run_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("amazon_accounts.id", ondelete="CASCADE"), index=True
    )

    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    day_of_week: Mapped[int] = mapped_column(default=0, nullable=False)  # 0 = Monday
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC")
    next_run_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )

    organization: Mapped["Organization"] = relationship("Organization")


from app.models.user import Organization  # noqa: E402
