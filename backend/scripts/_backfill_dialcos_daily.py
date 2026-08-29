"""One-off: rebuild Dialcos vendor history at daily granularity."""
import asyncio
import sys
from datetime import date, datetime

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
        print(f"start {datetime.utcnow().isoformat()}", flush=True)
        total = await svc.backfill_vendor_sales_data(
            acc, org, start_date=date(2024, 1, 1), end_date=date.today()
        )
        print(f"done {datetime.utcnow().isoformat()}", flush=True)
        print(f"records: {total} windows_skipped: {svc.backfill_windows_skipped}", flush=True)


asyncio.run(main())
