"""Amazon Account model."""
from __future__ import annotations
import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, ForeignKey, DateTime, Text, Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
import enum

from app.db.base import Base


class AccountType(str, enum.Enum):
    """Amazon account type."""
    SELLER = "seller"
    VENDOR = "vendor"


class SyncStatus(str, enum.Enum):
    """Sync status."""
    PENDING = "pending"
    SYNCING = "syncing"
    SUCCESS = "success"
    ERROR = "error"


class AmazonAccount(Base):
    """Amazon account model."""
    __tablename__ = "amazon_accounts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    account_name: Mapped[str] = mapped_column(String(255), nullable=False)
    account_type: Mapped[AccountType] = mapped_column(Enum(AccountType), nullable=False)
    marketplace_id: Mapped[str] = mapped_column(String(50), nullable=False)
    marketplace_country: Mapped[str] = mapped_column(String(10), nullable=False)
    seller_id: Mapped[str] = mapped_column(String(100), nullable=True)

    # SP-API Credentials (encrypted)
    sp_api_refresh_token_encrypted: Mapped[str] = mapped_column(Text, nullable=True)
    ads_api_refresh_token_encrypted: Mapped[str] = mapped_column(Text, nullable=True)

    # Login credentials for web scraping (encrypted)
    login_email_encrypted: Mapped[str] = mapped_column(Text, nullable=True)
    login_password_encrypted: Mapped[str] = mapped_column(Text, nullable=True)

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_sync_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    sync_status: Mapped[SyncStatus] = mapped_column(Enum(SyncStatus), default=SyncStatus.PENDING)
    sync_error_message: Mapped[str] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    organization: Mapped["Organization"] = relationship("Organization", back_populates="amazon_accounts")
    sales_data: Mapped[list["SalesData"]] = relationship(
        "SalesData", back_populates="account", cascade="all, delete-orphan"
    )
    inventory_data: Mapped[list["InventoryData"]] = relationship(
        "InventoryData", back_populates="account", cascade="all, delete-orphan"
    )
    advertising_campaigns: Mapped[list["AdvertisingCampaign"]] = relationship(
        "AdvertisingCampaign", back_populates="account", cascade="all, delete-orphan"
    )
    products: Mapped[list["Product"]] = relationship(
        "Product", back_populates="account", cascade="all, delete-orphan"
    )
    forecasts: Mapped[list["Forecast"]] = relationship(
        "Forecast", back_populates="account", cascade="all, delete-orphan"
    )
    sync_jobs: Mapped[list["SyncJob"]] = relationship(
        "SyncJob", back_populates="account", cascade="all, delete-orphan"
    )


# Forward references
from app.models.user import Organization
from app.models.sales_data import SalesData
from app.models.inventory import InventoryData
from app.models.advertising import AdvertisingCampaign
from app.models.product import Product
from app.models.forecast import Forecast
from app.models.sync_job import SyncJob
