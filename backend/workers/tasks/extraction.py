"""Data extraction Celery tasks."""
from __future__ import annotations

import asyncio
from datetime import datetime
from uuid import UUID
import logging

from workers.celery_app import celery_app
from app.core.sync_health import classify_sync_exception
from app.core.exceptions import AmazonAPIError

logger = logging.getLogger(__name__)


def run_async(coro_factory):
    """Run an async function in sync context with a fresh event loop.

    Takes a zero-arg callable that returns a coroutine. The callable is
    invoked *after* a fresh engine/session factory is installed so that
    asyncpg futures created inside the coroutine are bound to this loop.

    Disposes the shared engine afterwards to release asyncpg connections
    tied to the loop — prevents "Future attached to a different loop"
    errors on subsequent calls within the same Celery worker.
    """
    from app.db.session import reset_engine_for_worker

    # Install a fresh engine + session factory for this task's loop.
    reset_engine_for_worker()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro_factory())
    finally:
        try:
            from app.db.session import engine
            loop.run_until_complete(engine.dispose())
        except Exception:
            pass
        loop.close()


async def _persist_sync_failure_state(account_id: str, exc: Exception, kind: str, error_code: str | None = None):
    """Persist failure metadata without losing retry context."""
    from app.db import session as db_session
    from app.models.amazon_account import AmazonAccount, SyncStatus
    from sqlalchemy import select

    async with db_session.AsyncSessionLocal() as db:
        result = await db.execute(
            select(AmazonAccount).where(AmazonAccount.id == UUID(account_id))
        )
        account = result.scalar_one_or_none()
        if account is None:
            return

        failure_at = datetime.utcnow()
        account.last_sync_failed_at = failure_at
        account.last_sync_heartbeat_at = failure_at
        account.sync_error_message = str(exc)
        account.sync_error_kind = kind
        account.sync_error_code = error_code
        account.sync_status = SyncStatus.ERROR if kind == "terminal" else SyncStatus.SYNCING
        await db.commit()


@celery_app.task(bind=True, max_retries=3)
def sync_account(self, account_id: str):
    """Sync data for a single account."""
    from app.services.data_extraction import DataExtractionService

    async def _sync():
        from app.db import session as db_session
        async with db_session.AsyncSessionLocal() as db:
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
        result = run_async(_sync)
        logger.info(f"Sync completed for account {account_id}: {result}")
        return result

    except Exception as e:
        decision = classify_sync_exception(e, retries=self.request.retries, max_retries=self.max_retries)
        run_async(lambda: _persist_sync_failure_state(account_id, e, decision.kind, decision.error_code))

        if decision.kind == "terminal":
            logger.error(f"Sync failed permanently for account {account_id}: {e}")
            raise

        logger.warning(
            f"Sync failed transiently for account {account_id}: {e}. "
            f"Retrying in {decision.retry_delay}s"
        )
        raise self.retry(exc=e, countdown=decision.retry_delay)


@celery_app.task
def sync_all_accounts():
    """Sync all active accounts."""
    from app.models.amazon_account import AmazonAccount
    from sqlalchemy import select

    async def _get_account_ids():
        from app.db import session as db_session
        async with db_session.AsyncSessionLocal() as db:
            result = await db.execute(
                select(AmazonAccount.id)
                .where(AmazonAccount.is_active == True)
            )
            return [str(row[0]) for row in result.all()]

    account_ids = run_async(_get_account_ids)
    logger.info(f"Scheduling sync for {len(account_ids)} accounts")

    for account_id in account_ids:
        sync_account.delay(account_id)

    return {"scheduled": len(account_ids)}


@celery_app.task
def sync_sales_data(account_id: str, start_date: str = None, end_date: str = None):
    """Sync sales data for an account."""
    from app.services.data_extraction import DataExtractionService
    from app.models.amazon_account import AmazonAccount
    from datetime import date
    from sqlalchemy import select

    async def _sync():
        from app.db import session as db_session
        async with db_session.AsyncSessionLocal() as db:
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

    return run_async(_sync)


@celery_app.task
def sync_inventory_data(account_id: str):
    """Sync inventory data for an account."""
    from app.services.data_extraction import DataExtractionService
    from app.models.amazon_account import AmazonAccount
    from sqlalchemy import select

    async def _sync():
        from app.db import session as db_session
        async with db_session.AsyncSessionLocal() as db:
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
                count = await service.sync_inventory(account, organization)
            await db.commit()
            return {"records": count}

    return run_async(_sync)


@celery_app.task
def sync_advertising_data(account_id: str):
    """Sync advertising data for an account."""
    from app.services.data_extraction import DataExtractionService
    from app.models.amazon_account import AmazonAccount
    from sqlalchemy import select

    async def _sync():
        from app.db import session as db_session
        async with db_session.AsyncSessionLocal() as db:
            result = await db.execute(
                select(AmazonAccount).where(AmazonAccount.id == UUID(account_id))
            )
            account = result.scalar_one_or_none()

            if not account:
                raise ValueError(f"Account {account_id} not found")

            service = DataExtractionService(db)
            organization = await service._load_organization(account)
            count = await service.sync_advertising(account, organization)
            await db.commit()
            return {"records": count}

    return run_async(_sync)
