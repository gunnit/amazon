"""Data extraction Celery tasks."""
import asyncio
from uuid import UUID
import logging

from workers.celery_app import celery_app
from app.core.exceptions import AmazonAPIError

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

    except AmazonAPIError as e:
        # Do not retry on logic/credential errors
        logger.error(f"SP-API error for account {account_id}: {e.message} (code={e.error_code})")
        if e.error_code in ("MISSING_CREDENTIALS", "AUTH_FAILED", "INVALID_MARKETPLACE"):
            # Mark account as ERROR without retry
            _mark_account_error(account_id, e.message)
            raise
        raise self.retry(exc=e, countdown=300)

    except Exception as e:
        # Check for specific SP-API library exceptions
        exc_name = type(e).__name__
        if exc_name == "SellingApiForbiddenException":
            logger.error(f"SP-API forbidden for account {account_id}: {e}")
            _mark_account_error(account_id, f"Access forbidden: {e}")
            raise

        if exc_name == "SellingApiRequestThrottledException":
            logger.warning(f"SP-API throttled for account {account_id}, retrying in 60s")
            raise self.retry(exc=e, countdown=60)

        if exc_name in (
            "SellingApiServerException",
            "SellingApiTemporarilyUnavailableException",
        ):
            logger.warning(f"SP-API server error for account {account_id}: {e}, retrying in 300s")
            raise self.retry(exc=e, countdown=300)

        logger.exception(f"Sync failed for account {account_id}")
        raise self.retry(exc=e, countdown=300)


def _mark_account_error(account_id: str, error_message: str):
    """Mark an account as ERROR status (no retry)."""
    from app.db.session import AsyncSessionLocal
    from app.models.amazon_account import AmazonAccount, SyncStatus
    from sqlalchemy import select

    async def _update():
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(AmazonAccount).where(AmazonAccount.id == UUID(account_id))
            )
            account = result.scalar_one_or_none()
            if account:
                account.sync_status = SyncStatus.ERROR
                account.sync_error_message = error_message
                await db.commit()

    run_async(_update())


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
            organization = await service._load_organization(account)
            sd = date.fromisoformat(start_date) if start_date else None
            ed = date.fromisoformat(end_date) if end_date else None
            count = await service.sync_sales_data(account, organization, sd, ed)
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
            organization = await service._load_organization(account)
            count = await service.sync_inventory_data(account, organization)
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
            organization = await service._load_organization(account)
            count = await service.sync_advertising_data(account, organization)
            await db.commit()
            return {"records": count}

    return run_async(_sync())
