"""Forecast and prediction models."""
from __future__ import annotations
import uuid
from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from sqlalchemy import String, Integer, ForeignKey, DateTime, Numeric
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB

from app.db.base import Base


class Forecast(Base):
    """Sales forecast model."""
    __tablename__ = "forecasts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("amazon_accounts.id", ondelete="CASCADE"), index=True
    )
    asin: Mapped[str] = mapped_column(String(20), nullable=True, index=True)
    forecast_type: Mapped[str] = mapped_column(String(50), nullable=True)  # sales, units, revenue

    # Forecast Data
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    forecast_horizon_days: Mapped[int] = mapped_column(Integer, nullable=True)
    model_used: Mapped[str] = mapped_column(String(50), nullable=True)  # prophet, arima, xgboost
    confidence_interval: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=True)

    # Stored as JSONB for flexibility
    predictions: Mapped[dict] = mapped_column(JSONB, nullable=True)

    # Model Metrics
    mape: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=True)
    rmse: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=True)
    confidence_level: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    data_quality_notes: Mapped[Optional[List[str]]] = mapped_column(JSONB, nullable=True)

    # Relationships
    account: Mapped["AmazonAccount"] = relationship("AmazonAccount", back_populates="forecasts")


from app.models.amazon_account import AmazonAccount
