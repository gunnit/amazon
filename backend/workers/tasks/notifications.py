"""Notification Celery tasks.

The evaluation/delivery/digest logic lives in
``app.services.alert_check_service`` so the in-process APScheduler
deployment (prod has no Celery) runs the exact same code. These tasks are
thin wrappers for deployments that do run a worker.
"""
import logging

from workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task
def send_daily_digests():
    """Send daily digest emails to all users."""
    from app.services.alert_check_service import run_daily_digest

    return run_daily_digest()


@celery_app.task
def check_alerts():
    """Check all alert rules, create alerts, and deliver notifications."""
    from app.services.alert_check_service import run_alert_check

    return run_alert_check()
