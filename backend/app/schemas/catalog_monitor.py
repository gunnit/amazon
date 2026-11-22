"""Request and response models of the catalogue monitor API (R1)."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class RuleResultOut(BaseModel):
    key: str
    state: str
    mandatory: bool
    code: str
    details: dict = Field(default_factory=dict)


class QualityItem(BaseModel):
    asin: str
    sku: Optional[str] = None
    title: Optional[str] = None
    main_image_url: Optional[str] = None
    state: str
    score: int
    results: list[RuleResultOut]


class QualityItemDetail(QualityItem):
    content: Optional[dict] = None
    main_keyword: Optional[str] = None
    main_keyword_source: Optional[str] = None


class QualitySummary(BaseModel):
    green: int = 0
    yellow: int = 0
    red: int = 0
    grey: int = 0
    per_rule: dict[str, dict[str, int]] = Field(default_factory=dict)


class QualityResponse(BaseModel):
    summary: QualitySummary
    items: list[QualityItem]
    total: int
    unscanned: int
    page: int
    page_size: int
    last_scan_at: Optional[datetime] = None


class RuleConfigOut(BaseModel):
    key: str
    enabled: bool
    mandatory: bool
    params: dict


class RuleOverrideIn(BaseModel):
    marketplace_id: Optional[str] = Field(default=None, max_length=20)
    product_type: Optional[str] = Field(default=None, max_length=100)
    rule_key: str
    enabled: bool = True
    mandatory: bool = False
    params: Optional[dict[str, Any]] = None


class RuleOverrideOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    marketplace_id: Optional[str] = None
    product_type: Optional[str] = None
    rule_key: str
    enabled: bool
    mandatory: bool
    params: Optional[dict[str, Any]] = None
    updated_at: Optional[datetime] = None


class RulesResponse(BaseModel):
    defaults: dict[str, RuleConfigOut]
    overrides: list[RuleOverrideOut]


class RulesUpdateRequest(BaseModel):
    overrides: list[RuleOverrideIn]


class KeywordItem(BaseModel):
    asin: str = Field(min_length=1, max_length=20)
    keyword: str = Field(max_length=255)


class KeywordsUpdateRequest(BaseModel):
    account_id: UUID
    items: list[KeywordItem]


class KeywordsUpdateResponse(BaseModel):
    updated: int
    unknown: list[str]


class AccountRequest(BaseModel):
    account_id: UUID


class ScanStartResponse(BaseModel):
    started: bool


class ScanStateResponse(BaseModel):
    running: bool
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    summary: Optional[dict] = None


class CapabilityResponse(BaseModel):
    account_id: UUID
    results: dict
    vendor_code: Optional[str] = None
    checked_at: datetime


# ---- content protection, variations and approvals (R2, R3) ----


class AnomalyOut(BaseModel):
    id: UUID
    account_id: UUID
    asin: str
    title: Optional[str] = None
    kind: str
    field: str
    # content_changed only: modified|missing|added|reordered, as diff_content reports it
    change: Optional[str] = None
    status: str
    baseline_value: Any = None
    live_value: Any = None
    detected_at: datetime
    last_seen_at: datetime
    change_request_id: Optional[UUID] = None
    # Status of the linked restore request: while it is pending, valid, file_only or
    # approved the restore is in progress; otherwise accept and restore work again.
    change_request_status: Optional[str] = None


class AnomalyRestoreRequest(BaseModel):
    anomaly_ids: list[UUID] = Field(min_length=1)


class RestoreNotice(BaseModel):
    anomaly_id: UUID
    asin: str
    field: str
    reason: str


class ChangeRequestOut(BaseModel):
    id: UUID
    account_id: UUID
    batch_id: UUID
    asin: Optional[str] = None
    sku: Optional[str] = None
    kind: str
    operation: str
    product_type: Optional[str] = None
    status: str
    file_only: bool
    summary: Any = None
    validation_issues: Any = None
    submission_result: Any = None
    feed_id: Optional[str] = None
    created_at: datetime
    approved_at: Optional[datetime] = None
    submitted_at: Optional[datetime] = None


class ChangeBatchResponse(BaseModel):
    batch_id: Optional[UUID] = None
    requests: list[ChangeRequestOut]
    not_restorable: list[RestoreNotice] = Field(default_factory=list)
    skipped: list[RestoreNotice] = Field(default_factory=list)


class RowErrorOut(BaseModel):
    row: Optional[int] = None  # sheet row number; None when the message is not about one row
    asin: Optional[str] = None
    sku: Optional[str] = None
    message: str


class BulkUploadResponse(BaseModel):
    """Result of an upload that creates change requests (update mode or new items)."""

    batch_id: Optional[UUID] = None
    rows: int
    changes: int
    unchanged: int = 0
    keywords_updated: int = 0
    row_errors: list[RowErrorOut] = Field(default_factory=list)
    requests: list[ChangeRequestOut] = Field(default_factory=list)


class BaselineUploadResponse(BaseModel):
    updated: int
    keywords_updated: int = 0
    row_errors: list[RowErrorOut] = Field(default_factory=list)


class FieldChangeOut(BaseModel):
    field: str
    change: str
    baseline: Any = None
    live: Any = None


class HistoryVersionOut(BaseModel):
    id: UUID
    content_hash: str
    first_seen_at: datetime
    last_seen_at: datetime
    changes: list[FieldChangeOut]


class BaselineStatusResponse(BaseModel):
    asins_with_baseline: int
    asins_total: int
    families: int


class BaselinesRequest(BaseModel):
    account_id: UUID
    asins: Optional[list[str]] = None


class BaselinesResponse(BaseModel):
    count: int


class VariationChildOut(BaseModel):
    asin: str
    state: str  # ok|detached|unexpected|unknown


class VariationOut(BaseModel):
    parent_asin: str
    variation_theme: Optional[str] = None
    status: str  # ok|partial|broken
    children: list[VariationChildOut]
    anomaly_ids: list[UUID]


class VariationRestoreRequest(BaseModel):
    account_id: UUID
    parent_asin: str
    child_asins: Optional[list[str]] = None


class ChangeIdsRequest(BaseModel):
    ids: list[UUID] = Field(min_length=1)


class ChangeActionResponse(BaseModel):
    requests: list[ChangeRequestOut]
    skipped: dict[str, str] = Field(default_factory=dict)  # request id -> reason


class RefreshFeedRequest(BaseModel):
    account_id: UUID
    feed_id: str
