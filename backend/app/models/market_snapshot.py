"""Nightly per-ASIN fee-estimate and price/Buy Box snapshots."""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class FeeEstimate(Base):
    """Product Fees API estimate for one ASIN at its current price.

    Estimates, not actuals — asin_economics (Data Kiosk) and, later, finance
    events override these when available.
    """

    __tablename__ = "fee_estimates"
    __table_args__ = (
        UniqueConstraint("account_id", "asin", "snapshot_date", name="uq_fee_estimates_account_asin_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("amazon_accounts.id", ondelete="CASCADE"), index=True
    )
    asin: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    price_basis: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(8), nullable=True)
    estimated_fees: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class PriceSnapshot(Base):
    """Daily price + Buy Box snapshot per ASIN (Product Pricing API)."""

    __tablename__ = "price_snapshots"
    __table_args__ = (
        UniqueConstraint("account_id", "asin", "snapshot_date", name="uq_price_snapshots_account_asin_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("amazon_accounts.id", ondelete="CASCADE"), index=True
    )
    asin: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    our_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=True)
    buy_box_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=True)
    buy_box_seller_id: Mapped[str] = mapped_column(String(100), nullable=True)
    is_buy_box_ours: Mapped[bool] = mapped_column(Boolean, nullable=True)
    offer_count: Mapped[int] = mapped_column(Integer, nullable=True)
    is_fba: Mapped[bool] = mapped_column(Boolean, nullable=True)
    currency: Mapped[str] = mapped_column(String(8), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
