"""Market research endpoints."""
from datetime import datetime
import logging
import time
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select as sa_select

from app.api.deps import CurrentUser, CurrentOrganization, DbSession
from app.schemas.market_research import (
    MarketResearchCreate,
    MarketResearchResponse,
    MarketResearchListItem,
    ComparisonMatrixResponse,
    MarketSearchRequest,
    MarketSearchResult,
    MarketSearchResponse,
    ProductSnapshot,
    CompetitorSnapshot,
    AIAnalysis,
    AIRecommendation,
)
from app.services.market_research_service import (
    MarketResearchService,
    process_report_background,
    _backfill_missing_prices,
    _detect_sentinel_prices,
    _flag_sentinel_prices,
)
from app.config import settings
from workers.tasks.market_research import process_market_research

logger = logging.getLogger(__name__)

router = APIRouter()

MARKET_SEARCH_RESULT_LIMIT = 20
MARKET_SEARCH_CANDIDATE_LIMIT = 60


def _classify_market_search_pricing_failure(exc: Exception) -> str:
    """Map pricing lookup failures to stable UI-facing reason codes."""
    error_code = str(getattr(exc, "error_code", "") or getattr(exc, "code", "")).lower()
    message = str(exc).lower()
    if "throttl" in error_code or "throttl" in message:
        return "pricing_throttled"
    if (
        "forbidden" in error_code
        or "unauthorized" in error_code
        or "accessdenied" in error_code
        or "403" in message
        or "forbidden" in message
        or "not authorized" in message
    ):
        return "pricing_forbidden"
    return "pricing_failed"


def _mark_missing_price(row: dict, reason: str) -> None:
    missing = list(row.get("missing_data") or [])
    if "price" not in missing:
        missing.append("price")
    row["missing_data"] = missing
    row["price_unavailable_reason"] = reason


def _coerce_positive_price(value) -> Optional[float]:
    try:
        price = float(value)
    except (TypeError, ValueError):
        return None
    if price <= 0:
        return None
    return price


def _report_to_response(report) -> MarketResearchResponse:
    """Convert a MarketResearchReport model to response schema."""
    product_snapshot = None
    if report.product_snapshot:
        product_snapshot = ProductSnapshot(**report.product_snapshot)

    competitor_data = None
    if report.competitor_data:
        competitor_data = [CompetitorSnapshot(**c) for c in report.competitor_data]

    # Distinguish "AI narrative is off because no key is configured" from
    # "the AI call failed for this report" so the UI can be honest about it.
    ai_status = None
    if report.status == "completed":
        if report.ai_analysis:
            ai_status = "ok"
        elif settings.ANTHROPIC_API_KEY:
            ai_status = "unavailable"
        else:
            ai_status = "unconfigured"

    ai_analysis = None
    if report.ai_analysis:
        recs = [
            AIRecommendation(**r) for r in report.ai_analysis.get("recommendations", [])
        ]
        ai_analysis = AIAnalysis(
            strengths=report.ai_analysis.get("strengths", []),
            weaknesses=report.ai_analysis.get("weaknesses", []),
            recommendations=recs,
            overall_score=report.ai_analysis.get("overall_score", 50),
            summary=report.ai_analysis.get("summary", ""),
        )

    return MarketResearchResponse(
        id=str(report.id),
        organization_id=str(report.organization_id),
        account_id=str(report.account_id),
        source_asin=report.source_asin,
        marketplace=report.marketplace,
        language=report.language,
        title=report.title,
        status=report.status,
        progress_step=report.progress_step,
        progress_pct=report.progress_pct or 0,
        error_message=report.error_message,
        product_snapshot=product_snapshot,
        competitor_data=competitor_data,
        ai_analysis=ai_analysis,
        ai_status=ai_status,
        created_at=report.created_at.isoformat() if report.created_at else "",
        completed_at=report.completed_at.isoformat() if report.completed_at else None,
        last_refreshed_at=(
            report.last_refreshed_at.isoformat() if report.last_refreshed_at else None
        ),
    )


