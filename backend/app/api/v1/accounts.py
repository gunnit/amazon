"""Amazon account management endpoints."""
from datetime import date, timedelta
from typing import Dict, List, Union
from uuid import UUID
from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select

from app.api.deps import CurrentUser, CurrentOrganization, DbSession
from app.models.amazon_account import AmazonAccount, SyncStatus, AccountType
from app.models.product import Product
from app.models.sales_data import SalesData
from app.schemas.account import (
    AmazonAccountCreate, AmazonAccountUpdate, AmazonAccountResponse,
    AccountStatusResponse, AccountSummary
)
from app.core.security import encrypt_value
from app.core.exceptions import AmazonAPIError
from app.services.data_extraction import DAILY_TOTAL_ASIN, DataExtractionService

router = APIRouter()


def _account_to_response(account: AmazonAccount) -> AmazonAccountResponse:
    """Convert ORM account to response with computed fields."""
    return AmazonAccountResponse(
        id=account.id,
        organization_id=account.organization_id,
        account_name=account.account_name,
        account_type=account.account_type,
        marketplace_id=account.marketplace_id,
        marketplace_country=account.marketplace_country,
        advertising_profile_id=account.advertising_profile_id,
        is_active=account.is_active,
        last_sync_at=account.last_sync_at,
        sync_status=account.sync_status,
        sync_error_message=account.sync_error_message,
        last_sync_started_at=account.last_sync_started_at,
        last_sync_succeeded_at=account.last_sync_succeeded_at,
        last_sync_failed_at=account.last_sync_failed_at,
        last_sync_attempt_at=account.last_sync_attempt_at,
        last_sync_heartbeat_at=account.last_sync_heartbeat_at,
        sync_error_code=account.sync_error_code,
        sync_error_kind=account.sync_error_kind,
        has_refresh_token=bool(account.sp_api_refresh_token_encrypted),
        has_advertising_refresh_token=bool(account.advertising_refresh_token_encrypted),
        created_at=account.created_at,
        updated_at=account.updated_at,
    )


def _account_to_status_response(account: AmazonAccount) -> AccountStatusResponse:
    """Convert ORM account to status response."""
    return AccountStatusResponse(
        id=account.id,
        account_name=account.account_name,
        marketplace_country=account.marketplace_country,
        sync_status=account.sync_status,
        last_sync_at=account.last_sync_at,
        sync_error_message=account.sync_error_message,
        last_sync_started_at=account.last_sync_started_at,
        last_sync_succeeded_at=account.last_sync_succeeded_at,
        last_sync_failed_at=account.last_sync_failed_at,
        last_sync_attempt_at=account.last_sync_attempt_at,
        last_sync_heartbeat_at=account.last_sync_heartbeat_at,
        sync_error_code=account.sync_error_code,
        sync_error_kind=account.sync_error_kind,
    )


