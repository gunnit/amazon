"""Report and data schemas."""
from datetime import datetime, date
from typing import Literal, Optional, List
from uuid import UUID
from decimal import Decimal
from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator


class DateRangeParams(BaseModel):
    """Date range parameters for queries."""
    start_date: date
    end_date: date
    account_ids: Optional[List[UUID]] = None
    asins: Optional[List[str]] = None


class SalesDataResponse(BaseModel):
    """Schema for sales data response."""
    id: int
    account_id: UUID
    date: date
    asin: str
    sku: Optional[str]
    units_ordered: int
    units_ordered_b2b: int
    ordered_product_sales: Decimal
    ordered_product_sales_b2b: Decimal
    total_order_items: int
    currency: str

    class Config:
        from_attributes = True


class SalesDataAggregated(BaseModel):
    """Aggregated sales data."""
    date: date
    total_units: int
    total_sales: Decimal
    total_orders: int
    currency: str


class InventoryDataResponse(BaseModel):
    """Schema for inventory data response."""
    id: int
    account_id: UUID
    snapshot_date: date
    asin: str
    sku: Optional[str]
    fnsku: Optional[str]
    afn_fulfillable_quantity: int
    afn_inbound_working_quantity: int
    afn_inbound_shipped_quantity: int
    afn_reserved_quantity: int
    afn_total_quantity: int
    mfn_fulfillable_quantity: int

    class Config:
        from_attributes = True


class OrderItemResponse(BaseModel):
    """Schema for order item response."""

    id: int
    asin: Optional[str]
    sku: Optional[str]
    title: Optional[str]
    quantity: int
    item_price: Optional[Decimal]
    item_tax: Optional[Decimal]

    class Config:
        from_attributes = True


class OrderResponse(BaseModel):
    """Schema for order response."""

    id: int
    account_id: UUID
    amazon_order_id: str
    purchase_date: datetime
    order_status: str
    fulfillment_channel: Optional[str]
    order_total: Optional[Decimal]
    currency: Optional[str]
    marketplace_id: Optional[str]
    number_of_items: int
    created_at: datetime
    items: List[OrderItemResponse] = Field(default_factory=list)

    class Config:
        from_attributes = True


class OrderListResponse(BaseModel):
    """Paginated order response."""

    items: List[OrderResponse]
    total: int
    limit: int
    offset: int
    has_more: bool


class AdvertisingMetricsResponse(BaseModel):
    """Schema for advertising metrics response."""
    id: int
    campaign_id: str
    campaign_name: str
    campaign_type: str
    date: date
    impressions: int
    clicks: int
    cost: Decimal
    attributed_sales_7d: Decimal
    attributed_units_ordered_7d: int
    ctr: Optional[Decimal]
    cpc: Optional[Decimal]
    acos: Optional[Decimal]
    roas: Optional[Decimal]

    class Config:
        from_attributes = True


class AdvertisingAggregated(BaseModel):
    """Aggregated advertising data."""
    date: date
    total_impressions: int
    total_clicks: int
    total_cost: Decimal
    total_sales: Decimal
    avg_ctr: Decimal
    avg_acos: Decimal
    avg_roas: Decimal


class ProductResponse(BaseModel):
    """Schema for product response."""
    id: UUID
    account_id: UUID
    asin: str
    sku: Optional[str]
    title: Optional[str]
    brand: Optional[str]
    category: Optional[str]
    current_price: Optional[Decimal]
    current_bsr: Optional[int]
    review_count: Optional[int]
    rating: Optional[Decimal]
    is_active: bool

    class Config:
        from_attributes = True


class ReportScheduleCreate(BaseModel):
    """Legacy placeholder schema for creating a report schedule."""
    account_ids: List[UUID]
    report_type: str
    schedule_cron: str
    email_recipients: Optional[List[str]] = None


class ReportScheduleResponse(BaseModel):
    """Legacy placeholder schema for report schedule response."""
    id: UUID
    account_id: UUID
    job_type: str
    schedule_cron: Optional[str]
    is_enabled: bool
    last_run_at: Optional[datetime]
    last_run_status: Optional[str]
    next_run_at: Optional[datetime]

    class Config:
        from_attributes = True


