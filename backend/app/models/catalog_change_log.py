"""Audit log for catalog write operations."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CatalogChangeLog(Base):
    """Persistent trail of catalog mutations pushed through SP-API.

    One row per attempted change. The row is written regardless of SP-API
    success so that retries and partial failures remain auditable.
    """

    __tablename__ = "catalog_change_log"
    __table_args__ = (
        Index(
            "ix_catalog_change_log_account_asin_created_at",
            "account_id",
            "asin",
            "created_at",
        ),
        Index("ix_catalog_change_log_organization_id", "organization_id"),
        Index("ix_catalog_change_log_user_id", "user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("amazon_accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    asin: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, index=True)
    sku: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    field: Mapped[str] = mapped_column(String(32), nullable=False)
    old_value: Mapped[Optional[Any]] = mapped_column(JSONB, nullable=True)
    new_value: Mapped[Optional[Any]] = mapped_column(JSONB, nullable=True)

    sp_api_status: Mapped[str] = mapped_column(String(16), nullable=False)
    sp_api_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
