"""Brand analysis automation models."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, LargeBinary, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class BrandAnalysisJob(Base):
    """Long-running brand analysis job and generated deck artifact."""

    __tablename__ = "brand_analysis_jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    created_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    account_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("amazon_accounts.id", ondelete="SET NULL"), index=True, nullable=True
    )

    brand_name: Mapped[str] = mapped_column(String(255), nullable=False)
    language: Mapped[str] = mapped_column(String(5), nullable=False, default="en")
    mode: Mapped[str] = mapped_column(String(20), nullable=False, default="internal")
    market_type: Mapped[str] = mapped_column(String(20), nullable=False, default="brand")
    market_query: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    asin_list: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)

    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", index=True)
    progress_step: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    progress_pct: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    sync_attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_sync_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    next_retry_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    sync_idempotency_key: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    celery_task_id: Mapped[Optional[str]] = mapped_column(String(155), nullable=True)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    heartbeat_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    metrics: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    narrative: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    data_source_name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    metric_provenance: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    capability_matrix: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    data_coverage: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    limitations: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    storage_ref: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    artifact_filename: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    artifact_content_type: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    artifact_data: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    organization: Mapped["Organization"] = relationship("Organization")
    created_by: Mapped[Optional["User"]] = relationship("User")
    account: Mapped[Optional["AmazonAccount"]] = relationship("AmazonAccount")
    source_files: Mapped[list["BrandAnalysisSourceFile"]] = relationship(
        "BrandAnalysisSourceFile",
        back_populates="job",
        cascade="all, delete-orphan",
        order_by="BrandAnalysisSourceFile.year",
    )


class BrandAnalysisCapability(Base):
    """Persisted capability matrix for one organization/account/marketplace."""

    __tablename__ = "brand_analysis_capabilities"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "account_id",
            "marketplace_id",
            name="uq_brand_analysis_capabilities_org_account_marketplace",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("amazon_accounts.id", ondelete="CASCADE"), index=True, nullable=False
    )
    marketplace_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    sales_and_traffic_available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    data_kiosk_available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    brand_analytics_available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    brand_registry_available_or_inferred: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    product_pricing_available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    product_fees_available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    aplus_available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    finance_reports_available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    settlement_reports_available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    catalog_items_available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    listings_available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    missing_roles: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    last_error_by_capability: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    raw_diagnostics: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    organization: Mapped["Organization"] = relationship("Organization")
    account: Mapped["AmazonAccount"] = relationship("AmazonAccount")


class AsinOfferSnapshot(Base):
    """Current offer and Buy Box snapshot collected from Product Pricing."""

    __tablename__ = "asin_offer_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("amazon_accounts.id", ondelete="CASCADE"), index=True, nullable=False
    )
    marketplace_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    asin: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    seller_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    offer_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    buy_box_owner_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    buy_box_seller_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    buy_box_price: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), nullable=True)
    fulfillment_channel: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    is_fba: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    source: Mapped[str] = mapped_column(String(80), nullable=False, default="product_pricing")
    raw_payload: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    organization: Mapped["Organization"] = relationship("Organization")
    account: Mapped["AmazonAccount"] = relationship("AmazonAccount")


class BrandAnalysisSourceFile(Base):
    """Uploaded external yearly product export for a single analysis year."""

    __tablename__ = "brand_analysis_source_files"
    __table_args__ = (
        UniqueConstraint("job_id", "year", name="uq_brand_analysis_source_files_job_year"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("brand_analysis_jobs.id", ondelete="CASCADE"), index=True, nullable=False
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    uploaded_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    year: Mapped[int] = mapped_column(Integer, nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    file_data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    row_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    columns: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    column_validation: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    storage_ref: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    job: Mapped[BrandAnalysisJob] = relationship("BrandAnalysisJob", back_populates="source_files")
    organization: Mapped["Organization"] = relationship("Organization")
    uploaded_by: Mapped[Optional["User"]] = relationship("User")


from app.models.amazon_account import AmazonAccount  # noqa: E402
from app.models.user import Organization, User  # noqa: E402
