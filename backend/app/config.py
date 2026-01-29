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
    AMAZON_SP_API_AWS_ACCESS_KEY: Optional[str] = None
    AMAZON_SP_API_AWS_SECRET_KEY: Optional[str] = None
    AMAZON_SP_API_ROLE_ARN: Optional[str] = None

    # Amazon Advertising API
    AMAZON_ADS_CLIENT_ID: Optional[str] = None
    AMAZON_ADS_CLIENT_SECRET: Optional[str] = None
    AMAZON_ADS_PROFILE_ID: Optional[str] = None

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

    # Rate Limiting
    RATE_LIMIT_PER_MINUTE: int = 60

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
