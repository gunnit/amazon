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


class AdsConnectionState(str, Enum):
    """Resolved state of the Amazon Ads integration for a single account."""
    OK = "ok"
    MISSING_REFRESH_TOKEN = "missing_refresh_token"
    MISSING_PROFILE = "missing_profile"
    MISSING_CLIENT_CREDENTIALS = "missing_client_credentials"
    AUTH_FAILURE = "auth_failure"


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
    advertising_profile_id: Optional[str] = None
    advertising_refresh_token: Optional[str] = None

    # Optional login credentials for web scraping
    login_email: Optional[str] = None
    login_password: Optional[str] = None


class AmazonAccountUpdate(BaseModel):
    """Schema for updating an Amazon account."""
    account_name: Optional[str] = Field(None, min_length=1, max_length=255)
    account_type: Optional[AccountType] = None
    marketplace_id: Optional[str] = None
    marketplace_country: Optional[str] = Field(None, min_length=2, max_length=10)
    is_active: Optional[bool] = None
    refresh_token: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    advertising_profile_id: Optional[str] = None
    advertising_refresh_token: Optional[str] = None
    login_email: Optional[str] = None
    login_password: Optional[str] = None


class AdvertisingProfilesRequest(BaseModel):
    """Request available Advertising profiles for a refresh token or account."""
    refresh_token: Optional[str] = None
    account_id: Optional[UUID] = None
    marketplace_country: Optional[str] = Field(None, min_length=2, max_length=10)
    client_id: Optional[str] = None
    client_secret: Optional[str] = None


class AdvertisingProfileResponse(BaseModel):
    """Normalized Amazon Ads profile metadata."""
    profile_id: str
    account_name: Optional[str] = None
    country_code: Optional[str] = None
    marketplace_id: Optional[str] = None
    account_type: Optional[str] = None
    currency: Optional[str] = None
    timezone: Optional[str] = None


class AmazonAccountResponse(BaseModel):
    """Schema for Amazon account response."""
    id: UUID
    organization_id: UUID
    account_name: str
    account_type: AccountType
    marketplace_id: str
    marketplace_country: str
    advertising_profile_id: Optional[str]
    is_active: bool
    last_sync_at: Optional[datetime]
    sync_status: SyncStatus
    sync_error_message: Optional[str]
    last_sync_started_at: Optional[datetime] = None
    last_sync_succeeded_at: Optional[datetime] = None
    last_sync_failed_at: Optional[datetime] = None
    last_sync_attempt_at: Optional[datetime] = None
    last_sync_heartbeat_at: Optional[datetime] = None
    sync_error_code: Optional[str] = None
    sync_error_kind: Optional[str] = None
    has_refresh_token: bool = False
    has_advertising_refresh_token: bool = False
    has_ads_client_credentials: bool = False
    ads_connection_state: AdsConnectionState = AdsConnectionState.MISSING_REFRESH_TOKEN
    ads_connection_detail: Optional[str] = None
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
    last_sync_started_at: Optional[datetime] = None
    last_sync_succeeded_at: Optional[datetime] = None
    last_sync_failed_at: Optional[datetime] = None
    last_sync_attempt_at: Optional[datetime] = None
    last_sync_heartbeat_at: Optional[datetime] = None
    sync_error_code: Optional[str] = None
    sync_error_kind: Optional[str] = None
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
