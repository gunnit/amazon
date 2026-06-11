"""Weekly listing-quality score snapshots."""
from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ListingQualitySnapshot(Base):
    """Listing quality score (0-100) for one ASIN at one point in time.

    The live score is always computed on demand from warehouse data
    (listing_quality_service); snapshots exist for week-over-week trends.
    """

    __tablename__ = "listing_quality_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "account_id", "asin", "snapshot_date", name="uq_listing_quality_account_asin_date"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("amazon_accounts.id", ondelete="CASCADE"), index=True
    )
    asin: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    score: Mapped[int] = mapped_column(Integer, nullable=False)
    # Per-component detail: {component: {earned, max, detail}, ...}
    components: Mapped[dict] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
