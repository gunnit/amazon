"""Advertising models."""
import uuid
from datetime import datetime, date
from decimal import Decimal
from sqlalchemy import String, Integer, ForeignKey, DateTime, Date, Numeric, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class AdvertisingCampaign(Base):
    """Advertising campaign model."""
    __tablename__ = "advertising_campaigns"
    __table_args__ = (
        UniqueConstraint("account_id", "campaign_id", name="uq_ad_campaign_account_campaign"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("amazon_accounts.id", ondelete="CASCADE"), index=True
    )
    campaign_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    campaign_name: Mapped[str] = mapped_column(String(255), nullable=True)
    campaign_type: Mapped[str] = mapped_column(String(50), nullable=True)  # sponsoredProducts, sponsoredBrands, sponsoredDisplay
    state: Mapped[str] = mapped_column(String(20), nullable=True)  # enabled, paused, archived
    daily_budget: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=True)
    targeting_type: Mapped[str] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    # Relationships
    account: Mapped["AmazonAccount"] = relationship("AmazonAccount", back_populates="advertising_campaigns")
    metrics: Mapped[list["AdvertisingMetrics"]] = relationship(
        "AdvertisingMetrics", back_populates="campaign", cascade="all, delete-orphan"
    )


class AdvertisingMetrics(Base):
    """Advertising metrics model (time-series)."""
    __tablename__ = "advertising_metrics"
    __table_args__ = (
        UniqueConstraint("campaign_id", "date", name="uq_ad_metrics_campaign_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("advertising_campaigns.id", ondelete="CASCADE"), index=True
    )
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    # Performance Metrics
    impressions: Mapped[int] = mapped_column(Integer, default=0)
    clicks: Mapped[int] = mapped_column(Integer, default=0)
    cost: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)
    attributed_sales_1d: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)
    attributed_sales_7d: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)
    attributed_sales_14d: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)
    attributed_sales_30d: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)
    attributed_units_ordered_1d: Mapped[int] = mapped_column(Integer, default=0)
    attributed_units_ordered_7d: Mapped[int] = mapped_column(Integer, default=0)
    attributed_units_ordered_14d: Mapped[int] = mapped_column(Integer, default=0)
    attributed_units_ordered_30d: Mapped[int] = mapped_column(Integer, default=0)

    # Calculated metrics
    ctr: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=True)
    cpc: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=True)
    acos: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=True)
    roas: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    # Relationships
    campaign: Mapped["AdvertisingCampaign"] = relationship("AdvertisingCampaign", back_populates="metrics")


from app.models.amazon_account import AmazonAccount
