"""Celery task wrapper for market research processing."""
import logging
from typing import List, Optional

from workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=2)
def process_market_research(
    self,
    report_id: str,
    extra_asins: Optional[List[str]] = None,
    market_competitor_asins: Optional[List[str]] = None,
    search_query: Optional[str] = None,
    search_type: Optional[str] = None,
):
    """Dispatch market research processing through the shared service logic."""
    from app.services.market_research_service import process_report_background

    try:
        process_report_background(
            report_id=report_id,
            extra_asins=extra_asins,
            market_competitor_asins=market_competitor_asins,
            search_query=search_query,
            search_type=search_type,
        )
    except Exception as exc:
        logger.exception("Market research task failed for %s", report_id)
        raise self.retry(exc=exc, countdown=60)
