"""Nightly per-ASIN fee-estimate and price/Buy Box snapshots.

Uses the Product Fees and Product Pricing APIs (their own quotas — no
contention with the Reports API syncs). Seller accounts only.
"""
from __future__ import annotations

import asyncio
from datetime import date
from decimal import Decimal
import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.amazon_account import AccountType, AmazonAccount
from app.models.market_snapshot import FeeEstimate, PriceSnapshot
from app.models.product import Product

logger = logging.getLogger(__name__)

# Both APIs allow ~0.5-1 rps; pausing between ASINs keeps a 200-ASIN account
# within quota even with the per-call throttle retries on top.
MARKET_SNAPSHOT_MAX_ASINS_PER_ACCOUNT = 200
MARKET_SNAPSHOT_CALL_PAUSE_SECONDS = 1.5

# Marketplace currency for fee-estimate requests; the platform's marketplaces
# are EU-first, so EUR is the fallback (same default as the SP-API client).
_CURRENCY_BY_COUNTRY = {
    "US": "USD", "CA": "CAD", "MX": "MXN", "BR": "BRL",
    "GB": "GBP", "UK": "GBP", "SE": "SEK", "PL": "PLN",
    "JP": "JPY", "AU": "AUD", "SG": "SGD", "AE": "AED",
    "SA": "SAR", "TR": "TRY", "IN": "INR", "EG": "EGP",
}


def _currency_for_country(country: Optional[str]) -> str:
    return _CURRENCY_BY_COUNTRY.get((country or "").upper(), "EUR")


class MarketSnapshotService:
    """Snapshot current fees and offers for one account's active catalog."""

    def __init__(self, db: AsyncSession):
        self.db = db

    def _create_sp_api_client(self, account: AmazonAccount, organization=None):
        from app.core.amazon.credentials import resolve_credentials
        from app.core.amazon.sp_api_client import SPAPIClient, resolve_marketplace

        credentials = resolve_credentials(account, organization)
        marketplace = resolve_marketplace(account.marketplace_country)
        return SPAPIClient(credentials, marketplace, account_type=account.account_type.value)

    async def _upsert_fee_estimate(self, values: dict) -> None:
        stmt = pg_insert(FeeEstimate).values(**values)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_fee_estimates_account_asin_date",
            set_={
                "price_basis": stmt.excluded.price_basis,
                "currency": stmt.excluded.currency,
                "estimated_fees": stmt.excluded.estimated_fees,
            },
        )
        await self.db.execute(stmt)

    async def _upsert_price_snapshot(self, values: dict) -> None:
        stmt = pg_insert(PriceSnapshot).values(**values)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_price_snapshots_account_asin_date",
            set_={
                "our_price": stmt.excluded.our_price,
                "buy_box_price": stmt.excluded.buy_box_price,
                "buy_box_seller_id": stmt.excluded.buy_box_seller_id,
                "is_buy_box_ours": stmt.excluded.is_buy_box_ours,
                "offer_count": stmt.excluded.offer_count,
                "is_fba": stmt.excluded.is_fba,
                "currency": stmt.excluded.currency,
            },
        )
        await self.db.execute(stmt)

    async def snapshot_account(self, account: AmazonAccount, organization=None) -> dict:
        """Snapshot fees + prices for the account's active ASINs. Idempotent
        per (account, asin, day) — re-runs overwrite today's snapshot."""
        if account.account_type == AccountType.VENDOR:
            return {"prices": 0, "fees": 0}

        result = await self.db.execute(
            select(Product)
            .where(
                Product.account_id == account.id,
                Product.is_active.is_(True),
            )
            .order_by(Product.updated_at.desc())
            .limit(MARKET_SNAPSHOT_MAX_ASINS_PER_ACCOUNT)
        )
        products = result.scalars().all()
        if not products:
            return {"prices": 0, "fees": 0}

        client = self._create_sp_api_client(account, organization)
        today = date.today()
        currency = _currency_for_country(account.marketplace_country)
        prices = 0
        fees = 0

        for index, product in enumerate(products):
            if index > 0:
                await asyncio.sleep(MARKET_SNAPSHOT_CALL_PAUSE_SECONDS)

            offer: Optional[dict] = None
            try:
                offer = client.get_item_offer_snapshot(product.asin)
            except Exception as exc:
                logger.warning(
                    "Offer snapshot failed for %s/%s: %s",
                    account.account_name, product.asin, exc,
                )

            buy_box_price = None
            if offer:
                raw_price = offer.get("buy_box_price")
                buy_box_price = Decimal(str(raw_price)) if raw_price is not None else None
                buy_box_seller = offer.get("buy_box_seller_id")
                # Tri-state: None = unknown (no winner reported / no seller_id),
                # False = a competitor owns the Buy Box. `... or None` would
                # collapse False into None and make Buy Box loss undetectable.
                if buy_box_seller is None or not account.seller_id:
                    is_ours = None
                else:
                    is_ours = str(buy_box_seller) == str(account.seller_id)
                await self._upsert_price_snapshot({
                    "account_id": account.id,
                    "asin": product.asin,
                    "snapshot_date": today,
                    "our_price": product.current_price,
                    "buy_box_price": buy_box_price,
                    "buy_box_seller_id": str(buy_box_seller) if buy_box_seller else None,
                    "is_buy_box_ours": is_ours,
                    "offer_count": offer.get("offer_count"),
                    "is_fba": offer.get("is_fba"),
                    "currency": currency,
                })
                prices += 1

            price_basis = buy_box_price or product.current_price
            if price_basis:
                try:
                    estimated = client.estimate_fba_fee_for_asin(
                        product.asin, float(price_basis), currency=currency
                    )
                except Exception as exc:
                    logger.warning(
                        "Fee estimate failed for %s/%s: %s",
                        account.account_name, product.asin, exc,
                    )
                    estimated = None
                if estimated is not None:
                    await self._upsert_fee_estimate({
                        "account_id": account.id,
                        "asin": product.asin,
                        "snapshot_date": today,
                        "price_basis": price_basis,
                        "currency": currency,
                        "estimated_fees": estimated,
                    })
                    fees += 1

        await self.db.flush()
        logger.info(
            "Market snapshot for %s: %d price rows, %d fee rows (%d ASINs)",
            account.account_name, prices, fees, len(products),
        )
        return {"prices": prices, "fees": fees}
