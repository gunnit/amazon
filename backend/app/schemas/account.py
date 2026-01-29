"""Amazon account schemas."""
from datetime import datetime
from typing import Optional, List
from uuid import UUID
from pydantic import BaseModel, Field
from enum import Enum


class AccountType(str, Enum):
    SELLER = "seller"
    VENDOR = "vendor"


class SyncStatus(str, Enum):
    PENDING = "pending"
    SYNCING = "syncing"
    SUCCESS = "success"
    ERROR = "error"


class AmazonAccountCreate(BaseModel):
    """Schema for creating an Amazon account."""
    account_name: str = Field(..., min_length=1, max_length=255)
    account_type: AccountType
    marketplace_id: str = Field(..., min_length=1)
    marketplace_country: str = Field(..., min_length=2, max_length=10)

    # Optional SP-API credentials
    refresh_token: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None

    # Optional login credentials for web scraping
    login_email: Optional[str] = None
    login_password: Optional[str] = None


class AmazonAccountUpdate(BaseModel):
    """Schema for updating an Amazon account."""
    account_name: Optional[str] = Field(None, min_length=1, max_length=255)
    is_active: Optional[bool] = None
    refresh_token: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    login_email: Optional[str] = None
    login_password: Optional[str] = None


class AmazonAccountResponse(BaseModel):
    """Schema for Amazon account response."""
    id: UUID
    organization_id: UUID
    account_name: str
    account_type: AccountType
    marketplace_id: str
    marketplace_country: str
    is_active: bool
    last_sync_at: Optional[datetime]
    sync_status: SyncStatus
    sync_error_message: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class AccountStatusResponse(BaseModel):
    """Schema for account status response."""
    id: UUID
    account_name: str
    marketplace_country: str
    sync_status: SyncStatus
    last_sync_at: Optional[datetime]
    sync_error_message: Optional[str]
    total_sales_30d: float = 0
    total_units_30d: int = 0
    active_asins: int = 0


class AccountSummary(BaseModel):
    """Summary of all accounts."""
    total_accounts: int
    active_accounts: int
    syncing_accounts: int
    error_accounts: int
    accounts: List[AccountStatusResponse]
