"""Amazon account management endpoints."""
import logging
import secrets
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Union
from urllib.parse import quote, urlencode
from uuid import UUID
from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from jose import jwt as jose_jwt
from sqlalchemy import func, select

from app.api.deps import CurrentUser, CurrentOrganization, DbSession
from app.models.amazon_account import AmazonAccount, SyncStatus, AccountType
from app.models.product import Product
from app.models.sales_data import SalesData
from app.models.user import Organization
from app.schemas.account import (
    AmazonAccountCreate, AmazonAccountUpdate, AmazonAccountResponse,
    AccountStatusResponse, AccountSummary, AdvertisingProfilesRequest,
    AdvertisingProfileResponse, AdsConnectionState,
    AmazonOAuthStartRequest, AmazonOAuthStartResponse,
)
from app.core.security import decode_token, decrypt_value, encrypt_value
from app.core.exceptions import AmazonAPIError
from app.services.data_extraction import DAILY_TOTAL_ASIN, DataExtractionService
from app.services.sales_metrics import display_revenue_expr, display_units_expr

logger = logging.getLogger(__name__)

router = APIRouter()

# SP-API OAuth (Login with Amazon). All supported seller marketplaces share the
# unified European Seller Central; Vendor Central is per-country.
SELLER_CONSENT_HOST = "https://sellercentral-europe.amazon.com"
VENDOR_CONSENT_HOSTS = {
    "IT": "https://vendorcentral.amazon.it",
    "ES": "https://vendorcentral.amazon.es",
    "FR": "https://vendorcentral.amazon.fr",
    "DE": "https://vendorcentral.amazon.de",
    "UK": "https://vendorcentral.amazon.co.uk",
}
LWA_TOKEN_URL = "https://api.amazon.com/auth/o2/token"

ADS_PROFILE_SCAN_COUNTRIES = ("US", "IT", "JP")

ADS_AUTH_FAILURE_SYNC_CODES = {
    "MISSING_ADVERTISING_CLIENT_CREDENTIALS",
    "MISSING_ADVERTISING_REFRESH_TOKEN",
    "MISSING_ADVERTISING_PROFILE",
    "ADS_AUTH_FAILURE",
    "ADS_UNAUTHORIZED",          # persistent 401/403 from the Ads client
    "ADVERTISING_AUTH_FAILED",   # LWA/OAuth refresh failure
}


def _org_has_ads_client_credentials(organization) -> bool:
    """Return True if the org (or env fallback) has Ads client_id/client_secret configured."""
    from app.config import settings as app_settings

    advertising_api = (getattr(organization, "settings", None) or {}).get("advertising_api") or {}
    has_org_client_id = bool(advertising_api.get("client_id_enc"))
    has_org_client_secret = bool(advertising_api.get("client_secret_enc"))
    if has_org_client_id and has_org_client_secret:
        return True
    return bool(app_settings.AMAZON_ADS_CLIENT_ID and app_settings.AMAZON_ADS_CLIENT_SECRET)


def _resolve_ads_connection_state(
    account: AmazonAccount,
    organization=None,
) -> tuple[AdsConnectionState, Optional[str]]:
    """Resolve a structured Ads connection state for the UI."""
    has_client_creds = _org_has_ads_client_credentials(organization) if organization is not None else False
    if not has_client_creds:
        return (
            AdsConnectionState.MISSING_CLIENT_CREDENTIALS,
            "Organization Ads client_id/client_secret are not configured.",
        )
    if not account.advertising_refresh_token_encrypted:
        return (
            AdsConnectionState.MISSING_REFRESH_TOKEN,
            "Authorize this account in Amazon Ads to obtain a refresh token.",
        )
    if not account.advertising_profile_id:
        return (
            AdsConnectionState.MISSING_PROFILE,
            "Pick the Ads profile that matches this account's marketplace.",
        )
    sync_error_code = (account.sync_error_code or "").upper()
    if sync_error_code in ADS_AUTH_FAILURE_SYNC_CODES:
        return (
            AdsConnectionState.AUTH_FAILURE,
            account.sync_error_message or "Amazon rejected the latest Ads authorization.",
        )
    return AdsConnectionState.OK, None


