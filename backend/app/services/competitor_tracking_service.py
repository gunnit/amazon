"""Daily snapshots for tracked competitor ASINs (price, BSR, reviews, rating).

Uses the same per-ASIN fetch as market research reports (Catalog + Product
Pricing APIs). Data lands in ``competitors`` (current state) and
``competitor_history`` (one row per competitor per day) so price/BSR trends
survive across days. Reviews/rating stay NULL when Amazon does not expose
them — the UI renders that honestly instead of inventing values.
"""
from __future__ import annotations

import asyncio
from datetime import date, datetime
from decimal import Decimal
import logging
from typing import Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.amazon_account import AccountType, AmazonAccount
from app.models.competitor import Competitor, CompetitorHistory

logger = logging.getLogger(__name__)

# Same pacing as the nightly market snapshot: keeps Catalog/Pricing quotas
# safe even with the per-call throttle retries on top.
COMPETITOR_TRACKING_CALL_PAUSE_SECONDS = 1.5

# Alert when a tracked competitor's price moves at least this much versus the
# last known price (US-2.5: alerts for competitor price changes).
PRICE_CHANGE_ALERT_THRESHOLD_PCT = 5.0
COMPETITOR_PRICE_ALERT_KIND = "competitor_price_change"


def snapshot_to_fields(snapshot: dict) -> dict:
    """Map a ``_fetch_product_data`` snapshot onto competitor columns."""
    price = snapshot.get("price")
    rating = snapshot.get("rating")
    return {
        "title": snapshot.get("title"),
        "brand": snapshot.get("brand"),
        "price": Decimal(str(price)) if price is not None else None,
        "bsr": snapshot.get("bsr"),
        "review_count": snapshot.get("review_count"),
        "rating": Decimal(str(rating)) if rating is not None else None,
    }


def price_change_percent(previous, current) -> Optional[float]:
    """Percent change between two prices; None when not comparable."""
    if previous is None or current is None:
        return None
    previous = float(previous)
    current = float(current)
    if previous <= 0:
        return None
    return (current - previous) / previous * 100.0


