"""PDF generation service for forecast insight exports."""
from __future__ import annotations

import io
from datetime import datetime
from typing import Any, Dict, List, Optional
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def _fmt_number(value: Optional[float], digits: int = 2) -> str:
    if value is None:
        return "N/A"
    return f"{value:,.{digits}f}"


def _fmt_eur(value: Optional[float]) -> str:
    if value is None:
        return "N/A"
    return f"EUR {value:,.2f}"


class ForecastInsightsPdfBuilder:
    """Build a PDF report from forecast data and AI insights."""

    def __init__(
        self,
        *,
        title: str,
        account_name: str,
        asin: Optional[str],
        forecast_type: str,
        model_used: str,
        horizon_days: int,
        confidence_interval: float,
        generated_at: Optional[datetime],
        metrics: Dict[str, Optional[float | str]],
        analysis: Dict[str, Any],
        language: str = "en",
        is_monthly: bool = False,
    ):
        self.title = title
        self.account_name = account_name
        self.asin = asin
        self.forecast_type = forecast_type
        self.model_used = model_used
        self.horizon_days = horizon_days
        self.confidence_interval = confidence_interval
        self.generated_at = generated_at
        self.metrics = metrics
        self.analysis = analysis
        self.language = language
        self.is_monthly = is_monthly
        self.styles = self._build_styles()

    def _build_styles(self) -> Dict[str, ParagraphStyle]:
        base = getSampleStyleSheet()
        return {
            "title": ParagraphStyle(
                "title",
                parent=base["Heading1"],
                fontName="Helvetica-Bold",
                fontSize=20,
                leading=24,
                textColor=colors.HexColor("#1B2631"),
                spaceAfter=12,
            ),
            "section": ParagraphStyle(
                "section",
                parent=base["Heading2"],
                fontName="Helvetica-Bold",
                fontSize=12,
                leading=15,
                textColor=colors.HexColor("#1F4E79"),
                spaceBefore=12,
                spaceAfter=8,
            ),
            "body": ParagraphStyle(
                "body",
                parent=base["BodyText"],
                fontName="Helvetica",
                fontSize=9.5,
                leading=13,
                textColor=colors.HexColor("#2C3E50"),
                spaceAfter=6,
            ),
            "bullet": ParagraphStyle(
                "bullet",
                parent=base["BodyText"],
                fontName="Helvetica",
                fontSize=9.5,
                leading=13,
                leftIndent=14,
                bulletIndent=0,
                spaceAfter=4,
            ),
            "table_header": ParagraphStyle(
                "table_header",
                parent=base["BodyText"],
                fontName="Helvetica-Bold",
                fontSize=8,
                leading=10,
                textColor=colors.white,
                wordWrap="CJK",
            ),
            "table_cell": ParagraphStyle(
                "table_cell",
                parent=base["BodyText"],
                fontName="Helvetica",
                fontSize=7.5,
                leading=9.5,
                textColor=colors.HexColor("#2C3E50"),
                wordWrap="CJK",
            ),
        }

    def _labels(self) -> Dict[str, str]:
        if self.language == "it":
            return {
                "account": "Account",
                "asin": "ASIN",
                "type": "Tipo previsione",
                "model": "Modello",
                "horizon": "Orizzonte",
                "confidence": "Confidenza",
                "generated": "Generato il",
                "summary": "Executive Summary",
                "kpis": "Forecast KPIs",
                "trends": "Trend principali",
                "risks": "Rischi",
                "opportunities": "Opportunità",
                "recommendations": "Raccomandazioni",
                "priority": "Priorità",
                "action": "Azione",
                "rationale": "Motivazione",
                "expected_impact": "Impatto atteso",
                "high": "Alta",
                "medium": "Media",
                "low": "Bassa",
                "total_forecast": "Fatturato totale previsto",
                "avg_period": "Media mensile" if self.is_monthly else "Media giornaliera",
                "peak_period": "Mese di picco" if self.is_monthly else "Giorno di picco",
                "peak_value": "Fatturato di picco",
                "mape": "MAPE",
                "rmse": "RMSE",
            }
        return {
            "account": "Account",
            "asin": "ASIN",
            "type": "Forecast Type",
            "model": "Model",
            "horizon": "Horizon",
            "confidence": "Confidence",
            "generated": "Generated At",
            "summary": "Executive Summary",
            "kpis": "Forecast KPIs",
            "trends": "Key Trends",
            "risks": "Risks",
            "opportunities": "Opportunities",
            "recommendations": "Recommendations",
            "priority": "Priority",
            "action": "Action",
            "rationale": "Rationale",
            "expected_impact": "Expected Impact",
            "high": "High",
            "medium": "Medium",
            "low": "Low",
            "total_forecast": "Total Forecast Revenue",
            "avg_period": "Average Monthly" if self.is_monthly else "Average Daily",
            "peak_period": "Peak Month" if self.is_monthly else "Peak Day",
            "peak_value": "Peak Revenue",
            "mape": "MAPE",
            "rmse": "RMSE",
        }

    def _horizon_label(self) -> str:
        if self.is_monthly:
            months = max(1, round(self.horizon_days / 30))
            if self.language == "it":
                return f"{months} {'mese' if months == 1 else 'mesi'}"
            return f"{months} {'month' if months == 1 else 'months'}"
        suffix = "giorni" if self.language == "it" else "days"
        return f"{self.horizon_days} {suffix}"

    def build(self) -> bytes:
        labels = self._labels()
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            leftMargin=1.8 * cm,
            rightMargin=1.8 * cm,
            topMargin=1.6 * cm,
            bottomMargin=1.6 * cm,
        )
        elements: List[Any] = []

        elements.append(Paragraph(self.title, self.styles["title"]))

        meta_rows = [
            [labels["account"], self.account_name],
            [labels["asin"], self.asin or "All Products"],
            [labels["type"], self.forecast_type],
            [labels["model"], self.model_used],
            [labels["horizon"], self._horizon_label()],
            [labels["confidence"], f"{int(self.confidence_interval * 100)}%"],
            [
                labels["generated"],
                self.generated_at.strftime("%Y-%m-%d %H:%M") if self.generated_at else "N/A",
            ],
        ]
        meta_table = Table(meta_rows, colWidths=[4.0 * cm, 11.8 * cm])
        meta_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#EBF5FB")),
                    ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#2C3E50")),
                    ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                    ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#D5DBDB")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )
        elements.append(meta_table)
        elements.append(Spacer(1, 0.3 * cm))

        elements.append(Paragraph(labels["summary"], self.styles["section"]))
        elements.append(Paragraph(self.analysis.get("summary", ""), self.styles["body"]))

        elements.append(Paragraph(labels["kpis"], self.styles["section"]))
        mape_val = self.metrics.get("mape")
        kpi_rows = [
            [labels["total_forecast"], _fmt_eur(self.metrics.get("total_predicted"))],
            [labels["avg_period"], _fmt_eur(self.metrics.get("avg_daily"))],
            [labels["peak_period"], str(self.metrics.get("peak_day") or "N/A")],
            [labels["peak_value"], _fmt_eur(self.metrics.get("peak_value"))],
            [labels["mape"], f"{_fmt_number(mape_val)}%" if mape_val is not None else "N/A"],
            [labels["rmse"], _fmt_eur(self.metrics.get("rmse"))],
        ]
        kpi_table = Table(kpi_rows, colWidths=[5.0 * cm, 10.8 * cm])
        kpi_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F8F9FA")),
                    ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                    ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#E5E7E9")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )
        elements.append(kpi_table)

        for section_key in ("key_trends", "risks", "opportunities"):
            items = self.analysis.get(section_key) or []
            if not items:
                continue
            label_key = {
                "key_trends": "trends",
                "risks": "risks",
                "opportunities": "opportunities",
            }[section_key]
            elements.append(Paragraph(labels[label_key], self.styles["section"]))
            for item in items:
                elements.append(Paragraph(item, self.styles["bullet"], bulletText="•"))

        recommendations = self.analysis.get("recommendations") or []
        if recommendations:
            elements.append(Paragraph(labels["recommendations"], self.styles["section"]))
            rec_rows = [[
                Paragraph(escape(labels["priority"]), self.styles["table_header"]),
                Paragraph(escape(labels["action"]), self.styles["table_header"]),
                Paragraph(escape(labels["rationale"]), self.styles["table_header"]),
                Paragraph(escape(labels["expected_impact"]), self.styles["table_header"]),
            ]]
            priority_labels = {
                "high": labels["high"],
                "medium": labels["medium"],
                "low": labels["low"],
            }
            for rec in recommendations:
                rec_rows.append([
                    Paragraph(
                        escape(priority_labels.get(rec.get("priority", "medium"), rec.get("priority", "medium"))),
                        self.styles["table_cell"],
                    ),
                    Paragraph(escape(rec.get("action", "")), self.styles["table_cell"]),
                    Paragraph(escape(rec.get("rationale", "")), self.styles["table_cell"]),
                    Paragraph(escape(rec.get("expected_impact", "")), self.styles["table_cell"]),
                ])

            rec_table = Table(rec_rows, colWidths=[1.8 * cm, 4.4 * cm, 4.8 * cm, 4.8 * cm], repeatRows=1)
            rec_table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F4E79")),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#D5DBDB")),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("ALIGN", (0, 0), (0, -1), "LEFT"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 5),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                        ("TOPPADDING", (0, 0), (-1, -1), 5),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                    ]
                )
            )
            elements.append(rec_table)

        doc.build(elements)
        return buffer.getvalue()
