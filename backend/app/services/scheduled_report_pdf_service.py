"""PDF generation service for scheduled operational reports."""
from __future__ import annotations

import io
from datetime import datetime
from typing import Any, Dict, List

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def _stringify(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:,.2f}"
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M")
    return str(value)


class ScheduledOperationalPdfBuilder:
    """Build a compact multi-section PDF from collected export data."""

    def __init__(
        self,
        *,
        title: str,
        subtitle: str,
        generated_at: datetime,
        sections: List[Dict[str, Any]],
    ):
        self.title = title
        self.subtitle = subtitle
        self.generated_at = generated_at
        self.sections = sections
        base = getSampleStyleSheet()
        self.styles = {
            "title": ParagraphStyle(
                "title",
                parent=base["Heading1"],
                fontName="Helvetica-Bold",
                fontSize=20,
                leading=24,
                textColor=colors.HexColor("#1B2631"),
                spaceAfter=6,
            ),
            "subtitle": ParagraphStyle(
                "subtitle",
                parent=base["BodyText"],
                fontName="Helvetica",
                fontSize=10,
                leading=13,
                textColor=colors.HexColor("#5D6D7E"),
                spaceAfter=12,
            ),
            "section": ParagraphStyle(
                "section",
                parent=base["Heading2"],
                fontName="Helvetica-Bold",
                fontSize=13,
                leading=16,
                textColor=colors.HexColor("#1F4E79"),
                spaceBefore=8,
                spaceAfter=8,
            ),
            "body": ParagraphStyle(
                "body",
                parent=base["BodyText"],
                fontName="Helvetica",
                fontSize=9,
                leading=12,
                textColor=colors.HexColor("#2C3E50"),
            ),
        }

    def _summary_table(self, section: Dict[str, Any]) -> Table:
        headers = section["summary_headers"]
        rows = [
            [_stringify(row.get(column)) for column in section["summary_columns"]]
            for row in section["summary_rows"]
        ]
        table = Table([headers, *rows], repeatRows=1)
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F4E79")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#D5DBDB")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
                    ("LEFTPADDING", (0, 0), (-1, -1), 5),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        return table

    def _sheet_table(self, sheet: Dict[str, Any]) -> Table:
        headers = sheet["headers"]
        rows = [[_stringify(row.get(column)) for column in sheet["columns"]] for row in sheet["rows"]]
        table = Table([headers, *rows], repeatRows=1)
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EAF2F8")),
                    ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#2C3E50")),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                    ("FONTSIZE", (0, 0), (-1, -1), 7.5),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#D5DBDB")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F9FBFC")]),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ]
            )
        )
        return table

    def build(self) -> bytes:
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            leftMargin=1.5 * cm,
            rightMargin=1.5 * cm,
            topMargin=1.5 * cm,
            bottomMargin=1.5 * cm,
        )

        elements: List[Any] = [
            Paragraph(self.title, self.styles["title"]),
            Paragraph(self.subtitle, self.styles["subtitle"]),
            Paragraph(f"Generated at {self.generated_at.strftime('%Y-%m-%d %H:%M UTC')}", self.styles["body"]),
            Spacer(1, 0.35 * cm),
        ]

        for section_index, section in enumerate(self.sections):
            if section_index:
                elements.append(PageBreak())
            elements.append(Paragraph(section["title"], self.styles["section"]))
            elements.append(self._summary_table(section))
            elements.append(Spacer(1, 0.3 * cm))
            for sheet in section["sheets"]:
                elements.append(Paragraph(sheet["name"], self.styles["body"]))
                elements.append(Spacer(1, 0.1 * cm))
                elements.append(self._sheet_table(sheet))
                elements.append(Spacer(1, 0.25 * cm))

        doc.build(elements)
        return buffer.getvalue()
