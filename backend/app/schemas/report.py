"""Report and data schemas."""
from datetime import datetime, date
from typing import Optional, List
from uuid import UUID
from decimal import Decimal
from pydantic import BaseModel, Field


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


class AdvertisingMetricsResponse(BaseModel):
    """Schema for advertising metrics response."""
    id: int
    campaign_id: UUID
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
    """Schema for creating a report schedule."""
    account_ids: List[UUID]
    report_type: str  # sales, inventory, advertising
    schedule_cron: str
    email_recipients: Optional[List[str]] = None


class ReportScheduleResponse(BaseModel):
    """Schema for report schedule response."""
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