def _account_to_response(account: AmazonAccount, organization=None) -> AmazonAccountResponse:
    """Convert ORM account to response with computed fields."""
    ads_state, ads_detail = _resolve_ads_connection_state(account, organization)
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
        has_ads_client_credentials=_org_has_ads_client_credentials(organization) if organization is not None else False,
        ads_connection_state=ads_state,
        ads_connection_detail=ads_detail,
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
        last_backfill_status=account.last_backfill_status,
        last_backfill_started_at=account.last_backfill_started_at,
        last_backfill_completed_at=account.last_backfill_completed_at,
        last_backfill_records=account.last_backfill_records,
        last_backfill_windows_skipped=account.last_backfill_windows_skipped,
        last_backfill_error=account.last_backfill_error,
        last_backfill_range_start=account.last_backfill_range_start,
        last_backfill_range_end=account.last_backfill_range_end,
    )


def _get_org_advertising_setting(organization, key: str) -> Optional[str]:
    advertising_api = (getattr(organization, "settings", None) or {}).get("advertising_api")
    if not advertising_api:
        return None
    enc_value = advertising_api.get(key)
    if not enc_value:
        return None
    try:
        return decrypt_value(enc_value)
    except Exception:
        return None


def _normalize_ads_profile(profile: dict) -> AdvertisingProfileResponse:
    account_info = profile.get("accountInfo") or {}
    country_code = (
        profile.get("countryCode")
        or profile.get("country_code")
        or account_info.get("countryCode")
        or account_info.get("country_code")
    )
    account_name = (
        account_info.get("name")
        or account_info.get("accountName")
        or profile.get("accountName")
        or profile.get("name")
    )
    account_type = (
        account_info.get("type")
        or account_info.get("accountType")
        or profile.get("accountType")
        or profile.get("type")
    )
    marketplace_id = (
        profile.get("marketplaceId")
        or profile.get("marketplace_id")
        or account_info.get("marketplaceId")
        or account_info.get("marketplace_id")
    )
    if not marketplace_id and country_code:
        from app.core.amazon.advertising_client import ADS_MARKETPLACE_BY_COUNTRY

        marketplace_id = ADS_MARKETPLACE_BY_COUNTRY.get(str(country_code).upper())

    return AdvertisingProfileResponse(
        profile_id=str(profile.get("profileId") or profile.get("profile_id") or profile.get("id")),
        account_name=account_name,
        country_code=str(country_code).upper() if country_code else None,
        marketplace_id=marketplace_id,
        account_type=str(account_type).lower() if account_type else None,
        currency=profile.get("currencyCode") or profile.get("currency"),
        timezone=profile.get("timezone"),
    )


