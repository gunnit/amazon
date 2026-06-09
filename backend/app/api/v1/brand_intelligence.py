"""Weekly Brand Intelligence endpoints.

Scheduled, persisted, diff-based weekly brand reports. POST /generate enqueues
the pipeline (Celery, with an in-process fallback like Brand Analysis); the
client polls GET /reports/{id} until status reaches a terminal value.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import List
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import CurrentOrganization, CurrentUser, DbSession
from app.schemas.brand_intelligence import (
    GenerateRequest,
    GenerateResponse,
    ReportDetail,
    ReportSummary,
    ScheduleConfig,
)
from app.services.brand_intelligence_service import (
    BrandIntelligenceService,
    report_to_detail,
    report_to_summary,
    resolve_week_period,
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/reports", response_model=List[ReportSummary])
async def list_reports(
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
    account_id: UUID = Query(...),
    limit: int = Query(default=20, ge=1, le=100),
):
    service = BrandIntelligenceService(db)
    account = await service.resolve_account(organization.id, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")
    reports = await service.list_reports(organization.id, account_id, limit=limit)
    return [report_to_summary(r) for r in reports]


@router.get("/reports/latest", response_model=ReportDetail | None)
async def get_latest_report(
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
    account_id: UUID = Query(...),
):
    service = BrandIntelligenceService(db)
    account = await service.resolve_account(organization.id, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")
    report = await service.get_latest_completed(organization.id, account_id)
    if report is None:
        return None
    return report_to_detail(report)


@router.get("/reports/{report_id}", response_model=ReportDetail)
async def get_report(
    report_id: UUID,
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
):
    service = BrandIntelligenceService(db)
    report = await service.get_report(organization.id, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")
    return report_to_detail(report)


@router.post("/generate", response_model=GenerateResponse, status_code=status.HTTP_201_CREATED)
async def generate_report(
    payload: GenerateRequest,
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
):
    service = BrandIntelligenceService(db)
    account = await service.resolve_account(organization.id, payload.account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")

    period_start, period_end = resolve_week_period(payload.week)
    report = await service.create_pending_report(
        organization.id,
        account,
        period_start=period_start,
        period_end=period_end,
        generated_by="manual",
    )
    await db.commit()

    _enqueue(str(report.id))
    return GenerateResponse(id=report.id, status="pending")


@router.get("/schedule", response_model=ScheduleConfig)
async def get_schedule(
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
    account_id: UUID = Query(...),
):
    service = BrandIntelligenceService(db)
    account = await service.resolve_account(organization.id, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")
    schedule = await service.get_schedule(organization.id, account_id)
    if schedule is None:
        return ScheduleConfig(account_id=account_id, is_enabled=False, day_of_week=0, timezone="UTC")
    return ScheduleConfig(
        account_id=account_id,
        is_enabled=schedule.is_enabled,
        day_of_week=schedule.day_of_week,
        timezone=schedule.timezone,
    )


@router.put("/schedule", response_model=ScheduleConfig)
async def update_schedule(
    payload: ScheduleConfig,
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
):
    if not 0 <= payload.day_of_week <= 6:
        raise HTTPException(status_code=422, detail="day_of_week must be 0-6")
    service = BrandIntelligenceService(db)
    account = await service.resolve_account(organization.id, payload.account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")
    schedule = await service.upsert_schedule(
        organization.id,
        payload.account_id,
        is_enabled=payload.is_enabled,
        day_of_week=payload.day_of_week,
        timezone_name=payload.timezone,
    )
    await db.commit()
    return ScheduleConfig(
        account_id=payload.account_id,
        is_enabled=schedule.is_enabled,
        day_of_week=schedule.day_of_week,
        timezone=schedule.timezone,
    )


def _enqueue(report_id: str) -> None:
    """Enqueue the pipeline on Celery; fall back to an in-process thread if the
    broker is unreachable (mirrors Brand Analysis)."""
    from workers.tasks.brand_intelligence import process_brand_intelligence_report

    try:
        process_brand_intelligence_report.delay(report_id)
    except Exception:
        logger.exception(
            "Failed to enqueue brand intelligence %s on Celery; falling back to in-process thread",
            report_id,
        )
        import threading

        from app.services.brand_intelligence_service import process_brand_intelligence_report_job

        thread = threading.Thread(
            target=process_brand_intelligence_report_job, args=(report_id,), daemon=True
        )
        thread.start()
