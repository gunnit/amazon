"""Listing quality scoring from warehouse data.

Scores each product 0-100 from already-synced catalog fields — no Amazon API
calls, so it can run live for the endpoint and weekly for trend snapshots.
"""
from __future__ import annotations

from datetime import date
import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.amazon_account import AmazonAccount
from app.models.listing_quality import ListingQualitySnapshot
from app.models.product import Product

logger = logging.getLogger(__name__)

# Title length thresholds (Amazon recommends descriptive titles; very short
# titles convert poorly and index for fewer terms).
TITLE_FULL_LENGTH = 80
TITLE_PARTIAL_LENGTH = 30


def score_product(product: Product) -> Dict[str, Any]:
    """Score one product. Returns {score, components, issues}."""
    components: Dict[str, Dict[str, Any]] = {}
    issues: List[str] = []

    def add(name: str, earned: int, max_points: int, detail: str, issue: Optional[str] = None):
        components[name] = {"earned": earned, "max": max_points, "detail": detail}
        if issue and earned < max_points:
            issues.append(issue)

    title = (product.title or "").strip()
    if len(title) >= TITLE_FULL_LENGTH:
        add("title", 25, 25, f"{len(title)} chars")
    elif len(title) >= TITLE_PARTIAL_LENGTH:
        add("title", 15, 25, f"{len(title)} chars (short)", "Title is short — expand toward 80+ descriptive characters")
    elif title:
        add("title", 8, 25, f"{len(title)} chars (very short)", "Title is very short — expand toward 80+ descriptive characters")
    else:
        add("title", 0, 25, "missing", "Title is missing")

    add(
        "brand", 10 if product.brand else 0, 10,
        product.brand or "missing",
        "Brand attribute is missing",
    )
    add(
        "category", 10 if product.category else 0, 10,
        product.category or "missing",
        "Category is missing — check browse node assignment",
    )
    add(
        "price", 15 if product.current_price else 0, 15,
        str(product.current_price) if product.current_price else "missing",
        "No current price — listing may be inactive or missing an offer",
    )

    available = bool(product.is_active and product.is_available)
    add(
        "availability", 20 if available else 0, 20,
        "available" if available else "inactive or unavailable",
        "Listing is inactive or unavailable on Amazon",
    )

    add(
        "rating", 10 if product.rating is not None else 0, 10,
        str(product.rating) if product.rating is not None else "none",
        "No rating yet — consider review-generation (Vine, inserts within ToS)",
    )
    add(
        "reviews", 10 if (product.review_count or 0) > 0 else 0, 10,
        str(product.review_count or 0),
        "No reviews yet",
    )

    score = sum(c["earned"] for c in components.values())
    return {"score": score, "components": components, "issues": issues}


class ListingQualityService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def compute_for_account(self, account_id: UUID) -> List[Dict[str, Any]]:
        """Live scores for every active product, worst first (the fix list)."""
        result = await self.db.execute(
            select(Product).where(
                Product.account_id == account_id,
                Product.is_active.is_(True),
            )
        )
        products = result.scalars().all()
        scored = []
        for product in products:
            entry = score_product(product)
            entry.update({
                "asin": product.asin,
                "sku": product.sku,
                "title": product.title,
            })
            scored.append(entry)
        scored.sort(key=lambda e: e["score"])
        return scored

    async def snapshot_account(self, account: AmazonAccount) -> int:
        """Persist today's scores for week-over-week trending. Idempotent."""
        scored = await self.compute_for_account(account.id)
        today = date.today()
        for entry in scored:
            stmt = pg_insert(ListingQualitySnapshot).values(
                account_id=account.id,
                asin=entry["asin"],
                snapshot_date=today,
                score=entry["score"],
                components=entry["components"],
            )
            stmt = stmt.on_conflict_do_update(
                constraint="uq_listing_quality_account_asin_date",
                set_={
                    "score": stmt.excluded.score,
                    "components": stmt.excluded.components,
                },
            )
            await self.db.execute(stmt)
        await self.db.flush()
        logger.info(
            "Listing quality snapshot for %s: %d products",
            account.account_name, len(scored),
        )
        return len(scored)
