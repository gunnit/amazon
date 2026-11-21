"""Main keyword per ASIN for the listing-quality keyword checks (R1).

The operator-set keyword wins (``Product.main_keyword``, from the UI or the
Excel upload). Otherwise the Brand Analytics search term of the account's
latest ingested week in which the ASIN is among the top three clicked, picking
the term where it has the best click share. Otherwise there is no keyword and
the rules skip the keyword checks, saying so.
"""
from __future__ import annotations

import sys
from typing import Any, Iterable, Optional
from uuid import UUID

from sqlalchemy import func, select

from app.models.brand_search_term import BrandSearchTerm

BRAND_ANALYTICS_SOURCE = "brand_analytics"


def _manual_keyword(product: Any) -> Optional[str]:
    keyword = (product.main_keyword or "").strip()
    if keyword and product.main_keyword_source != BRAND_ANALYTICS_SOURCE:
        return keyword
    return None


def best_brand_analytics_terms(terms: Iterable[Any], asins: set[str]) -> dict[str, str]:
    """For each ASIN, the term where it has the highest click share.

    Ties go to the more searched term (lower search frequency rank), then to
    alphabetical order so the result is stable.
    """
    best: dict[str, tuple[tuple[float, int, str], str]] = {}
    for term in terms:
        text = (term.search_term or "").strip()
        if not text:
            continue
        rank = term.search_frequency_rank if term.search_frequency_rank is not None else sys.maxsize
        for entry in term.top_clicked or []:
            if not isinstance(entry, dict) or entry.get("asin") not in asins:
                continue
            share = entry.get("click_share")
            share = float(share) if isinstance(share, (int, float)) else -1.0
            key = (-share, rank, text)
            current = best.get(entry["asin"])
            if current is None or key < current[0]:
                best[entry["asin"]] = (key, text)
    return {asin: text for asin, (_, text) in best.items()}


async def resolve_main_keywords(db, account_id: UUID, products: list[Any]) -> dict[str, str]:
    """ASIN → main keyword; ASINs without one are absent."""
    keywords: dict[str, str] = {}
    pending: set[str] = set()
    for product in products:
        if not product.asin:
            continue
        manual = _manual_keyword(product)
        if manual:
            keywords[product.asin] = manual
        else:
            pending.add(product.asin)
    if not pending:
        return keywords

    latest_week = (
        select(func.max(BrandSearchTerm.week_start))
        .where(BrandSearchTerm.account_id == account_id)
        .scalar_subquery()
    )
    rows = (
        await db.execute(
            select(BrandSearchTerm).where(
                BrandSearchTerm.account_id == account_id,
                BrandSearchTerm.week_start == latest_week,
                BrandSearchTerm.contains_account_asin.is_(True),
            )
        )
    ).scalars().all()
    return {**best_brand_analytics_terms(rows, pending), **keywords}
