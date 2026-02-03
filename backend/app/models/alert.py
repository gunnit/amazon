"""Alert rules and alerts models."""
from __future__ import annotations
import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Boolean, ForeignKey, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY

from app.db.base import Base


class AlertRule(Base):
    """Alert rule configuration."""
    __tablename__ = "alert_rules"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )

    # Rule Definition
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    alert_type: Mapped[str] = mapped_column(String(50), nullable=False)  # low_stock, bsr_drop, price_change, sync_failure
    conditions: Mapped[dict] = mapped_column(JSONB, nullable=False)

    # Targeting
    applies_to_accounts: Mapped[list] = mapped_column(ARRAY(UUID(as_uuid=True)), nullable=True)
    applies_to_asins: Mapped[list] = mapped_column(ARRAY(String), nullable=True)

    # Notification
    notification_channels: Mapped[list] = mapped_column(ARRAY(String), nullable=True)  # email, webhook, slack
    notification_emails: Mapped[list] = mapped_column(ARRAY(String), nullable=True)
    webhook_url: Mapped[str] = mapped_column(String(500), nullable=True)

    # Status
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_triggered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    # Relationships
    organization: Mapped["Organization"] = relationship("Organization", back_populates="alert_rules")
    alerts: Mapped[list["Alert"]] = relationship("Alert", back_populates="rule", cascade="all, delete-orphan")


class Alert(Base):
    """Alert instance triggered by a rule."""
    __tablename__ = "alerts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    rule_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("alert_rules.id", ondelete="CASCADE"), index=True
    )
    account_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("amazon_accounts.id", ondelete="SET NULL"), nullable=True
    )
    asin: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(20), default="warning")
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    triggered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    rule: Mapped["AlertRule"] = relationship("AlertRule", back_populates="alerts")


from app.models.user import Organization
