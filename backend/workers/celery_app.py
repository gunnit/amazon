"""Celery application configuration."""
from celery import Celery
from celery.schedules import crontab
from celery.signals import setup_logging
import os

# Get Redis URL from environment
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/1")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/2")


@setup_logging.connect
def _configure_worker_logging(**kwargs):
    """Install JSON-structured logging + Sentry on Celery workers.

    Celery normally clobbers logging config after worker boot; the
    `setup_logging` signal is the documented way to take over fully.
    Imports are lazy so commands that introspect celery_app (e.g.
    `celery -A workers.celery_app inspect ...`) without a configured
    `DATABASE_URL` still work for ops debugging.
    """
    from app.observability import configure_logging, init_sentry

    configure_logging("inthezon-worker")
    init_sentry("inthezon-worker")

# Create Celery app
celery_app = Celery(
    "inthezon",
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND,
    include=[
        "workers.tasks.extraction",
        "workers.tasks.forecasting",
        "workers.tasks.forecast_exports",
        "workers.tasks.notifications",
        "workers.tasks.market_research",
        "workers.tasks.competitor_refresh",
        "workers.tasks.scheduled_reports",
        "workers.tasks.google_sheets",
        "workers.tasks.maintenance",
        "workers.tasks.strategic_recommendations",
        "workers.tasks.brand_analysis",
        "workers.tasks.brand_intelligence",
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
    # Enforce time-series retention weekly on Sunday at 4 AM
    "weekly-data-retention": {
        "task": "workers.tasks.maintenance.manage_data_retention",
        "schedule": crontab(hour=4, minute=0, day_of_week=0),
    },
    # Ensure next monthly partitions exist daily at 03:30
    "daily-partition-management": {
        "task": "workers.tasks.maintenance.manage_partitions",
        "schedule": crontab(hour=3, minute=30),
    },
    # Refresh stale tracked competitors daily at 5 AM UTC
    "daily-competitor-refresh": {
        "task": "workers.tasks.competitor_refresh.refresh_tracked_competitors",
        "schedule": crontab(hour=5, minute=0),
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
    # Poll recurring operational reports every 5 minutes
    "scheduled-report-scan": {
        "task": "workers.tasks.scheduled_reports.scan_scheduled_reports_due",
        "schedule": crontab(minute="*/5"),
    },
    # Recover scheduled report runs stuck without delivery every 15 minutes
    "scheduled-report-recovery": {
        "task": "workers.tasks.scheduled_reports.recover_stuck_scheduled_report_runs",
        "schedule": crontab(minute="*/15"),
    },
    # Recover brand analysis jobs stalled mid-run every 10 minutes
    "brand-analysis-recovery": {
        "task": "workers.tasks.brand_analysis.recover_stuck_brand_analysis_jobs",
        "schedule": crontab(minute="*/10"),
    },
    # Poll Google Sheets syncs every 5 minutes
    "google-sheets-sync-scan": {
        "task": "workers.tasks.google_sheets.scan_google_sheets_syncs_due",
        "schedule": crontab(minute="*/5"),
    },
    # Generate weekly strategic recommendations on Monday at 6 AM
    "weekly-strategic-recommendations": {
        "task": "workers.tasks.strategic_recommendations.generate_weekly_recommendations",
        "schedule": crontab(hour=6, minute=0, day_of_week=1),
    },
    # Poll due weekly Brand Intelligence schedules every 15 minutes
    "brand-intelligence-scan": {
        "task": "workers.tasks.brand_intelligence.scan_brand_intelligence_due",
        "schedule": crontab(minute="*/15"),
    },
    # Recover Brand Intelligence runs stalled mid-pipeline every 30 minutes
    "brand-intelligence-recovery": {
        "task": "workers.tasks.brand_intelligence.recover_stuck_brand_intelligence_runs",
        "schedule": crontab(minute="*/30"),
    },
}

if __name__ == "__main__":
    celery_app.start()
