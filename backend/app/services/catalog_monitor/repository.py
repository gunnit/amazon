"""Data access for the catalogue monitor (R1-R4). Never commits: callers do."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalog_monitor import (
    CatalogAnomaly,
    CatalogApiCapability,
    CatalogChangeRequest,
    ListingContentBaseline,
    ListingContentVersion,
    ListingQualityRule,
    VariationFamilyBaseline,
)
from app.models.listing_quality import ListingQualitySnapshot
from app.models.product import Product
from app.services.catalog_monitor.content import ListingContent, content_hash, content_to_dict
from app.services.catalog_monitor.rules import ListingEvaluation, evaluation_to_dict
from app.services.catalog_monitor.listing_health import listing_health_snapshot


class CatalogMonitorRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ---- products and versions ----

    async def products_to_scan(self, account_id: UUID) -> list[Product]:
        result = await self.db.execute(
            select(Product)
            .where(Product.account_id == account_id, Product.is_active.is_(True))
            .order_by(Product.asin)
        )
        return list(result.scalars().all())

    async def latest_versions(
        self, account_id: UUID, asins: Optional[list[str]] = None
    ) -> dict[str, ListingContentVersion]:
        """Latest version per ASIN (greatest ``last_seen_at``), one query, no history."""
        stmt = select(ListingContentVersion).where(ListingContentVersion.account_id == account_id)
        if asins is not None:
            if not asins:
                return {}
            stmt = stmt.where(ListingContentVersion.asin.in_(asins))
        stmt = stmt.distinct(ListingContentVersion.asin).order_by(
            ListingContentVersion.asin,
            ListingContentVersion.last_seen_at.desc(),
            ListingContentVersion.first_seen_at.desc(),
        )
        return {row.asin: row for row in (await self.db.execute(stmt)).scalars()}

    async def version_asins(self, account_id: UUID) -> list[str]:
        """ASINs with at least one stored version, sorted; no content is loaded."""
        result = await self.db.execute(
            select(ListingContentVersion.asin)
            .where(ListingContentVersion.account_id == account_id)
            .distinct()
            .order_by(ListingContentVersion.asin)
        )
        return [row[0] for row in result.all()]

    async def latest_skus(self, account_id: UUID) -> set[str]:
        """SKUs of each ASIN's latest version, read in SQL (``content->>'sku'``)."""
        sku = ListingContentVersion.content["sku"].astext
        stmt = (
            select(ListingContentVersion.asin, sku)
            .where(ListingContentVersion.account_id == account_id)
            .distinct(ListingContentVersion.asin)
            .order_by(
                ListingContentVersion.asin,
                ListingContentVersion.last_seen_at.desc(),
                ListingContentVersion.first_seen_at.desc(),
            )
        )
        return {row[1] for row in (await self.db.execute(stmt)).all() if row[1]}

    async def save_version(
        self, account_id: UUID, asin: str, content: ListingContent, seen_at: datetime
    ) -> tuple[ListingContentVersion, bool]:
        digest = content_hash(content)
        current = (await self.latest_versions(account_id, [asin])).get(asin)
        if current is not None and current.content_hash == digest:
            current.last_seen_at = seen_at
            return current, False
        version = ListingContentVersion(
            account_id=account_id,
            asin=asin,
            content_hash=digest,
            content=content_to_dict(content),
            first_seen_at=seen_at,
            last_seen_at=seen_at,
        )
        self.db.add(version)
        await self.db.flush()
        return version, True

    async def versions(
        self, account_id: UUID, asin: str, limit: int = 50
    ) -> list[ListingContentVersion]:
        result = await self.db.execute(
            select(ListingContentVersion)
            .where(ListingContentVersion.account_id == account_id, ListingContentVersion.asin == asin)
            .order_by(ListingContentVersion.first_seen_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    # ---- baselines ----

    async def baselines(
        self, account_id: UUID, asins: Optional[list[str]] = None
    ) -> dict[str, ListingContentBaseline]:
        """Baselines of the account, or only of ``asins``: each holds a full content
        payload, so callers working at catalogue scale pass the ASINs they need."""
        stmt = select(ListingContentBaseline).where(ListingContentBaseline.account_id == account_id)
        if asins is not None:
            if not asins:
                return {}
            stmt = stmt.where(ListingContentBaseline.asin.in_(asins))
        result = await self.db.execute(stmt)
        return {row.asin: row for row in result.scalars()}

    async def upsert_baseline(
        self,
        account_id: UUID,
        asin: str,
        content: ListingContent,
        source: str,
        user_id: Optional[UUID],
    ) -> ListingContentBaseline:
        result = await self.db.execute(
            select(ListingContentBaseline).where(
                ListingContentBaseline.account_id == account_id,
                ListingContentBaseline.asin == asin,
            )
        )
        row = result.scalar_one_or_none()
        now = datetime.utcnow()
        if row is None:
            row = ListingContentBaseline(account_id=account_id, asin=asin)
            self.db.add(row)
        row.content = content_to_dict(content)
        row.source = source
        row.approved_by_user_id = user_id
        row.approved_at = now
        await self.db.flush()
        return row

    async def family_baselines(self, account_id: UUID) -> list[VariationFamilyBaseline]:
        result = await self.db.execute(
            select(VariationFamilyBaseline)
            .where(VariationFamilyBaseline.account_id == account_id)
            .order_by(VariationFamilyBaseline.parent_asin)
        )
        return list(result.scalars().all())

    async def approved_variation_parent_links(
        self, account_id: UUID, source: str
    ) -> dict[str, tuple[list[str], Optional[str]]]:
        """Read the relationship fields without loading entire approved listings."""
        content = ListingContentBaseline.content
        stmt = select(
            ListingContentBaseline.asin, content["parent_asins"], content["variation_theme"].astext
        ).where(
            ListingContentBaseline.account_id == account_id,
            ListingContentBaseline.source == source,
        )
        return {
            asin: (parents, theme)
            for asin, parents, theme in (await self.db.execute(stmt)).all()
            if isinstance(parents, list) and parents
        }

    async def create_family_baseline_if_absent(
        self, account_id: UUID, parent_asin: str, theme: Optional[str], children: list[str]
    ) -> bool:
        """Recover a reference for these approved children without replacing a saved family."""
        stmt = (
            insert(VariationFamilyBaseline)
            .values(
                account_id=account_id, parent_asin=parent_asin,
                variation_theme=theme, child_asins=children, is_partial=True,
            )
            .on_conflict_do_nothing(constraint="uq_variation_baseline_account_parent")
            .returning(VariationFamilyBaseline.id)
        )
        return (await self.db.execute(stmt)).scalar_one_or_none() is not None

    async def upsert_family_baseline(
        self, account_id: UUID, parent_asin: str, theme: Optional[str], children: list[str]
    ) -> VariationFamilyBaseline:
        stmt = (
            insert(VariationFamilyBaseline)
            .values(
                account_id=account_id, parent_asin=parent_asin,
                variation_theme=theme, child_asins=children, is_partial=False,
            )
            .on_conflict_do_update(
                constraint="uq_variation_baseline_account_parent",
                set_=dict(
                    variation_theme=theme, child_asins=children,
                    is_partial=False, captured_at=datetime.utcnow(),
                ),
            )
            .returning(VariationFamilyBaseline)
        )
        return (await self.db.scalars(stmt, execution_options={"populate_existing": True})).one()

    # ---- anomalies ----

    async def open_anomalies(
        self, account_id: UUID
    ) -> dict[tuple[str, str, str], CatalogAnomaly]:
        result = await self.db.execute(
            select(CatalogAnomaly).where(
                CatalogAnomaly.account_id == account_id, CatalogAnomaly.status != "resolved"
            )
        )
        return {(row.asin, row.kind, row.field): row for row in result.scalars()}

    async def open_or_touch_anomaly(
        self,
        account_id: UUID,
        asin: str,
        kind: str,
        field: str,
        baseline_value: Any,
        live_value: Any,
        now: datetime,
    ) -> tuple[CatalogAnomaly, bool]:
        result = await self.db.execute(
            select(CatalogAnomaly).where(
                CatalogAnomaly.account_id == account_id,
                CatalogAnomaly.asin == asin,
                CatalogAnomaly.kind == kind,
                CatalogAnomaly.field == field,
                CatalogAnomaly.status != "resolved",
            )
        )
        existing = result.scalars().first()
        if existing is not None:
            existing.last_seen_at = now
            existing.live_value = live_value
            return existing, False
        anomaly = CatalogAnomaly(
            account_id=account_id,
            asin=asin,
            kind=kind,
            field=field,
            baseline_value=baseline_value,
            live_value=live_value,
            status="open",
            detected_at=now,
            last_seen_at=now,
        )
        self.db.add(anomaly)
        await self.db.flush()
        return anomaly, True

    async def resolve_anomaly(self, anomaly: CatalogAnomaly, now: datetime) -> None:
        anomaly.status = "resolved"
        anomaly.resolved_at = now
        await self.db.flush()

    # ---- change requests ----

    async def change_requests_for_feed(
        self, account_id: UUID, feed_id: str
    ) -> list[CatalogChangeRequest]:
        result = await self.db.execute(
            select(CatalogChangeRequest)
            .where(
                CatalogChangeRequest.account_id == account_id,
                CatalogChangeRequest.feed_id == feed_id,
            )
            .order_by(CatalogChangeRequest.created_at)
        )
        return list(result.scalars().all())

    # ---- quality, rules, capabilities ----

    async def save_quality_snapshot(
        self, account_id: UUID, asin: str, evaluation: ListingEvaluation, day: date,
        listing_health: Optional[dict] = None, checked_at: Optional[datetime] = None,
    ) -> None:
        result = await self.db.execute(
            select(ListingQualitySnapshot).where(
                ListingQualitySnapshot.account_id == account_id,
                ListingQualitySnapshot.asin == asin,
                ListingQualitySnapshot.snapshot_date <= day,
            ).order_by(ListingQualitySnapshot.snapshot_date.desc()).limit(1)
        )
        row = result.scalar_one_or_none()
        previous_health = (row.components or {}).get("listing_health") if row is not None else None
        if row is None or row.snapshot_date != day:
            row = ListingQualitySnapshot(account_id=account_id, asin=asin, snapshot_date=day)
            self.db.add(row)
        row.score = evaluation.score
        components = evaluation_to_dict(evaluation)
        if listing_health is not None and checked_at is not None:
            components["listing_health"] = listing_health_snapshot(listing_health, checked_at, previous_health)
        row.components = components
        await self.db.flush()

    async def rule_overrides(self, organization_id: UUID) -> list[ListingQualityRule]:
        result = await self.db.execute(
            select(ListingQualityRule).where(ListingQualityRule.organization_id == organization_id)
        )
        return list(result.scalars().all())

    async def capability(self, account_id: UUID) -> Optional[CatalogApiCapability]:
        result = await self.db.execute(
            select(CatalogApiCapability).where(CatalogApiCapability.account_id == account_id)
        )
        return result.scalar_one_or_none()

    async def save_capability(
        self, account_id: UUID, results: dict, vendor_code: Optional[str], now: datetime
    ) -> CatalogApiCapability:
        row = await self.capability(account_id)
        if row is None:
            row = CatalogApiCapability(account_id=account_id)
            self.db.add(row)
        row.results = results
        row.vendor_code = vendor_code
        row.checked_at = now
        await self.db.flush()
        return row
