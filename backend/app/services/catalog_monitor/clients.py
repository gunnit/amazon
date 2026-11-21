"""SP-API client construction for the catalogue monitor (R1-R4)."""
from __future__ import annotations

from typing import Any, Callable, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.amazon.credentials import resolve_credentials
from app.core.amazon.sp_api_client import SPAPIClient, resolve_marketplace
from app.models.amazon_account import AmazonAccount
from app.models.user import Organization

ClientFactory = Callable[[AmazonAccount, Any], SPAPIClient]


def default_client_factory(account: AmazonAccount, organization: Any) -> SPAPIClient:
    credentials = resolve_credentials(account, organization)
    marketplace = resolve_marketplace(account.marketplace_country)
    return SPAPIClient(credentials, marketplace, account_type=account.account_type.value)


async def load_organization(db: AsyncSession, account: AmazonAccount) -> Optional[Organization]:
    result = await db.execute(
        select(Organization).where(Organization.id == account.organization_id)
    )
    return result.scalar_one_or_none()
