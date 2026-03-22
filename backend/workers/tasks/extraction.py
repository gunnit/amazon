"""Data extraction Celery tasks."""
import asyncio
from uuid import UUID
import logging

from workers.celery_app import celery_app
from app.core.exceptions import AmazonAPIError

logger = logging.getLogger(__name__)


def run_async(coro):
    """Run async function in sync context with a fresh event loop.

    Disposes the shared engine afterwards so that asyncpg connections
    don't leak across event loops in the Celery worker process.
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        # Dispose the shared engine to release asyncpg connections tied
        # to this loop — prevents "Future attached to a different loop"
        # errors on subsequent calls within the same Celery worker.
        try:
            from app.db.session import engine
            loop.run_until_complete(engine.dispose())
        except Exception:
            pass
        loop.close()


@celery_app.task(bind=True, max_retries=3)
def sync_account(self, account_id: str):
    """Sync data for a single account."""
    from app.db.session import AsyncSessionLocal
    from app.services.data_extraction import DataExtractionService

    async def _sync():
        async with AsyncSessionLocal() as db:
            service = DataExtractionService(db)
            try:
                result = await service.sync_account(UUID(account_id))
                await db.commit()
                return result
            except Exception:
                # sync_account sets ERROR status via flush(); commit it
                # before the exception propagates so the status is persisted.
                await db.commit()
                raise

    try:
        logger.info(f"Starting sync for account {account_id}")
        result = run_async(_sync())
        logger.info(f"Sync completed for account {account_id}: {result}")
        return result

    except AmazonAPIError as e:
        logger.error(
            f"SP-API error for account {account_id}: "
            f"{e.message} (code={e.error_code})"
        )
        if e.error_code in ("MISSING_CREDENTIALS", "AUTH_FAILED", "INVALID_MARKETPLACE"):
            raise  # Error status already committed by _sync
        raise self.retry(exc=e, countdown=300)

    except Exception as e:
        exc_name = type(e).__name__
        if exc_name == "SellingApiForbiddenException":
            logger.error(f"SP-API forbidden for account {account_id}: {e}")
            raise  # Error status already committed by _sync

        if exc_name == "SellingApiRequestThrottledException":
            logger.warning(f"SP-API throttled for account {account_id}, retrying in 60s")
            raise self.retry(exc=e, countdown=60)

        if exc_name in (
            "SellingApiServerException",
            "SellingApiTemporarilyUnavailableException",
        ):
            logger.warning(
                f"SP-API server error for account {account_id}: {e}, retrying in 300s"
            )
            raise self.retry(exc=e, countdown=300)

        logger.exception(f"Sync failed for account {account_id}")
        raise self.retry(exc=e, countdown=300)


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
            from app.models.amazon_account import AccountType
            if account.account_type == AccountType.VENDOR:
                count = await service.sync_vendor_sales_data(account, organization, sd, ed)
            else:
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
            from app.models.amazon_account import AccountType
            if account.account_type == AccountType.VENDOR:
                logger.info(f"Skipping FBA inventory sync for vendor account {account_id}")
                count = 0
            else:
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
