"""Services for scheduled operational reports."""
from __future__ import annotations

import asyncio
import io
import logging
import threading
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.models.amazon_account import AmazonAccount
from app.models.scheduled_report import ScheduledReport, ScheduledReportRun
from app.models.user import Organization
from app.schemas.report import (
    ScheduledReportCreate,
    ScheduledReportParameters,
    ScheduledReportResponse,
    ScheduledReportRunResponse,
    ScheduledReportUpdate,
)
from app.services.export_service import ExportService
from app.services.scheduled_report_pdf_service import ScheduledOperationalPdfBuilder
from app.services.scheduled_report_utils import compute_next_run_at, resolve_report_period, utcnow

logger = logging.getLogger(__name__)

RUN_TERMINAL_STATUS = {"delivered", "failed"}


def _filename_slug(name: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "_" for ch in name).strip("_")[:48] or "report"


def _iso(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value else None


def _serialize_parameters(parameters: dict[str, Any]) -> ScheduledReportParameters:
    return ScheduledReportParameters(**(parameters or {}))


def scheduled_report_to_response(schedule: ScheduledReport) -> ScheduledReportResponse:
    """Serialize a scheduled report model."""
    return ScheduledReportResponse(
        id=str(schedule.id),
        name=schedule.name,
        report_types=list(schedule.report_types or []),
        frequency=schedule.frequency,
        format=schedule.format,
        timezone=schedule.timezone,
        account_ids=list(schedule.account_ids or []),
        recipients=list(schedule.recipients or []),
        parameters=_serialize_parameters(schedule.parameters or {}),
        schedule_config=schedule.schedule_config or {},
        is_enabled=schedule.is_enabled,
        last_run_at=_iso(schedule.last_run_at),
        last_run_status=schedule.last_run_status,
        next_run_at=_iso(schedule.next_run_at),
        created_at=_iso(schedule.created_at) or "",
        updated_at=_iso(schedule.updated_at) or "",
    )


def scheduled_report_run_to_response(run: ScheduledReportRun) -> ScheduledReportRunResponse:
    """Serialize a scheduled report run model."""
    return ScheduledReportRunResponse(
        id=str(run.id),
        scheduled_report_id=str(run.scheduled_report_id),
        status=run.status,
        generation_status=run.generation_status,
        delivery_status=run.delivery_status,
        progress_step=run.progress_step,
        error_message=run.error_message,
        triggered_at=run.triggered_at.isoformat(),
        period_start=run.period_start.isoformat(),
        period_end=run.period_end.isoformat(),
        completed_at=_iso(run.completed_at),
        artifact_filename=run.artifact_filename,
        download_ready=bool(run.artifact_data),
        recipients=list(run.recipients_snapshot or []),
    )


class ScheduledReportService:
    """CRUD and orchestration for scheduled reports."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def _validate_accounts(self, organization_id: UUID, account_ids: list[UUID]) -> list[str]:
        if not account_ids:
            return []
        result = await self.db.execute(
            select(AmazonAccount.id).where(
                AmazonAccount.organization_id == organization_id,
                AmazonAccount.id.in_(account_ids),
            )
        )
        found = {row[0] for row in result.all()}
        missing = [account_id for account_id in account_ids if account_id not in found]
        if missing:
            raise ValueError("One or more account IDs are invalid")
        return [str(account_id) for account_id in account_ids]

    async def _persist_org_timezone(self, organization: Organization, timezone_name: str) -> None:
        current = dict(organization.settings or {})
        if current.get("timezone") != timezone_name:
            current["timezone"] = timezone_name
            organization.settings = current

    async def list_schedules(self, organization_id: UUID) -> list[ScheduledReport]:
        result = await self.db.execute(
            select(ScheduledReport)
            .where(ScheduledReport.organization_id == organization_id)
            .order_by(ScheduledReport.created_at.desc())
        )
        return result.scalars().unique().all()

    async def get_schedule(self, schedule_id: UUID, organization_id: UUID) -> Optional[ScheduledReport]:
        result = await self.db.execute(
            select(ScheduledReport).where(
                ScheduledReport.id == schedule_id,
                ScheduledReport.organization_id == organization_id,
            )
        )
        return result.scalar_one_or_none()

    async def create_schedule(
        self,
        organization: Organization,
        user_id: UUID,
        payload: ScheduledReportCreate,
    ) -> ScheduledReport:
        account_ids = await self._validate_accounts(organization.id, payload.account_ids)
        await self._persist_org_timezone(organization, payload.timezone)

        schedule = ScheduledReport(
            organization_id=organization.id,
            created_by_id=user_id,
            name=payload.name.strip(),
            report_types=list(payload.report_types),
            frequency=payload.frequency,
            format=payload.format,
            timezone=payload.timezone,
            account_ids=account_ids,
            recipients=[str(email) for email in payload.recipients],
            parameters=payload.parameters.model_dump(),
            schedule_config=payload.schedule_config,
            is_enabled=payload.is_enabled,
            next_run_at=compute_next_run_at(payload.frequency, payload.schedule_config, payload.timezone),
        )
        self.db.add(schedule)
        await self.db.flush()
        await self.db.refresh(schedule)
        return schedule

    async def update_schedule(
        self,
        schedule: ScheduledReport,
        organization: Organization,
        payload: ScheduledReportUpdate,
    ) -> ScheduledReport:
        current = ScheduledReportCreate(
            name=payload.name if payload.name is not None else schedule.name,
            report_types=payload.report_types if payload.report_types is not None else list(schedule.report_types),
            frequency=payload.frequency if payload.frequency is not None else schedule.frequency,
            format=payload.format if payload.format is not None else schedule.format,
            timezone=payload.timezone if payload.timezone is not None else schedule.timezone,
            account_ids=[UUID(account_id) for account_id in (
                [str(account_id) for account_id in payload.account_ids] if payload.account_ids is not None else schedule.account_ids
            )],
            recipients=payload.recipients if payload.recipients is not None else list(schedule.recipients),
            parameters=payload.parameters if payload.parameters is not None else _serialize_parameters(schedule.parameters or {}),
            schedule_config=payload.schedule_config if payload.schedule_config is not None else (schedule.schedule_config or {}),
            is_enabled=payload.is_enabled if payload.is_enabled is not None else schedule.is_enabled,
        )

        schedule.name = current.name.strip()
        schedule.report_types = list(current.report_types)
        schedule.frequency = current.frequency
        schedule.format = current.format
        schedule.timezone = current.timezone
        schedule.account_ids = await self._validate_accounts(organization.id, current.account_ids)
        schedule.recipients = [str(email) for email in current.recipients]
        schedule.parameters = current.parameters.model_dump()
        schedule.schedule_config = current.schedule_config
        schedule.is_enabled = current.is_enabled
        schedule.next_run_at = (
            compute_next_run_at(schedule.frequency, schedule.schedule_config, schedule.timezone)
            if schedule.is_enabled
            else None
        )
        await self._persist_org_timezone(organization, current.timezone)
        await self.db.flush()
        await self.db.refresh(schedule)
        return schedule

    async def toggle_schedule(self, schedule: ScheduledReport, enabled: bool) -> ScheduledReport:
        schedule.is_enabled = enabled
        schedule.next_run_at = (
            compute_next_run_at(schedule.frequency, schedule.schedule_config, schedule.timezone)
            if enabled
            else None
        )
        await self.db.flush()
        await self.db.refresh(schedule)
        return schedule

    async def list_runs(self, schedule_id: UUID, organization_id: UUID, limit: int = 20) -> list[ScheduledReportRun]:
        result = await self.db.execute(
            select(ScheduledReportRun)
            .where(
                ScheduledReportRun.scheduled_report_id == schedule_id,
                ScheduledReportRun.organization_id == organization_id,
            )
            .order_by(ScheduledReportRun.triggered_at.desc())
            .limit(limit)
        )
        return result.scalars().all()

    async def get_run(self, run_id: UUID, organization_id: UUID) -> Optional[ScheduledReportRun]:
        result = await self.db.execute(
            select(ScheduledReportRun).where(
                ScheduledReportRun.id == run_id,
                ScheduledReportRun.organization_id == organization_id,
            )
        )
        return result.scalar_one_or_none()

    async def create_run(self, schedule: ScheduledReport, reference_time: Optional[datetime] = None) -> ScheduledReportRun:
        period_start, period_end = resolve_report_period(schedule.frequency, schedule.timezone, reference_time)
        run = ScheduledReportRun(
            scheduled_report_id=schedule.id,
            organization_id=schedule.organization_id,
            status="pending",
            generation_status="pending",
            delivery_status="pending",
            progress_step="Queued",
            period_start=period_start,
            period_end=period_end,
            report_name=schedule.name,
            format=schedule.format,
            timezone=schedule.timezone,
            recipients_snapshot=list(schedule.recipients or []),
            parameters_snapshot=dict(schedule.parameters or {}),
            report_types_snapshot=list(schedule.report_types or []),
        )
        self.db.add(run)
        schedule.last_run_at = utcnow()
        schedule.last_run_status = "pending"
        schedule.next_run_at = compute_next_run_at(schedule.frequency, schedule.schedule_config, schedule.timezone)
        await self.db.flush()
        await self.db.refresh(run)
        return run


class ScheduledReportArtifactService:
    """Generate report artifacts for scheduled runs."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.export_service = ExportService(db)

    async def build_artifact(self, schedule: ScheduledReport, run: ScheduledReportRun) -> tuple[bytes, str, str]:
        if schedule.format == "excel":
            payload, filename = await self.export_service.generate_excel_bundle(
                organization_id=schedule.organization_id,
                report_types=list(schedule.report_types),
                start_date=run.period_start,
                end_date=run.period_end,
                account_ids=[UUID(account_id) for account_id in (schedule.account_ids or [])] or None,
                group_by=(schedule.parameters or {}).get("group_by", "day"),
                low_stock_only=bool((schedule.parameters or {}).get("low_stock_only", False)),
                language=(schedule.parameters or {}).get("language", "en"),
                include_comparison=bool((schedule.parameters or {}).get("include_comparison", True)),
            )
            return payload, filename, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

        sections = await self._pdf_sections(schedule, run)
        builder = ScheduledOperationalPdfBuilder(
            title=schedule.name,
            subtitle=f"{run.period_start.isoformat()} to {run.period_end.isoformat()}",
            generated_at=utcnow(),
            sections=sections,
        )
        filename = f"{_filename_slug(schedule.name)}_{run.period_start.isoformat()}_{run.period_end.isoformat()}.pdf"
        return builder.build(), filename, "application/pdf"

    async def _pdf_sections(self, schedule: ScheduledReport, run: ScheduledReportRun) -> list[dict[str, Any]]:
        lang = (schedule.parameters or {}).get("language", "en")
        accounts = await self.export_service._get_accounts(
            schedule.organization_id,
            [UUID(account_id) for account_id in (schedule.account_ids or [])] or None,
        )
        sections: list[dict[str, Any]] = []
        for report_type in schedule.report_types:
            if report_type == "sales":
                collected = await self.export_service._collect_sales_data(
                    accounts,
                    run.period_start,
                    run.period_end,
                    (schedule.parameters or {}).get("group_by", "day"),
                    lang,
                    bool((schedule.parameters or {}).get("include_comparison", True)),
                )
            elif report_type == "inventory":
                collected = await self.export_service._collect_inventory_data(
                    accounts,
                    bool((schedule.parameters or {}).get("low_stock_only", False)),
                    lang,
                    bool((schedule.parameters or {}).get("include_comparison", True)),
                )
            else:
                collected = await self.export_service._collect_advertising_data(
                    accounts,
                    run.period_start,
                    run.period_end,
                    lang,
                    bool((schedule.parameters or {}).get("include_comparison", True)),
                )

            sections.append(
                {
                    "title": self.export_service._text(lang, f"{report_type}_report"),
                    "summary_headers": [self.export_service._text(lang, column) for column in collected["summary_columns"]],
                    "summary_columns": collected["summary_columns"],
                    "summary_rows": collected["summary_rows"],
                    "sheets": [
                        {
                            "name": sheet["name"],
                            "headers": [self.export_service._text(lang, column) for column in sheet["columns"]],
                            "columns": sheet["columns"],
                            "rows": sheet["rows"],
                        }
                        for sheet in collected["sheets"]
                    ],
                }
            )
        return sections


def enqueue_scheduled_run_processing(run_id: str) -> None:
    """Queue background execution for a scheduled report run."""
    from workers.tasks.scheduled_reports import process_scheduled_report_run_task

    try:
        process_scheduled_report_run_task.delay(run_id)
    except Exception:
        logger.exception("Failed to enqueue scheduled report run %s; using in-process thread fallback", run_id)
        thread = threading.Thread(target=process_scheduled_report_run_job, args=(run_id,), daemon=True)
        thread.start()


def process_scheduled_report_run_job(run_id: str) -> None:
    """Generate the scheduled report artifact and enqueue delivery."""
    from app.db.session import db_url as _db_url

    engine = create_async_engine(
        _db_url,
        echo=settings.APP_DEBUG,
        pool_size=2,
        max_overflow=1,
    )
    SessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False, autoflush=False)

    async def _process() -> None:
        async with SessionLocal() as db:
            run_result = await db.execute(select(ScheduledReportRun).where(ScheduledReportRun.id == UUID(run_id)))
            run = run_result.scalar_one_or_none()
            if not run:
                return

            schedule_result = await db.execute(select(ScheduledReport).where(ScheduledReport.id == run.scheduled_report_id))
            schedule = schedule_result.scalar_one_or_none()
            if not schedule:
                run.status = "failed"
                run.error_message = "Scheduled report not found"
                run.completed_at = utcnow()
                await db.commit()
                return

            try:
                run.status = "processing"
                run.generation_status = "processing"
                run.progress_step = "Generating report"
                schedule.last_run_status = "processing"
                await db.commit()

                artifact_service = ScheduledReportArtifactService(db)
                data, filename, content_type = await artifact_service.build_artifact(schedule, run)

                run.artifact_data = data
                run.artifact_filename = filename
                run.artifact_content_type = content_type
                run.generation_status = "generated"
                run.status = "generated"
                run.progress_step = "Report generated"
                schedule.last_run_status = "generated"
                await db.commit()
            except Exception as exc:
                logger.exception("Scheduled report generation failed for run %s", run_id)
                run.status = "failed"
                run.generation_status = "failed"
                run.delivery_status = "failed"
                run.error_message = str(exc)[:500]
                run.progress_step = "Generation failed"
                run.completed_at = utcnow()
                schedule.last_run_status = "failed"
                await db.commit()
                return

        from workers.tasks.scheduled_reports import deliver_scheduled_report_run_task

        try:
            deliver_scheduled_report_run_task.delay(run_id)
        except Exception:
            logger.exception("Failed to enqueue delivery for scheduled report run %s", run_id)
            deliver_scheduled_report_run_job(run_id)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_process())
    finally:
        loop.run_until_complete(engine.dispose())
        loop.close()


