"""Celery tasks for Weekly Brand Intelligence.

Mirrors the scheduled-reports machinery: a beat scanner enqueues due weekly
schedules, a per-report processor runs the aggregate->diff->generate pipeline,
and a recovery task force-finalizes runs whose worker stalled mid-pipeline.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from workers.celery_app import celery_app
from workers.tasks.scheduled_reports import run_async

logger = logging.getLogger(__name__)

# A run whose heartbeat is older than this is considered stalled and finalized.
STUCK_REPORT_THRESHOLD = timedelta(minutes=20)


@celery_app.task(bind=True, max_retries=1)
def process_brand_intelligence_report(self, report_id: str):
    """Run the brand-intelligence pipeline for one persisted report."""
    from app.services.brand_intelligence_service import process_brand_intelligence_report_job

    try:
        process_brand_intelligence_report_job(report_id)
    except Exception as exc:
        logger.exception("Brand intelligence task failed for %s", report_id)
        raise self.retry(exc=exc, countdown=60)


@celery_app.task
def scan_brand_intelligence_due():
    """Find enabled weekly schedules that are due and enqueue a report run."""
    from app.models.brand_intelligence import BrandIntelligenceSchedule
    from app.services.brand_intelligence_service import (
        BrandIntelligenceService,
        compute_next_weekly_run,
        resolve_week_period,
    )

    async def _scan():
        from app.db import session as db_session
        from workers.tasks.brand_intelligence import process_brand_intelligence_report

        now = datetime.now(timezone.utc)
        queued = 0
        async with db_session.AsyncSessionLocal() as db:
            result = await db.execute(
                select(BrandIntelligenceSchedule).where(
                    BrandIntelligenceSchedule.is_enabled.is_(True),
                    BrandIntelligenceSchedule.next_run_at.is_not(None),
                    BrandIntelligenceSchedule.next_run_at <= now,
                )
            )
            schedules = result.scalars().all()
            service = BrandIntelligenceService(db)
            report_ids = []
            for schedule in schedules:
                account = await service.resolve_account(
                    schedule.organization_id, schedule.account_id
                )
                if account is None:
                    schedule.is_enabled = False
                    continue
                period_start, period_end = resolve_week_period()
                report = await service.create_pending_report(
                    schedule.organization_id,
                    account,
                    period_start=period_start,
                    period_end=period_end,
                    generated_by="scheduler",
                )
                schedule.next_run_at = compute_next_weekly_run(
                    schedule.day_of_week, schedule.timezone
                )
                report_ids.append(str(report.id))
                queued += 1
            await db.commit()

        for report_id in report_ids:
            process_brand_intelligence_report.delay(report_id)
        return {"queued": queued}

    return run_async(_scan)


@celery_app.task
def recover_stuck_brand_intelligence_runs():
    """Force-finalize brand-intelligence runs whose worker stalled mid-pipeline.

    Mirrors ``recover_stuck_scheduled_report_runs``: a crash between phases leaves
    a report wedged in a running status with a stale heartbeat and the UI polling
    forever. Those rows are marked failed.
    """
    from app.models.brand_intelligence import (
        RUNNING_STATUSES,
        STATUS_FAILED,
        BrandIntelligenceReport,
    )

    async def _recover():
        from app.db import session as db_session

        cutoff = datetime.now(timezone.utc) - STUCK_REPORT_THRESHOLD
        failed = 0
        async with db_session.AsyncSessionLocal() as db:
            result = await db.execute(
                select(BrandIntelligenceReport).where(
                    BrandIntelligenceReport.status.in_(tuple(RUNNING_STATUSES)),
                    BrandIntelligenceReport.heartbeat_at.is_not(None),
                    BrandIntelligenceReport.heartbeat_at <= cutoff,
                )
            )
            now = datetime.utcnow()
            for report in result.scalars().all():
                report.status = STATUS_FAILED
                report.error_message = "Run stalled before completion and was failed by the monitor"
                report.heartbeat_at = now
                failed += 1
            await db.commit()
        return {"failed": failed}

    return run_async(_recover)
