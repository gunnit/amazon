"""Celery tasks for scheduled operational reports."""
import asyncio
import logging
from datetime import timezone

from sqlalchemy import select

from workers.celery_app import celery_app

logger = logging.getLogger(__name__)


def run_async(coro):
    """Run async code inside sync Celery tasks."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task
def scan_scheduled_reports_due():
    """Find due schedules and enqueue report generation."""
    from app.db.session import AsyncSessionLocal
    from app.models.scheduled_report import ScheduledReport
    from app.services.scheduled_report_service import ScheduledReportService, enqueue_scheduled_run_processing
    from datetime import datetime

    async def _scan():
        now = datetime.now(timezone.utc)
        queued = 0
        async with AsyncSessionLocal() as db:
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

    return run_async(_scan())


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
