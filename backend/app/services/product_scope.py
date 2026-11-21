"""Brand and category scope for product-level aggregations (R5).

Account-level totals come from the per-account daily total row (asin
``__DAILY_TOTAL__``) and cannot be split by product. When a brand or category
is selected, callers sum the per-ASIN rows of the matching products instead,
joined through ``products`` on (account, asin) and never mixed with the total
row, so nothing is counted twice.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import func

from app.models.product import Product


def clean_scope_value(value: Optional[str]) -> Optional[str]:
    """Trimmed filter value, or None when blank."""
    if value is None:
        return None
    value = value.strip()
    return value or None


def has_product_scope(brand: Optional[str], category: Optional[str]) -> bool:
    return bool(clean_scope_value(brand) or clean_scope_value(category))


def product_scope_conditions(brand: Optional[str], category: Optional[str]) -> list:
    """WHERE conditions on ``Product`` for the selected brand (any case) and category."""
    conditions = []
    brand = clean_scope_value(brand)
    category = clean_scope_value(category)
    if brand:
        conditions.append(func.lower(Product.brand) == brand.lower())
    if category:
        conditions.append(Product.category == category)
    return conditions
