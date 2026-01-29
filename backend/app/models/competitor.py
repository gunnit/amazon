"""Competitor tracking models."""
import uuid
from datetime import datetime, date
from decimal import Decimal
from sqlalchemy import String, Integer, Boolean, ForeignKey, DateTime, Date, Numeric, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class Competitor(Base):
    """Competitor product tracking."""
    __tablename__ = "competitors"
    __table_args__ = (
        UniqueConstraint("organization_id", "asin", "marketplace", name="uq_competitor_org_asin_marketplace"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    asin: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    marketplace: Mapped[str] = mapped_column(String(10), nullable=False)

    # Info
    title: Mapped[str] = mapped_column(Text, nullable=True)
    brand: Mapped[str] = mapped_column(String(255), nullable=True)

    # Current State
    current_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=True)
    current_bsr: Mapped[int] = mapped_column(Integer, nullable=True)
    review_count: Mapped[int] = mapped_column(Integer, nullable=True)
    rating: Mapped[Decimal] = mapped_column(Numeric(3, 2), nullable=True)

    is_tracking: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    # Relationships
    organization: Mapped["Organization"] = relationship("Organization", back_populates="competitors")
    history: Mapped[list["CompetitorHistory"]] = relationship(
        "CompetitorHistory", back_populates="competitor", cascade="all, delete-orphan"
    )


class CompetitorHistory(Base):
    """Competitor historical data."""
    __tablename__ = "competitor_history"
    __table_args__ = (
        UniqueConstraint("competitor_id", "date", name="uq_competitor_history_competitor_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    competitor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("competitors.id", ondelete="CASCADE"), index=True
    )
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=True)
    bsr: Mapped[int] = mapped_column(Integer, nullable=True)
    review_count: Mapped[int] = mapped_column(Integer, nullable=True)
    rating: Mapped[Decimal] = mapped_column(Numeric(3, 2), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    # Relationships
    competitor: Mapped["Competitor"] = relationship("Competitor", back_populates="history")


from app.models.user import Organization
