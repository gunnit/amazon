"""In-process account sync runner.

Replaces the Celery-based sync pipeline for deployments without Redis.
Follows the same private-engine-per-thread pattern as
`market_research_service.process_report_background` because the shared
asyncpg pool is bound to the FastAPI event loop and cannot be reused
safely from a separate thread/loop.
"""
from __future__ import annotations

import asyncio
from calendar import monthrange
from datetime import date, datetime, timedelta
import logging
import threading
from typing import Iterable, List, Optional, Set, Tuple
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.sync_health import classify_sync_exception
from app.db.session import db_url as _db_url
from app.models.amazon_account import (
    AccountType,
    AmazonAccount,
    BackfillStatus,
    SyncStatus,
)
from app.services.data_extraction import DataExtractionService

logger = logging.getLogger(__name__)

# A freshly connected account gets the maximum historical sales window Amazon
# allows so dashboards and forecasts have enough history immediately.
DEFAULT_BACKFILL_MONTHS = 24

# Vendor sales reports reach further back than the seller Sales & Traffic
# report's hard 2-year cap: Amazon serves ~4 years and rejects older ranges as
# prohibited (verified live: 48 months back returned data, 51 months FATALed).
# Windows past the sliding boundary fail per-window and are skipped cleanly.
VENDOR_BACKFILL_MAX_MONTHS = 48

# Prevent the daily full sync and the lighter intraday sales refresh from
# competing for the same Amazon Reports API quota.
_SCHEDULED_SYNC_LOCK = threading.Lock()

# Orders API has its own quota, so the hourly orders refresh only needs to
# guard against overlapping with itself, not with the report-based syncs.
_ORDERS_SYNC_LOCK = threading.Lock()

# A backfill thread dies silently if the web process restarts; anything still
# `running` after this long is considered lost and marked as errored.
BACKFILL_STUCK_THRESHOLD_HOURS = 6

# An errored backfill is resumed automatically by the recovery sweep once it
# is at least this old; re-stamping last_backfill_started_at on each attempt
# makes this the natural retry rate limit.
BACKFILL_RESUME_MIN_AGE_HOURS = 1

# Sales gap repair: look this far back for missing daily-total rows (bounded
# per account by its first-ever data point), stay behind Amazon's publish lag,
# and cap re-pulled windows per account per run so one account with a
# long-dead range cannot exhaust the report quota.
SALES_GAP_LOOKBACK_DAYS = 730
SALES_GAP_PUBLISH_LAG_DAYS = 2
SALES_GAP_MAX_WINDOWS_PER_ACCOUNT = 5


def _subtract_calendar_months(value: date, months: int) -> date:
    """Shift a date backward by calendar months, preserving the day when possible."""
    year = value.year
    month = value.month - months
    while month <= 0:
        month += 12
        year -= 1
    day = min(value.day, monthrange(year, month)[1])
    return date(year, month, day)


def _make_local_session_factory():
    engine = create_async_engine(
        _db_url,
        echo=False,
        pool_size=2,
        max_overflow=1,
    )
    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
    return engine, session_factory


async def _persist_sync_failure_state(account_id: UUID, session_factory, exc: Exception) -> None:
    """Persist failure metadata for in-process syncs, which do not have Celery retries."""
    decision = classify_sync_exception(exc)
    async with session_factory() as db:
        result = await db.execute(select(AmazonAccount).where(AmazonAccount.id == account_id))
        account = result.scalar_one_or_none()
        if account is None:
            return

        failure_at = datetime.utcnow()
        account.last_sync_failed_at = failure_at
        account.last_sync_heartbeat_at = failure_at
        account.sync_error_message = str(exc)
        account.sync_error_kind = decision.kind
        account.sync_error_code = decision.error_code
        account.sync_status = SyncStatus.ERROR
        await db.commit()


async def _sync_one(account_id: UUID, session_factory) -> None:
    async with session_factory() as db:
        service = DataExtractionService(db)
        try:
            result = await service.sync_account(account_id)
            await db.commit()
            logger.info(
                "In-process sync completed for %s: %s",
                account_id,
                {k: v for k, v in result.items() if k != "status"},
            )
        except Exception as exc:
            try:
                await db.rollback()
            except Exception:
                pass
            await _persist_sync_failure_state(account_id, session_factory, exc)
            logger.exception("In-process sync failed for %s", account_id)


