"""Weekly Brand Analytics search-term rankings."""
from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class BrandSearchTerm(Base):
    """One Brand Analytics search term for one reporting week.

    Stored only for terms whose top-3 clicked ASINs include at least one of the
    account's own ASINs — the full marketplace report is millions of rows.
    """

    __tablename__ = "brand_search_terms"
    __table_args__ = (
        UniqueConstraint("account_id", "week_start", "search_term", name="uq_brand_search_terms_account_week_term"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("amazon_accounts.id", ondelete="CASCADE"), index=True
    )
    week_start: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    week_end: Mapped[date] = mapped_column(Date, nullable=False)

    search_term: Mapped[str] = mapped_column(String(500), nullable=False)
    search_frequency_rank: Mapped[int] = mapped_column(Integer, nullable=True)
    department: Mapped[str] = mapped_column(String(255), nullable=True)

    # [{rank, asin, product_title, click_share, conversion_share}, ...] (top 3)
    top_clicked: Mapped[list] = mapped_column(JSONB, nullable=True)
    # True when one of the top clicked ASINs belongs to this account's catalog.
    contains_account_asin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
