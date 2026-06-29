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
RECOVERABLE_JOB_STATUSES = ("pending",)


def _as_utc_naive(value):
    if value is None:
        return None
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _is_stuck_brand_analysis_job(job, cutoff: datetime) -> bool:
    """Return true when a running job has no recent worker activity.

    Older rows and tasks lost before their first progress update can have no
    heartbeat. Fall back to started_at/updated_at/created_at so they do not
    stay in "preparing" forever.
    """
    from app.services.brand_analysis_service import RUNNING_STATUSES

    if job.status not in RUNNING_STATUSES and job.status not in RECOVERABLE_JOB_STATUSES:
        return False
    activity_at = (
        _as_utc_naive(getattr(job, "heartbeat_at", None))
        or _as_utc_naive(getattr(job, "started_at", None))
        or _as_utc_naive(getattr(job, "updated_at", None))
        or _as_utc_naive(getattr(job, "created_at", None))
    )
    return bool(activity_at and activity_at <= _as_utc_naive(cutoff))


@celery_app.task(bind=True, max_retries=1)
def process_brand_analysis(self, job_id: str):
    """Dispatch brand analysis processing through the shared service logic."""
    from app.services.brand_analysis_service import process_brand_analysis_job

    try:
        process_brand_analysis_job(job_id)
    except Exception as exc:
        logger.exception("Brand analysis task failed for %s", job_id)
        raise self.retry(exc=exc, countdown=60)


async def _recover_stuck_jobs(session_factory) -> dict:
    """Finalize brand analysis jobs whose worker/thread stalled mid-run.

    A crash or web-process restart between phase updates leaves a job wedged in
    a running (or never-picked-up ``pending``) status with a stale heartbeat and
    the UI polling forever. This force-finalizes those rows: cancellation-
    requested jobs become ``cancelled``, the rest ``failed``. Uses the
    (status, heartbeat_at) index added in migration 029.

    Takes a session factory so it can run both inside a Celery worker (shared
    engine via run_async) and inside the API's in-process scheduler, which must
    use a dedicated local engine rather than the live app's shared one.
    """
    from app.models.brand_analysis import BrandAnalysisJob
    from app.services.brand_analysis_service import RUNNING_STATUSES

    now = datetime.utcnow()
    cutoff = now - STUCK_JOB_THRESHOLD
    cancelled = 0
    failed = 0
    async with session_factory() as db:
        result = await db.execute(
            select(BrandAnalysisJob).where(
                BrandAnalysisJob.status.in_(tuple(RUNNING_STATUSES) + RECOVERABLE_JOB_STATUSES),
            )
        )
        for job in result.scalars().all():
            if not _is_stuck_brand_analysis_job(job, cutoff):
                continue
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


@celery_app.task
def recover_stuck_brand_analysis_jobs():
    """Celery entrypoint for the stuck-job recovery sweep."""

    async def _run():
        from app.db import session as db_session

        return await _recover_stuck_jobs(db_session.AsyncSessionLocal)

    return run_async(_run)
