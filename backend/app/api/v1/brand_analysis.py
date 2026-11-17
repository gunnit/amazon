"""Brand Analysis Automation endpoints.

Brand Analysis is autonomous: it uses Inthezon's internal Amazon/SP-API
data + Market Research enrichment for the main flow, and manual upload
of external yearly product exports as a fallback. A prospect deck can also
be built from a Helium 10 Market Tracker 360 market when Helium 10 is
connected (optional; see app/core/helium10.py).
"""
from __future__ import annotations

import io
import logging
import threading
import time
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse

from app.api.deps import CurrentOrganization, CurrentUser, DbSession
from app.schemas.brand_analysis import (
    BrandAnalysisCreate,
    BrandAnalysisJobResponse,
    BrandAnalysisListItem,
    BrandAnalysisSourceFileResponse,
    ColumnValidationReport,
)
from app.services.brand_analysis_service import (
    RUNNING_STATUSES,
    TERMINAL_STATUSES,
    BrandAnalysisDataError,
    BrandAnalysisJobRunningError,
    BrandAnalysisService,
)
from app.services.brand_analysis_storage import BrandAnalysisStorage, StorageRef
from app.config import settings
from workers.tasks.brand_analysis import process_brand_analysis

logger = logging.getLogger(__name__)

router = APIRouter()

# Market Tracker 360 market types (DSA MarketTypeEnum).
_MT360_TYPES = {1: "keywords", 2: "brands", 3: "asins", 4: "automatic", 5: "subcategories"}
_MARKETS_CACHE_SECONDS = 600  # each listing costs one call of the 1,000/month quota
_markets_cache: dict[str, Any] = {"at": 0.0, "markets": None}
_markets_lock = threading.Lock()


@router.get("/helium10/markets")
async def list_helium10_markets(current_user: CurrentUser, organization: CurrentOrganization):
    """Market Tracker 360 markets of the connected Helium 10 account."""
    import asyncio

    from app.core import helium10

    client = helium10.get_client()
    if client is None:
        return {"connected": False, "markets": [], "error": None}
    now = time.time()
    with _markets_lock:
        cached = _markets_cache["markets"]
        fresh = cached is not None and now - _markets_cache["at"] < _MARKETS_CACHE_SECONDS
    if not fresh:
        try:
            rows = await asyncio.to_thread(client.list_markets)
        except Exception as exc:  # network, auth or tool error: show it, don't 500
            logger.warning("Helium 10 market list failed: %s", exc)
            return {"connected": True, "markets": [], "error": "helium10_unavailable"}
        cached = [
            {
                "id": int(row["id"]),
                "name": str(row.get("name") or row["id"]),
                "marketplace": row.get("marketplace"),
                "type": _MT360_TYPES.get(row.get("type"), "other"),
                "products": row.get("numberOfProducts"),
            }
            for row in rows
            if row.get("id") is not None
        ]
        with _markets_lock:
            _markets_cache.update(at=now, markets=cached)
    return {"connected": True, "markets": cached, "error": None}


def _source_to_response(source) -> BrandAnalysisSourceFileResponse:
    return BrandAnalysisSourceFileResponse(
        id=str(source.id),
        year=source.year,
        filename=source.filename,
        content_type=source.content_type,
        file_size=source.file_size,
        row_count=source.row_count,
        columns=source.columns or [],
        column_validation=(
            ColumnValidationReport(**source.column_validation)
            if source.column_validation else None
        ),
        created_at=source.created_at.isoformat() if source.created_at else "",
    )


def _download_ready(job) -> bool:
    """A job is downloadable when it is completed and bytes can be located."""
    if job.status not in {"completed", "completed_with_limitations"}:
        return False
    if job.artifact_data:
        return True
    ref = StorageRef.from_dict(job.storage_ref)
    return bool(ref and ref.backend == "s3" and ref.key)