def _run_sync(account_ids: List[UUID]) -> None:
    engine, session_factory = _make_local_session_factory()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        for account_id in account_ids:
            loop.run_until_complete(_sync_one(account_id, session_factory))
    finally:
        try:
            loop.run_until_complete(engine.dispose())
        finally:
            loop.close()


def sync_account_in_thread(account_id: UUID) -> None:
    """Fire-and-forget sync of a single account in a daemon thread."""
    thread = threading.Thread(
        target=_run_sync,
        args=([account_id],),
        name=f"sync-{account_id}",
        daemon=True,
    )
    thread.start()


def sync_accounts_in_thread(account_ids: Iterable[UUID]) -> None:
    """Fire-and-forget sync of many accounts in a single daemon thread."""
    ids = list(account_ids)
    if not ids:
        return
    thread = threading.Thread(
        target=_run_sync,
        args=(ids,),
        name=f"sync-batch-{len(ids)}",
        daemon=True,
    )
    thread.start()


# ---------------------------------------------------------------------------
# Initial sync + historical backfill (first connect / on-demand re-backfill)
# ---------------------------------------------------------------------------


def _resolve_backfill_window(
    months: int,
    *,
    max_months: int = DEFAULT_BACKFILL_MONTHS,
    today: Optional[date] = None,
) -> Tuple[date, date]:
    """[start, end] for a backfill ``months`` deep, clamped to ``max_months``
    (sellers are capped at SP-API's 2 years; vendor reports reach further)."""
    end_date = today or date.today()
    earliest = _subtract_calendar_months(end_date, max_months)
    start_date = max(_subtract_calendar_months(end_date, months), earliest)
    return start_date, end_date


async def _mark_backfill_started(
    account_id: UUID, session_factory, start_date: date, end_date: date
) -> None:
    async with session_factory() as db:
        result = await db.execute(select(AmazonAccount).where(AmazonAccount.id == account_id))
        account = result.scalar_one_or_none()
        if account is None:
            return
        account.last_backfill_status = BackfillStatus.RUNNING.value
        account.last_backfill_started_at = datetime.utcnow()
        account.last_backfill_completed_at = None
        account.last_backfill_records = None
        account.last_backfill_windows_skipped = None
        account.last_backfill_error = None
        account.last_backfill_range_start = start_date
        account.last_backfill_range_end = end_date
        await db.commit()


async def _mark_backfill_failed(account_id: UUID, session_factory, exc: Exception) -> None:
    async with session_factory() as db:
        result = await db.execute(select(AmazonAccount).where(AmazonAccount.id == account_id))
        account = result.scalar_one_or_none()
        if account is None:
            return
        account.last_backfill_status = BackfillStatus.ERROR.value
        account.last_backfill_completed_at = datetime.utcnow()
        account.last_backfill_error = str(exc)[:2000]
        await db.commit()


async def _backfill_history_extras(
    account_id: UUID, session_factory, start_date: date, end_date: date
) -> None:
    """Best-effort seller history extras: orders, economics, MFN returns.

    Each source runs in its own session and try/except, so one failure never
    affects the others — or the sales last_backfill_* status, which is owned
    exclusively by the sales backfill."""
    from app.services.economics_service import EconomicsService

    async def _orders(db, account, organization):
        return await DataExtractionService(db).backfill_orders_history(
            account, organization, start_date=start_date, end_date=end_date
        )

    async def _economics(db, account, organization):
        return await EconomicsService(db).backfill_economics_history(
            account, organization, start_date=start_date, end_date=end_date
        )

    async def _returns(db, account, organization):
        return await DataExtractionService(db).backfill_returns_history(
            account, organization, start_date=start_date, end_date=end_date
        )

    for label, runner in (("orders", _orders), ("economics", _economics), ("returns", _returns)):
        async with session_factory() as db:
            result = await db.execute(select(AmazonAccount).where(AmazonAccount.id == account_id))
            account = result.scalar_one_or_none()
            if account is None:
                return
            # Capture before any rollback: the rollback expires ORM attributes
            # and a lazy refresh in the except path raises MissingGreenlet.
            account_name = account.account_name
            try:
                organization = await DataExtractionService(db)._load_organization(account)
                count = await runner(db, account, organization)
                await db.commit()
                logger.info(
                    "History backfill (%s) completed for %s: %d records",
                    label, account_name, count,
                )
            except Exception:
                try:
                    await db.rollback()
                except Exception:
                    pass
                logger.exception("History backfill (%s) failed for %s", label, account_name)


