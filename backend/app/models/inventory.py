"""Inventory data model."""
import uuid
from datetime import datetime, date
from sqlalchemy import String, Integer, ForeignKey, DateTime, Date, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class InventoryData(Base):
    """Inventory data model."""
    __tablename__ = "inventory_data"
    __table_args__ = (
        UniqueConstraint("account_id", "snapshot_date", "asin", name="uq_inventory_account_date_asin"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("amazon_accounts.id", ondelete="CASCADE"), index=True
    )
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    asin: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    sku: Mapped[str] = mapped_column(String(100), nullable=True)
    fnsku: Mapped[str] = mapped_column(String(20), nullable=True)

    # FBA Stock Levels
    afn_fulfillable_quantity: Mapped[int] = mapped_column(Integer, default=0)
    afn_inbound_working_quantity: Mapped[int] = mapped_column(Integer, default=0)
    afn_inbound_shipped_quantity: Mapped[int] = mapped_column(Integer, default=0)
    afn_reserved_quantity: Mapped[int] = mapped_column(Integer, default=0)
    afn_total_quantity: Mapped[int] = mapped_column(Integer, default=0)

    # MFN (Merchant Fulfilled)
    mfn_fulfillable_quantity: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    # Relationships
    account: Mapped["AmazonAccount"] = relationship("AmazonAccount", back_populates="inventory_data")


from app.models.amazon_account import AmazonAccount
