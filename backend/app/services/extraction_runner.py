"""In-process account sync runner.

Replaces the Celery-based sync pipeline for deployments without Redis.
Follows the same private-engine-per-thread pattern as
`market_research_service.process_report_background` because the shared
asyncpg pool is bound to the FastAPI event loop and cannot be reused
safely from a separate thread/loop.
"""
from __future__ import annotations

import asyncio
from calendar import monthrange
from datetime import date, datetime
import logging
import threading
from typing import Iterable, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.sync_health import classify_sync_exception
from app.db.session import db_url as _db_url
from app.models.amazon_account import AccountType, AmazonAccount, SyncStatus
from app.services.data_extraction import DataExtractionService

logger = logging.getLogger(__name__)

# A freshly connected account gets the maximum historical sales window Amazon
# allows so dashboards and forecasts have enough history immediately.
DEFAULT_BACKFILL_MONTHS = 24

# Prevent the daily full sync and the lighter intraday sales refresh from
# competing for the same Amazon Reports API quota.
_SCHEDULED_SYNC_LOCK = threading.Lock()


def _subtract_calendar_months(value: date, months: int) -> date:
    """Shift a date backward by calendar months, preserving the day when possible."""
    year = value.year
    month = value.month - months
    while month <= 0:
        month += 12
        year -= 1
    day = min(value.day, monthrange(year, month)[1])
    return date(year, month, day)


def _make_local_session_factory():
    engine = create_async_engine(
        _db_url,
        echo=False,
        pool_size=2,
        max_overflow=1,
    )
    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
    return engine, session_factory


async def _persist_sync_failure_state(account_id: UUID, session_factory, exc: Exception) -> None:
    """Persist failure metadata for in-process syncs, which do not have Celery retries."""
    decision = classify_sync_exception(exc)
    async with session_factory() as db:
        result = await db.execute(select(AmazonAccount).where(AmazonAccount.id == account_id))
        account = result.scalar_one_or_none()
        if account is None:
            return

        failure_at = datetime.utcnow()
        account.last_sync_failed_at = failure_at
        account.last_sync_heartbeat_at = failure_at
        account.sync_error_message = str(exc)
        account.sync_error_kind = decision.kind
        account.sync_error_code = decision.error_code
        account.sync_status = SyncStatus.ERROR
        await db.commit()


async def _sync_one(account_id: UUID, session_factory) -> None:
    async with session_factory() as db:
        service = DataExtractionService(db)
        try:
            result = await service.sync_account(account_id)
            await db.commit()
            logger.info(
                "In-process sync completed for %s: %s",
                account_id,
                {k: v for k, v in result.items() if k != "status"},
            )
        except Exception as exc:
            try:
                await db.rollback()
            except Exception:
                pass
            await _persist_sync_failure_state(account_id, session_factory, exc)
            logger.exception("In-process sync failed for %s", account_id)


def _run_sync(account_ids: List[UUID]) -> None:
    engine, session_factory = _make_local_session_factory()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        for account_id in account_ids:
            loop.run_until_complete(_sync_one(account_id, session_factory))
    finally:
        try:
            loop.run_until_complete(engine.dispose())
        finally:
            loop.close()


def sync_account_in_thread(account_id: UUID) -> None:
    """Fire-and-forget sync of a single account in a daemon thread."""
    thread = threading.Thread(
        target=_run_sync,
        args=([account_id],),
        name=f"sync-{account_id}",
        daemon=True,
    )
    thread.start()


def sync_accounts_in_thread(account_ids: Iterable[UUID]) -> None:
    """Fire-and-forget sync of many accounts in a single daemon thread."""
    ids = list(account_ids)
    if not ids:
        return
    thread = threading.Thread(
        target=_run_sync,
        args=(ids,),
        name=f"sync-batch-{len(ids)}",
        daemon=True,
    )
    thread.start()


# ---------------------------------------------------------------------------
# Initial sync + historical backfill (first connect / on-demand re-backfill)
# ---------------------------------------------------------------------------


def _resolve_backfill_window(months: int, *, today: Optional[date] = None) -> Tuple[date, date]:
    """[start, end] for a backfill ``months`` deep, clamped to SP-API's 2-year cap."""
    end_date = today or date.today()
    earliest = _subtract_calendar_months(end_date, DEFAULT_BACKFILL_MONTHS)
    start_date = max(_subtract_calendar_months(end_date, months), earliest)
    return start_date, end_date


async def _initial_sync_one(account_id: UUID, backfill_months: int, session_factory) -> None:
    """First-connect pipeline: a full current sync, then a historical sales
    backfill. Phase 1 stamps account status and fetches current
    inventory/orders/ads/products + recent sales; phase 2 fills older sales
    history for forecasting. The backfill is best-effort and never downgrades a
    successful sync."""
    # Phase 1 — full current sync (also sets sync_status / error state).
    async with session_factory() as db:
        service = DataExtractionService(db)
        try:
            result = await service.sync_account(account_id)
            await db.commit()
            logger.info(
                "Initial sync completed for %s: %s",
                account_id,
                {k: v for k, v in result.items() if k != "status"},
            )
        except Exception as exc:
            try:
                await db.rollback()
            except Exception:
                pass
            await _persist_sync_failure_state(account_id, session_factory, exc)
            logger.exception("Initial sync failed for %s; skipping backfill", account_id)
            return

    # Phase 2 — historical sales backfill (best-effort; commits per month).
    async with session_factory() as db:
        result = await db.execute(select(AmazonAccount).where(AmazonAccount.id == account_id))
        account = result.scalar_one_or_none()
        if account is None:
            return
        service = DataExtractionService(db)
        start_date, end_date = _resolve_backfill_window(backfill_months)
        try:
            organization = await service._load_organization(account)
            if account.account_type == AccountType.VENDOR:
                count = await service.backfill_vendor_sales_data(
                    account, organization, start_date=start_date, end_date=end_date
                )
            else:
                count = await service.backfill_sales_data(
                    account, organization, start_date=start_date, end_date=end_date
                )
            logger.info(
                "Historical backfill completed for %s: %d records (%s..%s)",
                account_id, count, start_date, end_date,
            )
        except Exception:
            try:
                await db.rollback()
            except Exception:
                pass
            logger.exception(
                "Historical backfill failed for %s (current sync already succeeded)",
                account_id,
            )