async def _run_sales_backfill(
    account_id: UUID, session_factory, start_date: date, end_date: date
) -> None:
    """Run the historical sales backfill over [start_date, end_date] and record
    its outcome in the last_backfill_* fields; sellers then get the best-effort
    history extras. The caller must already have stamped the backfill started."""
    async with session_factory() as db:
        result = await db.execute(select(AmazonAccount).where(AmazonAccount.id == account_id))
        account = result.scalar_one_or_none()
        if account is None:
            return
        is_vendor = account.account_type == AccountType.VENDOR
        service = DataExtractionService(db)
        try:
            organization = await service._load_organization(account)
            if is_vendor:
                count = await service.backfill_vendor_sales_data(
                    account, organization, start_date=start_date, end_date=end_date
                )
            else:
                count = await service.backfill_sales_data(
                    account, organization, start_date=start_date, end_date=end_date
                )
            skipped = service.backfill_windows_skipped
            account.last_backfill_status = (
                BackfillStatus.PARTIAL.value if skipped else BackfillStatus.SUCCESS.value
            )
            account.last_backfill_completed_at = datetime.utcnow()
            account.last_backfill_records = count
            account.last_backfill_windows_skipped = skipped
            account.last_backfill_error = None
            await db.commit()
            logger.info(
                "Historical backfill completed for %s: %d records (%s..%s), %d windows skipped",
                account_id, count, start_date, end_date, skipped,
            )
        except Exception as exc:
            try:
                await db.rollback()
            except Exception:
                pass
            await _mark_backfill_failed(account_id, session_factory, exc)
            logger.exception("Historical sales backfill failed for %s", account_id)
            return

    if not is_vendor:
        await _backfill_history_extras(account_id, session_factory, start_date, end_date)


async def _initial_sync_one(account_id: UUID, backfill_months: int, session_factory) -> None:
    """First-connect pipeline: a full current sync, then a historical backfill.
    Phase 1 stamps account status and fetches current
    inventory/orders/ads/products + recent sales; phase 2 fills older sales
    history for forecasting, plus orders/economics/returns history for sellers.
    The backfill is best-effort and never downgrades a successful sync; its
    outcome is tracked in the last_backfill_* fields."""
    # Phase 1 — full current sync (also sets sync_status / error state).
    async with session_factory() as db:
        service = DataExtractionService(db)
        try:
            result = await service.sync_account(account_id)
            await db.commit()
            logger.info(
                "Initial sync completed for %s: %s",
                account_id,
                {k: v for k, v in result.items() if k != "status"},
            )
        except Exception as exc:
            try:
                await db.rollback()
            except Exception:
                pass
            await _persist_sync_failure_state(account_id, session_factory, exc)
            logger.exception("Initial sync failed for %s; skipping backfill", account_id)
            return

    # Phase 2 — historical sales backfill (best-effort; commits per month).
    # The window is resolved only after loading the account because vendors
    # get a deeper one than the seller report's 2-year cap allows.
    async with session_factory() as db:
        result = await db.execute(select(AmazonAccount).where(AmazonAccount.id == account_id))
        account = result.scalar_one_or_none()
        if account is None:
            return
        if account.account_type == AccountType.VENDOR:
            backfill_months = max_months = VENDOR_BACKFILL_MAX_MONTHS
        else:
            max_months = DEFAULT_BACKFILL_MONTHS
    start_date, end_date = _resolve_backfill_window(backfill_months, max_months=max_months)
    await _mark_backfill_started(account_id, session_factory, start_date, end_date)
    await _run_sales_backfill(account_id, session_factory, start_date, end_date)


def _run_initial_sync(account_ids: List[UUID], backfill_months: int) -> None:
    engine, session_factory = _make_local_session_factory()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        for account_id in account_ids:
            loop.run_until_complete(
                _initial_sync_one(account_id, backfill_months, session_factory)
            )
    finally:
        try:
            loop.run_until_complete(engine.dispose())
        finally:
            loop.close()


def initial_sync_in_thread(
    account_id: UUID, backfill_months: int = DEFAULT_BACKFILL_MONTHS
) -> None:
    """Fire-and-forget first-connect sync + historical backfill in a daemon thread."""
    thread = threading.Thread(
        target=_run_initial_sync,
        args=([account_id], backfill_months),
        name=f"initial-sync-{account_id}",
        daemon=True,
    )
    thread.start()


