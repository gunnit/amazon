"""Celery task wrapper for forecast export package generation."""
import logging

from workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=2)
def process_forecast_export(self, job_id: str):
    """Dispatch forecast export package processing."""
    from app.services.forecast_export_service import process_forecast_export_job

    try:
        process_forecast_export_job(job_id)
    except Exception as exc:
        logger.exception("Forecast export task failed for %s", job_id)
        raise self.retry(exc=exc, countdown=60)
