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
    UserCreate, UserResponse, UserLogin, Token,
    OrganizationCreate, OrganizationResponse
)
from app.core.security import (
    verify_password, get_password_hash,
    create_access_token, create_refresh_token, decode_token
)
from app.api.deps import CurrentUser, DbSession

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