def initial_sync_accounts_in_thread(
    account_ids: Iterable[UUID], backfill_months: int = DEFAULT_BACKFILL_MONTHS
) -> int:
    """Fire-and-forget sync + historical backfill for many accounts.

    Accounts are processed sequentially in a single daemon thread so a bulk
    backfill of already-connected accounts never runs N report pipelines
    against the same SP-API quota at once. Returns the number scheduled."""
    ids = list(account_ids)
    if not ids:
        return 0
    thread = threading.Thread(
        target=_run_initial_sync,
        args=(ids, backfill_months),
        name=f"initial-sync-batch-{len(ids)}",
        daemon=True,
    )
    thread.start()
    return len(ids)


async def list_active_account_ids(
    db: AsyncSession,
    organization_id: Optional[UUID] = None,
) -> List[UUID]:
    """Return ids of active accounts, optionally scoped to one organization."""
    stmt = select(AmazonAccount.id).where(AmazonAccount.is_active.is_(True))
    if organization_id is not None:
        stmt = stmt.where(AmazonAccount.organization_id == organization_id)
    result = await db.execute(stmt)
    return [row[0] for row in result.all()]


async def list_active_seller_account_ids(db: AsyncSession) -> List[UUID]:
    """Return active seller account ids for the lightweight sales refresh."""
    result = await db.execute(
        select(AmazonAccount.id).where(
            AmazonAccount.is_active.is_(True),
            AmazonAccount.account_type == AccountType.SELLER,
        )
    )
    return [row[0] for row in result.all()]


async def _refresh_recent_seller_sales(account_id: UUID, session_factory) -> int:
    """Refresh the rolling seller Sales & Traffic window without a full account sync."""
    async with session_factory() as db:
        result = await db.execute(select(AmazonAccount).where(AmazonAccount.id == account_id))
        account = result.scalar_one_or_none()
        if account is None:
            return 0

        service = DataExtractionService(db)
        try:
            organization = await service._load_organization(account)
            count = await service.sync_sales_data(account, organization)
            await db.commit()
            logger.info(
                "Recent seller sales refresh completed for %s: %d records",
                account.account_name,
                count,
            )
            return count
        except Exception:
            try:
                await db.rollback()
            except Exception:
                pass
            logger.exception("Recent seller sales refresh failed for %s", account.account_name)
            return 0


def run_recent_seller_sales_sync_all() -> dict:
    """Refresh recent seller sales several times daily as Amazon publishes them."""
    if not _SCHEDULED_SYNC_LOCK.acquire(blocking=False):
        logger.info("Recent seller sales refresh skipped: another scheduled sync is running")
        return {"status": "skipped", "accounts": 0, "records": 0}

    engine = None
    loop = None
    try:
        engine, session_factory = _make_local_session_factory()
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        async def _collect() -> List[UUID]:
            async with session_factory() as db:
                return await list_active_seller_account_ids(db)

        account_ids = loop.run_until_complete(_collect())
        logger.info("Recent seller sales refresh: starting %d accounts", len(account_ids))
        records = 0
        for account_id in account_ids:
            records += loop.run_until_complete(
                _refresh_recent_seller_sales(account_id, session_factory)
            )
        logger.info(
            "Recent seller sales refresh: finished %d accounts, %d records",
            len(account_ids),
            records,
        )
        return {"status": "success", "accounts": len(account_ids), "records": records}
    finally:
        try:
            if loop is not None and engine is not None:
                loop.run_until_complete(engine.dispose())
        finally:
            if loop is not None:
                loop.close()
            _SCHEDULED_SYNC_LOCK.release()


# ---------------------------------------------------------------------------
# Backfill recovery sweep
# ---------------------------------------------------------------------------


async def _recover_stuck_backfills(session_factory) -> int:
    """Mark backfills stuck in `running` (dead thread after a restart) as errored."""
    cutoff = datetime.utcnow() - timedelta(hours=BACKFILL_STUCK_THRESHOLD_HOURS)
    async with session_factory() as db:
        result = await db.execute(
            select(AmazonAccount).where(
                AmazonAccount.last_backfill_status == BackfillStatus.RUNNING.value,
                AmazonAccount.last_backfill_started_at < cutoff,
            )
        )
        accounts = result.scalars().all()
        for account in accounts:
            account.last_backfill_status = BackfillStatus.ERROR.value
            account.last_backfill_completed_at = datetime.utcnow()
            account.last_backfill_error = (
                f"Backfill did not report completion within "
                f"{BACKFILL_STUCK_THRESHOLD_HOURS}h; it was likely interrupted by a "
                f"process restart. It will be resumed automatically."
            )
        await db.commit()
        return len(accounts)


