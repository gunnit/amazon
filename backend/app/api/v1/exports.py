"""Export endpoints for Excel, PowerPoint, CSV, and PDF packages."""
from typing import Dict, List, Optional
from datetime import date, timedelta
from uuid import UUID
import io
import logging
from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, func

from app.api.deps import CurrentUser, CurrentOrganization, DbSession
from app.models.amazon_account import AmazonAccount
from app.models.forecast_export_job import ForecastExportJob
from app.models.sales_data import SalesData
from app.schemas.exports import ForecastExportCreate, ForecastExportJobResponse
from app.services.data_extraction import DAILY_TOTAL_ASIN
from app.services.export_service import ExportService
from app.services.forecast_export_service import (
    ForecastExportService,
    build_forecast_excel_filename,
    build_forecast_workbook_bytes,
)
from app.models.advertising import AdvertisingCampaign, AdvertisingMetrics
from workers.tasks.forecast_exports import process_forecast_export

logger = logging.getLogger(__name__)

router = APIRouter()


def _forecast_export_job_to_response(job: ForecastExportJob) -> ForecastExportJobResponse:
    """Convert a forecast export job model to its response schema."""
    return ForecastExportJobResponse(
        id=str(job.id),
        forecast_id=str(job.forecast_id),
        status=job.status,
        progress_step=job.progress_step,
        progress_pct=job.progress_pct or 0,
        error_message=job.error_message,
        include_insights=job.include_insights,
        template=job.template,
        language=job.language,
        download_ready=job.status == "completed" and bool(job.artifact_data),
        created_at=job.created_at.isoformat() if job.created_at else "",
        completed_at=job.completed_at.isoformat() if job.completed_at else None,
    )