def _run_initial_sync(account_id: UUID, backfill_months: int) -> None:
    engine, session_factory = _make_local_session_factory()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(
            _initial_sync_one(account_id, backfill_months, session_factory)
        )
    finally:
        try:
            loop.run_until_complete(engine.dispose())
        finally:
            loop.close()


def initial_sync_in_thread(
    account_id: UUID, backfill_months: int = DEFAULT_BACKFILL_MONTHS
) -> None:
    """Fire-and-forget first-connect sync + historical backfill in a daemon thread."""
    thread = threading.Thread(
        target=_run_initial_sync,
        args=(account_id, backfill_months),
        name=f"initial-sync-{account_id}",
        daemon=True,
    )
    thread.start()


async def list_active_account_ids(
    db: AsyncSession,
    organization_id: Optional[UUID] = None,
) -> List[UUID]:
    """Return ids of active accounts, optionally scoped to one organization."""
    stmt = select(AmazonAccount.id).where(AmazonAccount.is_active.is_(True))
    if organization_id is not None:
        stmt = stmt.where(AmazonAccount.organization_id == organization_id)
    result = await db.execute(stmt)
    return [row[0] for row in result.all()]


async def list_active_seller_account_ids(db: AsyncSession) -> List[UUID]:
    """Return active seller account ids for the lightweight sales refresh."""
    result = await db.execute(
        select(AmazonAccount.id).where(
            AmazonAccount.is_active.is_(True),
            AmazonAccount.account_type == AccountType.SELLER,
        )
    )
    return [row[0] for row in result.all()]


async def _refresh_recent_seller_sales(account_id: UUID, session_factory) -> int:
    """Refresh the rolling seller Sales & Traffic window without a full account sync."""
    async with session_factory() as db:
        result = await db.execute(select(AmazonAccount).where(AmazonAccount.id == account_id))
        account = result.scalar_one_or_none()
        if account is None:
            return 0

        service = DataExtractionService(db)
        try:
            organization = await service._load_organization(account)
            count = await service.sync_sales_data(account, organization)
            await db.commit()
            logger.info(
                "Recent seller sales refresh completed for %s: %d records",
                account.account_name,
                count,
            )
            return count
        except Exception:
            try:
                await db.rollback()
            except Exception:
                pass
            logger.exception("Recent seller sales refresh failed for %s", account.account_name)
            return 0


def run_recent_seller_sales_sync_all() -> dict:
    """Refresh recent seller sales several times daily as Amazon publishes them."""
    if not _SCHEDULED_SYNC_LOCK.acquire(blocking=False):
        logger.info("Recent seller sales refresh skipped: another scheduled sync is running")
        return {"status": "skipped", "accounts": 0, "records": 0}

    engine = None
    loop = None
    try:
        engine, session_factory = _make_local_session_factory()
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        async def _collect() -> List[UUID]:
            async with session_factory() as db:
                return await list_active_seller_account_ids(db)

        account_ids = loop.run_until_complete(_collect())
        logger.info("Recent seller sales refresh: starting %d accounts", len(account_ids))
        records = 0
        for account_id in account_ids:
            records += loop.run_until_complete(
                _refresh_recent_seller_sales(account_id, session_factory)
            )
        logger.info(
            "Recent seller sales refresh: finished %d accounts, %d records",
            len(account_ids),
            records,
        )
        return {"status": "success", "accounts": len(account_ids), "records": records}
    finally:
        try:
            if loop is not None and engine is not None:
                loop.run_until_complete(engine.dispose())
        finally:
            if loop is not None:
                loop.close()
            _SCHEDULED_SYNC_LOCK.release()


def run_daily_sync_all() -> None:
    """Entrypoint for the scheduler: sync every active account once."""
    if not _SCHEDULED_SYNC_LOCK.acquire(blocking=False):
        logger.info("Daily sync skipped: another scheduled sync is running")
        return

    engine = None
    loop = None
    try:
        engine, session_factory = _make_local_session_factory()
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        async def _collect() -> List[UUID]:
            async with session_factory() as db:
                return await list_active_account_ids(db)

        account_ids = loop.run_until_complete(_collect())
        if not account_ids:
            logger.info("Daily sync: no active accounts")
            return
        logger.info("Daily sync: starting %d accounts", len(account_ids))
        for account_id in account_ids:
            loop.run_until_complete(_sync_one(account_id, session_factory))
        logger.info("Daily sync: finished")
    finally:
        try:
            if loop is not None and engine is not None:
                loop.run_until_complete(engine.dispose())
        finally:
            if loop is not None:
                loop.close()
            _SCHEDULED_SYNC_LOCK.release()
