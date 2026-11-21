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
