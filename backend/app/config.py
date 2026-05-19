"""Application configuration settings."""
from typing import Optional, List
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Application
    APP_ENV: str = "development"
    APP_DEBUG: bool = True
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
    PARTITION_MANAGED_TABLES: List[str] = [
        "sales_data",
        "inventory_data",
        "advertising_metrics",
        "orders",
    ]

    # In-process scheduler (replaces Celery beat on free tier / no-Redis deploys)
    ENABLE_INPROCESS_SCHEDULER: bool = False
    INPROCESS_SYNC_HOUR_UTC: int = 2
    INPROCESS_SYNC_MINUTE_UTC: int = 0

    # CORS
    CORS_ORIGINS: List[str] = ["http://localhost:5173", "http://localhost:3000"]

    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


settings = get_settings()
