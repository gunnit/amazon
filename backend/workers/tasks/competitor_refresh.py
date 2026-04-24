"""Periodic competitor refresh Celery task."""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.config import settings
from workers.celery_app import celery_app

logger = logging.getLogger(__name__)

MAX_COMPETITORS_PER_RUN = 50
STALE_AFTER_HOURS = 24
PER_ASIN_DELAY_SECONDS = 1.0
_CACHE_MISS = object()


def _build_sync_database_url(database_url: str) -> str:
    """Normalize the configured database URL for sync SQLAlchemy usage."""
    if database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql+psycopg2://", 1)
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+psycopg2://", 1)
    if "asyncpg" in database_url:
        return database_url.replace("postgresql+asyncpg", "postgresql+psycopg2")
    return database_url


sync_engine = create_engine(
    _build_sync_database_url(settings.DATABASE_URL),
    echo=settings.APP_DEBUG,
    pool_pre_ping=True,
)
SyncSessionLocal = sessionmaker(bind=sync_engine, autoflush=False, autocommit=False)


def _snapshot_has_tracked_metrics(snapshot: dict) -> bool:
    """Require at least one tracked metric before persisting a refresh."""
    return any(
        snapshot.get(field) is not None
        for field in ("price", "bsr", "review_count", "rating")
    )


def _apply_snapshot_to_competitor(competitor, snapshot: dict) -> None:
    """Update the tracked competitor record with the latest snapshot values."""
    if snapshot.get("title"):
        competitor.title = snapshot["title"]
    if snapshot.get("brand"):
        competitor.brand = snapshot["brand"]
    if snapshot.get("price") is not None:
        competitor.current_price = Decimal(str(snapshot["price"]))
    if snapshot.get("bsr") is not None:
        competitor.current_bsr = int(snapshot["bsr"])
    if snapshot.get("review_count") is not None:
        competitor.review_count = int(snapshot["review_count"])
    if snapshot.get("rating") is not None:
        competitor.rating = Decimal(str(snapshot["rating"]))


def _upsert_competitor_history(session, competitor, history_date) -> None:
    """Insert or update the daily competitor history snapshot."""
    from app.models.competitor import CompetitorHistory

    history = session.execute(
        select(CompetitorHistory).where(
            CompetitorHistory.competitor_id == competitor.id,
            CompetitorHistory.date == history_date,
        )
    ).scalar_one_or_none()

    if history:
        history.price = competitor.current_price
        history.bsr = competitor.current_bsr
        history.review_count = competitor.review_count
        history.rating = competitor.rating
        return

    session.add(
        CompetitorHistory(
            competitor_id=competitor.id,
            date=history_date,
            price=competitor.current_price,
            bsr=competitor.current_bsr,
            review_count=competitor.review_count,
            rating=competitor.rating,
        )
    )


def _resolve_refresh_client(
    session,
    competitor,
    organization_cache: dict,
    account_cache: dict,
    client_cache: dict,
):
    """Resolve the SP-API client for a competitor's org and marketplace."""
    from app.core.amazon.credentials import resolve_credentials
    from app.core.amazon.sp_api_client import SPAPIClient, resolve_marketplace
    from app.models.amazon_account import AmazonAccount
    from app.models.user import Organization

    org = organization_cache.get(competitor.organization_id, _CACHE_MISS)
    if org is _CACHE_MISS:
        org = session.execute(
            select(Organization).where(Organization.id == competitor.organization_id)
        ).scalar_one_or_none()
        organization_cache[competitor.organization_id] = org
    if org is None:
        logger.warning(
            "Skipping competitor %s: organization %s not found",
            competitor.asin,
            competitor.organization_id,
        )
        return None

    account_key = (competitor.organization_id, competitor.marketplace)
    account = account_cache.get(account_key, _CACHE_MISS)
    if account is _CACHE_MISS:
        account = session.execute(
            select(AmazonAccount)
            .where(
                AmazonAccount.organization_id == competitor.organization_id,
                AmazonAccount.marketplace_country == competitor.marketplace,
                AmazonAccount.is_active == True,
            )
            .order_by(AmazonAccount.updated_at.desc(), AmazonAccount.created_at.desc())
        ).scalars().first()
        account_cache[account_key] = account
    if account is None:
        logger.warning(
            "Skipping competitor %s: no active account for org=%s marketplace=%s",
            competitor.asin,
            competitor.organization_id,
            competitor.marketplace,
        )
        return None

    client = client_cache.get(account.id)
    if client is not None:
        return client

    credentials = resolve_credentials(account, org)
    marketplace = resolve_marketplace(account.marketplace_country)
    client = SPAPIClient(
        credentials,
        marketplace,
        account_type=account.account_type.value,
    )
    client_cache[account.id] = client
    return client