@router.post("/generate", response_model=MarketResearchResponse)
async def generate_report(
    data: MarketResearchCreate,
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
):
    """Create a new market research report.

    Competitors are discovered automatically via SP-API catalog search.
    Optionally, extra_competitor_asins can be provided to include specific ASINs.
    """
    if data.extra_competitor_asins and len(data.extra_competitor_asins) > settings.MARKET_RESEARCH_MAX_COMPETITORS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Maximum {settings.MARKET_RESEARCH_MAX_COMPETITORS} extra competitors allowed",
        )

    service = MarketResearchService(db)
    try:
        report = await service.create_report(
            org_id=organization.id,
            user_id=current_user.id,
            data=data,
        )
        await db.commit()
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )

    task_kwargs = {
        "extra_asins": data.extra_competitor_asins or [],
        "market_competitor_asins": data.market_competitor_asins or [],
        "search_query": data.search_query,
        "search_type": data.search_type,
        "market_search_results": [
            snapshot.model_dump()
            for snapshot in (data.market_search_results or [])
        ],
    }

    def _run_inline() -> None:
        import threading

        thread = threading.Thread(
            target=process_report_background,
            args=(str(report.id),),
            kwargs=task_kwargs,
            daemon=True,
        )
        thread.start()

    if settings.run_tasks_inline:
        # No Celery worker in this deployment: dispatch in-process deterministically.
        _run_inline()
    else:
        try:
            process_market_research.delay(str(report.id), **task_kwargs)
        except Exception:
            logger.exception(
                "Failed to enqueue market research %s on Celery; falling back to in-process thread",
                report.id,
            )
            _run_inline()

    return _report_to_response(report)


@router.get("", response_model=List[MarketResearchListItem])
async def list_reports(
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
    limit: int = 20,
    offset: int = 0,
):
    """List market research reports for the organization."""
    service = MarketResearchService(db)
    reports = await service.list_reports(organization.id, limit, offset)

    return [
        MarketResearchListItem(
            id=str(r.id),
            title=r.title,
            source_asin=r.source_asin,
            status=r.status,
            language=r.language,
            created_at=r.created_at.isoformat() if r.created_at else "",
            competitor_count=len(r.competitor_data) if r.competitor_data else 0,
        )
        for r in reports
    ]


@router.get("/{report_id}", response_model=MarketResearchResponse)
async def get_report(
    report_id: UUID,
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
):
    """Get a market research report by ID."""
    service = MarketResearchService(db)
    report = await service.get_report(report_id, organization.id)

    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report not found",
        )

    return _report_to_response(report)


@router.post("/{report_id}/refresh", response_model=MarketResearchResponse)
async def refresh_report(
    report_id: UUID,
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
):
    """Refresh competitor snapshots for an existing completed report."""
    from app.core.amazon.credentials import resolve_credentials
    from app.core.amazon.sp_api_client import SPAPIClient, resolve_marketplace
    from app.models.amazon_account import AmazonAccount
    from app.models.market_research import MarketResearchReport
    from app.services.market_research_service import _fetch_product_data
    from app.services.market_research_service import _backfill_missing_prices_from_catalog

    result = await db.execute(
        sa_select(MarketResearchReport)
        .where(
            MarketResearchReport.id == report_id,
            MarketResearchReport.organization_id == organization.id,
        )
        .with_for_update()
    )
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report not found",
        )

    if report.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only completed reports can be refreshed",
        )

    existing_competitors = report.competitor_data or []
    if not existing_competitors:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Report has no competitor data to refresh",
        )

    result = await db.execute(
        sa_select(AmazonAccount).where(
            AmazonAccount.id == report.account_id,
            AmazonAccount.organization_id == organization.id,
        )
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account not found or does not belong to organization",
        )

    try:
        credentials = resolve_credentials(account, organization)
        marketplace = resolve_marketplace(account.marketplace_country)
        client = SPAPIClient(
            credentials,
            marketplace,
            account_type=account.account_type.value,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to connect to Amazon SP-API: {exc}",
        )

    refreshed_competitors = []
    total_competitors = len(existing_competitors)
    for index, existing_snapshot in enumerate(existing_competitors):
        current_snapshot = dict(existing_snapshot or {})
        asin = current_snapshot.get("asin")

        if not asin:
            fetch_errors = list(current_snapshot.get("fetch_errors") or [])
            fetch_errors.append("asin:missing")
            current_snapshot["fetch_errors"] = list(dict.fromkeys(fetch_errors))
            refreshed_competitors.append(current_snapshot)
        else:
            fresh_snapshot = _fetch_product_data(client, str(asin).upper())
            merged_snapshot = dict(current_snapshot)
            merged_snapshot.update(fresh_snapshot)
            if fresh_snapshot.get("fetch_errors"):
                merged_snapshot["fetch_errors"] = fresh_snapshot["fetch_errors"]
            else:
                merged_snapshot.pop("fetch_errors", None)
            if "catalog_unavailable_reason" not in fresh_snapshot:
                merged_snapshot.pop("catalog_unavailable_reason", None)
            if "pricing_unavailable_reason" not in fresh_snapshot:
                merged_snapshot.pop("pricing_unavailable_reason", None)
            refreshed_competitors.append(merged_snapshot)

        if index < total_competitors - 1:
            time.sleep(1.0)

    # Re-run the batched price backfill and sentinel detection over the
    # refreshed dataset: a placeholder price that appears for the first time
    # during a refresh must be flagged exactly like at generation time.
    product_snapshot = dict(report.product_snapshot or {})
    all_snapshots = ([product_snapshot] if product_snapshot else []) + refreshed_competitors
    _backfill_missing_prices(client, all_snapshots)
    await _backfill_missing_prices_from_catalog(db, report.account_id, all_snapshots)
    _flag_sentinel_prices(all_snapshots)
    if product_snapshot:
        report.product_snapshot = product_snapshot

    report.competitor_data = refreshed_competitors
    report.last_refreshed_at = datetime.utcnow()
    await db.commit()
    await db.refresh(report)

    return _report_to_response(report)


