"""Display-metric expressions for sales data.

Vendor accounts store ordered (sell-in) revenue/units in
``ordered_product_sales`` / ``units_ordered`` and shipped (sell-through,
SOURCING view) in ``shipped_revenue`` / ``shipped_units``. User-facing figures
prefer shipped, falling back to ordered when shipped is null or 0 — which
happens for recent unsettled months and for seller accounts that never populate
shipped. ``nullif(., 0)`` ensures a 0 or absent shipped value falls back to
ordered rather than displaying zero.
"""
from sqlalchemy import func

from app.models.sales_data import SalesData


def display_revenue_expr():
    return func.coalesce(func.nullif(SalesData.shipped_revenue, 0), SalesData.ordered_product_sales)


def display_units_expr():
    return func.coalesce(func.nullif(SalesData.shipped_units, 0), SalesData.units_ordered)
