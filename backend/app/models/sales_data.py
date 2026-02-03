"""Sales data model."""
from __future__ import annotations
import uuid
from datetime import datetime, date
from decimal import Decimal
from sqlalchemy import String, Integer, ForeignKey, DateTime, Date, Numeric, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class SalesData(Base):
    """Sales data model (time-series)."""
    __tablename__ = "sales_data"
    __table_args__ = (
        UniqueConstraint("account_id", "date", "asin", name="uq_sales_data_account_date_asin"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("amazon_accounts.id", ondelete="CASCADE"), index=True
    )
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    asin: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    sku: Mapped[str] = mapped_column(String(100), nullable=True)

    # Metrics
    units_ordered: Mapped[int] = mapped_column(Integer, default=0)
    units_ordered_b2b: Mapped[int] = mapped_column(Integer, default=0)
    ordered_product_sales: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    ordered_product_sales_b2b: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    total_order_items: Mapped[int] = mapped_column(Integer, default=0)

    # Currency
    currency: Mapped[str] = mapped_column(String(3), default="EUR")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    # Relationships
    account: Mapped["AmazonAccount"] = relationship("AmazonAccount", back_populates="sales_data")


from app.models.amazon_account import AmazonAccount
