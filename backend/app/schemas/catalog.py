"""Pydantic schemas for catalog management endpoints."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Generic, List, Optional, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

ASIN_PATTERN = r"^[A-Z0-9]{10}$"
CURRENCY_PATTERN = r"^[A-Z]{3}$"


T = TypeVar("T")


class BulkErrorCode(str, Enum):
    INVALID_INPUT = "invalid_input"
    PRODUCT_NOT_FOUND = "product_not_found"
    MISSING_SKU = "missing_sku"
    SP_API_ERROR = "sp_api_error"
    UNEXPECTED_ERROR = "unexpected_error"


class BulkRowError(BaseModel):
    row: Optional[int] = None
    asin: Optional[str] = None
    sku: Optional[str] = None
    error: str
    code: BulkErrorCode = BulkErrorCode.UNEXPECTED_ERROR


class BulkResult(BaseModel, Generic[T]):
    account_id: UUID
    total: int
    succeeded: int
    failed: int
    skipped: int = 0
    successes: List[T] = Field(default_factory=list)
    errors: List[BulkRowError] = Field(default_factory=list)


# ---------------------------------------------------------------------
# Price updates
# ---------------------------------------------------------------------


class PriceUpdate(BaseModel):
    asin: Optional[str] = Field(default=None, pattern=ASIN_PATTERN)
    sku: Optional[str] = Field(default=None, min_length=1, max_length=100)
    price: Decimal = Field(..., ge=0, decimal_places=2)

    def model_post_init(self, __context: Any) -> None:
        if not self.asin and not self.sku:
            raise ValueError("PriceUpdate requires either asin or sku")


class PriceUpdateResult(BaseModel):
    asin: Optional[str] = None
    sku: Optional[str] = None
    price: Decimal


class BulkPriceUpdateRequest(BaseModel):
    account_id: UUID
    updates: List[PriceUpdate] = Field(..., min_length=1)
    product_type: str = Field(default="PRODUCT", min_length=1, max_length=100)


# ---------------------------------------------------------------------
# Bulk listing update result
# ---------------------------------------------------------------------


class BulkListingUpdateResult(BaseModel):
    sku: str
    fields: List[str]


# ---------------------------------------------------------------------
# Availability
# ---------------------------------------------------------------------


class AvailabilityUpdateRequest(BaseModel):
    account_id: UUID
    is_available: bool
    quantity: Optional[int] = Field(default=None, ge=0)
    product_type: str = Field(default="PRODUCT", min_length=1, max_length=100)


class AvailabilityResult(BaseModel):
    asin: str
    sku: str
    is_available: bool
    pushed_quantity: int


# ---------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------


class CatalogChangeField(str, Enum):
    PRICE = "price"
    QUANTITY = "quantity"
    AVAILABILITY = "availability"
    IMAGE = "image"
    LISTING = "listing"


class CatalogChangeStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


class CatalogChangeLogEntry(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    account_id: UUID
    user_id: Optional[UUID] = None
    asin: Optional[str] = None
    sku: Optional[str] = None
    field: CatalogChangeField
    old_value: Optional[Any] = None
    new_value: Optional[Any] = None
    sp_api_status: CatalogChangeStatus
    sp_api_error: Optional[str] = None
    created_at: datetime