async def _load_account_metrics(
    db: DbSession,
    account_ids: List[UUID],
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> Dict[UUID, Dict[str, Union[float, int]]]:
    """Load per-account metrics used by dashboard drill-down cards.

    When a date range is supplied the sales window matches it; otherwise it
    defaults to the trailing 30 days used by the Accounts page snapshot.
    """
    if not account_ids:
        return {}

    period_end = end_date or date.today()
    period_start = start_date or (period_end - timedelta(days=29))

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
                func.sum(display_revenue_expr()).label("total_sales_30d"),
                func.sum(display_units_expr()).label("total_units_30d"),
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
    return [_account_to_response(a, organization) for a in result.scalars().all()]


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

    # A freshly connected account has no data yet. Kick off an initial sync plus
    # a historical sales backfill in the background so dashboards and forecasts
    # are populated without the user triggering anything manually. The row must
    # be committed first: the background thread opens its own DB connection and
    # would not see an uncommitted account (same pattern as trigger_sync).
    if account.sp_api_refresh_token_encrypted or account.advertising_refresh_token_encrypted:
        account.sync_status = SyncStatus.SYNCING
        await db.commit()
        await db.refresh(account)
        from app.services.extraction_runner import initial_sync_in_thread
        initial_sync_in_thread(account.id)

    return _account_to_response(account, organization)


def _resolve_sp_api_app_id(organization) -> Optional[str]:
    """SP-API solution/application id: org settings → env fallback."""
    from app.config import settings as app_settings
    from app.core.amazon.credentials import _get_org_sp_api_setting

    return (
        _get_org_sp_api_setting(organization, "app_id_enc")
        or app_settings.AMAZON_SP_API_APP_ID
    )


def _oauth_redirect_uri() -> str:
    """Must exactly match an OAuth Redirect URI registered on the SP-API app."""
    from app.config import settings as app_settings

    return f"{app_settings.APP_API_URL.rstrip('/')}/api/v1/accounts/oauth/callback"


@router.post("/oauth/start", response_model=AmazonOAuthStartResponse)
async def start_amazon_oauth(
    oauth_in: AmazonOAuthStartRequest,
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
):
    """Build the Amazon consent URL the browser should be redirected to.

    The signed state token carries the org/user and the account parameters so
    the unauthenticated callback can finish the connection safely.
    """
    from app.config import settings as app_settings

    app_id = _resolve_sp_api_app_id(organization)
    if not app_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="SP-API application id is not configured (AMAZON_SP_API_APP_ID).",
        )

    if oauth_in.account_id:
        result = await db.execute(
            select(AmazonAccount).where(
                AmazonAccount.id == oauth_in.account_id,
                AmazonAccount.organization_id == organization.id,
            )
        )
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")

    if oauth_in.account_type.value == "vendor":
        consent_host = VENDOR_CONSENT_HOSTS.get(oauth_in.marketplace_country.upper())
        if not consent_host:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Vendor OAuth is not supported for marketplace {oauth_in.marketplace_country}.",
            )
    else:
        consent_host = SELLER_CONSENT_HOST

    state = jose_jwt.encode(
        {
            "type": "amazon_oauth",
            "org": str(organization.id),
            "sub": str(current_user.id),
            "account_id": str(oauth_in.account_id) if oauth_in.account_id else None,
            "account_name": oauth_in.account_name,
            "account_type": oauth_in.account_type.value,
            "marketplace_id": oauth_in.marketplace_id,
            "marketplace_country": oauth_in.marketplace_country,
            "exp": datetime.utcnow() + timedelta(minutes=30),
            "jti": secrets.token_urlsafe(8),
        },
        app_settings.JWT_SECRET_KEY,
        algorithm=app_settings.JWT_ALGORITHM,
    )

    # version=beta is required while the SP-API app is in Draft status.
    consent_url = f"{consent_host}/apps/authorize/consent?" + urlencode(
        {"application_id": app_id, "state": state, "version": "beta"}
    )
    return AmazonOAuthStartResponse(consent_url=consent_url)


