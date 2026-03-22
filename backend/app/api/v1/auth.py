"""Authentication endpoints."""
from datetime import timedelta
from uuid import UUID
from fastapi import APIRouter, HTTPException, status, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import re

from app.db.session import get_db
from app.models.user import User, Organization, OrganizationMember, UserRole
from app.schemas.user import (
    UserCreate, UserUpdate, UserResponse, UserLogin, Token,
    PasswordChange, NotificationPreferences,
    OrganizationCreate, OrganizationResponse,
    OrganizationApiKeysUpdate, OrganizationApiKeysResponse,
)
from app.core.security import (
    verify_password, get_password_hash,
    create_access_token, create_refresh_token, decode_token,
    encrypt_value, decrypt_value,
)
from app.api.deps import CurrentUser, CurrentOrganization, DbSession

router = APIRouter()


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(user_in: UserCreate, db: DbSession):
    """Register a new user."""
    # Check if user exists
    result = await db.execute(select(User).where(User.email == user_in.email))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )

    # Create user
    user = User(
        email=user_in.email,
        hashed_password=get_password_hash(user_in.password),
        full_name=user_in.full_name,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)

    # Create default organization for user
    slug = re.sub(r'[^a-z0-9-]', '', user_in.email.split('@')[0].lower())
    org = Organization(
        name=f"{user_in.full_name or user_in.email}'s Organization",
        slug=f"{slug}-{str(user.id)[:8]}",
    )
    db.add(org)
    await db.flush()

    # Add user as org admin
    membership = OrganizationMember(
        user_id=user.id,
        organization_id=org.id,
        role=UserRole.ADMIN,
    )
    db.add(membership)

    return user


@router.post("/login", response_model=Token)
async def login(user_in: UserLogin, db: DbSession):
    """Login and get JWT tokens."""
    # Find user
    result = await db.execute(select(User).where(User.email == user_in.email))
    user = result.scalar_one_or_none()

    if not user or not verify_password(user_in.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive"
        )

    # Create tokens
    access_token = create_access_token(data={"sub": str(user.id)})
    refresh_token = create_refresh_token(data={"sub": str(user.id)})

    return Token(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer"
    )


@router.post("/refresh", response_model=Token)
async def refresh_token(refresh_token: str, db: DbSession):
    """Refresh JWT tokens."""
    payload = decode_token(refresh_token)

    if payload is None or payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("sub")
    result = await db.execute(select(User).where(User.id == UUID(user_id)))
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Create new tokens
    access_token = create_access_token(data={"sub": str(user.id)})
    new_refresh_token = create_refresh_token(data={"sub": str(user.id)})

    return Token(
        access_token=access_token,
        refresh_token=new_refresh_token,
        token_type="bearer"
    )


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: CurrentUser):
    """Get current user information."""
    return current_user


@router.put("/me", response_model=UserResponse)
async def update_current_user(
    user_in: UserUpdate,
    current_user: CurrentUser,
    db: DbSession,
):
    """Update current user's profile."""
    # If email is changing, check uniqueness
    if user_in.email is not None and user_in.email != current_user.email:
        result = await db.execute(select(User).where(User.email == user_in.email))
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )
        current_user.email = user_in.email

    if user_in.full_name is not None:
        current_user.full_name = user_in.full_name

    if user_in.password is not None:
        current_user.hashed_password = get_password_hash(user_in.password)

    await db.flush()
    await db.refresh(current_user)
    return current_user


@router.put("/me/password")
async def change_password(
    password_in: PasswordChange,
    current_user: CurrentUser,
    db: DbSession,
):
    """Change the current user's password."""
    if not verify_password(password_in.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect"
        )

    current_user.hashed_password = get_password_hash(password_in.new_password)
    await db.flush()
    return {"message": "Password changed successfully"}


@router.get("/me/notifications", response_model=NotificationPreferences)
async def get_notification_preferences(
    current_user: CurrentUser,
    organization: CurrentOrganization,
):
    """Get notification preferences for the current user."""
    prefs = (organization.settings or {}).get(f"notification_prefs_{current_user.id}")
    if prefs:
        return NotificationPreferences(**prefs)
    return NotificationPreferences()


@router.put("/me/notifications", response_model=NotificationPreferences)
async def update_notification_preferences(
    prefs_in: NotificationPreferences,
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
):
    """Update notification preferences for the current user."""
    current_settings = dict(organization.settings or {})
    current_settings[f"notification_prefs_{current_user.id}"] = prefs_in.model_dump()
    organization.settings = current_settings
    await db.flush()
    return prefs_in


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
async def delete_current_user(
    current_user: CurrentUser,
    db: DbSession,
):
    """Permanently delete the current user's account."""
    await db.delete(current_user)


