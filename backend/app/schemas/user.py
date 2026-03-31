"""User and authentication schemas."""
from datetime import datetime
from typing import Optional, List
from uuid import UUID
from pydantic import BaseModel, EmailStr, Field


class UserCreate(BaseModel):
    """Schema for creating a new user."""
    email: EmailStr
    password: str = Field(..., min_length=8)
    full_name: Optional[str] = None


class UserUpdate(BaseModel):
    """Schema for updating a user."""
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    password: Optional[str] = Field(None, min_length=8)


class UserResponse(BaseModel):
    """Schema for user response."""
    id: UUID
    email: EmailStr
    full_name: Optional[str]
    is_active: bool
    is_superuser: bool
    created_at: datetime

    class Config:
        from_attributes = True


class UserLogin(BaseModel):
    """Schema for user login."""
    email: EmailStr
    password: str


class OrganizationCreate(BaseModel):
    """Schema for creating an organization."""
    name: str = Field(..., min_length=1, max_length=255)
    slug: str = Field(..., min_length=1, max_length=100, pattern=r'^[a-z0-9-]+$')


class OrganizationResponse(BaseModel):
    """Schema for organization response."""
    id: UUID
    name: str
    slug: str
    timezone: str = "UTC"
    created_at: datetime

    class Config:
        from_attributes = True


class OrganizationMemberResponse(BaseModel):
    """Schema for organization member response."""
    user_id: UUID
    organization_id: UUID
    role: str
    user: UserResponse

    class Config:
        from_attributes = True


class OrganizationApiKeysUpdate(BaseModel):
    """Schema for updating organization SP-API credentials."""
    sp_api_client_id: Optional[str] = None
    sp_api_client_secret: Optional[str] = None
    sp_api_aws_access_key: Optional[str] = None
    sp_api_aws_secret_key: Optional[str] = None
    sp_api_role_arn: Optional[str] = None


class OrganizationApiKeysResponse(BaseModel):
    """Schema for organization SP-API credentials (masked)."""
    sp_api_client_id: Optional[str] = None
    sp_api_aws_access_key: Optional[str] = None
    sp_api_role_arn: Optional[str] = None
    has_client_secret: bool = False
    has_aws_secret_key: bool = False


class PasswordChange(BaseModel):
    """Schema for changing password."""
    current_password: str
    new_password: str = Field(..., min_length=8)


class NotificationPreferences(BaseModel):
    """Schema for notification preferences."""
    daily_digest: bool = True
    alert_emails: bool = True
    sync_notifications: bool = False


class Token(BaseModel):
    """Schema for JWT token response."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TokenPayload(BaseModel):
    """Schema for JWT token payload."""
    sub: str  # user_id
    exp: int
    type: str  # access or refresh
