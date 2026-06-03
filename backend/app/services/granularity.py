"""Resolve the natural time granularity of a set of Amazon accounts.

Vendor Central data is reported monthly (one settled row per month); Seller
Central data is daily. When both are mixed in a single view the series need to
be plotted on different cadences, so callers ask this helper which granularity
applies to the accounts in scope and surface it to the frontend.
"""
from enum import Enum
from typing import Iterable, List, Optional
from uuid import UUID

from sqlalchemy import select

from app.models.amazon_account import AccountType, AmazonAccount


class Granularity(str, Enum):
    DAILY = "daily"
    MONTHLY = "monthly"
    MIXED = "mixed"
    UNKNOWN = "unknown"


def granularity_for_account_types(account_types: Iterable[AccountType]) -> Granularity:
    """Resolve granularity from the account types already in hand."""
    has_seller = False
    has_vendor = False
    for account_type in account_types:
        if account_type == AccountType.VENDOR:
            has_vendor = True
        elif account_type == AccountType.SELLER:
            has_seller = True

    if has_seller and has_vendor:
        return Granularity.MIXED
    if has_vendor:
        return Granularity.MONTHLY
    if has_seller:
        return Granularity.DAILY
    return Granularity.UNKNOWN


async def resolve_granularity(
    db,
    organization_id: UUID,
    account_ids: Optional[List[UUID]] = None,
) -> Granularity:
    """Resolve granularity for the organization's accounts (optionally scoped).

    When ``account_ids`` is empty/None the whole organization is considered,
    matching how the analytics endpoints treat an unscoped request.
    """
    query = select(AmazonAccount.account_type).where(
        AmazonAccount.organization_id == organization_id
    )
    if account_ids:
        query = query.where(AmazonAccount.id.in_(account_ids))

    rows = (await db.execute(query)).scalars().all()
    return granularity_for_account_types(rows)
