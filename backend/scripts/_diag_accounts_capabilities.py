"""One-off prod diagnostics: account/backfill state, sales coverage, capability probe errors."""
import asyncio
import json
import sys

sys.path.insert(0, "/app")

from sqlalchemy import func, select, text

from app.db.session import AsyncSessionLocal
from app.models.amazon_account import AmazonAccount
from app.models.brand_analysis import BrandAnalysisCapability
from app.models.sales_data import SalesData


async def main():
    async with AsyncSessionLocal() as db:
        accounts = (await db.execute(select(AmazonAccount))).scalars().all()
        print("=== ACCOUNTS ===")
        for a in accounts:
            print(json.dumps({
                "id": str(a.id),
                "name": a.account_name,
                "type": getattr(a.account_type, "value", a.account_type),
                "marketplace": a.marketplace_id,
                "seller_id": a.seller_id,
                "created_at": str(a.created_at),
                "last_sync_at": str(a.last_sync_at),
                "sync_status": getattr(a.sync_status, "value", a.sync_status),
                "sync_error_code": a.sync_error_code,
                "sync_error_message": (a.sync_error_message or "")[:200],
                "has_token": bool(a.sp_api_refresh_token_encrypted),
                "backfill_status": a.last_backfill_status,
                "backfill_started": str(a.last_backfill_started_at),
                "backfill_completed": str(a.last_backfill_completed_at),
                "backfill_records": a.last_backfill_records,
                "backfill_error": (a.last_backfill_error or "")[:200],
                "backfill_range": f"{a.last_backfill_range_start} .. {a.last_backfill_range_end}",
            }, default=str))

        print("=== SALES COVERAGE (daily totals per account per year) ===")
        rows = (await db.execute(text("""
            SELECT account_id::text, EXTRACT(YEAR FROM date)::int AS yr,
                   COUNT(*) FILTER (WHERE asin = '__DAILY_TOTAL__') AS daily_rows,
                   COUNT(*) AS all_rows,
                   MIN(date)::text AS min_d, MAX(date)::text AS max_d,
                   ROUND(SUM(CASE WHEN asin = '__DAILY_TOTAL__'
                             THEN COALESCE(NULLIF(ordered_product_sales, 0), shipped_revenue, 0)
                             ELSE 0 END)::numeric, 0) AS rev
            FROM sales_data GROUP BY 1, 2 ORDER BY 1, 2
        """))).all()
        name_by_id = {str(a.id): a.account_name for a in accounts}
        for r in rows:
            print(f"{name_by_id.get(r[0], r[0])[:20]:20s} {r[1]} daily={r[2]:4d} all={r[3]:6d} {r[4]}..{r[5]} rev={r[6]}")

        print("=== CAPABILITIES ===")
        caps = (await db.execute(select(BrandAnalysisCapability))).scalars().all()
        for c in caps:
            cap_bools = {k: getattr(c, k, None) for k in (
                "sales_and_traffic_available", "data_kiosk_available", "brand_analytics_available",
                "brand_registry_available_or_inferred", "product_pricing_available",
                "product_fees_available", "aplus_available", "finance_reports_available",
                "settlement_reports_available", "catalog_items_available", "listings_available")}
            print(json.dumps({
                "account": name_by_id.get(str(c.account_id), str(c.account_id)),
                "marketplace": c.marketplace_id,
                "checked_at": str(c.checked_at),
                "caps": cap_bools,
                "errors": c.last_error_by_capability,
                "missing_roles": c.missing_roles,
            }, default=str))


asyncio.run(main())
