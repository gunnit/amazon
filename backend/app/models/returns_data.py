"""Returns data model."""
from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ReturnData(Base):
    """Persisted FBA customer return events."""

    __tablename__ = "returns_data"
    __table_args__ = (
        Index("ix_returns_data_account_return_date", "account_id", "return_date"),
        Index("ix_returns_data_asin", "asin"),
        Index("ix_returns_data_amazon_order_id", "amazon_order_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("amazon_accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    amazon_order_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    asin: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    sku: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    return_date: Mapped[date] = mapped_column(Date, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, default=0)
    reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    disposition: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    detailed_disposition: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    account: Mapped["AmazonAccount"] = relationship("AmazonAccount", back_populates="returns_data")


from app.models.amazon_account import AmazonAccount
