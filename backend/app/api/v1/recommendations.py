"""Strategic recommendations endpoints (US-7.5)."""
from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import CurrentOrganization, CurrentUser, DbSession
from app.schemas.strategic_recommendation import (
    StrategicRecommendationGenerateRequest,
    StrategicRecommendationGenerateResponse,
    StrategicRecommendationOut,
    StrategicRecommendationStatusUpdate,
)
from app.services.strategic_recommendations_service import (
    VALID_CATEGORIES,
    VALID_STATUSES,
    StrategicRecommendationsService,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("", response_model=list[StrategicRecommendationOut])
async def list_recommendations(
    db: DbSession,
    org: CurrentOrganization,
    status_: Optional[str] = Query(default=None, alias="status"),
    category: Optional[str] = Query(default=None),
    account_id: Optional[UUID] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    if status_ and status_ not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status: {status_}")
    if category and category not in VALID_CATEGORIES:
        raise HTTPException(status_code=400, detail=f"Invalid category: {category}")
    service = StrategicRecommendationsService(db)
    return await service.list_recommendations(
        org.id,
        status=status_,
        category=category,
        account_id=account_id,
        limit=limit,
        offset=offset,
    )


@router.get("/{rec_id}", response_model=StrategicRecommendationOut)
async def get_recommendation(
    rec_id: UUID,
    db: DbSession,
    org: CurrentOrganization,
):
    service = StrategicRecommendationsService(db)
    rec = await service.get(rec_id, org.id)
    if rec is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recommendation not found")
    return rec


@router.patch("/{rec_id}", response_model=StrategicRecommendationOut)
async def update_recommendation_status(
    rec_id: UUID,
    payload: StrategicRecommendationStatusUpdate,
    db: DbSession,
    org: CurrentOrganization,
):
    service = StrategicRecommendationsService(db)
    try:
        rec = await service.mark_status(
            rec_id, org.id, payload.status, outcome_notes=payload.outcome_notes
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    await db.commit()
    return rec


@router.post(
    "/generate",
    response_model=StrategicRecommendationGenerateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def generate_recommendations(
    payload: StrategicRecommendationGenerateRequest,
    db: DbSession,
    org: CurrentOrganization,
    current_user: CurrentUser,
):
    service = StrategicRecommendationsService(db)
    try:
        created = await service.generate_for_organization(
            org.id,
            user_id=current_user.id,
            lookback_days=payload.lookback_days,
            language=payload.language,
            account_id=payload.account_id,
            asin=payload.asin,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except RuntimeError as exc:
        # AI not configured
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        # AI returned invalid JSON
        logger.exception("AI failure generating recommendations for org %s", org.id)
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    await db.commit()
    return StrategicRecommendationGenerateResponse(
        created_count=len(created),
        recommendations=created,
    )
