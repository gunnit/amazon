"""Celery tasks for scheduled operational reports."""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from workers.celery_app import celery_app

logger = logging.getLogger(__name__)

# A run that has been generated but not delivered, or left mid-processing, for
# longer than this is considered stuck and is recovered by the monitor task.
STUCK_RUN_THRESHOLD = timedelta(minutes=30)


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
def scan_scheduled_reports_due():
    """Find due schedules and enqueue report generation."""
    from app.models.scheduled_report import ScheduledReport
    from app.services.scheduled_report_service import ScheduledReportService, enqueue_scheduled_run_processing
    from datetime import datetime

    async def _scan():
        from app.db import session as db_session
        now = datetime.now(timezone.utc)
        queued = 0
        async with db_session.AsyncSessionLocal() as db:
            result = await db.execute(
                select(ScheduledReport).where(
                    ScheduledReport.is_enabled == True,
                    ScheduledReport.next_run_at.is_not(None),
                    ScheduledReport.next_run_at <= now,
                )
            )
            schedules = result.scalars().all()
            service = ScheduledReportService(db)
            for schedule in schedules:
                run = await service.create_run(schedule, now)
                queued += 1
                enqueue_scheduled_run_processing(str(run.id))
            await db.commit()
        return {"queued": queued}

    return run_async(_scan)


@celery_app.task(bind=True, max_retries=2)
def process_scheduled_report_run_task(self, run_id: str):
    """Generate the scheduled report artifact."""
    from app.services.scheduled_report_service import process_scheduled_report_run_job

    try:
        process_scheduled_report_run_job(run_id)
    except Exception as exc:
        logger.exception("Scheduled report processing failed for %s", run_id)
        raise self.retry(exc=exc, countdown=60)


@celery_app.task(bind=True, max_retries=2)
def deliver_scheduled_report_run_task(self, run_id: str):
    """Deliver the generated scheduled report by email."""
    from app.services.scheduled_report_service import deliver_scheduled_report_run_job

    try:
        deliver_scheduled_report_run_job(run_id)
    except Exception as exc:
        logger.exception("Scheduled report delivery failed for %s", run_id)
        raise self.retry(exc=exc, countdown=120)


@celery_app.task
def recover_stuck_scheduled_report_runs():
    """Safety net for runs whose delivery was never (re)queued.

    If processing crashes after retries, or the delivery enqueue is lost, a run
    can be left non-terminal forever. This re-enqueues delivery for generated
    runs and marks runs stuck mid-processing as failed.
    """
    from app.models.scheduled_report import ScheduledReportRun
    from app.services.scheduled_report_service import RUN_TERMINAL_STATUS, utcnow

    async def _recover():
        from app.db import session as db_session
        from workers.tasks.scheduled_reports import deliver_scheduled_report_run_task

        cutoff = datetime.now(timezone.utc) - STUCK_RUN_THRESHOLD
        redelivered = 0
        failed = 0
        async with db_session.AsyncSessionLocal() as db:
            result = await db.execute(
                select(ScheduledReportRun).where(
                    ScheduledReportRun.status.notin_(tuple(RUN_TERMINAL_STATUS)),
                    ScheduledReportRun.triggered_at <= cutoff,
                )
            )
            runs = result.scalars().all()
            for run in runs:
                if run.generation_status == "generated" and run.delivery_status in ("pending", "processing"):
                    deliver_scheduled_report_run_task.delay(str(run.id))
                    redelivered += 1
                else:
                    run.status = "failed"
                    run.generation_status = "failed"
                    run.delivery_status = "failed"
                    run.error_message = "Run stalled before completion and was failed by the monitor"
                    run.progress_step = "Stalled"
                    run.completed_at = utcnow()
                    failed += 1
            await db.commit()
        return {"redelivered": redelivered, "failed": failed}

    return run_async(_recover)
