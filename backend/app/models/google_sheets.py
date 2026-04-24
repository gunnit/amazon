"""Google Sheets integration models."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class GoogleSheetsConnection(Base):
    """OAuth connection to a user's Google account."""

    __tablename__ = "google_sheets_connections"
    __table_args__ = (
        UniqueConstraint("user_id", "organization_id", name="uq_gsheets_conn_user_org"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )

    google_email: Mapped[str] = mapped_column(String(255), nullable=False)
    refresh_token_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    access_token_encrypted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    token_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    scopes: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    connected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )

    user: Mapped["User"] = relationship("User")
    organization: Mapped["Organization"] = relationship("Organization")


class GoogleSheetsSync(Base):
    """Configuration for automatic periodic sync to Google Sheets."""

    __tablename__ = "google_sheets_syncs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    connection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("google_sheets_connections.id", ondelete="CASCADE"), index=True
    )
    created_by_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    spreadsheet_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    spreadsheet_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    frequency: Mapped[str] = mapped_column(String(20), nullable=False)  # daily, weekly
    sync_mode: Mapped[str] = mapped_column(String(20), nullable=False)  # overwrite, append
    data_types: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    account_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    parameters: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    schedule_config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC")

    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_run_status: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    next_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )

    organization: Mapped["Organization"] = relationship("Organization")
    connection: Mapped["GoogleSheetsConnection"] = relationship("GoogleSheetsConnection")
    created_by: Mapped["User"] = relationship("User")
    runs: Mapped[list["GoogleSheetsSyncRun"]] = relationship(
        "GoogleSheetsSyncRun",
        back_populates="sync",
        cascade="all, delete-orphan",
        order_by=lambda: GoogleSheetsSyncRun.triggered_at.desc(),
    )


class GoogleSheetsSyncRun(Base):
    """Execution record for a Google Sheets sync."""

    __tablename__ = "google_sheets_sync_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sync_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("google_sheets_syncs.id", ondelete="CASCADE"), index=True
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    progress_step: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    triggered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    rows_written: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    spreadsheet_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    data_types_snapshot: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)

    sync: Mapped["GoogleSheetsSync"] = relationship("GoogleSheetsSync", back_populates="runs")
    organization: Mapped["Organization"] = relationship("Organization")


from app.models.user import Organization, User