@router.get("/oauth/callback")
async def amazon_oauth_callback(
    db: DbSession,
    state: str = Query(...),
    spapi_oauth_code: Optional[str] = Query(default=None),
    selling_partner_id: Optional[str] = Query(default=None),
    error: Optional[str] = Query(default=None),
):
    """LWA redirect target: exchange the oauth code for a refresh token.

    Unauthenticated by design — Amazon redirects the user's browser here; the
    signed `state` issued by /oauth/start is what ties the request to an
    org/user. Always redirects back to the frontend accounts page.
    """
    from app.config import settings as app_settings
    from app.core.amazon.credentials import _get_org_sp_api_setting

    frontend = app_settings.APP_FRONTEND_URL.rstrip("/")

    def fail(reason: str) -> RedirectResponse:
        return RedirectResponse(f"{frontend}/accounts?amazon_status=error&reason={quote(reason)}")

    payload = decode_token(state)
    if not payload or payload.get("type") != "amazon_oauth":
        return fail("invalid_state")
    if error or not spapi_oauth_code:
        return fail(error or "missing_code")

    org_result = await db.execute(
        select(Organization).where(Organization.id == UUID(payload["org"]))
    )
    org = org_result.scalar_one_or_none()
    if not org:
        return fail("organization_not_found")

    client_id = (
        _get_org_sp_api_setting(org, "client_id_enc")
        or app_settings.AMAZON_SP_API_CLIENT_ID
    )
    client_secret = (
        _get_org_sp_api_setting(org, "client_secret_enc")
        or app_settings.AMAZON_SP_API_CLIENT_SECRET
    )
    if not client_id or not client_secret:
        return fail("missing_client_credentials")

    import httpx

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            LWA_TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": spapi_oauth_code.strip(),
                "redirect_uri": _oauth_redirect_uri(),
                "client_id": client_id,
                "client_secret": client_secret,
            },
        )
    if resp.status_code != 200:
        logger.warning(
            "Amazon OAuth code exchange failed: %s %s", resp.status_code, resp.text[:300]
        )
        return fail("token_exchange_failed")
    refresh_token = resp.json().get("refresh_token")
    if not refresh_token:
        return fail("no_refresh_token")

    account = None
    is_new = True
    if payload.get("account_id"):
        result = await db.execute(
            select(AmazonAccount).where(
                AmazonAccount.id == UUID(payload["account_id"]),
                AmazonAccount.organization_id == org.id,
            )
        )
        account = result.scalar_one_or_none()
        if not account:
            return fail("account_not_found")
        is_new = False

    if account is None:
        account = AmazonAccount(
            organization_id=org.id,
            account_name=payload.get("account_name")
            or (f"Amazon {selling_partner_id}" if selling_partner_id else "Amazon account"),
            account_type=AccountType(payload["account_type"]),
            marketplace_id=payload["marketplace_id"],
            marketplace_country=payload["marketplace_country"],
        )
        db.add(account)

    account.sp_api_refresh_token_encrypted = encrypt_value(refresh_token)
    if selling_partner_id:
        account.seller_id = selling_partner_id
    account.sync_status = SyncStatus.SYNCING
    account.sync_error_message = None
    account.sync_error_code = None
    account.sync_error_kind = None
    await db.commit()
    await db.refresh(account)

    # New accounts get the first-connect sync + historical backfill; existing
    # accounts only need a fresh sync with the re-authorized token.
    if is_new:
        from app.services.extraction_runner import initial_sync_in_thread

        initial_sync_in_thread(account.id)
    else:
        from app.services.extraction_runner import sync_account_in_thread

        sync_account_in_thread(account.id)

    return RedirectResponse(
        f"{frontend}/accounts?amazon_status=connected&account={quote(account.account_name)}"
    )


@router.get("/summary", response_model=AccountSummary)
async def get_accounts_summary(
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
    start_date: Optional[date] = Query(default=None),
    end_date: Optional[date] = Query(default=None),
):
    """Get summary of all accounts with status."""
    result = await db.execute(
        select(AmazonAccount)
        .where(AmazonAccount.organization_id == organization.id)
    )
    accounts = result.scalars().all()
    account_metrics = await _load_account_metrics(
        db, [account.id for account in accounts], start_date, end_date
    )

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