@router.get("/{report_id}/comparison-matrix", response_model=ComparisonMatrixResponse)
async def get_comparison_matrix(
    report_id: UUID,
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
):
    """Get a dimension-by-dimension comparison matrix for a completed report."""
    service = MarketResearchService(db)
    report = await service.get_report(report_id, organization.id)

    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report not found",
        )

    if report.status != "completed" or not report.product_snapshot or not report.competitor_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Comparison matrix is only available for completed reports with competitor data",
        )

    return service.get_comparison_matrix(report)


@router.delete("/{report_id}")
async def delete_report(
    report_id: UUID,
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
):
    """Delete a market research report."""
    service = MarketResearchService(db)
    deleted = await service.delete_report(report_id, organization.id)

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report not found",
        )

    await db.commit()
    return {"status": "deleted"}


@router.post("/market-search", response_model=MarketSearchResponse)
async def market_search(
    data: MarketSearchRequest,
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
):
    """Search the market by keyword, brand, or ASIN (Market Tracker 360).

    Returns a list of products found on Amazon matching the search query,
    with their metrics (price, BSR, reviews, rating).
    """
    from sqlalchemy import select as sa_select
    from app.models.amazon_account import AmazonAccount
    from app.core.amazon.sp_api_client import SPAPIClient, resolve_marketplace
    from app.core.amazon.credentials import resolve_credentials
    from app.models.user import Organization
    from app.models.product import Product

    # Verify account belongs to org
    result = await db.execute(
        sa_select(AmazonAccount).where(
            AmazonAccount.id == UUID(data.account_id),
            AmazonAccount.organization_id == organization.id,
        )
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account not found or does not belong to organization",
        )

    # Load org for credential resolution
    org_result = await db.execute(
        sa_select(Organization).where(Organization.id == organization.id)
    )
    org = org_result.scalar_one_or_none()

    try:
        credentials = resolve_credentials(account, org)
        marketplace = resolve_marketplace(account.marketplace_country)
        client = SPAPIClient(
            credentials, marketplace,
            account_type=account.account_type.value,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to connect to Amazon SP-API: {e}",
        )

    async def _load_internal_price_fallbacks(asins: List[str]) -> dict[str, float]:
        """Return saved account catalog prices for ASINs already known internally."""
        normalized = list(dict.fromkeys(asin.upper() for asin in asins if asin))
        if not normalized:
            return {}

        result = await db.execute(
            sa_select(Product.asin, Product.current_price)
            .where(
                Product.account_id == account.id,
                Product.asin.in_(normalized),
                Product.current_price.is_not(None),
            )
        )
        prices: dict[str, float] = {}
        for asin, current_price in result.all():
            price = _coerce_positive_price(current_price)
            if price is not None:
                prices[str(asin).upper()] = price
        return prices

    async def _priced_results(items: List[dict], limit: int) -> List[dict]:
        """Return up to ``limit`` catalog results, enriching with Pricing API data when possible.

        Products without a price are still returned. The previous behaviour
        silently dropped them, which left the user with an empty market search
        whenever SP-API Pricing wasn't available (vendor accounts, throttling,
        403s, or items with no live offers). Missing fields are flagged via
        ``missing_data`` so the UI can display "N/A" markers explicitly.
        """
        missing_price_asins = [
            item["asin"]
            for item in items
            if item.get("asin") and item.get("price") is None
        ]
        pricing_failure_reason = None
        if getattr(client, "is_vendor", False):
            price_map = {}
            pricing_failure_reason = "pricing_unsupported_account_type"
        else:
            try:
                price_map = client.get_market_prices_for_asins(missing_price_asins)
            except Exception as exc:
                pricing_failure_reason = _classify_market_search_pricing_failure(exc)
                logger.warning(
                    "Bulk pricing lookup failed for market search; continuing without prices: %s",
                    exc,
                )
                price_map = {}

        still_missing = [
            asin
            for asin in missing_price_asins
            if price_map.get(str(asin).upper()) is None
        ]
        internal_price_map = await _load_internal_price_fallbacks(still_missing)

        enriched_items: List[dict] = []
        for item in items[:limit]:
            enriched = dict(item)
            if enriched.get("price") is None:
                price = price_map.get(str(enriched.get("asin", "")).upper())
                if price is not None:
                    enriched["price"] = float(price)
            if enriched.get("price") is None:
                price = internal_price_map.get(str(enriched.get("asin", "")).upper())
                if price is not None:
                    enriched["price"] = price

            if enriched.get("price") is None:
                _mark_missing_price(
                    enriched,
                    pricing_failure_reason or "api_no_price",
                )
            elif _coerce_positive_price(enriched.get("price")) is None:
                enriched["price"] = None
                _mark_missing_price(enriched, "invalid_price")

            missing_fields = [
                field
                for field in ("price", "bsr", "review_count", "rating")
                if enriched.get(field) is None
            ]
            if missing_fields:
                enriched["missing_data"] = missing_fields

            enriched_items.append(enriched)

        return enriched_items

    # Perform the search based on type
    from app.core.exceptions import AmazonAPIError

    try:
        if data.search_type == "asin":
            # For ASIN search: get the specific product + discover competitors
            from app.services.market_research_service import _fetch_product_data
            product = _fetch_product_data(client, data.query.upper())
            results = await _priced_results([product], limit=1)

            # Also discover related products using the product title
            title = product.get("title", "")
            if title:
                related = client.search_catalog_by_keyword(
                    title[:80],
                    max_results=MARKET_SEARCH_CANDIDATE_LIMIT,
                )
                related = [item for item in related if item["asin"] != data.query.upper()]
                results.extend(
                    await _priced_results(
                        related,
                        limit=max(MARKET_SEARCH_RESULT_LIMIT - len(results), 0),
                    )
                )
        else:
            # keyword or brand search
            raw_results = client.search_catalog_by_keyword(
                data.query,
                max_results=MARKET_SEARCH_CANDIDATE_LIMIT,
            )
            results = await _priced_results(raw_results, limit=MARKET_SEARCH_RESULT_LIMIT)
    except AmazonAPIError as e:
        error_code = getattr(e, "error_code", "UNKNOWN")
        if error_code == "THROTTLED":
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Amazon API rate limited. Please try again in a few seconds.",
            )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Amazon API error: {e}",
        )
    except Exception as e:
        logger.exception(f"Unexpected error in market search: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search failed: {str(e)[:200]}",
        )

    # Flag repeated placeholder prices server-side so every client gets
    # honest data, not just the web UI (which re-applies the same guard).
    sentinel_values = _detect_sentinel_prices(
        [float(r["price"]) for r in results if r.get("price") is not None]
    )
    for r in results:
        price = r.get("price")
        if price is not None and float(price) <= 0:
            r["price"] = None
            _mark_missing_price(r, "invalid_price")
        elif price is not None and float(price) in sentinel_values:
            r["price_unreliable"] = True
            _mark_missing_price(r, "price_unreliable")

    search_results = [
        MarketSearchResult(
            asin=r.get("asin", ""),
            title=r.get("title"),
            brand=r.get("brand"),
            category=r.get("category"),
            price=r.get("price"),
            bsr=r.get("bsr"),
            review_count=r.get("review_count"),
            rating=r.get("rating"),
            missing_data=r.get("missing_data") or None,
            price_unreliable=r.get("price_unreliable") or None,
            price_unavailable_reason=r.get("price_unavailable_reason"),
        )
        for r in results
    ]

    return MarketSearchResponse(
        results=search_results,
        total_found=len(search_results),
        query=data.query,
        search_type=data.search_type,
    )
