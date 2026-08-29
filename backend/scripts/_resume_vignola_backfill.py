"""Resume Vignola's seller backfill from where the deploy restart killed it."""
import asyncio
import sys
from datetime import date, datetime

sys.path.insert(0, "/app")

from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models.amazon_account import AmazonAccount


async def main():
    from app.services.data_extraction import DataExtractionService

    async with AsyncSessionLocal() as db:
        account = (
            await db.execute(select(AmazonAccount).where(AmazonAccount.account_name == "VIGNOLA"))
        ).scalar_one()
        svc = DataExtractionService(db)
        org = await svc._load_organization(account)
        start, end = date(2024, 10, 1), date.today()
        print(f"resuming backfill {start}..{end}", flush=True)
        count = await svc.backfill_sales_data(account, org, start_date=start, end_date=end)
        skipped = svc.backfill_windows_skipped
        account = (
            await db.execute(select(AmazonAccount).where(AmazonAccount.id == account.id))
        ).scalar_one()
        account.last_backfill_status = "partial" if skipped else "success"
        account.last_backfill_completed_at = datetime.utcnow()
        account.last_backfill_records = count
        account.last_backfill_windows_skipped = skipped
        account.last_backfill_error = None
        await db.commit()
        print(f"DONE records={count} windows_skipped={skipped}", flush=True)


asyncio.run(main())