class CompetitorTrackingService:
    """Fetch and persist competitor snapshots for one organization."""

    def __init__(self, db: AsyncSession):
        self.db = db

    def _create_sp_api_client(self, account: AmazonAccount, organization=None):
        from app.core.amazon.credentials import resolve_credentials
        from app.core.amazon.sp_api_client import SPAPIClient, resolve_marketplace

        credentials = resolve_credentials(account, organization)
        marketplace = resolve_marketplace(account.marketplace_country)
        return SPAPIClient(credentials, marketplace, account_type=account.account_type.value)

    async def pick_fetch_account(self, organization_id: UUID) -> Optional[AmazonAccount]:
        """Pick the account whose credentials fetch competitor data.

        Sellers first: the Product Pricing API is seller-only, so a vendor
        credential would collect BSR but never prices. Any active account can
        still read the catalog when no seller exists.
        """
        result = await self.db.execute(
            select(AmazonAccount)
            .where(
                AmazonAccount.organization_id == organization_id,
                AmazonAccount.is_active.is_(True),
            )
            .order_by(AmazonAccount.created_at)
        )
        accounts = result.scalars().all()
        sellers = [a for a in accounts if a.account_type == AccountType.SELLER]
        # ponytail: one fetch account per org; per-marketplace routing when a
        # client tracks competitors across multiple marketplaces.
        return sellers[0] if sellers else (accounts[0] if accounts else None)

    async def snapshot_competitor(
        self, client, competitor: Competitor, *, emit_alerts: bool = True
    ) -> bool:
        """Fetch one competitor and persist current state + today's history row.

        Returns True when at least one metric came back. Known values are
        never clobbered by a transient fetch miss.
        """
        from app.services.market_research_service import _fetch_product_data

        snapshot = await asyncio.to_thread(_fetch_product_data, client, competitor.asin)
        fields = snapshot_to_fields(snapshot)
        previous_price = competitor.current_price

        if fields["title"]:
            competitor.title = fields["title"]
        if fields["brand"]:
            competitor.brand = fields["brand"]
        if fields["price"] is not None:
            competitor.current_price = fields["price"]
        if fields["bsr"] is not None:
            competitor.current_bsr = fields["bsr"]
        if fields["review_count"] is not None:
            competitor.review_count = fields["review_count"]
        if fields["rating"] is not None:
            competitor.rating = fields["rating"]

        stmt = pg_insert(CompetitorHistory).values(
            competitor_id=competitor.id,
            date=date.today(),
            price=fields["price"],
            bsr=fields["bsr"],
            review_count=fields["review_count"],
            rating=fields["rating"],
        )
        # Re-runs on the same day keep known values instead of nulling them.
        stmt = stmt.on_conflict_do_update(
            constraint="uq_competitor_history_competitor_date",
            set_={
                "price": func.coalesce(stmt.excluded.price, CompetitorHistory.price),
                "bsr": func.coalesce(stmt.excluded.bsr, CompetitorHistory.bsr),
                "review_count": func.coalesce(
                    stmt.excluded.review_count, CompetitorHistory.review_count
                ),
                "rating": func.coalesce(stmt.excluded.rating, CompetitorHistory.rating),
            },
        )
        await self.db.execute(stmt)

        if emit_alerts:
            change = price_change_percent(previous_price, fields["price"])
            if change is not None and abs(change) >= PRICE_CHANGE_ALERT_THRESHOLD_PCT:
                try:
                    await self._emit_price_change_alert(
                        competitor, previous_price, fields["price"], change
                    )
                except Exception as exc:
                    logger.warning(
                        "Competitor price alert emit failed for %s: %s",
                        competitor.asin, exc,
                    )

        return any(
            fields[key] is not None for key in ("price", "bsr", "review_count", "rating")
        )

    async def _emit_price_change_alert(
        self, competitor: Competitor, previous_price, new_price, change_pct: float
    ) -> None:
        from app.models.alert import Alert, AlertRule

        result = await self.db.execute(
            select(AlertRule).where(
                AlertRule.organization_id == competitor.organization_id,
                AlertRule.alert_type == "price_change",
                AlertRule.name == "Competitor price changes",
            )
        )
        rule = result.scalars().first()
        if rule is None:
            rule = AlertRule(
                organization_id=competitor.organization_id,
                name="Competitor price changes",
                alert_type="price_change",
                conditions={"auto_created": True, "threshold_pct": PRICE_CHANGE_ALERT_THRESHOLD_PCT},
                notification_channels=[],
                is_enabled=True,
            )
            self.db.add(rule)
            await self.db.flush()

        dedup_key = f"{COMPETITOR_PRICE_ALERT_KIND}:{competitor.id}:{date.today().isoformat()}"
        existing = await self.db.execute(
            select(Alert).where(Alert.rule_id == rule.id, Alert.dedup_key == dedup_key)
        )
        if existing.scalars().first() is not None:
            return

        now = datetime.utcnow()
        direction = "up" if change_pct > 0 else "down"
        label = competitor.title or competitor.asin
        self.db.add(
            Alert(
                rule_id=rule.id,
                organization_id=competitor.organization_id,
                asin=competitor.asin,
                event_kind=COMPETITOR_PRICE_ALERT_KIND,
                dedup_key=dedup_key,
                message=(
                    f"Competitor price {direction} {abs(change_pct):.1f}% for {label}: "
                    f"{float(previous_price):.2f} -> {float(new_price):.2f}"
                ),
                details={
                    "competitor_id": str(competitor.id),
                    "asin": competitor.asin,
                    "previous_price": float(previous_price),
                    "new_price": float(new_price),
                    "change_pct": round(change_pct, 2),
                },
                severity="warning",
                triggered_at=now,
                last_seen_at=now,
            )
        )
        rule.last_triggered_at = now

    async def sync_organization(self, organization_id: UUID) -> int:
        """Snapshot every tracked competitor of an organization once."""
        result = await self.db.execute(
            select(Competitor)
            .where(
                Competitor.organization_id == organization_id,
                Competitor.is_tracking.is_(True),
            )
            .order_by(Competitor.created_at)
        )
        competitors = result.scalars().all()
        if not competitors:
            return 0

        account = await self.pick_fetch_account(organization_id)
        if account is None:
            logger.info(
                "Competitor tracking skipped for org %s: no active account",
                organization_id,
            )
            return 0

        from app.services.data_extraction import DataExtractionService

        organization = await DataExtractionService(self.db)._load_organization(account)
        client = self._create_sp_api_client(account, organization)

        updated = 0
        for index, competitor in enumerate(competitors):
            if index > 0:
                await asyncio.sleep(COMPETITOR_TRACKING_CALL_PAUSE_SECONDS)
            try:
                if await self.snapshot_competitor(client, competitor):
                    updated += 1
            except Exception as exc:
                logger.warning(
                    "Competitor snapshot failed for %s/%s: %s",
                    organization_id, competitor.asin, exc,
                )
        await self.db.flush()
        logger.info(
            "Competitor tracking for org %s: %d/%d competitors updated",
            organization_id, updated, len(competitors),
        )
        return updated