def _job_to_response(job) -> BrandAnalysisJobResponse:
    return BrandAnalysisJobResponse(
        id=str(job.id),
        organization_id=str(job.organization_id),
        created_by_id=str(job.created_by_id) if job.created_by_id else None,
        account_id=str(job.account_id) if job.account_id else None,
        brand_name=job.brand_name,
        language=job.language,
        mode=job.mode,
        market_type=job.market_type,
        market_query=job.market_query,
        asin_list=job.asin_list or None,
        status=job.status,
        progress_step=job.progress_step,
        progress_pct=job.progress_pct or 0,
        error_message=job.error_message,
        error_code=job.error_code,
        data_source_name=job.data_source_name,
        metrics=job.metrics,
        metric_provenance=job.metric_provenance,
        capability_matrix=job.capability_matrix,
        data_coverage=job.data_coverage,
        limitations=job.limitations,
        sync_attempt_count=job.sync_attempt_count or 0,
        last_sync_error=job.last_sync_error,
        next_retry_at=job.next_retry_at.isoformat() if job.next_retry_at else None,
        narrative=job.narrative,
        source_files=[_source_to_response(source) for source in getattr(job, "source_files", [])],
        download_ready=_download_ready(job),
        artifact_filename=job.artifact_filename,
        created_at=job.created_at.isoformat() if job.created_at else "",
        updated_at=job.updated_at.isoformat() if job.updated_at else None,
        completed_at=job.completed_at.isoformat() if job.completed_at else None,
    )


def _job_to_list_item(job) -> BrandAnalysisListItem:
    return BrandAnalysisListItem(
        id=str(job.id),
        brand_name=job.brand_name,
        language=job.language,
        mode=job.mode,
        market_type=job.market_type,
        status=job.status,
        progress_pct=job.progress_pct or 0,
        error_message=job.error_message,
        error_code=job.error_code,
        source_years=sorted(source.year for source in getattr(job, "source_files", [])),
        download_ready=_download_ready(job),
        created_at=job.created_at.isoformat() if job.created_at else "",
        completed_at=job.completed_at.isoformat() if job.completed_at else None,
    )


@router.post("", response_model=BrandAnalysisJobResponse, status_code=status.HTTP_201_CREATED)
async def create_brand_analysis_job(
    payload: BrandAnalysisCreate,
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
):
    """Create a new brand analysis job."""
    service = BrandAnalysisService(db)
    try:
        job = await service.create_job(
            org_id=organization.id,
            user_id=current_user.id,
            data=payload,
        )
        await db.commit()
        job = await service.get_job(job.id, organization.id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return _job_to_response(job)


@router.get("", response_model=list[BrandAnalysisListItem])
async def list_brand_analysis_jobs(
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
    limit: int = 50,
    offset: int = 0,
):
    """List previous brand analysis jobs for the organization."""
    service = BrandAnalysisService(db)
    jobs = await service.list_jobs(organization.id, limit=limit, offset=offset)
    return [_job_to_list_item(job) for job in jobs]


@router.post("/{job_id}/upload/{year}", response_model=BrandAnalysisJobResponse)
async def upload_brand_analysis_export(
    job_id: UUID,
    year: int,
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
    file: UploadFile = File(...),
):
    """Upload a 2024 or 2025 external yearly product export as a fallback.

    Accepts CSV / XLSX with at minimum ASIN + revenue columns. Useful
    when Inthezon's internal SP-API data is incomplete for one or both
    years.
    """
    if year not in {2024, 2025}:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Year must be 2024 or 2025")

    service = BrandAnalysisService(db)
    job = await service.get_job(job_id, organization.id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Brand analysis job not found")

    data = await file.read()
    max_bytes = settings.BRAND_ANALYSIS_MAX_UPLOAD_MB * 1024 * 1024
    if len(data) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds {settings.BRAND_ANALYSIS_MAX_UPLOAD_MB} MB upload limit",
        )

    try:
        await service.save_source_file(
            job=job,
            year=year,
            filename=file.filename or f"yearly_export_{year}.csv",
            content_type=file.content_type,
            data=data,
            uploaded_by_id=current_user.id,
        )
        await db.commit()
    except BrandAnalysisDataError as exc:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    job = await service.get_job(job_id, organization.id)
    return _job_to_response(job)


@router.post("/{job_id}/start", response_model=BrandAnalysisJobResponse)
async def start_brand_analysis_processing(
    job_id: UUID,
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
):
    """Start deterministic analysis and PPTX generation."""
    service = BrandAnalysisService(db)
    job = await service.get_job(job_id, organization.id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Brand analysis job not found")
    if job.status in RUNNING_STATUSES:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Job is already running ({job.status})")

    from app.services.brand_analysis_service import _canonical_mode

    canonical = _canonical_mode(job.mode)
    source_years = {source.year for source in job.source_files}
    if canonical == "manual" and not {2024, 2025}.issubset(source_years):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Upload both 2024 and 2025 yearly product exports before starting manual processing",
        )
    if canonical == "helium10_mt360":
        from app.core import helium10

        if not helium10.is_configured():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Helium 10 is not connected",
            )
    if canonical == "internal" and not job.account_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Internal data mode requires a connected Amazon account",
        )

    job.status = "pending"
    job.progress_step = "Queued"
    job.progress_pct = 0
    job.error_message = None
    job.error_code = None
    job.last_sync_error = None
    job.next_retry_at = None
    job.cancel_requested = False
    job.celery_task_id = None
    job.started_at = None
    await db.commit()

    import threading

    from app.services.brand_analysis_service import process_brand_analysis_job

    def _run_inline() -> None:
        job.started_at = datetime.utcnow()
        thread = threading.Thread(target=process_brand_analysis_job, args=(str(job.id),), daemon=True)
        thread.start()

    if settings.run_tasks_inline:
        # No Celery worker in this deployment: skip the broker entirely so the
        # job is dispatched deterministically (a blocking .delay() inside an
        # async route can stall the event loop).
        _run_inline()
        await db.commit()
    else:
        try:
            async_result = process_brand_analysis.delay(str(job.id))
            job.celery_task_id = async_result.id
            job.started_at = datetime.utcnow()
            await db.commit()
        except Exception:
            logger.exception(
                "Failed to enqueue brand analysis %s on Celery; falling back to in-process thread",
                job.id,
            )
            await db.rollback()
            _run_inline()
            await db.commit()

    job = await service.get_job(job_id, organization.id)
    return _job_to_response(job)


