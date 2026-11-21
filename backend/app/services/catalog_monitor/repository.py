"""Data access for the catalogue monitor (R1-R4). Never commits: callers do."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalog_monitor import (
    CatalogAnomaly,
    CatalogApiCapability,
    ListingContentBaseline,
    ListingContentVersion,
    ListingQualityRule,
    VariationFamilyBaseline,
)
from app.models.listing_quality import ListingQualitySnapshot
from app.models.product import Product
from app.services.catalog_monitor.content import ListingContent, content_hash, content_to_dict
from app.services.catalog_monitor.rules import ListingEvaluation, evaluation_to_dict


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
        stmt = select(ListingContentVersion).where(ListingContentVersion.account_id == account_id)
        if asins is not None:
            if not asins:
                return {}
            stmt = stmt.where(ListingContentVersion.asin.in_(asins))
        stmt = stmt.order_by(
            ListingContentVersion.asin,
            ListingContentVersion.last_seen_at,
            ListingContentVersion.first_seen_at,
        )
        latest: dict[str, ListingContentVersion] = {}
        for row in (await self.db.execute(stmt)).scalars():
            latest[row.asin] = row  # ascending order: the last row per ASIN wins
        return latest

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

    async def baselines(self, account_id: UUID) -> dict[str, ListingContentBaseline]:
        result = await self.db.execute(
            select(ListingContentBaseline).where(ListingContentBaseline.account_id == account_id)
        )
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

    async def upsert_family_baseline(
        self, account_id: UUID, parent_asin: str, theme: Optional[str], children: list[str]
    ) -> VariationFamilyBaseline:
        result = await self.db.execute(
            select(VariationFamilyBaseline).where(
                VariationFamilyBaseline.account_id == account_id,
                VariationFamilyBaseline.parent_asin == parent_asin,
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            row = VariationFamilyBaseline(account_id=account_id, parent_asin=parent_asin)
            self.db.add(row)
        row.variation_theme = theme
        row.child_asins = list(children)
        row.captured_at = datetime.utcnow()
        await self.db.flush()
        return row

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
        existing = (await self.open_anomalies(account_id)).get((asin, kind, field))
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

    # ---- quality, rules, capabilities ----

    async def save_quality_snapshot(
        self, account_id: UUID, asin: str, evaluation: ListingEvaluation, day: date
    ) -> None:
        result = await self.db.execute(
            select(ListingQualitySnapshot).where(
                ListingQualitySnapshot.account_id == account_id,
                ListingQualitySnapshot.asin == asin,
                ListingQualitySnapshot.snapshot_date == day,
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            row = ListingQualitySnapshot(account_id=account_id, asin=asin, snapshot_date=day)
            self.db.add(row)
        row.score = evaluation.score
        row.components = evaluation_to_dict(evaluation)
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