async def _claim_resumable_backfills(session_factory) -> List[UUID]:
    """Claim errored backfills that are due for an automatic resume.

    Claiming re-marks them as running and re-stamps last_backfill_started_at,
    so a resume that dies is re-claimed by a later sweep and retries are
    naturally rate-limited to one per BACKFILL_RESUME_MIN_AGE_HOURS."""
    cutoff = datetime.utcnow() - timedelta(hours=BACKFILL_RESUME_MIN_AGE_HOURS)
    async with session_factory() as db:
        result = await db.execute(
            select(AmazonAccount).where(
                AmazonAccount.is_active.is_(True),
                AmazonAccount.last_backfill_status == BackfillStatus.ERROR.value,
                AmazonAccount.last_backfill_started_at < cutoff,
                AmazonAccount.last_backfill_range_start.is_not(None),
                AmazonAccount.last_backfill_range_end.is_not(None),
            )
        )
        accounts = result.scalars().all()
        for account in accounts:
            account.last_backfill_status = BackfillStatus.RUNNING.value
            account.last_backfill_started_at = datetime.utcnow()
            account.last_backfill_completed_at = None
        await db.commit()
        return [account.id for account in accounts]


async def _resume_backfill_one(account_id: UUID, session_factory) -> None:
    """Resume a claimed backfill from its earliest missing daily-total date.

    Re-runs the sales backfill (plus the seller history extras) over
    [first hole, original range end]; when the recorded range has no holes the
    backfill is marked successful without calling Amazon."""
    from app.models.sales_data import SalesData
    from app.services.data_extraction import DAILY_TOTAL_ASIN, VENDOR_REPORT_LAG_DAYS

    async with session_factory() as db:
        result = await db.execute(select(AmazonAccount).where(AmazonAccount.id == account_id))
        account = result.scalar_one_or_none()
        if account is None:
            return
        account_name = account.account_name
        range_start = account.last_backfill_range_start
        range_end = account.last_backfill_range_end

        # Stay behind the publish lag so trailing not-yet-published days are
        # not treated as holes (that would re-pull the tail window every hour).
        lag_days = (
            VENDOR_REPORT_LAG_DAYS
            if account.account_type == AccountType.VENDOR
            else SALES_GAP_PUBLISH_LAG_DAYS
        )
        detect_end = min(range_end, date.today() - timedelta(days=lag_days))

        missing: List[Tuple[date, date]] = []
        if range_start <= detect_end:
            rows = await db.execute(
                select(SalesData.date).where(
                    SalesData.account_id == account.id,
                    SalesData.asin == DAILY_TOTAL_ASIN,
                    SalesData.date >= range_start,
                    SalesData.date <= detect_end,
                )
            )
            existing = {row[0] for row in rows.all()}
            missing = _missing_date_windows(existing, range_start, detect_end)

        if not missing:
            account.last_backfill_status = BackfillStatus.SUCCESS.value
            account.last_backfill_completed_at = datetime.utcnow()
            account.last_backfill_error = None
            await db.commit()
            logger.info(
                "Backfill resume for %s: no missing dates in %s..%s, marked success",
                account_name, range_start, detect_end,
            )
            return

        resume_start = min(start for start, _ in missing)

    logger.info(
        "Resuming backfill for %s from %s (recorded range %s..%s)",
        account_name, resume_start, range_start, range_end,
    )
    await _run_sales_backfill(account_id, session_factory, resume_start, range_end)


def _run_backfill_resume(account_ids: List[UUID]) -> None:
    engine, session_factory = _make_local_session_factory()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        for account_id in account_ids:
            try:
                loop.run_until_complete(_resume_backfill_one(account_id, session_factory))
            except Exception:
                logger.exception("Backfill resume failed for %s", account_id)
    finally:
        try:
            loop.run_until_complete(engine.dispose())
        finally:
            loop.close()


def run_backfill_recovery_sweep() -> dict:
    """Entrypoint for the scheduler: recover backfills lost to process restarts
    and resume errored ones from their first missing date."""
    engine, session_factory = _make_local_session_factory()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        recovered = loop.run_until_complete(_recover_stuck_backfills(session_factory))
        if recovered:
            logger.warning("Backfill recovery sweep: marked %d stuck backfill(s) as error", recovered)
        resumable = loop.run_until_complete(_claim_resumable_backfills(session_factory))
        if resumable:
            logger.info("Backfill recovery sweep: resuming %d backfill(s)", len(resumable))
            thread = threading.Thread(
                target=_run_backfill_resume,
                args=(resumable,),
                name=f"backfill-resume-{len(resumable)}",
                daemon=True,
            )
            thread.start()
        return {"status": "success", "recovered": recovered, "resumed": len(resumable)}
    finally:
        try:
            loop.run_until_complete(engine.dispose())
        finally:
            loop.close()


