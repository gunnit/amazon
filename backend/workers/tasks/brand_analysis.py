"""Celery task wrapper for Brand Analysis Automation."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from workers.celery_app import celery_app
from workers.tasks.scheduled_reports import run_async

logger = logging.getLogger(__name__)

# A running job whose heartbeat is older than this is considered stalled
# (worker crash / lost task) and is finalized by the recovery task.
STUCK_JOB_THRESHOLD = timedelta(minutes=20)


@celery_app.task(bind=True, max_retries=1)
def process_brand_analysis(self, job_id: str):
    """Dispatch brand analysis processing through the shared service logic."""
    from app.services.brand_analysis_service import process_brand_analysis_job

    try:
        process_brand_analysis_job(job_id)
    except Exception as exc:
        logger.exception("Brand analysis task failed for %s", job_id)
        raise self.retry(exc=exc, countdown=60)


@celery_app.task
def recover_stuck_brand_analysis_jobs():
    """Finalize brand analysis jobs whose worker stalled mid-run.

    A crash between phase updates leaves a job wedged in a running status with
    a stale heartbeat and the UI polling forever. This force-finalizes those
    rows: cancellation-requested jobs become ``cancelled``, the rest ``failed``.
    Uses the (status, heartbeat_at) index added in migration 029.
    """
    from app.models.brand_analysis import BrandAnalysisJob
    from app.services.brand_analysis_service import RUNNING_STATUSES

    async def _recover():
        from app.db import session as db_session

        cutoff = datetime.now(timezone.utc) - STUCK_JOB_THRESHOLD
        cancelled = 0
        failed = 0
        async with db_session.AsyncSessionLocal() as db:
            result = await db.execute(
                select(BrandAnalysisJob).where(
                    BrandAnalysisJob.status.in_(tuple(RUNNING_STATUSES)),
                    BrandAnalysisJob.heartbeat_at.is_not(None),
                    BrandAnalysisJob.heartbeat_at <= cutoff,
                )
            )
            now = datetime.utcnow()
            for job in result.scalars().all():
                if job.cancel_requested:
                    job.status = "cancelled"
                    job.progress_step = "Cancelled by user"
                    job.error_message = None
                    cancelled += 1
                else:
                    job.status = "failed"
                    job.progress_step = "Stalled"
                    job.error_message = "Job stalled before completion and was failed by the monitor"
                    failed += 1
                job.progress_pct = 100
                job.completed_at = now
                job.updated_at = now
                job.heartbeat_at = now
            await db.commit()
        return {"cancelled": cancelled, "failed": failed}

    return run_async(_recover)
