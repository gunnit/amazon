"""Catalogue monitoring tables: content protection, variations, change requests,
listing quality rules, Product Type Definition cache, image checks, API capabilities."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def _pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def _account_fk() -> Mapped[uuid.UUID]:
    return mapped_column(
        UUID(as_uuid=True),
        ForeignKey("amazon_accounts.id", ondelete="CASCADE"),
        nullable=False,
    )


def _org_fk() -> Mapped[uuid.UUID]:
    return mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )


def _user_fk(nullable: bool = True) -> Mapped[Optional[uuid.UUID]]:
    return mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=nullable,
    )


def _ts(nullable: bool = False) -> Mapped[datetime]:
    return mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=nullable
    )


class ListingContentVersion(Base):
    """Distinct content snapshots per ASIN (a new row only when the hash changes)."""

    __tablename__ = "listing_content_versions"
    __table_args__ = (
        Index(
            "ix_listing_content_versions_account_asin_last_seen",
            "account_id",
            "asin",
            "last_seen_at",
        ),
    )

    id: Mapped[uuid.UUID] = _pk()
    account_id: Mapped[uuid.UUID] = _account_fk()
    asin: Mapped[str] = mapped_column(String(20), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    content: Mapped[Any] = mapped_column(JSONB, nullable=False)
    first_seen_at: Mapped[datetime] = _ts()
    last_seen_at: Mapped[datetime] = _ts()


class ListingContentBaseline(Base):
    """Approved reference content for an ASIN."""

    __tablename__ = "listing_content_baselines"
    __table_args__ = (
        UniqueConstraint("account_id", "asin", name="uq_listing_content_baseline_account_asin"),
    )

    id: Mapped[uuid.UUID] = _pk()
    account_id: Mapped[uuid.UUID] = _account_fk()
    asin: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[Any] = mapped_column(JSONB, nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)  # live_snapshot|excel_upload
    approved_by_user_id: Mapped[Optional[uuid.UUID]] = _user_fk()
    approved_at: Mapped[datetime] = _ts()


class VariationFamilyBaseline(Base):
    """Approved parent/children composition of a variation family."""

    __tablename__ = "variation_family_baselines"
    __table_args__ = (
        UniqueConstraint("account_id", "parent_asin", name="uq_variation_baseline_account_parent"),
    )

    id: Mapped[uuid.UUID] = _pk()
    account_id: Mapped[uuid.UUID] = _account_fk()
    parent_asin: Mapped[str] = mapped_column(String(20), nullable=False)
    variation_theme: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    child_asins: Mapped[Any] = mapped_column(JSONB, nullable=False, default=list)
    is_partial: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    captured_at: Mapped[datetime] = _ts()


class CatalogAnomaly(Base):
    """Detected divergence from a baseline; one open row per (account, asin, kind, field)."""

    __tablename__ = "catalog_anomalies"
    __table_args__ = (
        Index(
            "uq_catalog_anomalies_open",
            "account_id",
            "asin",
            "kind",
            "field",
            unique=True,
            postgresql_where=text("status <> 'resolved'"),
        ),
    )

    id: Mapped[uuid.UUID] = _pk()
    account_id: Mapped[uuid.UUID] = _account_fk()
    asin: Mapped[str] = mapped_column(String(20), nullable=False)
    # content_changed|child_detached|family_broken|unexpected_child|theme_changed
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    field: Mapped[str] = mapped_column(String(80), nullable=False)
    baseline_value: Mapped[Optional[Any]] = mapped_column(JSONB, nullable=True)
    live_value: Mapped[Optional[Any]] = mapped_column(JSONB, nullable=True)
    # open|acknowledged|restore_requested|resolved
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open")
    detected_at: Mapped[datetime] = _ts()
    last_seen_at: Mapped[datetime] = _ts()
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    change_request_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)


class CatalogChangeRequest(Base):
    """A proposed catalogue write; nothing reaches Amazon until it is approved."""

    __tablename__ = "catalog_change_requests"
    __table_args__ = (Index("ix_catalog_change_requests_batch_id", "batch_id"),)

    id: Mapped[uuid.UUID] = _pk()
    organization_id: Mapped[uuid.UUID] = _org_fk()
    account_id: Mapped[uuid.UUID] = _account_fk()
    batch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    asin: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    sku: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    # bulk_update|content_restore|variation_restore|new_item
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    operation: Mapped[str] = mapped_column(String(16), nullable=False)  # PATCH|PUT
    product_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    payload: Mapped[Any] = mapped_column(JSONB, nullable=False)
    summary: Mapped[Optional[Any]] = mapped_column(JSONB, nullable=True)
    # pending|valid|invalid|approved|rejected|submitted|accepted|failed|file_only
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    validation_issues: Mapped[Optional[Any]] = mapped_column(JSONB, nullable=True)
    submission_result: Mapped[Optional[Any]] = mapped_column(JSONB, nullable=True)
    feed_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_by_user_id: Mapped[Optional[uuid.UUID]] = _user_fk()
    approved_by_user_id: Mapped[Optional[uuid.UUID]] = _user_fk()
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    submitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class ListingQualityRule(Base):
    """Per-organisation rule configuration, optionally scoped by marketplace / product type."""

    __tablename__ = "listing_quality_rules"
    __table_args__ = (
        # NULLS NOT DISTINCT emulated with coalesce.
        Index(
            "uq_listing_quality_rules_scope",
            "organization_id",
            text("coalesce(marketplace_id, '')"),
            text("coalesce(product_type, '')"),
            "rule_key",
            unique=True,
        ),
    )

    id: Mapped[uuid.UUID] = _pk()
    organization_id: Mapped[uuid.UUID] = _org_fk()
    marketplace_id: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    product_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    rule_key: Mapped[str] = mapped_column(String(40), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    mandatory: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    params: Mapped[Optional[Any]] = mapped_column(JSONB, nullable=True)
    updated_by_user_id: Mapped[Optional[uuid.UUID]] = _user_fk()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )


class ProductTypeDefinitionCache(Base):
    """Cached Product Type Definition (required attributes) per marketplace."""

    __tablename__ = "product_type_definitions_cache"
    __table_args__ = (
        UniqueConstraint("marketplace_id", "product_type", name="uq_ptd_cache_marketplace_type"),
    )

    id: Mapped[uuid.UUID] = _pk()
    marketplace_id: Mapped[str] = mapped_column(String(20), nullable=False)
    product_type: Mapped[str] = mapped_column(String(100), nullable=False)
    required_attributes: Mapped[Any] = mapped_column(JSONB, nullable=False)
    property_names: Mapped[Any] = mapped_column(JSONB, nullable=False)
    fetched_at: Mapped[datetime] = _ts()


class ImageCheck(Base):
    """Result of a main-image check (white background, fill ratio), keyed by URL hash."""

    __tablename__ = "image_checks"

    id: Mapped[uuid.UUID] = _pk()
    url_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    white_background: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    fill_ratio: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    width: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    height: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    checked_at: Mapped[datetime] = _ts()


class CatalogApiCapability(Base):
    """Which catalogue APIs an account can actually use (probed, one row per account)."""

    __tablename__ = "catalog_api_capabilities"

    id: Mapped[uuid.UUID] = _pk()
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("amazon_accounts.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    results: Mapped[Any] = mapped_column(JSONB, nullable=False)
    vendor_code: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    checked_at: Mapped[datetime] = _ts()
