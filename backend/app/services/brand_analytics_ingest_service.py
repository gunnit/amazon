"""Weekly Brand Analytics search-terms ingestion.

Stores, per account and reporting week, the search terms whose top-3 clicked
ASINs include one of the account's own ASINs. Requires the seller to be Brand
Registry enrolled; permission failures are logged and skipped (the capability
matrix in brand_analysis_capabilities tracks availability).
"""
from __future__ import annotations

from datetime import date, timedelta
import logging
from typing import Optional, Set, Tuple

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.amazon_account import AccountType, AmazonAccount
from app.models.brand_search_term import BrandSearchTerm
from app.models.product import Product

logger = logging.getLogger(__name__)

# Amazon Brand Analytics weeks run Sunday..Saturday; the weekly report is
# published a few days after the week closes.
BA_WEEK_SETTLE_LAG_DAYS = 3


def resolve_last_settled_ba_week(today: Optional[date] = None) -> Tuple[date, date]:
    """Most recent Sunday..Saturday week that closed at least
    BA_WEEK_SETTLE_LAG_DAYS ago."""
    today = today or date.today()
    days_since_saturday = (today.weekday() - 5) % 7
    week_end = today - timedelta(days=days_since_saturday or 7)
    if (today - week_end).days < BA_WEEK_SETTLE_LAG_DAYS:
        week_end -= timedelta(days=7)
    return week_end - timedelta(days=6), week_end


class BrandAnalyticsIngestService:
    """Pull and persist the weekly search-terms signal for one account."""

    def __init__(self, db: AsyncSession):
        self.db = db

    def _create_sp_api_client(self, account: AmazonAccount, organization=None):
        from app.core.amazon.credentials import resolve_credentials
        from app.core.amazon.sp_api_client import SPAPIClient, resolve_marketplace

        credentials = resolve_credentials(account, organization)
        marketplace = resolve_marketplace(account.marketplace_country)
        return SPAPIClient(credentials, marketplace, account_type=account.account_type.value)

    async def _own_asins(self, account: AmazonAccount) -> Set[str]:
        result = await self.db.execute(
            select(Product.asin).where(Product.account_id == account.id)
        )
        return {row[0] for row in result.all() if row[0]}

    async def _upsert_term(self, values: dict) -> None:
        stmt = pg_insert(BrandSearchTerm).values(**values)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_brand_search_terms_account_week_term",
            set_={
                "week_end": stmt.excluded.week_end,
                "search_frequency_rank": stmt.excluded.search_frequency_rank,
                "department": stmt.excluded.department,
                "top_clicked": stmt.excluded.top_clicked,
                "contains_account_asin": stmt.excluded.contains_account_asin,
            },
        )
        await self.db.execute(stmt)

    async def sync_search_terms(
        self,
        account: AmazonAccount,
        organization=None,
        week_start: Optional[date] = None,
        week_end: Optional[date] = None,
    ) -> int:
        """Ingest one reporting week (default: last settled). Idempotent per
        (account, week_start, search_term)."""
        if account.account_type == AccountType.VENDOR:
            return 0

        if week_start is None or week_end is None:
            week_start, week_end = resolve_last_settled_ba_week()

        own_asins = await self._own_asins(account)
        if not own_asins:
            logger.info(
                "Brand search terms skipped for %s: no catalog ASINs to match against",
                account.account_name,
            )
            return 0

        client = self._create_sp_api_client(account, organization)
        signal = client.get_brand_analytics_search_terms(week_start, week_end)

        count = 0
        for term in signal.get("terms") or []:
            search_term = term.get("search_term")
            if not search_term:
                continue
            top_clicked = term.get("top_clicked_asins") or []
            term_asins = {
                entry.get("asin") for entry in top_clicked if isinstance(entry, dict)
            }
            if not (term_asins & own_asins):
                # The marketplace-wide report is enormous; keep only terms
                # where one of the account's ASINs is a top-3 clicked item.
                continue
            await self._upsert_term({
                "account_id": account.id,
                "week_start": week_start,
                "week_end": week_end,
                "search_term": str(search_term)[:500],
                "search_frequency_rank": term.get("search_frequency_rank"),
                "department": term.get("department"),
                "top_clicked": top_clicked,
                "contains_account_asin": True,
            })
            count += 1

        await self.db.flush()
        logger.info(
            "Brand search terms for %s week %s..%s: stored %d of %d terms",
            account.account_name, week_start, week_end, count, signal.get("term_count", 0),
        )
        return count