@router.post("/{job_id}/cancel", response_model=BrandAnalysisJobResponse)
async def cancel_brand_analysis_job(
    job_id: UUID,
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
):
    """Request cancellation of a running or queued brand analysis job.

    Pending/not-yet-running jobs are cancelled immediately. Running jobs are
    flagged for cooperative cancellation (the processor aborts at its next
    phase boundary) and the Celery task is revoked best-effort. Already
    terminal jobs return 409.
    """
    service = BrandAnalysisService(db)
    job = await service.get_job(job_id, organization.id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Brand analysis job not found")
    if job.status in TERMINAL_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Job is already finished ({job.status})",
        )

    await service.request_cancel(job_id, organization.id)
    await db.commit()
    job = await service.get_job(job_id, organization.id)
    return _job_to_response(job)


@router.get("/{job_id}/download")
async def download_brand_analysis_pptx(
    job_id: UUID,
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
):
    """Download the generated Brand Analysis PPTX."""
    service = BrandAnalysisService(db)
    job = await service.get_job(job_id, organization.id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Brand analysis job not found")
    if job.status not in {"completed", "completed_with_limitations"}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Brand analysis deck is not ready (status: {job.status})",
        )

    ref = StorageRef.from_dict(job.storage_ref)
    bytes_data = BrandAnalysisStorage().load(ref, fallback=job.artifact_data)
    if not bytes_data:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Brand analysis deck artifact is missing",
        )

    filename = job.artifact_filename or f"brand_analysis_{job.id}.pptx"
    return StreamingResponse(
        io.BytesIO(bytes_data),
        media_type=job.artifact_content_type or "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{job_id}", response_model=BrandAnalysisJobResponse)
async def get_brand_analysis_job(
    job_id: UUID,
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
):
    """Get brand analysis job status and metrics."""
    service = BrandAnalysisService(db)
    job = await service.get_job(job_id, organization.id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Brand analysis job not found")
    return _job_to_response(job)


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_brand_analysis_job(
    job_id: UUID,
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
):
    """Delete a brand analysis job and its artifacts.

    A running job cannot be deleted directly; cancel it first to avoid
    orphaning artifacts and racing the worker's final commit.
    """
    service = BrandAnalysisService(db)
    try:
        deleted = await service.delete_job(job_id, organization.id)
    except BrandAnalysisJobRunningError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Brand analysis job not found")
    await db.commit()
    return None