# ---------------------------------------------------------------------------
# Sales gap detection + repair
# ---------------------------------------------------------------------------


def _missing_date_windows(
    existing: Set[date], start: date, end: date
) -> List[Tuple[date, date]]:
    """Group dates in [start, end] absent from ``existing`` into contiguous
    windows, most recent first (recent gaps matter more and the per-run window
    cap must not starve them behind an old unfixable range)."""
    windows: List[Tuple[date, date]] = []
    window_start: Optional[date] = None
    current = start
    while current <= end:
        if current not in existing:
            if window_start is None:
                window_start = current
        elif window_start is not None:
            windows.append((window_start, current - timedelta(days=1)))
            window_start = None
        current += timedelta(days=1)
    if window_start is not None:
        windows.append((window_start, end))
    windows.reverse()
    return windows


async def _repair_sales_gaps_one(account_id: UUID, session_factory) -> int:
    """Find and re-pull missing daily-total sales dates for one account."""
    from app.models.sales_data import SalesData
    from app.services.data_extraction import DAILY_TOTAL_ASIN, VENDOR_REPORT_LAG_DAYS
    from app.core.exceptions import AmazonAPIError

    async with session_factory() as db:
        result = await db.execute(select(AmazonAccount).where(AmazonAccount.id == account_id))
        account = result.scalar_one_or_none()
        if account is None:
            return 0

        is_vendor = account.account_type == AccountType.VENDOR
        lag_days = VENDOR_REPORT_LAG_DAYS if is_vendor else SALES_GAP_PUBLISH_LAG_DAYS
        end = date.today() - timedelta(days=lag_days)
        start = date.today() - timedelta(days=SALES_GAP_LOOKBACK_DAYS)

        first_row = await db.execute(
            select(func.min(SalesData.date)).where(
                SalesData.account_id == account.id,
                SalesData.asin == DAILY_TOTAL_ASIN,
            )
        )
        earliest = first_row.scalar()
        if earliest is None:
            # No sales history at all: that is the backfill's job, not a gap.
            return 0
        # Never probe before the account's first-ever data point: Amazon has
        # nothing there, and unfillable windows would burn the nightly quota.
        start = max(start, earliest)

        rows = await db.execute(
            select(SalesData.date).where(
                SalesData.account_id == account.id,
                SalesData.asin == DAILY_TOTAL_ASIN,
                SalesData.date >= start,
                SalesData.date <= end,
            )
        )
        existing = {row[0] for row in rows.all()}

        windows = _missing_date_windows(existing, start, end)
        if not windows:
            return 0
        if len(windows) > SALES_GAP_MAX_WINDOWS_PER_ACCOUNT:
            logger.info(
                "Sales gap repair for %s: %d windows found, repairing the %d most recent",
                account.account_name, len(windows), SALES_GAP_MAX_WINDOWS_PER_ACCOUNT,
            )
            windows = windows[:SALES_GAP_MAX_WINDOWS_PER_ACCOUNT]

        service = DataExtractionService(db)
        organization = await service._load_organization(account)
        repaired = 0
        for window_start, window_end in windows:
            try:
                if is_vendor:
                    # Handles the DAY report's 15-day-per-request cap itself.
                    count = await service.backfill_vendor_sales_data(
                        account, organization,
                        start_date=window_start, end_date=window_end,
                    )
                else:
                    count = await service.sync_sales_data(
                        account, organization, window_start, window_end
                    )
            except AmazonAPIError as exc:
                # Report failures happen before any rows are written; skip the
                # window without a rollback (a rollback would expire the loaded
                # account/organization and break the remaining windows).
                logger.warning(
                    "Sales gap repair window %s..%s failed for %s: %s",
                    window_start, window_end, account.account_name, exc,
                )
                continue
            await db.commit()
            repaired += count
            logger.info(
                "Sales gap repaired for %s: %s..%s (%d records)",
                account.account_name, window_start, window_end, count,
            )
        return repaired


