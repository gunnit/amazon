"""Data extraction Celery tasks."""
import asyncio
from uuid import UUID
import logging

from workers.celery_app import celery_app

logger = logging.getLogger(__name__)


def run_async(coro):
    """Run async function in sync context."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(bind=True, max_retries=3)
def sync_account(self, account_id: str):
    """Sync data for a single account."""
    from app.db.session import AsyncSessionLocal
    from app.services.data_extraction import DataExtractionService

    async def _sync():
        async with AsyncSessionLocal() as db:
            service = DataExtractionService(db)
            result = await service.sync_account(UUID(account_id))
            await db.commit()
            return result

    try:
        logger.info(f"Starting sync for account {account_id}")
        result = run_async(_sync())
        logger.info(f"Sync completed for account {account_id}: {result}")
        return result

    except Exception as e:
        logger.exception(f"Sync failed for account {account_id}")
        raise self.retry(exc=e, countdown=300)  # Retry in 5 minutes


@celery_app.task
def sync_all_accounts():
    """Sync all active accounts."""
    from app.db.session import AsyncSessionLocal
    from app.models.amazon_account import AmazonAccount
    from sqlalchemy import select

    async def _get_account_ids():
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(AmazonAccount.id)
                .where(AmazonAccount.is_active == True)
            )
            return [str(row[0]) for row in result.all()]

    account_ids = run_async(_get_account_ids())
    logger.info(f"Scheduling sync for {len(account_ids)} accounts")

    for account_id in account_ids:
        sync_account.delay(account_id)

    return {"scheduled": len(account_ids)}


@celery_app.task
def sync_sales_data(account_id: str, start_date: str = None, end_date: str = None):
    """Sync sales data for an account."""
    from app.db.session import AsyncSessionLocal
    from app.services.data_extraction import DataExtractionService
    from app.models.amazon_account import AmazonAccount
    from datetime import date
    from sqlalchemy import select

    async def _sync():
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(AmazonAccount).where(AmazonAccount.id == UUID(account_id))
            )
            account = result.scalar_one_or_none()

            if not account:
                raise ValueError(f"Account {account_id} not found")

            service = DataExtractionService(db)
            sd = date.fromisoformat(start_date) if start_date else None
            ed = date.fromisoformat(end_date) if end_date else None
            count = await service.sync_sales_data(account, sd, ed)
            await db.commit()
            return {"records": count}

    return run_async(_sync())


@celery_app.task
def sync_inventory_data(account_id: str):
    """Sync inventory data for an account."""
    from app.db.session import AsyncSessionLocal
    from app.services.data_extraction import DataExtractionService
    from app.models.amazon_account import AmazonAccount
    from sqlalchemy import select

    async def _sync():
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(AmazonAccount).where(AmazonAccount.id == UUID(account_id))
            )
            account = result.scalar_one_or_none()

            if not account:
                raise ValueError(f"Account {account_id} not found")

            service = DataExtractionService(db)
            count = await service.sync_inventory_data(account)
            await db.commit()
            return {"records": count}

    return run_async(_sync())


@celery_app.task
def sync_advertising_data(account_id: str):
    """Sync advertising data for an account."""
    from app.db.session import AsyncSessionLocal
    from app.services.data_extraction import DataExtractionService
    from app.models.amazon_account import AmazonAccount
    from sqlalchemy import select

    async def _sync():
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(AmazonAccount).where(AmazonAccount.id == UUID(account_id))
            )
            account = result.scalar_one_or_none()

            if not account:
                raise ValueError(f"Account {account_id} not found")

            service = DataExtractionService(db)
            count = await service.sync_advertising_data(account)
            await db.commit()
            return {"records": count}

    return run_async(_sync())
