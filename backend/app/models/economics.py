"""Per-ASIN economics from the SP-API Data Kiosk economics dataset."""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AsinEconomics(Base):
    """Daily per-ASIN sales, fees, ad spend and net proceeds (seller accounts).

    Fees and net proceeds come from Amazon's economics dataset, so they are
    Amazon-computed actual/estimated charges, not our own fee estimates.
    """

    __tablename__ = "asin_economics"
    __table_args__ = (
        UniqueConstraint("account_id", "date", "asin", name="uq_asin_economics_account_date_asin"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("amazon_accounts.id", ondelete="CASCADE"), index=True
    )
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    asin: Mapped[str] = mapped_column(String(20), nullable=False, index=True)

    units_ordered: Mapped[int] = mapped_column(Integer, nullable=True)
    units_refunded: Mapped[int] = mapped_column(Integer, nullable=True)
    net_units_sold: Mapped[int] = mapped_column(Integer, nullable=True)
    ordered_product_sales: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=True)
    net_product_sales: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(8), nullable=True)

    total_fees: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=True)
    ads_spend: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=True)
    net_proceeds_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=True)
    net_proceeds_per_unit: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=True)

    # Per-fee-type detail: {feeTypeName: amount, ...}
    fee_breakdown: Mapped[dict] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )
