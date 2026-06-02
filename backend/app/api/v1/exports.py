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
from app.services.strategic_recommendations_export import (
    build_recommendations_workbook_bytes,
)
from app.services.strategic_recommendations_service import (
    VALID_CATEGORIES as REC_VALID_CATEGORIES,
    VALID_STATUSES as REC_VALID_STATUSES,
    StrategicRecommendationsService,
)
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
    from datetime import datetime
    from openpyxl import Workbook

    from app.services.excel_templates import TEMPLATES, ExcelTemplateRenderer

    accounts_query = select(AmazonAccount.id).where(
        AmazonAccount.organization_id == organization.id
    )
    if account_ids:
        accounts_query = accounts_query.where(AmazonAccount.id.in_(account_ids))

    sales_rows: List[Dict] = []
    ads_rows: List[Dict] = []

    if include_sales:
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
        for sale in result.scalars().all():
            sales_rows.append({
                "date": sale.date.isoformat(),
                "asin": sale.asin,
                "sku": sale.sku or "",
                "units_ordered": sale.units_ordered,
                "revenue": float(sale.ordered_product_sales),
                "orders": sale.total_order_items,
                "currency": sale.currency,
            })

    if include_advertising:
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
        for metric, campaign_name in result.all():
            ads_rows.append({
                "date": metric.date.isoformat(),
                "campaign": campaign_name or "",
                "impressions": metric.impressions,
                "clicks": metric.clicks,
                "cost": float(metric.cost),
                "sales": float(metric.attributed_sales_7d),
                "roas": float(metric.roas or 0),
                "acos": float(metric.acos or 0),
            })

    renderer = ExcelTemplateRenderer(TEMPLATES["corporate"])
    wb = Workbook()
    wb.remove(wb.active)

    # Summary / KPI sheet
    summary_rows: List[Dict] = []
    if include_sales:
        summary_rows.append({"metric": "Units Ordered", "current_value": sum(r["units_ordered"] or 0 for r in sales_rows)})
        summary_rows.append({"metric": "Revenue", "current_value": round(sum(r["revenue"] for r in sales_rows), 2)})
        summary_rows.append({"metric": "Orders", "current_value": sum(r["orders"] or 0 for r in sales_rows)})
    if include_advertising:
        summary_rows.append({"metric": "Ad Impressions", "current_value": sum(r["impressions"] or 0 for r in ads_rows)})
        summary_rows.append({"metric": "Ad Clicks", "current_value": sum(r["clicks"] or 0 for r in ads_rows)})
        summary_rows.append({"metric": "Ad Spend", "current_value": round(sum(r["cost"] for r in ads_rows), 2)})
        summary_rows.append({"metric": "Ad Sales", "current_value": round(sum(r["sales"] for r in ads_rows), 2)})

    ws_summary = wb.create_sheet(title="Summary")
    next_row = renderer.write_title_banner(
        ws_summary,
        title="Inthezon Report",
        subtitle=f"{start_date.isoformat()} — {end_date.isoformat()}",
        metadata_rows=[
            ("Organization", organization.name),
            ("Period", f"{start_date} to {end_date}"),
            ("Generated at", datetime.utcnow().strftime("%Y-%m-%d %H:%M")),
        ],
    )
    renderer.write_summary_sheet(
        ws_summary,
        summary_rows,
        ["metric", "current_value"],
        ["Metric", "Value"],
        start_row=next_row,
    )

    if include_sales:
        ws_sales = wb.create_sheet(title="Sales Data")
        renderer.write_data_sheet(
            ws_sales,
            sales_rows,
            ["date", "asin", "sku", "units_ordered", "revenue", "orders", "currency"],
            ["Date", "ASIN", "SKU", "Units Ordered", "Revenue", "Orders", "Currency"],
        )

    if include_advertising:
        ws_ads = wb.create_sheet(title="Advertising")
        renderer.write_data_sheet(
            ws_ads,
            ads_rows,
            ["date", "campaign", "impressions", "clicks", "cost", "sales", "roas", "acos"],
            ["Date", "Campaign", "Impressions", "Clicks", "Cost", "Sales", "ROAS", "ACoS"],
        )

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
    language: str = Query(default="en", regex="^(en|it)$"),
):
    """Generate PowerPoint presentation."""
    from pptx import Presentation
    from pptx.util import Inches, Pt
    from pptx.dml.color import RGBColor
    from pptx.enum.text import PP_ALIGN

    accounts_result = await db.execute(
        select(AmazonAccount).where(AmazonAccount.organization_id == organization.id)
    )
    all_accounts = list(accounts_result.scalars().all())
    if account_ids:
        wanted = set(account_ids)
        scoped_accounts = [a for a in all_accounts if a.id in wanted]
    else:
        scoped_accounts = all_accounts
    scoped_account_ids = [a.id for a in scoped_accounts]

    # Totals come from the same daily aggregate rows used everywhere else
    # (export_service, sales reports). Summing per-ASIN rows alongside the
    # DAILY_TOTAL_ASIN aggregate double-counts revenue/units/orders.
    totals_revenue = 0.0
    totals_units = 0
    totals_orders = 0
    active_asins = 0
    currency = "EUR"
    if scoped_account_ids:
        totals_query = (
            select(
                func.sum(SalesData.ordered_product_sales).label("revenue"),
                func.sum(SalesData.units_ordered).label("units"),
                func.sum(SalesData.total_order_items).label("orders"),
                func.max(SalesData.currency).label("currency"),
            )
            .where(
                SalesData.account_id.in_(scoped_account_ids),
                SalesData.asin == DAILY_TOTAL_ASIN,
                SalesData.date >= start_date,
                SalesData.date <= end_date,
            )
        )
        totals = (await db.execute(totals_query)).one()
        totals_revenue = float(totals.revenue or 0)
        totals_units = int(totals.units or 0)
        totals_orders = int(totals.orders or 0)
        currency = totals.currency or "EUR"

        active_asins_query = (
            select(func.count(func.distinct(SalesData.asin)))
            .where(
                SalesData.account_id.in_(scoped_account_ids),
                SalesData.asin != DAILY_TOTAL_ASIN,
                SalesData.date >= start_date,
                SalesData.date <= end_date,
            )
        )
        active_asins = int((await db.execute(active_asins_query)).scalar() or 0)

    is_it = language == "it"

    def _label(en: str, it: str) -> str:
        return it if is_it else en

    def _money(value: float) -> str:
        if currency == "EUR":
            return f"€{value:,.2f}"
        if currency == "USD":
            return f"${value:,.2f}"
        if currency == "GBP":
            return f"£{value:,.2f}"
        return f"{value:,.2f} {currency}"

    def _safe_divide(a: float, b: float) -> float:
        return (a / b) if b else 0.0

    scope_label = (
        ", ".join(a.account_name for a in scoped_accounts)
        if scoped_accounts
        else _label("All accounts", "Tutti gli account")
    )
    if len(scope_label) > 80:
        scope_label = scope_label[:77] + "…"

    prs = Presentation()

    title_slide_layout = prs.slide_layouts[0]
    slide = prs.slides.add_slide(title_slide_layout)
    slide.shapes.title.text = _label(
        "Amazon Performance Report", "Report Prestazioni Amazon"
    )
    slide.placeholders[1].text = (
        f"{start_date.isoformat()} — {end_date.isoformat()}\n"
        f"{_label('Account scope', 'Ambito account')}: {scope_label}\n"
        f"{_label('Generated by Inthezon', 'Generato da Inthezon')}"
    )

    blank_slide_layout = prs.slide_layouts[6]
    slide = prs.slides.add_slide(blank_slide_layout)

    txBox = slide.shapes.add_textbox(Inches(0.5), Inches(0.4), Inches(9), Inches(0.8))
    title_para = txBox.text_frame.paragraphs[0]
    title_para.text = _label("Key Performance Indicators", "Indicatori di Performance")
    title_para.font.size = Pt(28)
    title_para.font.bold = True

    period_box = slide.shapes.add_textbox(
        Inches(0.5), Inches(1.15), Inches(9), Inches(0.4)
    )
    period_para = period_box.text_frame.paragraphs[0]
    period_para.text = (
        f"{_label('Period', 'Periodo')}: {start_date.isoformat()} — {end_date.isoformat()}  ·  "
        f"{_label('Scope', 'Ambito')}: {scope_label}"
    )
    period_para.font.size = Pt(12)
    period_para.font.color.rgb = RGBColor(90, 90, 90)

    kpis = [
        (_label("Total Revenue", "Fatturato Totale"), _money(totals_revenue)),
        (_label("Units Sold", "Unità Vendute"), f"{totals_units:,}"),
        (_label("Total Orders", "Ordini Totali"), f"{totals_orders:,}"),
        (
            _label("Avg. Order Value", "Valore Medio Ordine"),
            _money(_safe_divide(totals_revenue, totals_orders)),
        ),
        (
            _label("Avg. Selling Price", "Prezzo Medio Vendita"),
            _money(_safe_divide(totals_revenue, totals_units)),
        ),
        (_label("Active ASINs", "ASIN Attivi"), f"{active_asins:,}"),
    ]

    box_width = Inches(2.9)
    box_height = Inches(1.4)
    gap = Inches(0.1)
    columns = 3
    for index, (label, value) in enumerate(kpis):
        row = index // columns
        col = index % columns
        left = Inches(0.5) + (box_width + gap) * col
        top = Inches(1.8) + (box_height + gap) * row

        shape = slide.shapes.add_shape(1, left, top, box_width, box_height)
        shape.fill.solid()
        shape.fill.fore_color.rgb = RGBColor(31, 78, 121)
        shape.line.fill.background()

        tf = shape.text_frame
        tf.word_wrap = True
        p_label = tf.paragraphs[0]
        p_label.text = label
        p_label.font.size = Pt(12)
        p_label.font.color.rgb = RGBColor(255, 255, 255)
        p_label.alignment = PP_ALIGN.CENTER

        p_value = tf.add_paragraph()
        p_value.text = value
        p_value.font.size = Pt(22)
        p_value.font.bold = True
        p_value.font.color.rgb = RGBColor(255, 255, 255)
        p_value.alignment = PP_ALIGN.CENTER

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


