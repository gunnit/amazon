"""Celery tasks for Google Sheets syncs."""
import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select

from workers.celery_app import celery_app

logger = logging.getLogger(__name__)


def run_async(coro_factory):
    """Run async code inside sync Celery tasks.

    Installs a fresh engine/session factory so asyncpg futures created
    inside the coroutine are bound to this loop, then disposes the
    engine afterwards to prevent "Future attached to a different loop"
    errors on later invocations within the same worker process.
    """
    from app.db.session import reset_engine_for_worker

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


@celery_app.task
def scan_google_sheets_syncs_due():
    """Find due Google Sheets syncs and enqueue their runs."""
    from app.models.google_sheets import GoogleSheetsSync
    from app.services.google_sheets_service import (
        GoogleSheetsService,
        enqueue_google_sheets_run_processing,
    )

    async def _scan():
        from app.db import session as db_session
        now = datetime.now(timezone.utc)
        queued = 0
        async with db_session.AsyncSessionLocal() as db:
            result = await db.execute(
                select(GoogleSheetsSync).where(
                    GoogleSheetsSync.is_enabled == True,
                    GoogleSheetsSync.next_run_at.is_not(None),
                    GoogleSheetsSync.next_run_at <= now,
                )
            )
            syncs = result.scalars().all()
            service = GoogleSheetsService(db)
            for sync in syncs:
                run = await service.create_run(sync, reference_time=now)
                queued += 1
                enqueue_google_sheets_run_processing(str(run.id))
            await db.commit()
        return {"queued": queued}

    return run_async(_scan)


@celery_app.task(bind=True, max_retries=2)
def process_google_sheets_sync_task(self, run_id: str):
    """Execute a Google Sheets sync run."""
    from app.services.google_sheets_service import process_google_sheets_sync_job

    try:
        process_google_sheets_sync_job(run_id)
    except Exception as exc:
        logger.exception("Google Sheets sync processing failed for %s", run_id)
        raise self.retry(exc=exc, countdown=120)