def run_sales_gap_repair_all() -> dict:
    """Entrypoint for the scheduler: re-pull missing sales dates per account."""
    if not _SCHEDULED_SYNC_LOCK.acquire(blocking=False):
        logger.info("Sales gap repair skipped: another scheduled sync is running")
        return {"status": "skipped", "accounts": 0, "records": 0}

    engine = None
    loop = None
    try:
        engine, session_factory = _make_local_session_factory()
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        async def _collect() -> List[UUID]:
            async with session_factory() as db:
                return await list_active_account_ids(db)

        account_ids = loop.run_until_complete(_collect())
        records = 0
        for account_id in account_ids:
            try:
                records += loop.run_until_complete(
                    _repair_sales_gaps_one(account_id, session_factory)
                )
            except Exception:
                logger.exception("Sales gap repair failed for %s", account_id)
        logger.info(
            "Sales gap repair: finished %d accounts, %d records repaired",
            len(account_ids), records,
        )
        return {"status": "success", "accounts": len(account_ids), "records": records}
    finally:
        try:
            if loop is not None and engine is not None:
                loop.run_until_complete(engine.dispose())
        finally:
            if loop is not None:
                loop.close()
            _SCHEDULED_SYNC_LOCK.release()


# ---------------------------------------------------------------------------
# Hourly incremental orders refresh (near-real-time "today" metrics)
# ---------------------------------------------------------------------------


async def _refresh_recent_orders(account_id: UUID, session_factory) -> int:
    """Incrementally sync recent orders for one seller account."""
    async with session_factory() as db:
        result = await db.execute(select(AmazonAccount).where(AmazonAccount.id == account_id))
        account = result.scalar_one_or_none()
        if account is None or account.account_type == AccountType.VENDOR:
            return 0

        service = DataExtractionService(db)
        try:
            organization = await service._load_organization(account)
            count = await service.sync_orders(account, organization)
            await db.commit()
            return count
        except Exception:
            try:
                await db.rollback()
            except Exception:
                pass
            logger.exception("Recent orders refresh failed for %s", account.account_name)
            return 0


def run_recent_orders_sync_all() -> dict:
    """Entrypoint for the scheduler: hourly incremental orders pull for sellers.

    Uses the Orders API (separate quota from the Reports API), so it only
    guards against overlapping with itself. Overlap with the daily full sync is
    harmless: orders are upserted by amazon_order_id."""
    if not _ORDERS_SYNC_LOCK.acquire(blocking=False):
        logger.info("Recent orders refresh skipped: previous run still in progress")
        return {"status": "skipped", "accounts": 0, "records": 0}

    engine = None
    loop = None
    try:
        engine, session_factory = _make_local_session_factory()
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        async def _collect() -> List[UUID]:
            async with session_factory() as db:
                return await list_active_seller_account_ids(db)

        account_ids = loop.run_until_complete(_collect())
        records = 0
        for account_id in account_ids:
            records += loop.run_until_complete(
                _refresh_recent_orders(account_id, session_factory)
            )
        logger.info(
            "Recent orders refresh: finished %d accounts, %d records",
            len(account_ids), records,
        )
        return {"status": "success", "accounts": len(account_ids), "records": records}
    finally:
        try:
            if loop is not None and engine is not None:
                loop.run_until_complete(engine.dispose())
        finally:
            if loop is not None:
                loop.close()
            _ORDERS_SYNC_LOCK.release()


# ---------------------------------------------------------------------------
# New data sources: economics, market snapshots, brand search terms,
# listing quality
# ---------------------------------------------------------------------------


def _run_seller_job(label: str, per_account, lock: Optional[threading.Lock] = None) -> dict:
    """Run an async per-account job for every active seller account.

    Same engine/loop lifecycle as the other scheduled entrypoints. When a lock
    is given (jobs on the shared Reports API quota) a busy lock skips the run."""
    if lock is not None and not lock.acquire(blocking=False):
        logger.info("%s skipped: another scheduled sync is running", label)
        return {"status": "skipped", "accounts": 0, "records": 0}

    engine = None
    loop = None
    try:
        engine, session_factory = _make_local_session_factory()
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        async def _collect() -> List[UUID]:
            async with session_factory() as db:
                return await list_active_seller_account_ids(db)

        account_ids = loop.run_until_complete(_collect())
        records = 0
        for account_id in account_ids:
            try:
                records += loop.run_until_complete(per_account(account_id, session_factory))
            except Exception:
                logger.exception("%s failed for %s", label, account_id)
        logger.info("%s: finished %d accounts, %d records", label, len(account_ids), records)
        return {"status": "success", "accounts": len(account_ids), "records": records}
    finally:
        try:
            if loop is not None and engine is not None:
                loop.run_until_complete(engine.dispose())
        finally:
            if loop is not None:
                loop.close()
            if lock is not None:
                lock.release()