@router.post("/forecast-csv")
async def export_forecast_csv(
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
    forecast_id: UUID = Query(...),
):
    """Generate a CSV export for a single forecast (history + predictions)."""
    import csv

    service = ForecastExportService(db)
    try:
        context = await service._get_forecast_context(
            org_id=organization.id,
            forecast_id=forecast_id,
            template="corporate",
            language="en",
        )
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Forecast not found",
        )

    forecast = context.forecast
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["segment", "date", "predicted_value", "lower_bound", "upper_bound", "currency"])

    for point in context.historical:
        writer.writerow([
            "historical",
            point.date.isoformat(),
            round(point.value, 2),
            "",
            "",
            "EUR",
        ])

    for p in (forecast.predictions or []):
        pred_date = p["date"]
        value = p["value"]
        writer.writerow([
            "forecast",
            pred_date if isinstance(pred_date, str) else pred_date.isoformat(),
            round(value, 2),
            round(p.get("lower", value * 0.8), 2),
            round(p.get("upper", value * 1.2), 2),
            "EUR",
        ])

    safe_name = context.account_name.replace(" ", "_")[:30]
    horizon = forecast.forecast_horizon_days or 30
    filename = f"inthezon_forecast_{safe_name}_{forecast.forecast_type or 'sales'}_{horizon}d_{date.today().isoformat()}.csv"

    return StreamingResponse(
        io.BytesIO(buffer.getvalue().encode("utf-8")),
        media_type="text/csv",
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

    # Build filename. The title may contain non-ASCII characters (e.g. the
    # narrow no-break space U+202F from Amazon listings) which break the
    # latin-1-only HTTP Content-Disposition header, so reduce it to safe ASCII.
    raw_title = (report.title or "report").replace(":", "")
    safe_title = "".join(
        ch if (ch.isascii() and (ch.isalnum() or ch in "-_")) else "_"
        for ch in raw_title
    )[:60].strip("_") or "report"
    filename = f"inthezon_{safe_title}_{date.today()}.pdf"

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/recommendations-xlsx")
async def export_recommendations_xlsx(
    db: DbSession,
    organization: CurrentOrganization,
    current_user: CurrentUser,
    status_: Optional[str] = Query(default=None, alias="status"),
    category: Optional[str] = Query(default=None),
    account_id: Optional[UUID] = Query(default=None),
    asin: Optional[str] = Query(default=None),
    ids: Optional[List[UUID]] = Query(default=None),
    language: str = Query(default="en", regex="^(en|it)$"),
    limit: int = Query(default=200, ge=1, le=500),
):
    """Export the matching strategic recommendations as a client-facing XLSX."""
    if status_ and status_ not in REC_VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status: {status_}")
    if category and category not in REC_VALID_CATEGORIES:
        raise HTTPException(status_code=400, detail=f"Invalid category: {category}")

    service = StrategicRecommendationsService(db)
    recommendations = await service.list_recommendations(
        organization.id,
        status=status_,
        category=category,
        account_id=account_id,
        limit=limit,
    )

    if ids:
        id_set = {str(rec_id) for rec_id in ids}
        recommendations = [rec for rec in recommendations if str(rec.id) in id_set]

    if asin:
        normalized = asin.strip().upper()

        def _matches_asin(rec) -> bool:
            ctx = rec.context if isinstance(rec.context, dict) else None
            if not ctx:
                return False
            asins = ctx.get("asins")
            if isinstance(asins, list) and normalized in {
                str(value).upper() for value in asins if isinstance(value, str)
            }:
                return True
            filters = ctx.get("generation_filters")
            if isinstance(filters, dict):
                raw = filters.get("asin")
                if isinstance(raw, str) and raw.upper() == normalized:
                    return True
            return False

        recommendations = [rec for rec in recommendations if _matches_asin(rec)]

    if not recommendations:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No recommendations match the requested filters",
        )

    accounts_result = await db.execute(
        select(AmazonAccount.id, AmazonAccount.account_name).where(
            AmazonAccount.organization_id == organization.id
        )
    )
    account_names = {str(row.id): row.account_name for row in accounts_result.all()}

    workbook_bytes = build_recommendations_workbook_bytes(
        recommendations,
        account_names=account_names,
        language=language,
        scope_account_id=str(account_id) if account_id else None,
        scope_asin=asin.strip().upper() if asin else None,
    )

    today = date.today().isoformat()
    suffix = (
        asin.strip().upper()
        if asin
        else (str(account_id)[:8] if account_id else "all")
    )
    filename = f"inthezon_recommendations_{suffix}_{today}_{language}.xlsx"

    return StreamingResponse(
        io.BytesIO(workbook_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{export_id}/download")
async def download_export(
    export_id: UUID,
    current_user: CurrentUser,
    organization: CurrentOrganization,
    db: DbSession,
):
    """Download a previously generated export by job id."""
    service = ForecastExportService(db)
    job = await service.get_job(export_id, organization.id)
    if not job or not job.artifact_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Export not found",
        )

    filename = job.artifact_filename or f"export_{job.id}.zip"
    return StreamingResponse(
        io.BytesIO(job.artifact_data),
        media_type=job.artifact_content_type or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
