"""Amazon credential resolution helpers."""
from __future__ import annotations

import logging

from app.config import settings
from app.core.security import decrypt_value
from app.core.exceptions import AmazonAPIError
from app.core.amazon.advertising_client import resolve_ads_base_url

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


def _get_org_advertising_setting(organization, key: str) -> str | None:
    """Decrypt a single Advertising API credential from organization settings."""
    if not organization:
        return None
    advertising_api = (getattr(organization, "settings", None) or {}).get("advertising_api")
    if not advertising_api:
        return None
    enc_value = advertising_api.get(key)
    if not enc_value:
        return None
    try:
        return decrypt_value(enc_value)
    except Exception:
        logger.warning(f"Failed to decrypt org advertising setting {key}")
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


def resolve_advertising_credentials(account, organization=None) -> dict:
    """Resolve Advertising API credentials for an account."""
    refresh_token = None

    if getattr(account, "advertising_refresh_token_encrypted", None):
        try:
            refresh_token = decrypt_value(account.advertising_refresh_token_encrypted)
            logger.info(f"Using per-account advertising credentials for {account.account_name}")
        except Exception:
            logger.warning(
                f"Failed to decrypt advertising token for {account.account_name}"
            )

    if not refresh_token:
        raise AmazonAPIError(
            f"No Advertising refresh token available for account {account.account_name}",
            error_code="MISSING_ADVERTISING_CREDENTIALS",
        )

    profile_id = getattr(account, "advertising_profile_id", None) or settings.AMAZON_ADS_PROFILE_ID
    if not profile_id:
        raise AmazonAPIError(
            f"No Advertising profile ID configured for account {account.account_name}",
            error_code="MISSING_ADVERTISING_PROFILE",
        )

    client_id = (
        _get_org_advertising_setting(organization, "client_id_enc")
        or settings.AMAZON_ADS_CLIENT_ID
    )
    client_secret = (
        _get_org_advertising_setting(organization, "client_secret_enc")
        or settings.AMAZON_ADS_CLIENT_SECRET
    )

    if not client_id or not client_secret:
        raise AmazonAPIError(
            f"Missing Advertising client credentials for account {account.account_name}",
            error_code="MISSING_ADVERTISING_CREDENTIALS",
        )

    return {
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "profile_id": str(profile_id),
        "base_url": resolve_ads_base_url(account.marketplace_country),
    }
