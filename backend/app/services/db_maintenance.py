"""In-process database maintenance.

Creation-only mirror of the Celery ``manage_partitions`` task: ensures the
current + next PARTITION_FUTURE_MONTHS monthly partitions exist on every
managed table so inserts never hit a missing partition.

Deliberately does NOT port partition drops or ``manage_data_retention``:
DATA_RETENTION_MONTHS is 24, but the client's vendor account carries ~4 years
of history that must be preserved (long-term retention is a stated
requirement). Nothing in prod may delete time-series data.
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import date

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import settings

logger = logging.getLogger(__name__)

SQL_IDENTIFIER_RE = re.compile(r"^[a-z_][a-z0-9_]*$")


def run_partition_ensure() -> dict | None:
    """Ensure current and future monthly partitions exist (idempotent UDF)."""
    from app.db.session import db_url as _db_url

    months_ahead = max(0, int(settings.PARTITION_FUTURE_MONTHS))
    managed_tables = [
        t for t in settings.PARTITION_MANAGED_TABLES if SQL_IDENTIFIER_RE.fullmatch(t)
    ]
    today = date.today()

    async def _ensure() -> dict:
        outcomes: dict[str, list[str]] = {}
        engine = create_async_engine(_db_url, echo=False, pool_size=1, max_overflow=0)
        try:
            async with engine.begin() as connection:
                for table_name in managed_tables:
                    table_outcomes: list[str] = []
                    for offset in range(0, months_ahead + 1):
                        year = today.year
                        month = today.month + offset
                        while month > 12:
                            month -= 12
                            year += 1
                        result = await connection.execute(
                            text("SELECT public.ensure_monthly_partition(:table, :year, :month)"),
                            {"table": table_name, "year": year, "month": month},
                        )
                        table_outcomes.append(result.scalar() or "")
                    outcomes[table_name] = table_outcomes
        finally:
            await engine.dispose()
        return outcomes

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        outcomes = loop.run_until_complete(_ensure())
        created = sum(
            1 for results in outcomes.values() for r in results if r.startswith("created")
        )
        if created:
            logger.info("Partition ensure created %d partition(s)", created)
        return {"tables": len(outcomes), "created": created}
    except Exception:
        logger.exception("In-process partition ensure failed")
        return None
    finally:
        loop.close()
