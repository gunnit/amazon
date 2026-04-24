"""In-process account sync runner.

Replaces the Celery-based sync pipeline for deployments without Redis.
Follows the same private-engine-per-thread pattern as
`market_research_service.process_report_background` because the shared
asyncpg pool is bound to the FastAPI event loop and cannot be reused
safely from a separate thread/loop.
"""
from __future__ import annotations

import asyncio
from datetime import datetime
import logging
import threading
from typing import Iterable, List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings
from app.core.sync_health import classify_sync_exception
from app.db.session import db_url as _db_url
from app.models.amazon_account import AmazonAccount, SyncStatus
from app.services.data_extraction import DataExtractionService

logger = logging.getLogger(__name__)


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


def run_daily_sync_all() -> None:
    """Entrypoint for the scheduler: sync every active account once."""
    engine, session_factory = _make_local_session_factory()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
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
            loop.run_until_complete(engine.dispose())
        finally:
            loop.close()
