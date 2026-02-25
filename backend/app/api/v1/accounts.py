"""Amazon account management endpoints."""
from typing import List
from uuid import UUID
from fastapi import APIRouter, HTTPException, status, BackgroundTasks
from sqlalchemy import select

from app.api.deps import CurrentUser, CurrentOrganization, DbSession
from app.models.amazon_account import AmazonAccount, SyncStatus, AccountType
from app.schemas.account import (
    AmazonAccountCreate, AmazonAccountUpdate, AmazonAccountResponse,
    AccountStatusResponse, AccountSummary
)
from app.config import settings
from app.core.security import encrypt_value, decrypt_value
from app.core.exceptions import AmazonAPIError
from app.services.data_extraction import DataExtractionService

router = APIRouter()


@router.get("", response_model=List[AmazonAccountResponse])
async def list_accounts(
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
):
    """List all connected Amazon accounts."""
    result = await db.execute(
        select(AmazonAccount)
        .where(AmazonAccount.organization_id == organization.id)
        .order_by(AmazonAccount.created_at.desc())
    )
    return result.scalars().all()


@router.post("", response_model=AmazonAccountResponse, status_code=status.HTTP_201_CREATED)
async def create_account(
    account_in: AmazonAccountCreate,
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
):
    """Connect a new Amazon account."""
    account = AmazonAccount(
        organization_id=organization.id,
        account_name=account_in.account_name,
        account_type=AccountType(account_in.account_type),
        marketplace_id=account_in.marketplace_id,
        marketplace_country=account_in.marketplace_country,
    )

    # Encrypt credentials if provided
    if account_in.refresh_token:
        account.sp_api_refresh_token_encrypted = encrypt_value(account_in.refresh_token)
    if account_in.login_email:
        account.login_email_encrypted = encrypt_value(account_in.login_email)
    if account_in.login_password:
        account.login_password_encrypted = encrypt_value(account_in.login_password)

    db.add(account)
    await db.flush()
    await db.refresh(account)

    return account


@router.get("/summary", response_model=AccountSummary)
async def get_accounts_summary(
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
):
    """Get summary of all accounts with status."""
    result = await db.execute(
        select(AmazonAccount)
        .where(AmazonAccount.organization_id == organization.id)
    )
    accounts = result.scalars().all()

    account_statuses = []
    for acc in accounts:
        account_statuses.append(AccountStatusResponse(
            id=acc.id,
            account_name=acc.account_name,
            marketplace_country=acc.marketplace_country,
            sync_status=acc.sync_status,
            last_sync_at=acc.last_sync_at,
            sync_error_message=acc.sync_error_message,
            total_sales_30d=0,  # Will be populated from aggregated data
            total_units_30d=0,
            active_asins=0,
        ))

    return AccountSummary(
        total_accounts=len(accounts),
        active_accounts=sum(1 for a in accounts if a.is_active),
        syncing_accounts=sum(1 for a in accounts if a.sync_status == SyncStatus.SYNCING),
        error_accounts=sum(1 for a in accounts if a.sync_status == SyncStatus.ERROR),
        accounts=account_statuses,
    )


@router.get("/{account_id}", response_model=AmazonAccountResponse)
async def get_account(
    account_id: UUID,
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
):
    """Get account details."""
    result = await db.execute(
        select(AmazonAccount)
        .where(
            AmazonAccount.id == account_id,
            AmazonAccount.organization_id == organization.id
        )
    )
    account = result.scalar_one_or_none()

    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account not found"
        )

    return account


@router.put("/{account_id}", response_model=AmazonAccountResponse)
async def update_account(
    account_id: UUID,
    account_in: AmazonAccountUpdate,
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
):
    """Update account settings."""
    result = await db.execute(
        select(AmazonAccount)
        .where(
            AmazonAccount.id == account_id,
            AmazonAccount.organization_id == organization.id
        )
    )
    account = result.scalar_one_or_none()

    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account not found"
        )

    # Update fields
    if account_in.account_name is not None:
        account.account_name = account_in.account_name
    if account_in.is_active is not None:
        account.is_active = account_in.is_active
    if account_in.refresh_token is not None:
        account.sp_api_refresh_token_encrypted = encrypt_value(account_in.refresh_token)
    if account_in.login_email is not None:
        account.login_email_encrypted = encrypt_value(account_in.login_email)
    if account_in.login_password is not None:
        account.login_password_encrypted = encrypt_value(account_in.login_password)

    await db.flush()
    await db.refresh(account)

    return account


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(
    account_id: UUID,
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
):
    """Disconnect/delete an account."""
    result = await db.execute(
        select(AmazonAccount)
        .where(
            AmazonAccount.id == account_id,
            AmazonAccount.organization_id == organization.id
        )
    )
    account = result.scalar_one_or_none()

    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account not found"
        )

    await db.delete(account)


@router.post("/{account_id}/test-connection")
async def test_connection(
    account_id: UUID,
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
):
    """Test SP-API connection for an account."""
    result = await db.execute(
        select(AmazonAccount)
        .where(
            AmazonAccount.id == account_id,
            AmazonAccount.organization_id == organization.id
        )
    )
    account = result.scalar_one_or_none()

    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account not found"
        )

    if settings.USE_MOCK_DATA:
        return {
            "status": "ok",
            "mode": "mock",
            "marketplace": account.marketplace_country,
            "message": "Mock mode enabled - connection test skipped",
        }

    try:
        from app.core.amazon.credentials import resolve_credentials
        from app.core.amazon.sp_api_client import SPAPIClient, resolve_marketplace

        credentials = resolve_credentials(account, organization)
        marketplace = resolve_marketplace(account.marketplace_country)
        client = SPAPIClient(credentials, marketplace)
        smoke_result = client.smoke_test()
        return {
            "status": "ok",
            "mode": "live",
            **smoke_result,
        }
    except AmazonAPIError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Connection test failed: {e.message}",
        )


@router.post("/{account_id}/sync", response_model=AccountStatusResponse)
async def trigger_sync(
    account_id: UUID,
    background_tasks: BackgroundTasks,
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
):
    """Trigger manual data sync for an account."""
    result = await db.execute(
        select(AmazonAccount)
        .where(
            AmazonAccount.id == account_id,
            AmazonAccount.organization_id == organization.id
        )
    )
    account = result.scalar_one_or_none()

    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account not found"
        )

    # Update status to syncing
    account.sync_status = SyncStatus.SYNCING
    account.sync_error_message = None
    await db.flush()

    # Queue background sync task via Celery
    from workers.tasks.extraction import sync_account as sync_account_task
    sync_account_task.delay(str(account_id))

    return AccountStatusResponse(
        id=account.id,
        account_name=account.account_name,
        marketplace_country=account.marketplace_country,
        sync_status=account.sync_status,
        last_sync_at=account.last_sync_at,
        sync_error_message=account.sync_error_message,
    )


@router.get("/{account_id}/status", response_model=AccountStatusResponse)
async def get_account_status(
    account_id: UUID,
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
):
    """Get sync status for an account."""
    result = await db.execute(
        select(AmazonAccount)
        .where(
            AmazonAccount.id == account_id,
            AmazonAccount.organization_id == organization.id
        )
    )
    account = result.scalar_one_or_none()

    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account not found"
        )

    return AccountStatusResponse(
        id=account.id,
        account_name=account.account_name,
        marketplace_country=account.marketplace_country,
        sync_status=account.sync_status,
        last_sync_at=account.last_sync_at,
        sync_error_message=account.sync_error_message,
    )
