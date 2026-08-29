"""One-off: finish Dialcos daily history — 2024-09 gap + 2025-06 onwards."""
import asyncio
import sys
from datetime import date, datetime

sys.path.insert(0, "/app")

from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models.amazon_account import AmazonAccount

DIALCOS = "5d89b2d9-4760-4659-821a-16cceee61425"
RANGES = [
    (date(2024, 9, 1), date(2024, 9, 30)),
    (date(2025, 6, 1), date.today()),
]


async def main():
    async with AsyncSessionLocal() as db:
        from app.services.data_extraction import DataExtractionService

        svc = DataExtractionService(db)
        acc = (
            await db.execute(select(AmazonAccount).where(AmazonAccount.id == DIALCOS))
        ).scalar_one()
        org = await svc._load_organization(acc)
        for start, end in RANGES:
            print(f"RANGE_START {start}..{end} {datetime.utcnow().isoformat()}", flush=True)
            total = await svc.backfill_vendor_sales_data(acc, org, start_date=start, end_date=end)
            print(f"RANGE_DONE {start}..{end} records={total} skipped={svc.backfill_windows_skipped}", flush=True)
        print("ALL_DONE", flush=True)


asyncio.run(main())
