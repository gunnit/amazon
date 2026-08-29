"""One-off: run the new daily vendor sync for Dialcos over a recent window."""
import asyncio
import sys
from datetime import date

sys.path.insert(0, "/app")

from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models.amazon_account import AmazonAccount

DIALCOS = "5d89b2d9-4760-4659-821a-16cceee61425"


async def main():
    async with AsyncSessionLocal() as db:
        from app.services.data_extraction import DataExtractionService

        svc = DataExtractionService(db)
        acc = (
            await db.execute(select(AmazonAccount).where(AmazonAccount.id == DIALCOS))
        ).scalar_one()
        org = await svc._load_organization(acc)
        count = await svc.sync_vendor_sales_data(
            acc, org, start_date=date(2026, 5, 20), end_date=date(2026, 6, 11)
        )
        await db.commit()
        print(f"records written: {count}")
        print(f"fallback used: {svc.vendor_sales_used_po_fallback}")
        print(f"windows skipped: {svc.vendor_sales_months_skipped}")


asyncio.run(main())
