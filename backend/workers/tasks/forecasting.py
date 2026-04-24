"""Forecasting Celery tasks."""
import asyncio
from uuid import UUID
import logging

from workers.celery_app import celery_app

logger = logging.getLogger(__name__)


def run_async(coro_factory):
    """Run async function in sync context.

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
def generate_forecast(account_id: str, asin: str = None, horizon_days: int = 30):
    """Generate forecast for an account/product."""
    from app.services.forecast_service import ForecastService

    async def _generate():
        from app.db import session as db_session
        async with db_session.AsyncSessionLocal() as db:
            service = ForecastService(db)
            forecast = await service.generate_forecast(
                UUID(account_id),
                asin=asin,
                horizon_days=horizon_days,
            )
            await db.commit()
            return {"forecast_id": str(forecast.id)}

    try:
        logger.info(f"Generating forecast for account {account_id}, asin={asin}")
        result = run_async(_generate)
        logger.info(f"Forecast generated: {result}")
        return result

    except Exception as e:
        logger.exception(f"Forecast generation failed for account {account_id}")
        raise


@celery_app.task
def generate_all_forecasts():
    """Generate forecasts for all active accounts."""
    from app.models.amazon_account import AmazonAccount
    from sqlalchemy import select

    async def _get_account_ids():
        from app.db import session as db_session
        async with db_session.AsyncSessionLocal() as db:
            result = await db.execute(
                select(AmazonAccount.id)
                .where(AmazonAccount.is_active == True)
            )
            return [str(row[0]) for row in result.all()]

    account_ids = run_async(_get_account_ids)
    logger.info(f"Scheduling forecast generation for {len(account_ids)} accounts")

    for account_id in account_ids:
        generate_forecast.delay(account_id)

    return {"scheduled": len(account_ids)}


@celery_app.task
def calculate_trend_scores(account_id: str):
    """Calculate trend scores for all products in an account."""
    from app.services.forecast_service import ForecastService
    from app.models.product import Product
    from sqlalchemy import select

    async def _calculate():
        from app.db import session as db_session
        async with db_session.AsyncSessionLocal() as db:
            # Get all products for account
            result = await db.execute(
                select(Product.asin)
                .where(
                    Product.account_id == UUID(account_id),
                    Product.is_active == True,
                )
            )
            asins = [row[0] for row in result.all()]

            service = ForecastService(db)
            trends = []

            for asin in asins:
                try:
                    trend = await service.get_product_trend_score(UUID(account_id), asin)
                    trends.append(trend)
                except Exception as e:
                    logger.warning(f"Failed to calculate trend for {asin}: {e}")

            return {"trends": trends}

    return run_async(_calculate)
