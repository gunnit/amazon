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
# Matches `<parent>_yYYYYmMM` partition names; `<parent>_default` is excluded
# by design so we never drop the catch-all partition.
PARTITION_NAME_RE = re.compile(r"^(?P<parent>[a-z_][a-z0-9_]*)_y(?P<year>\d{4})m(?P<month>\d{2})$")

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


def _list_partitions(connection, parent: str) -> list[str]:
    """Return partition names attached to `parent` (excluding the parent itself)."""
    rows = connection.execute(
        text(
            """
            SELECT c.relname
            FROM pg_class p
            JOIN pg_inherits i ON i.inhparent = p.oid
            JOIN pg_class c ON c.oid = i.inhrelid
            WHERE p.relname = :parent
              AND p.relnamespace = 'public'::regnamespace
            ORDER BY c.relname
            """
        ),
        {"parent": parent},
    ).scalars().all()
    return list(rows)


def _drop_expired_partitions_for(connection, parent: str, cutoff: date) -> list[str]:
    """Drop monthly partitions of `parent` whose range ends before `cutoff`.

    Partitions are named `<parent>_yYYYYmMM`. The `_default` partition (and
    anything else not matching the convention) is intentionally never dropped.
    """
    dropped: list[str] = []
    for partition_name in _list_partitions(connection, parent):
        match = PARTITION_NAME_RE.match(partition_name)
        if not match or match.group("parent") != parent:
            continue
        year = int(match.group("year"))
        month = int(match.group("month"))
        # The partition's upper bound is the first day of the next month.
        # Drop only if that upper bound is at or before the cutoff date —
        # i.e., the partition contains no data within the retention window.
        upper_year = year + (1 if month == 12 else 0)
        upper_month = 1 if month == 12 else month + 1
        upper_bound = date(upper_year, upper_month, 1)
        if upper_bound <= cutoff:
            safe = _quoted_identifier(partition_name)
            connection.execute(text(f"DROP TABLE IF EXISTS public.{safe}"))
            dropped.append(partition_name)
            logger.info(
                "Dropped expired partition",
                extra={
                    "event": "partition_dropped",
                    "parent": parent,
                    "partition": partition_name,
                    "cutoff": cutoff.isoformat(),
                },
            )
    return dropped


@celery_app.task
def manage_partitions():
    """Create future monthly partitions and drop expired ones on managed tables.

    For each table in settings.PARTITION_MANAGED_TABLES:

    1. Calls public.ensure_monthly_partition() (installed in 015) for the
       current month + the next PARTITION_FUTURE_MONTHS months. The UDF is
       idempotent and returns 'skipped: ...' for tables that are still plain.
    2. Drops any `<table>_yYYYYmMM` partition whose upper bound is at or
       before today − DATA_RETENTION_MONTHS. The `_default` partition is
       never touched (we want the catch-all to remain).

    Safe to run on partially-partitioned databases — non-partitioned tables
    are reported under outcomes['<table>'] as 'skipped' for creation and
    yield no drops.
    """
    months_ahead = max(0, int(settings.PARTITION_FUTURE_MONTHS))
    managed_tables = [t for t in settings.PARTITION_MANAGED_TABLES if SQL_IDENTIFIER_RE.fullmatch(t)]
    today = date.today()
    cutoff = _subtract_months(today, max(1, int(settings.DATA_RETENTION_MONTHS)))

    create_outcomes: dict[str, list[str]] = {}
    drop_outcomes: dict[str, list[str]] = {}
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
            create_outcomes[table_name] = table_outcomes
            logger.info(
                "Partition creation outcomes",
                extra={
                    "event": "partition_create_outcomes",
                    "table": table_name,
                    "months_ahead": months_ahead,
                    "outcomes": table_outcomes,
                },
            )
            drop_outcomes[table_name] = _drop_expired_partitions_for(connection, table_name, cutoff)

    return {
        "checked_at": today.isoformat(),
        "months_ahead": months_ahead,
        "retention_cutoff": cutoff.isoformat(),
        "created": create_outcomes,
        "dropped": drop_outcomes,
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
