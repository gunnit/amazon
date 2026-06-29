"""Application configuration settings."""
from typing import Optional, List
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Application
    APP_ENV: str = "development"
    APP_DEBUG: bool = False
    APP_SECRET_KEY: str = "your-secret-key-change-in-production-min-32-chars"
    APP_API_URL: str = "http://localhost:8000"
    APP_FRONTEND_URL: str = "http://localhost:5173"

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/inthezon"
    DATABASE_POOL_SIZE: int = 20
    DATABASE_MAX_OVERFLOW: int = 10

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

    # JWT
    JWT_SECRET_KEY: str = "your-jwt-secret-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Amazon SP-API
    AMAZON_SP_API_APP_ID: Optional[str] = None
    AMAZON_SP_API_CLIENT_ID: Optional[str] = None
    AMAZON_SP_API_CLIENT_SECRET: Optional[str] = None
    AMAZON_SP_API_REFRESH_TOKEN: Optional[str] = None
    AMAZON_SP_API_AWS_ACCESS_KEY: Optional[str] = None
    AMAZON_SP_API_AWS_SECRET_KEY: Optional[str] = None
    AMAZON_SP_API_ROLE_ARN: Optional[str] = None

    # SP-API Settings
    SP_API_REPORT_POLL_INTERVAL_SECONDS: int = 15
    SP_API_REPORT_POLL_MAX_ATTEMPTS: int = 40

    # Amazon Advertising API
    AMAZON_ADS_CLIENT_ID: Optional[str] = None
    AMAZON_ADS_CLIENT_SECRET: Optional[str] = None
    AMAZON_ADS_PROFILE_ID: Optional[str] = None
    AMAZON_ADS_API_BASE_URL: Optional[str] = None
    AMAZON_ADS_REPORT_POLL_INTERVAL_SECONDS: int = 15
    AMAZON_ADS_REPORT_POLL_MAX_ATTEMPTS: int = 40

    # AWS S3
    AWS_S3_BUCKET: str = "inthezon-reports"
    AWS_S3_REGION: str = "eu-south-1"
    AWS_ACCESS_KEY_ID: Optional[str] = None
    AWS_SECRET_ACCESS_KEY: Optional[str] = None
    # Empty string means no ACL header — required for buckets with
    # BlockPublicAccess enabled (default on new AWS accounts).
    CATALOG_IMAGE_S3_ACL: str = "public-read"

    # SendGrid
    SENDGRID_API_KEY: Optional[str] = None
    SENDGRID_FROM_EMAIL: str = "noreply@niuexa.ai"

    # Encryption
    ENCRYPTION_KEY: Optional[str] = None

    # Anthropic (AI Analysis)
    ANTHROPIC_API_KEY: Optional[str] = None
    MARKET_RESEARCH_MAX_COMPETITORS: int = 5

    # Deprecated external market API boundary (not used by Brand Analysis).
    # These optional values are retained only so older environments keep
    # booting; the production Brand Analysis path is internal Amazon data
    # plus Market Research, with generic external yearly uploads as fallback.
    HELIUM10_USERNAME: Optional[str] = None
    HELIUM10_PASSWORD: Optional[str] = None
    HELIUM10_API_BASE_URL: Optional[str] = None
    HELIUM10_API_KEY: Optional[str] = None
    HELIUM10_AUTOMATION_ENABLED: bool = False

    # Brand Analysis
    BRAND_ANALYSIS_MAX_UPLOAD_MB: int = 25
    BRAND_ANALYSIS_STORAGE_BACKEND: str = "db"  # "db" or "s3"
    BRAND_ANALYSIS_SALES_TRAFFIC_RECOVERY_DAYS: int = 730
    BRAND_ANALYSIS_PARTIAL_USABLE_MONTHS: int = 3
    BRAND_ANALYSIS_MAX_SYNC_ATTEMPTS: int = 1
    BRAND_ANALYSIS_SYNC_WINDOW_TIMEOUT_SECONDS: int = 900
    BRAND_ANALYSIS_CAPABILITY_CACHE_TTL_HOURS: int = 24

    # Google OAuth (Sheets integration)
    GOOGLE_CLIENT_ID: Optional[str] = None
    GOOGLE_CLIENT_SECRET: Optional[str] = None
    GOOGLE_REDIRECT_URI: Optional[str] = None

    # Rate Limiting
    RATE_LIMIT_PER_MINUTE: int = 60

    # Data Retention
    DATA_RETENTION_MONTHS: int = 24
    DATA_ARCHIVE_ENABLED: bool = False
    PARTITION_FUTURE_MONTHS: int = 3
    # Only tables actually converted by migration 023_partition_ts_tables.
    # inventory_data and orders are NOT partitioned (different access
    # patterns); they remain row-deleted by manage_data_retention.
    PARTITION_MANAGED_TABLES: List[str] = [
        "sales_data",
        "advertising_metrics",
        "advertising_metrics_by_asin",
        "bsr_history",
    ]

    # In-process scheduler (replaces Celery beat on free tier / no-Redis deploys)
    ENABLE_INPROCESS_SCHEDULER: bool = False
    INPROCESS_SYNC_HOUR_UTC: int = 2
    INPROCESS_SYNC_MINUTE_UTC: int = 0
    # Seller Sales & Traffic is lightweight enough to refresh several times a
    # day. This catches Amazon's normal publication lag without re-running the
    # heavier inventory/orders/ads/catalog sync.
    INPROCESS_SALES_REFRESH_HOURS_UTC: str = "0,6,12,18"
    INPROCESS_SALES_REFRESH_MINUTE_UTC: int = 15
    # How often the in-process scheduler scans for due scheduled reports. The
    # scan is a cheap query; any due report is generated + emailed in a daemon
    # thread, so no separate Celery/Redis worker is required.
    SCHEDULED_REPORT_SCAN_INTERVAL_MINUTES: int = 10
    # When True, on-demand long jobs (brand analysis, market research) skip
    # Celery entirely and run in a daemon thread inside the API process, so
    # dispatch is deterministic instead of relying on .delay() failing fast to
    # trigger the in-process fallback. Defaults off, but see ``run_tasks_inline``
    # which also turns it on automatically wherever the in-process scheduler is
    # enabled (i.e. a deploy with no separate Celery worker). The stuck-job
    # recovery sweep heals threads lost to a web-process restart.
    EXECUTE_TASKS_INLINE: bool = False
    # How often the in-process scheduler finalizes brand-analysis jobs whose
    # worker/thread stalled (e.g. killed by a deploy mid-run).
    BRAND_ANALYSIS_RECOVERY_INTERVAL_MINUTES: int = 10

    # CORS
    CORS_ORIGINS: List[str] = ["http://localhost:5173", "http://localhost:3000"]

    # Observability
    # When SENTRY_DSN is empty the SDK is not initialized at all — the app
    # starts and runs normally without error tracking.
    SENTRY_DSN: Optional[str] = None
    SENTRY_TRACES_SAMPLE_RATE: float = 0.1
    LOG_LEVEL: str = "INFO"
    # "json" → structured logs (one line per record, suitable for Render's
    # log aggregator and Sentry breadcrumbs). "text" → human-readable for
    # local dev. Anything else falls back to "text".
    LOG_FORMAT: str = "json"

    class Config:
        env_file = ".env"
        case_sensitive = True

    @property
    def is_production(self) -> bool:
        return self.APP_ENV.lower() == "production"

    @property
    def run_tasks_inline(self) -> bool:
        """Whether on-demand long jobs should run in-process (no Celery worker).

        True when explicitly requested, or implicitly whenever the in-process
        scheduler is enabled — that flag already marks a deploy that has no
        separate Celery worker, so on-demand tasks must run inline there too.
        """
        return self.EXECUTE_TASKS_INLINE or self.ENABLE_INPROCESS_SCHEDULER


# Placeholder defaults that must never survive into production.
_INSECURE_JWT_DEFAULTS = {"your-jwt-secret-change-in-production"}


def validate_production_settings(s: "Settings") -> None:
    """Fail fast on insecure configuration when running in production.

    A no-op outside production so local/dev keeps working with defaults.
    Raises RuntimeError so the app refuses to boot with a placeholder
    JWT secret; logs a loud warning for non-fatal misconfiguration.
    """
    if not s.is_production:
        return

    import logging

    logger = logging.getLogger(__name__)

    if s.JWT_SECRET_KEY in _INSECURE_JWT_DEFAULTS or len(s.JWT_SECRET_KEY) < 32:
        raise RuntimeError(
            "JWT_SECRET_KEY is using an insecure default or is too short "
            "(min 32 chars). Set a strong JWT_SECRET_KEY before deploying to "
            "production."
        )

    if "localhost" in s.APP_FRONTEND_URL or "127.0.0.1" in s.APP_FRONTEND_URL:
        logger.warning(
            "APP_FRONTEND_URL is still pointing at localhost (%s) in production; "
            "password-reset links will be broken. Set it to the public frontend URL.",
            s.APP_FRONTEND_URL,
        )


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


settings = get_settings()
