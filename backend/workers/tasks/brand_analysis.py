"""Celery task wrapper for Brand Analysis Automation."""
from __future__ import annotations

import logging

from workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=1)
def process_brand_analysis(self, job_id: str):
    """Dispatch brand analysis processing through the shared service logic."""
    from app.services.brand_analysis_service import process_brand_analysis_job

    try:
        process_brand_analysis_job(job_id)
    except Exception as exc:
        logger.exception("Brand analysis task failed for %s", job_id)
        raise self.retry(exc=exc, countdown=60)
