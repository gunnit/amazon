"""Sync job model."""
from __future__ import annotations
import uuid
from datetime import datetime
from sqlalchemy import String, Integer, Boolean, ForeignKey, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class SyncJob(Base):
    """Scheduled sync job model."""
    __tablename__ = "sync_jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("amazon_accounts.id", ondelete="CASCADE"), index=True
    )
    job_type: Mapped[str] = mapped_column(String(50), nullable=False)  # sales, inventory, advertising, catalog

    # Scheduling
    schedule_cron: Mapped[str] = mapped_column(String(100), nullable=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    # Last Run
    last_run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    last_run_status: Mapped[str] = mapped_column(String(20), nullable=True)  # success, error, running
    last_run_error: Mapped[str] = mapped_column(Text, nullable=True)
    last_run_records_processed: Mapped[int] = mapped_column(Integer, nullable=True)

    # Next Run
    next_run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    # Relationships
    account: Mapped["AmazonAccount"] = relationship("AmazonAccount", back_populates="sync_jobs")


from app.models.amazon_account import AmazonAccount