@router.post("/advertising/profiles", response_model=List[AdvertisingProfileResponse])
async def list_advertising_profiles(
    profiles_in: AdvertisingProfilesRequest,
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
):
    """List Amazon Ads profiles available to an Ads authorization."""
    refresh_token = profiles_in.refresh_token

    if profiles_in.account_id:
        result = await db.execute(
            select(AmazonAccount).where(
                AmazonAccount.id == profiles_in.account_id,
                AmazonAccount.organization_id == organization.id,
            )
        )
        account = result.scalar_one_or_none()
        if not account:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
        if not refresh_token and account.advertising_refresh_token_encrypted:
            try:
                refresh_token = decrypt_value(account.advertising_refresh_token_encrypted)
            except Exception as exc:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Could not decrypt Advertising refresh token for this account",
                ) from exc

    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide an Advertising refresh token or an account with Ads credentials",
        )

    from app.config import settings
    from app.core.amazon.advertising_client import AdvertisingAPIClient

    client_id = (
        profiles_in.client_id
        or _get_org_advertising_setting(organization, "client_id_enc")
        or settings.AMAZON_ADS_CLIENT_ID
    )
    client_secret = (
        profiles_in.client_secret
        or _get_org_advertising_setting(organization, "client_secret_enc")
        or settings.AMAZON_ADS_CLIENT_SECRET
    )
    if not client_id or not client_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Advertising client_id and client_secret are required to list profiles",
        )

    countries = [profiles_in.marketplace_country.upper()] if profiles_in.marketplace_country else list(ADS_PROFILE_SCAN_COUNTRIES)
    profiles_by_id: Dict[str, AdvertisingProfileResponse] = {}
    errors: List[str] = []

    for country in countries:
        client = AdvertisingAPIClient(
            client_id=client_id,
            client_secret=client_secret,
            refresh_token=refresh_token,
            marketplace_country=country,
        )
        try:
            for profile in client.list_profiles():
                normalized = _normalize_ads_profile(profile)
                if normalized.profile_id and normalized.profile_id != "None":
                    profiles_by_id[normalized.profile_id] = normalized
        except AmazonAPIError as exc:
            errors.append(f"{country}: {exc.message}")
        finally:
            client.close()

    if not profiles_by_id and errors:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not list Advertising profiles. " + " | ".join(errors),
        )

    return list(profiles_by_id.values())


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

    return _account_to_response(account, organization)


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
    if account_in.account_type is not None:
        account.account_type = AccountType(account_in.account_type)
    if account_in.marketplace_id is not None:
        account.marketplace_id = account_in.marketplace_id
    if account_in.marketplace_country is not None:
        account.marketplace_country = account_in.marketplace_country
    if account_in.is_active is not None:
        account.is_active = account_in.is_active
    token_newly_connected = False
    if account_in.refresh_token is not None:
        token_newly_connected = not account.sp_api_refresh_token_encrypted
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

    # An account created without SP-API credentials skips the initial
    # sync/backfill at creation time. When the refresh token is connected later
    # (e.g. the client completes the Login-with-Amazon authorization afterwards)
    # kick off the same full sync + historical backfill so the account
    # auto-populates without a manual trigger. Only fires if no backfill has
    # ever run, so editing other fields never restarts one.
    if token_newly_connected and account.last_backfill_status is None:
        account.sync_status = SyncStatus.SYNCING
        await db.commit()
        await db.refresh(account)
        from app.services.extraction_runner import initial_sync_in_thread
        initial_sync_in_thread(account.id)

    return _account_to_response(account, organization)


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


@router.post("/{account_id}/backfill", response_model=AccountStatusResponse)
async def trigger_backfill(
    account_id: UUID,
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
    months: int = Query(default=24, ge=1, le=24),
):
    """Re-sync an account and backfill historical sales (up to 24 months).

    For accounts connected before auto-backfill existed, or whose history is too
    short for a reliable forecast. Runs in the background; poll account status."""
    result = await db.execute(
        select(AmazonAccount).where(
            AmazonAccount.id == account_id,
            AmazonAccount.organization_id == organization.id,
        )
    )
    account = result.scalar_one_or_none()

    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account not found"
        )

    account.sync_status = SyncStatus.SYNCING
    account.sync_error_message = None
    account.sync_error_code = None
    account.sync_error_kind = None
    await db.commit()
    await db.refresh(account)

    from app.services.extraction_runner import initial_sync_in_thread
    initial_sync_in_thread(account_id, backfill_months=months)

    return _account_to_status_response(account)


@router.post("/backfill-all", response_model=List[AccountStatusResponse])
async def trigger_backfill_all(
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
    months: int = Query(default=24, ge=1, le=24),
):
    """Re-sync + backfill every active connected account in the organization.

    Brings accounts connected before auto-backfill existed up to the maximum
    Amazon history. Accounts are processed sequentially in the background to
    respect Reports API quotas; poll /accounts/summary for per-account
    last_backfill_* status."""
    result = await db.execute(
        select(AmazonAccount).where(
            AmazonAccount.organization_id == organization.id,
            AmazonAccount.is_active.is_(True),
        )
    )
    accounts = [
        a for a in result.scalars().all()
        if a.sp_api_refresh_token_encrypted or a.advertising_refresh_token_encrypted
    ]
    if not accounts:
        return []

    for account in accounts:
        account.sync_status = SyncStatus.SYNCING
        account.sync_error_message = None
        account.sync_error_code = None
        account.sync_error_kind = None
    await db.commit()

    from app.services.extraction_runner import initial_sync_accounts_in_thread
    initial_sync_accounts_in_thread([a.id for a in accounts], backfill_months=months)

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
