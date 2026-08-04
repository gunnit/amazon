"""Display-metric expressions for sales data.

Vendor accounts store ordered (sell-in) revenue/units in
``ordered_product_sales`` / ``units_ordered`` and shipped (sell-through,
SOURCING view) in ``shipped_revenue`` / ``shipped_units``. User-facing figures
prefer shipped, falling back to ordered only when shipped is NULL — no SOURCING
data for that row (seller accounts, or a window whose SOURCING report failed).
A stored 0 is a real value: Amazon ordered but shipped nothing that day. Treating
it as missing made every per-ASIN sum add that day's ordered revenue on top of
the shipped total, so per-ASIN sums exceeded the __DAILY_TOTAL__ sentinel by
10-20%.
"""
from sqlalchemy import func

from app.models.sales_data import SalesData


def display_revenue_expr():
    return func.coalesce(SalesData.shipped_revenue, SalesData.ordered_product_sales)


def display_units_expr():
    return func.coalesce(SalesData.shipped_units, SalesData.units_ordered)