async def _load_account_metrics(
    db: DbSession,
    account_ids: List[UUID],
) -> Dict[UUID, Dict[str, Union[float, int]]]:
    """Load per-account metrics used by dashboard drill-down cards."""
    if not account_ids:
        return {}

    period_end = date.today()
    period_start = period_end - timedelta(days=29)

    metrics: Dict[UUID, Dict[str, Union[float, int]]] = {
        account_id: {
            "total_sales_30d": 0.0,
            "total_units_30d": 0,
            "active_asins": 0,
        }
        for account_id in account_ids
    }

    sales_rows = (
        await db.execute(
            select(
                SalesData.account_id,
                func.sum(SalesData.ordered_product_sales).label("total_sales_30d"),
                func.sum(SalesData.units_ordered).label("total_units_30d"),
            )
            .where(
                SalesData.account_id.in_(account_ids),
                SalesData.asin == DAILY_TOTAL_ASIN,
                SalesData.date >= period_start,
                SalesData.date <= period_end,
            )
            .group_by(SalesData.account_id)
        )
    ).all()

    for row in sales_rows:
        metrics[row.account_id]["total_sales_30d"] = float(row.total_sales_30d or 0)
        metrics[row.account_id]["total_units_30d"] = int(row.total_units_30d or 0)

    product_rows = (
        await db.execute(
            select(
                Product.account_id,
                func.count(func.distinct(Product.asin)).label("active_asins"),
            )
            .where(
                Product.account_id.in_(account_ids),
                Product.is_active.is_(True),
            )
            .group_by(Product.account_id)
        )
    ).all()

    for row in product_rows:
        metrics[row.account_id]["active_asins"] = int(row.active_asins or 0)

    recent_sales_asin_rows = (
        await db.execute(
            select(
                SalesData.account_id,
                func.count(func.distinct(SalesData.asin)).label("recent_active_asins"),
            )
            .where(
                SalesData.account_id.in_(account_ids),
                SalesData.asin != DAILY_TOTAL_ASIN,
                SalesData.date >= period_start,
                SalesData.date <= period_end,
            )
            .group_by(SalesData.account_id)
        )
    ).all()

    for row in recent_sales_asin_rows:
        if not metrics[row.account_id]["active_asins"]:
            metrics[row.account_id]["active_asins"] = int(row.recent_active_asins or 0)

    return metrics


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
    return [_account_to_response(a) for a in result.scalars().all()]


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
    if account_in.advertising_profile_id:
        account.advertising_profile_id = account_in.advertising_profile_id
    if account_in.advertising_refresh_token:
        account.advertising_refresh_token_encrypted = encrypt_value(account_in.advertising_refresh_token)
    if account_in.login_email:
        account.login_email_encrypted = encrypt_value(account_in.login_email)
    if account_in.login_password:
        account.login_password_encrypted = encrypt_value(account_in.login_password)

    db.add(account)
    await db.flush()
    await db.refresh(account)

    return _account_to_response(account)


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
    account_metrics = await _load_account_metrics(db, [account.id for account in accounts])

    account_statuses = []
    for acc in accounts:
        status_response = _account_to_status_response(acc)
        metrics = account_metrics.get(acc.id)
        if metrics:
            status_response.total_sales_30d = float(metrics["total_sales_30d"])
            status_response.total_units_30d = int(metrics["total_units_30d"])
            status_response.active_asins = int(metrics["active_asins"])
        account_statuses.append(status_response)

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

    return _account_to_response(account)


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
    if account_in.advertising_profile_id is not None:
        account.advertising_profile_id = account_in.advertising_profile_id
    if account_in.advertising_refresh_token is not None:
        account.advertising_refresh_token_encrypted = encrypt_value(account_in.advertising_refresh_token)
    if account_in.login_email is not None:
        account.login_email_encrypted = encrypt_value(account_in.login_email)
    if account_in.login_password is not None:
        account.login_password_encrypted = encrypt_value(account_in.login_password)

    await db.flush()
    await db.refresh(account)

    return _account_to_response(account)


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

    try:
        from app.core.amazon.credentials import resolve_credentials
        from app.core.amazon.sp_api_client import SPAPIClient, resolve_marketplace

        credentials = resolve_credentials(account, organization)
        marketplace = resolve_marketplace(account.marketplace_country)
        client = SPAPIClient(credentials, marketplace, account_type=account.account_type.value)
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
    account.sync_error_code = None
    account.sync_error_kind = None
    await db.commit()
    await db.refresh(account)

    # Run sync in-process (no Redis/Celery on free tier).
    from app.services.extraction_runner import sync_account_in_thread
    sync_account_in_thread(account_id)

    return _account_to_status_response(account)


@router.post("/sync-all", response_model=List[AccountStatusResponse])
async def trigger_sync_all(
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
):
    """Trigger sync for every active account in the organization."""
    result = await db.execute(
        select(AmazonAccount).where(
            AmazonAccount.organization_id == organization.id,
            AmazonAccount.is_active.is_(True),
        )
    )
    accounts = result.scalars().all()
    if not accounts:
        return []

    for account in accounts:
        account.sync_status = SyncStatus.SYNCING
        account.sync_error_message = None
        account.sync_error_code = None
        account.sync_error_kind = None
    await db.commit()

    from app.services.extraction_runner import sync_accounts_in_thread
    sync_accounts_in_thread([a.id for a in accounts])

    return [_account_to_status_response(a) for a in accounts]


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

    return _account_to_status_response(account)
