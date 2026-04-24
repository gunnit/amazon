"""Order data models."""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Order(Base):
    """Persisted Amazon order header data."""

    __tablename__ = "orders"
    __table_args__ = (
        Index("ix_orders_account_purchase_date", "account_id", "purchase_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("amazon_accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    amazon_order_id: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        unique=True,
        index=True,
    )
    purchase_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    order_status: Mapped[str] = mapped_column(String(50), nullable=False)
    fulfillment_channel: Mapped[str] = mapped_column(String(50), nullable=True)
    order_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=True)
    marketplace_id: Mapped[str] = mapped_column(String(50), nullable=True)
    number_of_items: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    account: Mapped["AmazonAccount"] = relationship("AmazonAccount", back_populates="orders")
    items: Mapped[list["OrderItem"]] = relationship(
        "OrderItem",
        back_populates="order",
        cascade="all, delete-orphan",
    )


class OrderItem(Base):
    """Persisted Amazon order line item data."""

    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    asin: Mapped[str] = mapped_column(String(20), nullable=True, index=True)
    sku: Mapped[str] = mapped_column(String(100), nullable=True)
    title: Mapped[str] = mapped_column(Text, nullable=True)
    quantity: Mapped[int] = mapped_column(Integer, default=0)
    item_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=True)
    item_tax: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=True)

    order: Mapped["Order"] = relationship("Order", back_populates="items")


from app.models.amazon_account import AmazonAccount
