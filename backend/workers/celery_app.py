"""Celery application configuration."""
from celery import Celery
from celery.schedules import crontab
import os

# Get Redis URL from environment
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/1")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/2")

# Create Celery app
celery_app = Celery(
    "inthezon",
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND,
    include=[
        "workers.tasks.extraction",
        "workers.tasks.forecasting",
        "workers.tasks.notifications",
    ],
)

# Configure Celery
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600,  # 1 hour max
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
)

# Configure scheduled tasks (Celery Beat)
celery_app.conf.beat_schedule = {
    # Sync all accounts daily at 2 AM
    "daily-account-sync": {
        "task": "workers.tasks.extraction.sync_all_accounts",
        "schedule": crontab(hour=2, minute=0),
    },
    # Generate forecasts weekly on Sunday at 3 AM
    "weekly-forecasts": {
        "task": "workers.tasks.forecasting.generate_all_forecasts",
        "schedule": crontab(hour=3, minute=0, day_of_week=0),
    },
    # Send daily digest at 8 AM
    "daily-digest": {
        "task": "workers.tasks.notifications.send_daily_digests",
        "schedule": crontab(hour=8, minute=0),
    },
    # Check alerts every hour
    "hourly-alert-check": {
        "task": "workers.tasks.notifications.check_alerts",
        "schedule": crontab(minute=0),
    },
}

if __name__ == "__main__":
    celery_app.start()