@router.post("/organization", response_model=OrganizationResponse, status_code=status.HTTP_201_CREATED)
async def create_organization(org_in: OrganizationCreate, current_user: CurrentUser, db: DbSession):
    """Create a new organization."""
    # Check if slug exists
    result = await db.execute(select(Organization).where(Organization.slug == org_in.slug))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Organization slug already exists"
        )

    org = Organization(name=org_in.name, slug=org_in.slug)
    db.add(org)
    await db.flush()

    # Add creator as admin
    membership = OrganizationMember(
        user_id=current_user.id,
        organization_id=org.id,
        role=UserRole.ADMIN,
    )
    db.add(membership)
    await db.refresh(org)

    return org


@router.get("/organization", response_model=OrganizationResponse)
async def get_current_organization(current_user: CurrentUser, db: DbSession):
    """Get current user's organization."""
    result = await db.execute(
        select(Organization)
        .join(OrganizationMember)
        .where(OrganizationMember.user_id == current_user.id)
    )
    org = result.scalar_one_or_none()

    if not org:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User is not a member of any organization"
        )

    return org


def _mask_value(value: str | None) -> str | None:
    """Mask a credential value, showing first 8 and last 3 chars."""
    if not value:
        return None
    if len(value) <= 12:
        return value[:3] + "***"
    return value[:8] + "***" + value[-3:]


def _build_api_keys_response(sp_api: dict | None) -> OrganizationApiKeysResponse:
    """Build a masked response from stored sp_api settings."""
    if not sp_api:
        return OrganizationApiKeysResponse()

    client_id = None
    aws_access_key = None
    try:
        if sp_api.get("client_id_enc"):
            client_id = _mask_value(decrypt_value(sp_api["client_id_enc"]))
    except Exception:
        client_id = "(decryption error)"
    try:
        if sp_api.get("aws_access_key_enc"):
            aws_access_key = _mask_value(decrypt_value(sp_api["aws_access_key_enc"]))
    except Exception:
        aws_access_key = "(decryption error)"

    role_arn = None
    try:
        if sp_api.get("role_arn_enc"):
            role_arn = decrypt_value(sp_api["role_arn_enc"])
    except Exception:
        role_arn = "(decryption error)"

    return OrganizationApiKeysResponse(
        sp_api_client_id=client_id,
        sp_api_aws_access_key=aws_access_key,
        sp_api_role_arn=role_arn,
        has_client_secret=bool(sp_api.get("client_secret_enc")),
        has_aws_secret_key=bool(sp_api.get("aws_secret_key_enc")),
    )


@router.get("/organization/api-keys", response_model=OrganizationApiKeysResponse)
async def get_organization_api_keys(
    current_user: CurrentUser,
    organization: CurrentOrganization,
):
    """Get masked SP-API credentials for the organization."""
    sp_api = (organization.settings or {}).get("sp_api")
    return _build_api_keys_response(sp_api)


@router.put("/organization/api-keys", response_model=OrganizationApiKeysResponse)
async def update_organization_api_keys(
    keys_in: OrganizationApiKeysUpdate,
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
):
    """Save SP-API credentials for the organization (encrypted)."""
    current_settings = dict(organization.settings or {})
    sp_api = dict(current_settings.get("sp_api", {}))

    if keys_in.sp_api_client_id is not None:
        sp_api["client_id_enc"] = encrypt_value(keys_in.sp_api_client_id)
    if keys_in.sp_api_client_secret is not None:
        sp_api["client_secret_enc"] = encrypt_value(keys_in.sp_api_client_secret)
    if keys_in.sp_api_aws_access_key is not None:
        sp_api["aws_access_key_enc"] = encrypt_value(keys_in.sp_api_aws_access_key)
    if keys_in.sp_api_aws_secret_key is not None:
        sp_api["aws_secret_key_enc"] = encrypt_value(keys_in.sp_api_aws_secret_key)
    if keys_in.sp_api_role_arn is not None:
        sp_api["role_arn_enc"] = encrypt_value(keys_in.sp_api_role_arn)

    current_settings["sp_api"] = sp_api
    organization.settings = current_settings
    await db.flush()
    await db.refresh(organization)

    return _build_api_keys_response(sp_api)


@router.delete("/organization/api-keys", response_model=OrganizationApiKeysResponse)
async def delete_organization_api_keys(
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
):
    """Remove all saved SP-API credentials for the organization."""
    current_settings = dict(organization.settings or {})
    current_settings.pop("sp_api", None)
    organization.settings = current_settings
    await db.flush()
    await db.refresh(organization)

    return _build_api_keys_response(None)
