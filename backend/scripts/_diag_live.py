"""One-off live diagnostics: Bitron orders since Apr 12 + Dialcos vendor DAY report test."""
import asyncio
import json
import sys
from datetime import date, datetime, timezone

sys.path.insert(0, "/app")

from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models.amazon_account import AmazonAccount

BITRON = "7f195a92-70ba-4d81-92d2-42671cd9aa5f"
DIALCOS = "5d89b2d9-4760-4659-821a-16cceee61425"


async def main():
    which = sys.argv[1] if len(sys.argv) > 1 else "both"
    async with AsyncSessionLocal() as db:
        from app.services.data_extraction import DataExtractionService

        svc = DataExtractionService(db)

        if which in ("both", "bitron"):
            acc = (
                await db.execute(select(AmazonAccount).where(AmazonAccount.id == BITRON))
            ).scalar_one()
            org = await svc._load_organization(acc)
            client = svc._create_sp_api_client(acc, org)
            orders = client.fetch_orders(
                created_after=datetime(2026, 4, 12, tzinfo=timezone.utc),
                created_before=datetime(2026, 6, 11, tzinfo=timezone.utc),
            )
            print(f"BITRON orders 2026-04-12..2026-06-11: {len(orders)}")
            for o in orders[:10]:
                print(
                    "  ",
                    o.get("AmazonOrderId"),
                    o.get("PurchaseDate"),
                    o.get("OrderStatus"),
                    (o.get("OrderTotal") or {}).get("Amount"),
                )

        if which in ("both", "dialcos"):
            acc = (
                await db.execute(select(AmazonAccount).where(AmazonAccount.id == DIALCOS))
            ).scalar_one()
            org = await svc._load_organization(acc)
            client = svc._create_sp_api_client(acc, org)
            raw = client.request_and_download_report(
                report_type="GET_VENDOR_SALES_REPORT",
                start_date=date(2024, 6, 1),
                end_date=date(2024, 6, 15),
                report_options={
                    "reportPeriod": "DAY",
                    "sellingProgram": "RETAIL",
                    "distributorView": "MANUFACTURING",
                },
            )
            if isinstance(raw, dict) and "document" in raw:
                doc = raw["document"]
                if isinstance(doc, (bytes, bytearray)):
                    doc = doc.decode("utf-8")
                raw = json.loads(doc) if isinstance(doc, str) else doc
            elif isinstance(raw, str):
                raw = json.loads(raw)
            agg = raw.get("salesAggregate") or []
            by_asin = raw.get("salesByAsin") or []
            print(f"DIALCOS DAY report: salesAggregate entries={len(agg)} salesByAsin entries={len(by_asin)}")
            for row in agg[:5]:
                print("  agg:", json.dumps(row)[:200])
            dates = sorted({r.get("startDate") for r in agg if isinstance(r, dict)})
            print(f"  distinct agg dates: {len(dates)} first={dates[:3]} last={dates[-3:]}")


asyncio.run(main())