@celery_app.task
def refresh_tracked_competitors():
    """Refresh stale tracked competitors and persist a daily history row."""
    from app.models.competitor import Competitor, CompetitorHistory
    from app.services.market_research_service import _fetch_product_data

    now = datetime.utcnow()
    stale_cutoff = now - timedelta(hours=STALE_AFTER_HOURS)
    history_date = now.date()
    refreshed = 0
    skipped = 0
    failed = 0

    last_refresh_sq = (
        select(
            CompetitorHistory.competitor_id.label("competitor_id"),
            func.max(CompetitorHistory.created_at).label("last_refreshed_at"),
        )
        .group_by(CompetitorHistory.competitor_id)
        .subquery()
    )

    with SyncSessionLocal() as session:
        rows = session.execute(
            select(Competitor, last_refresh_sq.c.last_refreshed_at)
            .outerjoin(
                last_refresh_sq,
                last_refresh_sq.c.competitor_id == Competitor.id,
            )
            .where(Competitor.is_tracking == True)
            .where(
                func.coalesce(
                    last_refresh_sq.c.last_refreshed_at,
                    Competitor.created_at,
                ) < stale_cutoff
            )
            .order_by(
                func.coalesce(
                    last_refresh_sq.c.last_refreshed_at,
                    Competitor.created_at,
                ).asc(),
                Competitor.created_at.asc(),
            )
            .limit(MAX_COMPETITORS_PER_RUN)
        ).all()

        organization_cache: dict = {}
        account_cache: dict = {}
        client_cache: dict = {}

        for index, row in enumerate(rows):
            competitor = row[0]
            try:
                client = _resolve_refresh_client(
                    session=session,
                    competitor=competitor,
                    organization_cache=organization_cache,
                    account_cache=account_cache,
                    client_cache=client_cache,
                )
                if client is None:
                    skipped += 1
                    continue

                snapshot = _fetch_product_data(client, competitor.asin)
                if not _snapshot_has_tracked_metrics(snapshot):
                    logger.warning(
                        "Skipping competitor %s refresh: no tracked metrics returned (%s)",
                        competitor.asin,
                        snapshot.get("fetch_errors"),
                    )
                    skipped += 1
                    continue

                _apply_snapshot_to_competitor(competitor, snapshot)
                _upsert_competitor_history(session, competitor, history_date)
                session.commit()
                refreshed += 1
            except Exception as exc:
                session.rollback()
                failed += 1
                logger.exception(
                    "Tracked competitor refresh failed for %s: %s",
                    competitor.asin,
                    exc,
                )
            finally:
                if index < len(rows) - 1:
                    time.sleep(PER_ASIN_DELAY_SECONDS)

    logger.info(
        "Tracked competitor refresh run completed: selected=%s refreshed=%s skipped=%s failed=%s",
        len(rows),
        refreshed,
        skipped,
        failed,
    )
    return {
        "selected": len(rows),
        "refreshed": refreshed,
        "skipped": skipped,
        "failed": failed,
        "stale_cutoff": stale_cutoff.isoformat(),
    }
