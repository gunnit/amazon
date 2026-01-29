"""Product and BSR models."""
import uuid
from datetime import datetime, date
from decimal import Decimal
from sqlalchemy import String, Integer, Boolean, ForeignKey, DateTime, Date, Numeric, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class Product(Base):
    """Product catalog model."""
    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint("account_id", "asin", name="uq_product_account_asin"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("amazon_accounts.id", ondelete="CASCADE"), index=True
    )
    asin: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    sku: Mapped[str] = mapped_column(String(100), nullable=True)

    # Product Info
    title: Mapped[str] = mapped_column(Text, nullable=True)
    brand: Mapped[str] = mapped_column(String(255), nullable=True)
    category: Mapped[str] = mapped_column(String(255), nullable=True)
    subcategory: Mapped[str] = mapped_column(String(255), nullable=True)

    # Current State
    current_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=True)
    current_bsr: Mapped[int] = mapped_column(Integer, nullable=True)
    review_count: Mapped[int] = mapped_column(Integer, nullable=True)
    rating: Mapped[Decimal] = mapped_column(Numeric(3, 2), nullable=True)

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    account: Mapped["AmazonAccount"] = relationship("AmazonAccount", back_populates="products")
    bsr_history: Mapped[list["BSRHistory"]] = relationship(
        "BSRHistory", back_populates="product", cascade="all, delete-orphan"
    )


class BSRHistory(Base):
    """BSR history for trend analysis."""
    __tablename__ = "bsr_history"
    __table_args__ = (
        UniqueConstraint("product_id", "date", "category", name="uq_bsr_product_date_category"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), index=True
    )
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(255), nullable=True)
    bsr: Mapped[int] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    # Relationships
    product: Mapped["Product"] = relationship("Product", back_populates="bsr_history")


from app.models.amazon_account import AmazonAccount
