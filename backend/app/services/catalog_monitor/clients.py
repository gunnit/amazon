"""SP-API client construction for the catalogue monitor (R1-R4).

Outside production, ``DEV_FIXTURE_AMAZON_DIR`` swaps SP-API for a ``FixtureClient``
that reads and writes JSON files, so the monitor runs locally without Amazon.
"""
from __future__ import annotations

from typing import Any, Callable, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.amazon.credentials import resolve_credentials
from app.core.amazon.sp_api_client import SPAPIClient, resolve_marketplace
from app.models.amazon_account import AmazonAccount
from app.models.user import Organization
from app.services.catalog_monitor.fixture_client import FixtureClient, active_fixture_dir

ClientFactory = Callable[[AmazonAccount, Any], SPAPIClient]


def default_client_factory(account: AmazonAccount, organization: Any) -> SPAPIClient:
    fixture_dir = active_fixture_dir()
    if fixture_dir:
        return FixtureClient(  # type: ignore[return-value] - the same calls, from local files
            fixture_dir, account.marketplace_id, account_type=account.account_type.value
        )
    credentials = resolve_credentials(account, organization)
    marketplace = resolve_marketplace(account.marketplace_country)
    return SPAPIClient(credentials, marketplace, account_type=account.account_type.value)


async def load_organization(db: AsyncSession, account: AmazonAccount) -> Optional[Organization]:
    result = await db.execute(
        select(Organization).where(Organization.id == account.organization_id)
    )
    return result.scalar_one_or_none()