@router.post("/csv")
async def export_to_csv_package(
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
    report_type: str = Query(..., regex="^(sales|inventory|advertising)$"),
    start_date: date = Query(default_factory=lambda: date.today() - timedelta(days=30)),
    end_date: date = Query(default_factory=lambda: date.today()),
    account_ids: Optional[List[UUID]] = Query(default=None),
    group_by: str = Query(default="day", regex="^(day|week|month)$"),
    low_stock_only: bool = Query(default=False),
    language: str = Query(default="en", regex="^(en|it)$"),
    include_comparison: bool = Query(default=True),
):
    """Generate a professional CSV ZIP package for the selected report."""
    export_service = ExportService(db)
    package_bytes, filename = await export_service.generate_csv_package(
        organization_id=organization.id,
        report_type=report_type,
        start_date=start_date,
        end_date=end_date,
        account_ids=account_ids,
        group_by=group_by,
        low_stock_only=low_stock_only,
        language=language,
        include_comparison=include_comparison,
    )

    return StreamingResponse(
        io.BytesIO(package_bytes),
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.post("/bundle")
async def export_bundle(
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
    report_types: List[str] = Query(...),
    start_date: date = Query(default_factory=lambda: date.today() - timedelta(days=30)),
    end_date: date = Query(default_factory=lambda: date.today()),
    account_ids: Optional[List[UUID]] = Query(default=None),
    group_by: str = Query(default="day", regex="^(day|week|month)$"),
    low_stock_only: bool = Query(default=False),
    language: str = Query(default="en", regex="^(en|it)$"),
    include_comparison: bool = Query(default=True),
):
    """Generate a bundled CSV ZIP package with multiple report types."""
    valid_types = {"sales", "inventory", "advertising"}
    for rt in report_types:
        if rt not in valid_types:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid report_type: {rt}. Must be one of {valid_types}",
            )

    export_service = ExportService(db)
    package_bytes, filename = await export_service.generate_bundle_package(
        organization_id=organization.id,
        report_types=report_types,
        start_date=start_date,
        end_date=end_date,
        account_ids=account_ids,
        group_by=group_by,
        low_stock_only=low_stock_only,
        language=language,
        include_comparison=include_comparison,
    )

    return StreamingResponse(
        io.BytesIO(package_bytes),
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.post("/excel-bundle")
async def export_excel_bundle(
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
    report_types: List[str] = Query(...),
    start_date: date = Query(default_factory=lambda: date.today() - timedelta(days=30)),
    end_date: date = Query(default_factory=lambda: date.today()),
    account_ids: Optional[List[UUID]] = Query(default=None),
    group_by: str = Query(default="day", regex="^(day|week|month)$"),
    low_stock_only: bool = Query(default=False),
    language: str = Query(default="en", regex="^(en|it)$"),
    include_comparison: bool = Query(default=True),
    template: str = Query(default="corporate", regex="^(clean|corporate|executive)$"),
):
    """Generate a styled Excel workbook with multiple report types."""
    valid_types = {"sales", "inventory", "advertising"}
    for rt in report_types:
        if rt not in valid_types:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid report_type: {rt}. Must be one of {valid_types}",
            )

    export_service = ExportService(db)
    package_bytes, filename = await export_service.generate_excel_bundle(
        organization_id=organization.id,
        report_types=report_types,
        start_date=start_date,
        end_date=end_date,
        template=template,
        account_ids=account_ids,
        group_by=group_by,
        low_stock_only=low_stock_only,
        language=language,
        include_comparison=include_comparison,
    )

    return StreamingResponse(
        io.BytesIO(package_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.post("/excel")
async def export_to_excel(
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
    start_date: date = Query(default_factory=lambda: date.today() - timedelta(days=30)),
    end_date: date = Query(default_factory=lambda: date.today()),
    account_ids: Optional[List[UUID]] = Query(default=None),
    include_sales: bool = Query(default=True),
    include_advertising: bool = Query(default=True),
):
    """Generate Excel export of data."""
    import pandas as pd
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment

    accounts_query = select(AmazonAccount.id).where(
        AmazonAccount.organization_id == organization.id
    )
    if account_ids:
        accounts_query = accounts_query.where(AmazonAccount.id.in_(account_ids))

    # Create workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Summary"

    # Header styling
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")

    # Summary sheet
    ws["A1"] = "Inthezon Report"
    ws["A1"].font = Font(bold=True, size=16)
    ws["A3"] = f"Period: {start_date} to {end_date}"
    ws["A4"] = f"Generated: {date.today()}"

    if include_sales:
        # Sales data sheet
        sales_ws = wb.create_sheet("Sales Data")

        # Get sales data
        sales_query = (
            select(SalesData)
            .where(
                SalesData.account_id.in_(accounts_query),
                SalesData.asin != DAILY_TOTAL_ASIN,
                SalesData.date >= start_date,
                SalesData.date <= end_date,
            )
            .order_by(SalesData.date.desc())
        )
        result = await db.execute(sales_query)
        sales_data = result.scalars().all()

        # Headers
        headers = ["Date", "ASIN", "SKU", "Units Ordered", "Revenue", "Orders", "Currency"]
        for col, header in enumerate(headers, 1):
            cell = sales_ws.cell(row=1, column=col, value=header)
            cell.font = header_font
            cell.fill = header_fill

        # Data rows
        for row_num, sale in enumerate(sales_data, 2):
            sales_ws.cell(row=row_num, column=1, value=sale.date.isoformat())
            sales_ws.cell(row=row_num, column=2, value=sale.asin)
            sales_ws.cell(row=row_num, column=3, value=sale.sku or "")
            sales_ws.cell(row=row_num, column=4, value=sale.units_ordered)
            sales_ws.cell(row=row_num, column=5, value=float(sale.ordered_product_sales))
            sales_ws.cell(row=row_num, column=6, value=sale.total_order_items)
            sales_ws.cell(row=row_num, column=7, value=sale.currency)

    if include_advertising:
        # Advertising data sheet
        ads_ws = wb.create_sheet("Advertising")

        campaigns_query = select(AdvertisingCampaign.id).where(
            AdvertisingCampaign.account_id.in_(accounts_query)
        )

        ads_query = (
            select(AdvertisingMetrics, AdvertisingCampaign.campaign_name)
            .join(AdvertisingCampaign)
            .where(
                AdvertisingMetrics.campaign_id.in_(campaigns_query),
                AdvertisingMetrics.date >= start_date,
                AdvertisingMetrics.date <= end_date,
            )
            .order_by(AdvertisingMetrics.date.desc())
        )
        result = await db.execute(ads_query)
        ads_data = result.all()

        # Headers
        headers = ["Date", "Campaign", "Impressions", "Clicks", "Cost", "Sales", "ROAS", "ACoS"]
        for col, header in enumerate(headers, 1):
            cell = ads_ws.cell(row=1, column=col, value=header)
            cell.font = header_font
            cell.fill = header_fill

        # Data rows
        for row_num, (metric, campaign_name) in enumerate(ads_data, 2):
            ads_ws.cell(row=row_num, column=1, value=metric.date.isoformat())
            ads_ws.cell(row=row_num, column=2, value=campaign_name or "")
            ads_ws.cell(row=row_num, column=3, value=metric.impressions)
            ads_ws.cell(row=row_num, column=4, value=metric.clicks)
            ads_ws.cell(row=row_num, column=5, value=float(metric.cost))
            ads_ws.cell(row=row_num, column=6, value=float(metric.attributed_sales_7d))
            ads_ws.cell(row=row_num, column=7, value=float(metric.roas or 0))
            ads_ws.cell(row=row_num, column=8, value=float(metric.acos or 0))

    # Save to bytes
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)

    filename = f"inthezon_report_{start_date}_{end_date}.xlsx"

    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.post("/powerpoint")
async def export_to_powerpoint(
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
    start_date: date = Query(default_factory=lambda: date.today() - timedelta(days=30)),
    end_date: date = Query(default_factory=lambda: date.today()),
    account_ids: Optional[List[UUID]] = Query(default=None),
    template: str = Query(default="default"),
):
    """Generate PowerPoint presentation."""
    from pptx import Presentation
    from pptx.util import Inches, Pt
    from pptx.dml.color import RgbColor
    from pptx.enum.text import PP_ALIGN

    accounts_query = select(AmazonAccount.id).where(
        AmazonAccount.organization_id == organization.id
    )
    if account_ids:
        accounts_query = accounts_query.where(AmazonAccount.id.in_(account_ids))

    # Get aggregated data
    sales_query = (
        select(
            func.sum(SalesData.ordered_product_sales).label("revenue"),
            func.sum(SalesData.units_ordered).label("units"),
            func.sum(SalesData.total_order_items).label("orders"),
        )
        .where(
            SalesData.account_id.in_(accounts_query),
            SalesData.date >= start_date,
            SalesData.date <= end_date,
        )
    )
    result = await db.execute(sales_query)
    totals = result.one()

    # Create presentation
    prs = Presentation()

    # Title slide
    title_slide_layout = prs.slide_layouts[0]
    slide = prs.slides.add_slide(title_slide_layout)
    title = slide.shapes.title
    subtitle = slide.placeholders[1]

    title.text = "Amazon Performance Report"
    subtitle.text = f"{start_date} to {end_date}\nGenerated by Inthezon"

    # KPIs slide
    blank_slide_layout = prs.slide_layouts[6]
    slide = prs.slides.add_slide(blank_slide_layout)

    # Title
    left = Inches(0.5)
    top = Inches(0.5)
    width = Inches(9)
    height = Inches(1)
    txBox = slide.shapes.add_textbox(left, top, width, height)
    tf = txBox.text_frame
    p = tf.paragraphs[0]
    p.text = "Key Performance Indicators"
    p.font.size = Pt(32)
    p.font.bold = True

    # KPI boxes
    kpis = [
        ("Total Revenue", f"${float(totals.revenue or 0):,.2f}"),
        ("Units Sold", f"{int(totals.units or 0):,}"),
        ("Total Orders", f"{int(totals.orders or 0):,}"),
    ]

    for i, (label, value) in enumerate(kpis):
        left = Inches(0.5 + i * 3)
        top = Inches(2)
        width = Inches(2.5)
        height = Inches(1.5)

        shape = slide.shapes.add_shape(1, left, top, width, height)  # Rectangle
        shape.fill.solid()
        shape.fill.fore_color.rgb = RgbColor(68, 114, 196)

        tf = shape.text_frame
        tf.word_wrap = True

        p = tf.paragraphs[0]
        p.text = label
        p.font.size = Pt(14)
        p.font.color.rgb = RgbColor(255, 255, 255)
        p.alignment = PP_ALIGN.CENTER

        p = tf.add_paragraph()
        p.text = value
        p.font.size = Pt(24)
        p.font.bold = True
        p.font.color.rgb = RgbColor(255, 255, 255)
        p.alignment = PP_ALIGN.CENTER

    # Save to bytes
    output = io.BytesIO()
    prs.save(output)
    output.seek(0)

    filename = f"inthezon_presentation_{start_date}_{end_date}.pptx"

    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.post("/forecast-excel")
async def export_forecast_excel(
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
    forecast_id: UUID = Query(...),
    template: str = Query(default="corporate", regex="^(clean|corporate|executive)$"),
    language: str = Query(default="en", regex="^(en|it)$"),
):
    """Generate a styled Excel workbook for a single forecast."""
    service = ForecastExportService(db)
    try:
        context = await service._get_forecast_context(
            org_id=organization.id,
            forecast_id=forecast_id,
            template=template,
            language=language,
        )
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Forecast not found",
        )

    workbook_bytes = build_forecast_workbook_bytes(
        context.forecast,
        context.account_name,
        template=template,
        language=language,
    )
    filename = build_forecast_excel_filename(
        context.forecast,
        context.account_name,
        template=template,
        language=language,
    )

    return StreamingResponse(
        io.BytesIO(workbook_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/forecast-package", response_model=ForecastExportJobResponse)
async def create_forecast_export_package(
    request: ForecastExportCreate,
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
):
    """Create an async forecast export package job."""
    service = ForecastExportService(db)
    try:
        job = await service.create_job(
            org_id=organization.id,
            user_id=current_user.id,
            forecast_id=UUID(request.forecast_id),
            template=request.template,
            language=request.language,
            include_insights=request.include_insights,
        )
        await db.commit()
    except ValueError as exc:
        message = str(exc)
        if "not configured" in message:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=message)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=message)

    try:
        process_forecast_export.delay(str(job.id))
    except Exception:
        logger.exception(
            "Failed to enqueue forecast export %s on Celery; falling back to in-process thread",
            job.id,
        )
        import threading

        from app.services.forecast_export_service import process_forecast_export_job

        thread = threading.Thread(
            target=process_forecast_export_job,
            args=(str(job.id),),
            daemon=True,
        )
        thread.start()

    return _forecast_export_job_to_response(job)


