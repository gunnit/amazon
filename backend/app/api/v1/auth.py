"""Authentication endpoints."""
from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Body, HTTPException, status, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import re

from app.db.session import get_db
from app.models.user import User, Organization, OrganizationMember, UserRole
from app.schemas.user import (
    UserCreate, UserUpdate, UserResponse, UserLogin, Token,
    PasswordChange, NotificationPreferences, EmailDeliveryStatus,
    ForgotPasswordRequest, ResetPasswordRequest,
    OrganizationCreate, OrganizationUpdate, OrganizationResponse,
    OrganizationApiKeysUpdate, OrganizationApiKeysResponse,
)
from app.core.security import (
    verify_password, get_password_hash,
    create_access_token, create_refresh_token, decode_token,
    create_password_reset_token,
    encrypt_value, decrypt_value,
)
from app.config import settings
from app.services.notification_service import NotificationService
from app.api.deps import (
    CurrentUser, CurrentOrganization, DbSession,
    RateLimiter, revoke_token, security,
)
from fastapi.security import HTTPAuthorizationCredentials

router = APIRouter()

# Sensitive endpoints get a tight limit; the rest of the auth surface relies
# on authentication. Window is fixed at 60s.
_auth_limit = RateLimiter(max_requests=10, window_seconds=60, scope="auth")


class RefreshRequest(BaseModel):
    refresh_token: str


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(_auth_limit)],
)
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


@router.post("/login", response_model=Token, dependencies=[Depends(_auth_limit)])
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


@router.post("/refresh", response_model=Token, dependencies=[Depends(_auth_limit)])
async def refresh_token(
    db: DbSession,
    body: Optional[RefreshRequest] = None,
    refresh_token: Optional[str] = None,
):
    """Refresh JWT tokens.

    Accepts the token in the request body (preferred). A `refresh_token`
    query param is still honoured for backward compatibility with older
    clients, but the body should be used going forward.
    """
    token = body.refresh_token if body else refresh_token
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_token(token)

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


@router.post("/logout", status_code=status.HTTP_200_OK)
async def logout(
    current_user: CurrentUser,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    body: Optional[RefreshRequest] = None,
):
    """Revoke the caller's access token (and refresh token if supplied)."""
    access_payload = decode_token(credentials.credentials) or {}
    if not revoke_token(access_payload.get("jti"), access_payload.get("exp")):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Token revocation is currently unavailable",
        )

    if body and body.refresh_token:
        refresh_payload = decode_token(body.refresh_token) or {}
        revoke_token(refresh_payload.get("jti"), refresh_payload.get("exp"))

    return {"message": "Logged out successfully"}


@router.post("/forgot-password", dependencies=[Depends(_auth_limit)])
async def forgot_password(request: ForgotPasswordRequest, db: DbSession):
    """Request a password reset link. Always returns 200 to avoid user enumeration."""
    result = await db.execute(select(User).where(User.email == request.email))
    user = result.scalar_one_or_none()

    if user and user.is_active:
        token = create_password_reset_token(user.id)
        reset_link = f"{settings.APP_FRONTEND_URL}/reset-password?token={token}"
        html_content = f"""
        <html>
        <body style="font-family: Arial, sans-serif;">
            <h2 style="color: #4472C4;">Reset your password</h2>
            <p>We received a request to reset your Inthezon password.
            Click the link below to choose a new one. This link expires in 30 minutes.</p>
            <p><a href="{reset_link}"
                style="display: inline-block; padding: 10px 18px; background-color: #4472C4;
                color: white; text-decoration: none; border-radius: 4px;">Reset password</a></p>
            <p style="color: #666; font-size: 12px;">
                If you didn't request this, you can safely ignore this email.
            </p>
        </body>
        </html>
        """
        service = NotificationService(settings.SENDGRID_API_KEY)
        await service.send_email(
            to_emails=[user.email],
            subject="Reset your Inthezon password",
            html_content=html_content,
            from_email=settings.SENDGRID_FROM_EMAIL,
        )

    return {"message": "If an account exists for that email, a reset link has been sent."}


@router.post("/reset-password")
async def reset_password(request: ResetPasswordRequest, db: DbSession):
    """Reset a password using a valid reset token."""
    payload = decode_token(request.token)

    if payload is None or payload.get("type") != "password_reset":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token"
        )

    user_id = payload.get("sub")
    result = await db.execute(select(User).where(User.id == UUID(user_id)))
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token"
        )

    user.hashed_password = get_password_hash(request.new_password)
    await db.flush()
    return {"message": "Password has been reset successfully"}


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


