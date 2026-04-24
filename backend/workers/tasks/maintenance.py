"""Maintenance Celery tasks."""
from __future__ import annotations

import logging
import re
from calendar import monthrange
from datetime import date

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.config import settings
from workers.celery_app import celery_app

logger = logging.getLogger(__name__)
SQL_IDENTIFIER_RE = re.compile(r"^[a-z_][a-z0-9_]*$")

RETENTION_TABLES = (
    ("sales_data", "date"),
    ("inventory_data", "snapshot_date"),
    ("advertising_metrics", "date"),
    ("returns_data", "return_date"),
    ("bsr_history", "date"),
    ("competitor_history", "date"),
)


def _build_sync_database_url(database_url: str) -> str:
    """Normalize the configured database URL for sync SQLAlchemy usage."""
    if database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql+psycopg2://", 1)
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+psycopg2://", 1)
    if "asyncpg" in database_url:
        return database_url.replace("postgresql+asyncpg", "postgresql+psycopg2")
    return database_url


def _subtract_months(value: date, months: int) -> date:
    """Return a date shifted backward by the requested number of months."""
    year = value.year
    month = value.month - months
    while month <= 0:
        month += 12
        year -= 1
    day = min(value.day, monthrange(year, month)[1])
    return date(year, month, day)


def _quoted_identifier(identifier: str) -> str:
    """Return a safely quoted SQL identifier from the static allowlist."""
    if not SQL_IDENTIFIER_RE.fullmatch(identifier):
        raise ValueError(f"Invalid SQL identifier: {identifier}")
    return f'"{identifier}"'


sync_engine = create_engine(
    _build_sync_database_url(settings.DATABASE_URL),
    echo=settings.APP_DEBUG,
    pool_pre_ping=True,
)
SyncSessionLocal = sessionmaker(bind=sync_engine, autoflush=False, autocommit=False)


def _vacuum_analyze_table(table_name: str) -> None:
    """Reclaim space and refresh planner statistics after deletions."""
    safe_table_name = _quoted_identifier(table_name)
    with sync_engine.connect() as connection:
        connection = connection.execution_options(isolation_level="AUTOCOMMIT")
        connection.exec_driver_sql(f"VACUUM ANALYZE {safe_table_name}")


@celery_app.task
def manage_partitions():
    """Ensure monthly partitions exist for the next N months on managed tables.

    Iterates over settings.PARTITION_MANAGED_TABLES and invokes the
    public.ensure_monthly_partition() helper installed by migration 015.
    The helper is a no-op for non-partitioned tables, so this task is safe
    to run whether or not the operator has enabled partitioning.
    """
    months_ahead = max(0, int(settings.PARTITION_FUTURE_MONTHS))
    managed_tables = [t for t in settings.PARTITION_MANAGED_TABLES if SQL_IDENTIFIER_RE.fullmatch(t)]
    today = date.today()

    outcomes: dict[str, list[str]] = {}
    with sync_engine.connect() as connection:
        connection = connection.execution_options(isolation_level="AUTOCOMMIT")
        for table_name in managed_tables:
            table_outcomes: list[str] = []
            # Ensure the current month exists plus `months_ahead` future months.
            for offset in range(0, months_ahead + 1):
                year = today.year
                month = today.month + offset
                while month > 12:
                    month -= 12
                    year += 1
                result = connection.execute(
                    text("SELECT public.ensure_monthly_partition(:table, :year, :month)"),
                    {"table": table_name, "year": year, "month": month},
                )
                outcome = result.scalar() or ""
                table_outcomes.append(outcome)
            outcomes[table_name] = table_outcomes
            logger.info("Partition maintenance for %s: %s", table_name, table_outcomes)

    return {
        "checked_at": today.isoformat(),
        "months_ahead": months_ahead,
        "outcomes": outcomes,
    }


@celery_app.task
def manage_data_retention():
    """Delete expired time-series data and vacuum the affected tables."""
    if settings.DATA_RETENTION_MONTHS < 1:
        raise ValueError("DATA_RETENTION_MONTHS must be at least 1")

    cutoff_date = _subtract_months(date.today(), settings.DATA_RETENTION_MONTHS)
    deleted_counts: dict[str, int] = {}
    affected_tables: list[str] = []

    with SyncSessionLocal() as session:
        try:
            for table_name, date_column in RETENTION_TABLES:
                safe_table_name = _quoted_identifier(table_name)
                safe_date_column = _quoted_identifier(date_column)
                result = session.execute(
                    text(f"DELETE FROM {safe_table_name} WHERE {safe_date_column} < :cutoff_date"),
                    {"cutoff_date": cutoff_date},
                )
                deleted_count = max(result.rowcount or 0, 0)
                deleted_counts[table_name] = deleted_count
                if deleted_count > 0:
                    affected_tables.append(table_name)
                logger.info(
                    "Data retention cleanup for %s deleted %s rows older than %s",
                    table_name,
                    deleted_count,
                    cutoff_date,
                )
            session.commit()
        except Exception:
            session.rollback()
            raise

    for table_name in affected_tables:
        _vacuum_analyze_table(table_name)
        logger.info("Completed VACUUM ANALYZE for %s after retention cleanup", table_name)

    return {
        "cutoff_date": cutoff_date.isoformat(),
        "retention_months": settings.DATA_RETENTION_MONTHS,
        "deleted_records": deleted_counts,
        "vacuumed_tables": affected_tables,
    }