def deliver_scheduled_report_run_job(run_id: str) -> None:
    """Deliver a generated scheduled report via email."""
    from app.db.session import db_url as _db_url
    from app.services.notification_service import NotificationService

    engine = create_async_engine(
        _db_url,
        echo=settings.APP_DEBUG,
        pool_size=2,
        max_overflow=1,
    )
    SessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False, autoflush=False)

    async def _deliver() -> None:
        async with SessionLocal() as db:
            run_result = await db.execute(select(ScheduledReportRun).where(ScheduledReportRun.id == UUID(run_id)))
            run = run_result.scalar_one_or_none()
            if not run:
                return

            schedule_result = await db.execute(select(ScheduledReport).where(ScheduledReport.id == run.scheduled_report_id))
            schedule = schedule_result.scalar_one_or_none()
            if not schedule:
                return

            if not run.artifact_data:
                run.status = "failed"
                run.delivery_status = "failed"
                run.error_message = "Artifact is not available for delivery"
                run.completed_at = utcnow()
                schedule.last_run_status = "failed"
                await db.commit()
                return

            try:
                run.delivery_status = "processing"
                run.progress_step = "Sending email"
                schedule.last_run_status = "processing"
                await db.commit()

                service = NotificationService(sendgrid_api_key=settings.SENDGRID_API_KEY)
                sent = await service.send_email(
                    to_emails=list(run.recipients_snapshot or []),
                    subject=f"Inthezon Scheduled Report: {run.report_name}",
                    html_content=(
                        f"<p>Your scheduled report <strong>{run.report_name}</strong> is attached.</p>"
                        f"<p>Period: {run.period_start.isoformat()} to {run.period_end.isoformat()}</p>"
                    ),
                    attachments=[
                        {
                            "filename": run.artifact_filename or "report",
                            "content": run.artifact_data,
                            "content_type": run.artifact_content_type or "application/octet-stream",
                        }
                    ],
                )
                if not sent:
                    raise ValueError("Email delivery failed")

                run.delivery_status = "delivered"
                run.status = "delivered"
                run.progress_step = "Delivered"
                run.completed_at = utcnow()
                run.error_message = None
                schedule.last_run_status = "delivered"
                schedule.last_run_at = run.completed_at
                await db.commit()
            except Exception as exc:
                logger.exception("Scheduled report delivery failed for run %s", run_id)
                run.delivery_status = "failed"
                run.status = "failed"
                run.error_message = str(exc)[:500]
                run.progress_step = "Delivery failed"
                run.completed_at = utcnow()
                schedule.last_run_status = "failed"
                schedule.last_run_at = run.completed_at
                await db.commit()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_deliver())
    finally:
        loop.run_until_complete(engine.dispose())
        loop.close()
