# Configuration
> Generated from the source by `backend/scripts/gen_tech_docs.py`. Re-run it after changing the code; do not edit this page by hand.

Every setting on `Settings` in `app/config.py`. Secrets show `—` instead of a default. `required` means there is no default and the environment must provide it.

## Settings

| Setting | Type | Default |
| --- | --- | --- |
| `APP_ENV` | `str` | `'development'` |
| `APP_DEBUG` | `bool` | `False` |
| `APP_SECRET_KEY` | `str` | `—` |
| `APP_API_URL` | `str` | `'http://localhost:8000'` |
| `APP_FRONTEND_URL` | `str` | `'http://localhost:5173'` |
| `DATABASE_URL` | `str` | `'postgresql+asyncpg://postgres:postgres@localhost:5432/inthezon'` |
| `DATABASE_POOL_SIZE` | `int` | `20` |
| `DATABASE_MAX_OVERFLOW` | `int` | `10` |
| `REDIS_URL` | `str` | `'redis://localhost:6379/0'` |
| `CELERY_BROKER_URL` | `str` | `'redis://localhost:6379/1'` |
| `CELERY_RESULT_BACKEND` | `str` | `'redis://localhost:6379/2'` |
| `JWT_SECRET_KEY` | `str` | `—` |
| `JWT_ALGORITHM` | `str` | `'HS256'` |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | `int` | `—` |
| `JWT_REFRESH_TOKEN_EXPIRE_DAYS` | `int` | `—` |
| `AMAZON_SP_API_APP_ID` | `Optional[str]` | `None` |
| `AMAZON_SP_API_CLIENT_ID` | `Optional[str]` | `None` |
| `AMAZON_SP_API_CLIENT_SECRET` | `Optional[str]` | `—` |
| `AMAZON_SP_API_REFRESH_TOKEN` | `Optional[str]` | `—` |
| `AMAZON_SP_API_AWS_ACCESS_KEY` | `Optional[str]` | `—` |
| `AMAZON_SP_API_AWS_SECRET_KEY` | `Optional[str]` | `—` |
| `AMAZON_SP_API_ROLE_ARN` | `Optional[str]` | `None` |
| `SP_API_REPORT_POLL_INTERVAL_SECONDS` | `int` | `15` |
| `SP_API_REPORT_POLL_MAX_ATTEMPTS` | `int` | `40` |
| `AMAZON_ADS_CLIENT_ID` | `Optional[str]` | `None` |
| `AMAZON_ADS_CLIENT_SECRET` | `Optional[str]` | `—` |
| `AMAZON_ADS_PROFILE_ID` | `Optional[str]` | `None` |
| `AMAZON_ADS_API_BASE_URL` | `Optional[str]` | `None` |
| `AMAZON_ADS_REPORT_POLL_INTERVAL_SECONDS` | `int` | `15` |
| `AMAZON_ADS_REPORT_POLL_MAX_ATTEMPTS` | `int` | `40` |
| `AWS_S3_BUCKET` | `str` | `'inthezon-reports'` |
| `AWS_S3_REGION` | `str` | `'eu-south-1'` |
| `AWS_ACCESS_KEY_ID` | `Optional[str]` | `—` |
| `AWS_SECRET_ACCESS_KEY` | `Optional[str]` | `—` |
| `CATALOG_IMAGE_S3_ACL` | `str` | `'public-read'` |
| `SENDGRID_API_KEY` | `Optional[str]` | `—` |
| `SENDGRID_FROM_EMAIL` | `str` | `'noreply@niuexa.ai'` |
| `ENCRYPTION_KEY` | `Optional[str]` | `—` |
| `ANTHROPIC_API_KEY` | `Optional[str]` | `—` |
| `MARKET_RESEARCH_MAX_COMPETITORS` | `int` | `5` |
| `HELIUM10_USERNAME` | `Optional[str]` | `None` |
| `HELIUM10_PASSWORD` | `Optional[str]` | `—` |
| `HELIUM10_API_BASE_URL` | `Optional[str]` | `None` |
| `HELIUM10_API_KEY` | `Optional[str]` | `—` |
| `HELIUM10_AUTOMATION_ENABLED` | `bool` | `False` |
| `BRAND_ANALYSIS_MAX_UPLOAD_MB` | `int` | `25` |
| `BRAND_ANALYSIS_STORAGE_BACKEND` | `str` | `'db'` |
| `BRAND_ANALYSIS_SALES_TRAFFIC_RECOVERY_DAYS` | `int` | `730` |
| `BRAND_ANALYSIS_PARTIAL_USABLE_MONTHS` | `int` | `3` |
| `BRAND_ANALYSIS_MAX_SYNC_ATTEMPTS` | `int` | `1` |
| `BRAND_ANALYSIS_SYNC_WINDOW_TIMEOUT_SECONDS` | `int` | `900` |
| `BRAND_ANALYSIS_CAPABILITY_CACHE_TTL_HOURS` | `int` | `24` |
| `GOOGLE_CLIENT_ID` | `Optional[str]` | `None` |
| `GOOGLE_CLIENT_SECRET` | `Optional[str]` | `—` |
| `GOOGLE_REDIRECT_URI` | `Optional[str]` | `None` |
| `RATE_LIMIT_PER_MINUTE` | `int` | `60` |
| `DATA_RETENTION_MONTHS` | `int` | `24` |
| `DATA_ARCHIVE_ENABLED` | `bool` | `False` |
| `PARTITION_FUTURE_MONTHS` | `int` | `3` |
| `PARTITION_MANAGED_TABLES` | `List[str]` | `['sales_data', 'advertising_metrics', 'advertising_metrics_by_asin', 'bsr_history']` |
| `ENABLE_INPROCESS_SCHEDULER` | `bool` | `False` |
| `INPROCESS_SYNC_HOUR_UTC` | `int` | `2` |
| `INPROCESS_SYNC_MINUTE_UTC` | `int` | `0` |
| `INPROCESS_SALES_REFRESH_HOURS_UTC` | `str` | `'0,6,12,18'` |
| `INPROCESS_SALES_REFRESH_MINUTE_UTC` | `int` | `15` |
| `SCHEDULED_REPORT_SCAN_INTERVAL_MINUTES` | `int` | `10` |
| `EXECUTE_TASKS_INLINE` | `bool` | `False` |
| `BRAND_ANALYSIS_RECOVERY_INTERVAL_MINUTES` | `int` | `10` |
| `CORS_ORIGINS` | `List[str]` | `['http://localhost:5173', 'http://localhost:3000']` |
| `SENTRY_DSN` | `Optional[str]` | `None` |
| `SENTRY_TRACES_SAMPLE_RATE` | `float` | `0.1` |
| `LOG_LEVEL` | `str` | `'INFO'` |
| `LOG_FORMAT` | `str` | `'json'` |
