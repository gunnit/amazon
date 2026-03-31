"""Forecast export job model."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, LargeBinary, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ForecastExportJob(Base):
    """Async job tracking forecast export package generation."""

    __tablename__ = "forecast_export_jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    created_by_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    forecast_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("forecasts.id", ondelete="CASCADE"), index=True
    )

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    progress_step: Mapped[str] = mapped_column(String(100), nullable=True)
    progress_pct: Mapped[int] = mapped_column(nullable=True, default=0)
    error_message: Mapped[str] = mapped_column(Text, nullable=True)

    template: Mapped[str] = mapped_column(String(20), nullable=False, default="corporate")
    language: Mapped[str] = mapped_column(String(5), nullable=False, default="en")
    include_insights: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    artifact_filename: Mapped[str] = mapped_column(String(255), nullable=True)
    artifact_content_type: Mapped[str] = mapped_column(String(100), nullable=True)
    artifact_data: Mapped[bytes] = mapped_column(LargeBinary, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)

    organization: Mapped["Organization"] = relationship("Organization")
    created_by: Mapped["User"] = relationship("User")
    forecast: Mapped["Forecast"] = relationship("Forecast")


from app.models.forecast import Forecast
from app.models.user import Organization, User