@router.get("/me/email-status", response_model=EmailDeliveryStatus)
async def get_email_delivery_status(_current_user: CurrentUser):
    """Report whether outbound email is deliverable, without sending anything."""
    if not settings.SENDGRID_API_KEY:
        return EmailDeliveryStatus(
            status="missing_credentials",
            from_email=settings.SENDGRID_FROM_EMAIL,
            detail="Invio email non configurato: chiave SendGrid mancante sul server.",
        )
    return EmailDeliveryStatus(
        status="configured",
        from_email=settings.SENDGRID_FROM_EMAIL,
        detail=(
            f"Invio email attivo tramite il mittente {settings.SENDGRID_FROM_EMAIL}. "
            "La consegna richiede che questo mittente sia verificato su SendGrid."
        ),
    )


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


@router.put("/organization", response_model=OrganizationResponse)
async def update_current_organization(
    org_in: OrganizationUpdate,
    current_user: CurrentUser,
    db: DbSession,
):
    """Update the current user's organization (name)."""
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

    org.name = org_in.name
    await db.flush()
    await db.refresh(org)

    return org


def _mask_value(value: str | None) -> str | None:
    """Mask a credential value, showing first 8 and last 3 chars."""
    if not value:
        return None
    if len(value) <= 12:
        return value[:3] + "***"
    return value[:8] + "***" + value[-3:]


def _build_api_keys_response(
    sp_api: dict | None,
    advertising_api: dict | None = None,
) -> OrganizationApiKeysResponse:
    """Build a masked response from stored Amazon API settings."""
    if not sp_api and not advertising_api:
        return OrganizationApiKeysResponse()

    client_id = None
    aws_access_key = None
    try:
        if sp_api and sp_api.get("client_id_enc"):
            client_id = _mask_value(decrypt_value(sp_api["client_id_enc"]))
    except Exception:
        client_id = "(decryption error)"
    try:
        if sp_api and sp_api.get("aws_access_key_enc"):
            aws_access_key = _mask_value(decrypt_value(sp_api["aws_access_key_enc"]))
    except Exception:
        aws_access_key = "(decryption error)"

    role_arn = None
    try:
        if sp_api and sp_api.get("role_arn_enc"):
            role_arn = decrypt_value(sp_api["role_arn_enc"])
    except Exception:
        role_arn = "(decryption error)"

    advertising_client_id = None
    try:
        if advertising_api and advertising_api.get("client_id_enc"):
            advertising_client_id = _mask_value(decrypt_value(advertising_api["client_id_enc"]))
    except Exception:
        advertising_client_id = "(decryption error)"

    return OrganizationApiKeysResponse(
        sp_api_client_id=client_id,
        sp_api_aws_access_key=aws_access_key,
        sp_api_role_arn=role_arn,
        advertising_client_id=advertising_client_id,
        has_client_secret=bool(sp_api and sp_api.get("client_secret_enc")),
        has_aws_secret_key=bool(sp_api and sp_api.get("aws_secret_key_enc")),
        has_advertising_client_secret=bool(
            advertising_api and advertising_api.get("client_secret_enc")
        ),
    )


@router.get("/organization/api-keys", response_model=OrganizationApiKeysResponse)
async def get_organization_api_keys(
    current_user: CurrentUser,
    organization: CurrentOrganization,
):
    """Get masked SP-API credentials for the organization."""
    settings = organization.settings or {}
    sp_api = settings.get("sp_api")
    advertising_api = settings.get("advertising_api")
    return _build_api_keys_response(sp_api, advertising_api)


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
    advertising_api = dict(current_settings.get("advertising_api", {}))

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
    if keys_in.advertising_client_id is not None:
        advertising_api["client_id_enc"] = encrypt_value(keys_in.advertising_client_id)
    if keys_in.advertising_client_secret is not None:
        advertising_api["client_secret_enc"] = encrypt_value(keys_in.advertising_client_secret)

    current_settings["sp_api"] = sp_api
    current_settings["advertising_api"] = advertising_api
    organization.settings = current_settings
    await db.flush()
    await db.refresh(organization)

    return _build_api_keys_response(sp_api, advertising_api)


@router.delete("/organization/api-keys", response_model=OrganizationApiKeysResponse)
async def delete_organization_api_keys(
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
):
    """Remove all saved SP-API credentials for the organization."""
    current_settings = dict(organization.settings or {})
    current_settings.pop("sp_api", None)
    current_settings.pop("advertising_api", None)
    organization.settings = current_settings
    await db.flush()
    await db.refresh(organization)

    return _build_api_keys_response(None, None)
