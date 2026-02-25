"""Amazon SP-API credential resolution."""
import logging

from app.config import settings
from app.core.security import decrypt_value
from app.core.exceptions import AmazonAPIError

logger = logging.getLogger(__name__)


def _get_org_sp_api_setting(organization, key: str) -> str | None:
    """Decrypt a single SP-API credential from organization settings."""
    if not organization:
        return None
    sp_api = (getattr(organization, "settings", None) or {}).get("sp_api")
    if not sp_api:
        return None
    enc_value = sp_api.get(key)
    if not enc_value:
        return None
    try:
        return decrypt_value(enc_value)
    except Exception:
        logger.warning(f"Failed to decrypt org setting {key}")
        return None


def resolve_credentials(account, organization=None) -> dict:
    """Resolve SP-API credentials for an account.

    Priority:
    1. Per-account encrypted refresh token
    2. Global sandbox refresh token from .env (fallback)

    For app credentials (client_id, client_secret, aws_*):
    1. Organization settings (encrypted JSONB)
    2. Global env vars (fallback)
    """
    refresh_token = None

    # Try per-account credentials first
    if account.sp_api_refresh_token_encrypted:
        try:
            refresh_token = decrypt_value(account.sp_api_refresh_token_encrypted)
            logger.info(f"Using per-account credentials for {account.account_name}")
        except Exception:
            logger.warning(
                f"Failed to decrypt per-account token for {account.account_name}, "
                "trying global fallback"
            )

    # Fallback to global sandbox credentials
    if not refresh_token and settings.AMAZON_SP_API_REFRESH_TOKEN:
        refresh_token = settings.AMAZON_SP_API_REFRESH_TOKEN
        logger.info(
            f"Using global sandbox credentials (fallback) for {account.account_name}"
        )

    if not refresh_token:
        raise AmazonAPIError(
            f"No SP-API refresh token available for account {account.account_name}. "
            "Set per-account credentials or AMAZON_SP_API_REFRESH_TOKEN in .env.",
            error_code="MISSING_CREDENTIALS",
        )

    # Resolve app credentials: org settings → global env vars
    client_id = (
        _get_org_sp_api_setting(organization, "client_id_enc")
        or settings.AMAZON_SP_API_CLIENT_ID
    )
    client_secret = (
        _get_org_sp_api_setting(organization, "client_secret_enc")
        or settings.AMAZON_SP_API_CLIENT_SECRET
    )

    credentials = {
        "refresh_token": refresh_token,
        "lwa_app_id": client_id,
        "lwa_client_secret": client_secret,
    }

    # AWS credentials: org settings → global env vars
    aws_access_key = (
        _get_org_sp_api_setting(organization, "aws_access_key_enc")
        or settings.AMAZON_SP_API_AWS_ACCESS_KEY
    )
    aws_secret_key = (
        _get_org_sp_api_setting(organization, "aws_secret_key_enc")
        or settings.AMAZON_SP_API_AWS_SECRET_KEY
    )
    role_arn = (
        _get_org_sp_api_setting(organization, "role_arn_enc")
        or settings.AMAZON_SP_API_ROLE_ARN
    )

    if aws_access_key:
        credentials["aws_access_key"] = aws_access_key
    if aws_secret_key:
        credentials["aws_secret_key"] = aws_secret_key
    if role_arn:
        credentials["role_arn"] = role_arn

    return credentials