async def _with_account(account_id: UUID, session_factory, runner) -> int:
    """Load the account, run `runner(db, account)`, commit; 0 on failure."""
    async with session_factory() as db:
        result = await db.execute(select(AmazonAccount).where(AmazonAccount.id == account_id))
        account = result.scalar_one_or_none()
        if account is None:
            return 0
        # Capture before any rollback: the rollback expires ORM attributes and a
        # lazy refresh in the except path raises MissingGreenlet.
        account_name = account.account_name
        try:
            count = await runner(db, account)
            await db.commit()
            return count
        except Exception:
            try:
                await db.rollback()
            except Exception:
                pass
            logger.exception("Per-account job failed for %s", account_name)
            return 0


async def _sync_economics_one(account_id: UUID, session_factory) -> int:
    from app.services.economics_service import EconomicsService

    async def _run(db, account):
        service = EconomicsService(db)
        organization = await DataExtractionService(db)._load_organization(account)
        return await service.sync_asin_economics(account, organization)

    return await _with_account(account_id, session_factory, _run)


async def _snapshot_market_one(account_id: UUID, session_factory) -> int:
    from app.services.market_snapshot_service import MarketSnapshotService

    async def _run(db, account):
        service = MarketSnapshotService(db)
        organization = await DataExtractionService(db)._load_organization(account)
        result = await service.snapshot_account(account, organization)
        return result["prices"] + result["fees"]

    return await _with_account(account_id, session_factory, _run)


async def _sync_brand_terms_one(account_id: UUID, session_factory) -> int:
    from app.services.brand_analytics_ingest_service import BrandAnalyticsIngestService

    async def _run(db, account):
        service = BrandAnalyticsIngestService(db)
        organization = await DataExtractionService(db)._load_organization(account)
        return await service.sync_search_terms(account, organization)

    return await _with_account(account_id, session_factory, _run)


async def _snapshot_listing_quality_one(account_id: UUID, session_factory) -> int:
    from app.services.listing_quality_service import ListingQualityService

    async def _run(db, account):
        return await ListingQualityService(db).snapshot_account(account)

    return await _with_account(account_id, session_factory, _run)


def run_asin_economics_sync_all() -> dict:
    """Daily Data Kiosk economics pull (Data Kiosk quota, no report lock)."""
    return _run_seller_job("ASIN economics sync", _sync_economics_one)


def run_market_snapshot_all() -> dict:
    """Daily fee-estimate + price/Buy Box snapshots (Pricing/Fees quotas)."""
    return _run_seller_job("Market snapshot", _snapshot_market_one)


def run_brand_search_terms_sync_all() -> dict:
    """Weekly Brand Analytics search-terms ingestion (Reports API quota)."""
    return _run_seller_job(
        "Brand search terms sync", _sync_brand_terms_one, lock=_SCHEDULED_SYNC_LOCK
    )


def run_listing_quality_snapshot_all() -> dict:
    """Weekly listing-quality snapshots (warehouse data only)."""
    return _run_seller_job("Listing quality snapshot", _snapshot_listing_quality_one)


def run_daily_sync_all() -> None:
    """Entrypoint for the scheduler: sync every active account once."""
    if not _SCHEDULED_SYNC_LOCK.acquire(blocking=False):
        logger.info("Daily sync skipped: another scheduled sync is running")
        return

    engine = None
    loop = None
    try:
        engine, session_factory = _make_local_session_factory()
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        async def _collect() -> List[UUID]:
            async with session_factory() as db:
                return await list_active_account_ids(db)

        account_ids = loop.run_until_complete(_collect())
        if not account_ids:
            logger.info("Daily sync: no active accounts")
            return
        logger.info("Daily sync: starting %d accounts", len(account_ids))
        for account_id in account_ids:
            loop.run_until_complete(_sync_one(account_id, session_factory))
        logger.info("Daily sync: finished")
    finally:
        try:
            if loop is not None and engine is not None:
                loop.run_until_complete(engine.dispose())
        finally:
            if loop is not None:
                loop.close()
            _SCHEDULED_SYNC_LOCK.release()
