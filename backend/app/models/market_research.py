"""Market research report models."""
from __future__ import annotations
import uuid
from datetime import datetime
from sqlalchemy import String, ForeignKey, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB

from app.db.base import Base


class MarketResearchReport(Base):
    """Market research competitive analysis report."""
    __tablename__ = "market_research_reports"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    created_by_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("amazon_accounts.id", ondelete="CASCADE"), index=True
    )
    source_asin: Mapped[str] = mapped_column(String(20), nullable=False)
    marketplace: Mapped[str] = mapped_column(String(10), nullable=True)
    language: Mapped[str] = mapped_column(String(5), nullable=False, default="en")

    title: Mapped[str] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    error_message: Mapped[str] = mapped_column(Text, nullable=True)

    # JSONB data fields
    product_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=True)
    competitor_data: Mapped[list] = mapped_column(JSONB, nullable=True)
    ai_analysis: Mapped[dict] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    organization: Mapped["Organization"] = relationship("Organization")
    account: Mapped["AmazonAccount"] = relationship("AmazonAccount")
    created_by: Mapped["User"] = relationship("User")


from app.models.user import Organization, User
from app.models.amazon_account import AmazonAccount
