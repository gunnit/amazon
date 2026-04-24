"""Weekly strategic recommendations Celery tasks (US-7.5)."""
from __future__ import annotations

import asyncio
import logging

from workers.celery_app import celery_app

logger = logging.getLogger(__name__)


def run_async(coro_factory):
    """Run an async coroutine in a fresh event loop.

    Installs a fresh engine/session factory before the loop starts so
    asyncpg futures are bound to this loop, and disposes afterwards to
    prevent cross-loop leakage within the Celery worker process.
    """
    from app.db.session import reset_engine_for_worker

    reset_engine_for_worker()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro_factory())
    finally:
        try:
            from app.db.session import engine
            loop.run_until_complete(engine.dispose())
        except Exception:
            pass
        loop.close()


@celery_app.task
def generate_recommendations_for_org(org_id: str) -> dict:
    """Generate strategic recommendations for a single organization."""
    from uuid import UUID

    from app.services.strategic_recommendations_service import (
        StrategicRecommendationsService,
    )

    async def _run() -> dict:
        from app.db import session as db_session
        async with db_session.AsyncSessionLocal() as db:
            service = StrategicRecommendationsService(db)
            created = await service.generate_for_organization(UUID(org_id))
            await db.commit()
            return {"organization_id": org_id, "created_count": len(created)}

    try:
        result = run_async(_run)
        logger.info("Generated %s recommendations for org %s", result["created_count"], org_id)
        return result
    except RuntimeError as exc:
        # AI not configured — log and skip quietly
        logger.warning("Skipping org %s: %s", org_id, exc)
        return {"organization_id": org_id, "created_count": 0, "skipped": str(exc)}
    except Exception:
        logger.exception("Failed generating recommendations for org %s", org_id)
        raise


@celery_app.task
def generate_weekly_recommendations() -> dict:
    """Fan out recommendation generation across every active organization."""
    from app.models.user import Organization
    from sqlalchemy import select

    async def _get_org_ids() -> list[str]:
        from app.db import session as db_session
        async with db_session.AsyncSessionLocal() as db:
            result = await db.execute(select(Organization.id))
            return [str(row[0]) for row in result.all()]

    org_ids = run_async(_get_org_ids)
    logger.info("Scheduling weekly recommendations for %s organizations", len(org_ids))
    for org_id in org_ids:
        generate_recommendations_for_org.delay(org_id)
    return {"scheduled": len(org_ids)}