ScheduledReportType = Literal["sales", "inventory", "advertising"]
ScheduledReportFrequency = Literal["weekly", "monthly"]
ScheduledReportFormat = Literal["excel", "pdf"]
ScheduledReportRunStatus = Literal["pending", "processing", "generated", "delivered", "failed"]


class ScheduledReportParameters(BaseModel):
    """Supported runtime parameters for scheduled reports."""

    group_by: Literal["day", "week", "month"] = "day"
    low_stock_only: bool = False
    language: Literal["en", "it"] = "en"
    include_comparison: bool = True


class WeeklyScheduleConfig(BaseModel):
    """Weekly schedule settings."""

    weekday: int = Field(..., ge=0, le=6)
    hour: int = Field(..., ge=0, le=23)
    minute: int = Field(..., ge=0, le=59)


class MonthlyScheduleConfig(BaseModel):
    """Monthly schedule settings."""

    day_of_month: int = Field(..., ge=1, le=31)
    hour: int = Field(..., ge=0, le=23)
    minute: int = Field(..., ge=0, le=59)


class ScheduledReportCreate(BaseModel):
    """Create payload for a recurring operational report."""

    name: str = Field(..., min_length=1, max_length=255)
    report_types: List[ScheduledReportType]
    frequency: ScheduledReportFrequency
    format: ScheduledReportFormat
    timezone: str = Field(default="UTC", min_length=1, max_length=64)
    account_ids: List[UUID] = Field(default_factory=list)
    recipients: List[EmailStr]
    parameters: ScheduledReportParameters = Field(default_factory=ScheduledReportParameters)
    schedule_config: dict
    is_enabled: bool = True

    @field_validator("report_types")
    @classmethod
    def validate_report_types(cls, value: List[ScheduledReportType]) -> List[ScheduledReportType]:
        if not value:
            raise ValueError("At least one report type is required")
        return list(dict.fromkeys(value))

    @field_validator("recipients")
    @classmethod
    def validate_recipients(cls, value: List[EmailStr]) -> List[EmailStr]:
        if not value:
            raise ValueError("At least one recipient is required")
        return value

    @model_validator(mode="after")
    def validate_schedule_config(self) -> "ScheduledReportCreate":
        if self.frequency == "weekly":
            WeeklyScheduleConfig(**self.schedule_config)
        else:
            MonthlyScheduleConfig(**self.schedule_config)

        if "inventory" not in self.report_types and self.parameters.low_stock_only:
            raise ValueError("low_stock_only requires the inventory report")
        if "sales" not in self.report_types and self.parameters.group_by != "day":
            raise ValueError("group_by only applies to the sales report")
        return self


class ScheduledReportUpdate(BaseModel):
    """Update payload for a recurring operational report."""

    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    report_types: Optional[List[ScheduledReportType]] = None
    frequency: Optional[ScheduledReportFrequency] = None
    format: Optional[ScheduledReportFormat] = None
    timezone: Optional[str] = Field(default=None, min_length=1, max_length=64)
    account_ids: Optional[List[UUID]] = None
    recipients: Optional[List[EmailStr]] = None
    parameters: Optional[ScheduledReportParameters] = None
    schedule_config: Optional[dict] = None
    is_enabled: Optional[bool] = None


class ScheduledReportRunResponse(BaseModel):
    """Read model for a scheduled report execution."""

    id: str
    scheduled_report_id: str
    status: ScheduledReportRunStatus
    generation_status: str
    delivery_status: str
    progress_step: Optional[str] = None
    error_message: Optional[str] = None
    triggered_at: str
    period_start: str
    period_end: str
    completed_at: Optional[str] = None
    artifact_filename: Optional[str] = None
    download_ready: bool = False
    recipients: List[str] = Field(default_factory=list)


class ScheduledReportResponse(BaseModel):
    """Read model for a scheduled report configuration."""

    id: str
    name: str
    report_types: List[ScheduledReportType]
    frequency: ScheduledReportFrequency
    format: ScheduledReportFormat
    timezone: str
    account_ids: List[str]
    recipients: List[str]
    parameters: ScheduledReportParameters
    schedule_config: dict
    is_enabled: bool
    last_run_at: Optional[str] = None
    last_run_status: Optional[str] = None
    next_run_at: Optional[str] = None
    created_at: str
    updated_at: str


class ScheduledReportListResponse(BaseModel):
    """List wrapper for scheduled reports."""

    items: List[ScheduledReportResponse]