@router.get("/forecast-package/{job_id}", response_model=ForecastExportJobResponse)
async def get_forecast_export_package(
    job_id: UUID,
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
):
    """Get forecast export package job status."""
    service = ForecastExportService(db)
    job = await service.get_job(job_id, organization.id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Forecast export job not found",
        )
    return _forecast_export_job_to_response(job)


@router.get("/forecast-package/{job_id}/download")
async def download_forecast_export_package(
    job_id: UUID,
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
):
    """Download a completed forecast export package."""
    service = ForecastExportService(db)
    job = await service.get_job(job_id, organization.id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Forecast export job not found",
        )
    if job.status != "completed" or not job.artifact_data:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Forecast export is not ready (status: {job.status})",
        )

    filename = job.artifact_filename or f"forecast_export_{job.id}.zip"
    return StreamingResponse(
        io.BytesIO(job.artifact_data),
        media_type=job.artifact_content_type or "application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


class MarketResearchPdfRequest(BaseModel):
    """Request to generate a PDF for a market research report."""
    report_id: str
    language: str = Field(default="en", pattern="^(en|it)$")
    chart_images: Optional[Dict[str, str]] = None  # key -> base64 PNG


@router.post("/market-research-pdf")
async def export_market_research_pdf(
    request: MarketResearchPdfRequest,
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
):
    """Generate a professional PDF for a completed market research report."""
    from app.services.market_research_service import MarketResearchService
    from app.services.pdf_service import MarketResearchPdfBuilder

    service = MarketResearchService(db)
    report = await service.get_report(UUID(request.report_id), organization.id)

    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report not found",
        )
    if report.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Report is not completed (status: {report.status})",
        )

    try:
        builder = MarketResearchPdfBuilder(
            report=report,
            chart_images=request.chart_images,
            language=request.language,
        )
        pdf_bytes = builder.build()
    except Exception as e:
        logger.exception("PDF generation failed for report %s", request.report_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"PDF generation failed: {str(e)[:200]}",
        )

    # Build filename
    safe_title = (report.title or "report").replace(" ", "_").replace(":", "")[:60]
    filename = f"inthezon_{safe_title}_{date.today()}.pdf"

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{export_id}/download")
async def download_export(
    export_id: UUID,
    current_user: CurrentUser,
):
    """Download a previously generated export."""
    # This would retrieve from S3 in production
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Export not found"
    )
