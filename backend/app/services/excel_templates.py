"""Excel template styles and renderer for professional export formatting."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet


@dataclass
class TemplateStyle:
    """Visual parameters for an Excel template."""

    name: str
    # Header
    header_fill_color: str
    header_font_color: str
    header_font_size: int = 11
    # Rows
    row_even_fill: str = "FFFFFF"
    row_odd_fill: str = "F9F9F9"
    # KPI / accent
    kpi_accent_color: str = "333333"
    kpi_accent_size: int = 14
    kpi_accent_fill: str | None = None
    # Borders
    border_color: str = "E0E0E0"
    # Title banner
    title_fill_color: str | None = None
    title_font_color: str = "FFFFFF"
    title_font_size: int = 16
    subtitle_font_size: int = 11


CLEAN = TemplateStyle(
    name="clean",
    header_fill_color="F0F0F0",
    header_font_color="333333",
    row_even_fill="FFFFFF",
    row_odd_fill="F9F9F9",
    kpi_accent_color="333333",
    kpi_accent_size=14,
    border_color="E0E0E0",
    title_fill_color="F0F0F0",
    title_font_color="333333",
    title_font_size=16,
)

CORPORATE = TemplateStyle(
    name="corporate",
    header_fill_color="1F4E79",
    header_font_color="FFFFFF",
    row_even_fill="FFFFFF",
    row_odd_fill="D6E4F0",
    kpi_accent_color="1F4E79",
    kpi_accent_size=14,
    border_color="B4C6DB",
    title_fill_color="1F4E79",
    title_font_color="FFFFFF",
    title_font_size=16,
)

EXECUTIVE = TemplateStyle(
    name="executive",
    header_fill_color="1B2631",
    header_font_color="FFFFFF",
    row_even_fill="FFFFFF",
    row_odd_fill="EAECEE",
    kpi_accent_color="F39C12",
    kpi_accent_size=14,
    kpi_accent_fill="F39C12",
    border_color="ABB2B9",
    title_fill_color="1B2631",
    title_font_color="FFFFFF",
    title_font_size=16,
)

TEMPLATES: dict[str, TemplateStyle] = {
    "clean": CLEAN,
    "corporate": CORPORATE,
    "executive": EXECUTIVE,
}


class ExcelTemplateRenderer:
    """Renders styled Excel sheets using a TemplateStyle."""

    def __init__(self, style: TemplateStyle) -> None:
        self.style = style
        self._header_fill = PatternFill(
            start_color=style.header_fill_color,
            end_color=style.header_fill_color,
            fill_type="solid",
        )
        self._header_font = Font(
            bold=True,
            color=style.header_font_color,
            size=style.header_font_size,
        )
        self._even_fill = PatternFill(
            start_color=style.row_even_fill,
            end_color=style.row_even_fill,
            fill_type="solid",
        )
        self._odd_fill = PatternFill(
            start_color=style.row_odd_fill,
            end_color=style.row_odd_fill,
            fill_type="solid",
        )
        self._border = Border(
            left=Side(style="thin", color=style.border_color),
            right=Side(style="thin", color=style.border_color),
            top=Side(style="thin", color=style.border_color),
            bottom=Side(style="thin", color=style.border_color),
        )
        self._kpi_font = Font(
            bold=True,
            color=style.kpi_accent_color,
            size=style.kpi_accent_size,
        )
        self._kpi_fill = (
            PatternFill(
                start_color=style.kpi_accent_fill,
                end_color=style.kpi_accent_fill,
                fill_type="solid",
            )
            if style.kpi_accent_fill
            else None
        )
        self._title_fill = (
            PatternFill(
                start_color=style.title_fill_color,
                end_color=style.title_fill_color,
                fill_type="solid",
            )
            if style.title_fill_color
            else None
        )
        self._title_font = Font(
            bold=True,
            color=style.title_font_color,
            size=style.title_font_size,
        )
        self._subtitle_font = Font(
            color=style.title_font_color,
            size=style.subtitle_font_size,
        )

    def write_title_banner(
        self,
        ws: Worksheet,
        title: str,
        subtitle: str,
        metadata_rows: list[tuple[str, str]],
    ) -> int:
        """Write a branded title banner area. Returns the next free row."""
        num_cols = max(6, 2 + len(metadata_rows))

        # Title row
        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=num_cols)
        cell = ws.cell(row=1, column=1, value=title)
        cell.font = self._title_font
        cell.alignment = Alignment(horizontal="left", vertical="center")
        if self._title_fill:
            for col in range(1, num_cols + 1):
                ws.cell(row=1, column=col).fill = self._title_fill
            cell.fill = self._title_fill
        ws.row_dimensions[1].height = 36

        # Subtitle row
        ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=num_cols)
        cell = ws.cell(row=2, column=1, value=subtitle)
        cell.font = self._subtitle_font
        cell.alignment = Alignment(horizontal="left", vertical="center")
        if self._title_fill:
            for col in range(1, num_cols + 1):
                ws.cell(row=2, column=col).fill = self._title_fill
            cell.fill = self._title_fill
        ws.row_dimensions[2].height = 22

        # Metadata rows
        row_num = 4
        for label, value in metadata_rows:
            ws.cell(row=row_num, column=1, value=label).font = Font(bold=True, size=10)
            ws.cell(row=row_num, column=2, value=value).font = Font(size=10)
            row_num += 1

        return row_num + 1

    def write_data_sheet(
        self,
        ws: Worksheet,
        rows: list[dict[str, Any]],
        columns: list[str],
        headers: list[str],
        start_row: int = 1,
    ) -> None:
        """Write a data table with styled headers and alternating rows."""
        # Headers
        for col_idx, header in enumerate(headers, 1):
            cell = ws.cell(row=start_row, column=col_idx, value=header)
            cell.font = self._header_font
            cell.fill = self._header_fill
            cell.alignment = Alignment(horizontal="center", vertical="center")
            cell.border = self._border
        ws.row_dimensions[start_row].height = 28

        # Data rows
        for row_idx, row_data in enumerate(rows):
            excel_row = start_row + 1 + row_idx
            fill = self._even_fill if row_idx % 2 == 0 else self._odd_fill
            for col_idx, col_key in enumerate(columns, 1):
                value = row_data.get(col_key, "")
                value = self._normalize_value(value)
                cell = ws.cell(row=excel_row, column=col_idx, value=value)
                cell.fill = fill
                cell.border = self._border
                cell.alignment = Alignment(vertical="center")
                # Right-align numbers
                if isinstance(value, (int, float)):
                    cell.alignment = Alignment(horizontal="right", vertical="center")
                    if isinstance(value, float):
                        cell.number_format = '#,##0.00'
                    else:
                        cell.number_format = '#,##0'

        # Auto-width columns
        self._auto_width(ws, columns, headers, start_row, len(rows))

    def write_summary_sheet(
        self,
        ws: Worksheet,
        summary_rows: list[dict[str, Any]],
        columns: list[str],
        headers: list[str],
        start_row: int = 1,
    ) -> None:
        """Write a summary/KPI table with accent highlighting on values."""
        # Headers
        for col_idx, header in enumerate(headers, 1):
            cell = ws.cell(row=start_row, column=col_idx, value=header)
            cell.font = self._header_font
            cell.fill = self._header_fill
            cell.alignment = Alignment(horizontal="center", vertical="center")
            cell.border = self._border
        ws.row_dimensions[start_row].height = 28

        for row_idx, row_data in enumerate(summary_rows):
            excel_row = start_row + 1 + row_idx
            fill = self._even_fill if row_idx % 2 == 0 else self._odd_fill
            for col_idx, col_key in enumerate(columns, 1):
                value = row_data.get(col_key, "")
                value = self._normalize_value(value)
                cell = ws.cell(row=excel_row, column=col_idx, value=value)
                cell.fill = fill
                cell.border = self._border
                cell.alignment = Alignment(vertical="center")

                # KPI accent on current_value column
                if col_key == "current_value":
                    cell.font = self._kpi_font
                    if self._kpi_fill:
                        cell.fill = self._kpi_fill
                        cell.font = Font(
                            bold=True,
                            color="FFFFFF",
                            size=self.style.kpi_accent_size,
                        )

                # Change % formatting (green/red)
                if col_key == "change_percent" and value != "":
                    self.apply_change_formatting(cell, value)

                if isinstance(value, (int, float)):
                    cell.alignment = Alignment(horizontal="right", vertical="center")

        self._auto_width(ws, columns, headers, start_row, len(summary_rows))

    def apply_change_formatting(self, cell: Any, value: Any) -> None:
        """Apply green for positive, red for negative change values."""
        try:
            num = float(value)
        except (TypeError, ValueError):
            return
        if num > 0:
            cell.font = Font(bold=True, color="27AE60")
        elif num < 0:
            cell.font = Font(bold=True, color="E74C3C")

    def _normalize_value(self, value: Any) -> Any:
        """Convert values to Excel-friendly types."""
        if isinstance(value, Decimal):
            return float(value)
        if isinstance(value, datetime):
            return value.strftime("%Y-%m-%d %H:%M:%S")
        if isinstance(value, date):
            return value.isoformat()
        if value is None:
            return ""
        return value

    def _auto_width(
        self,
        ws: Worksheet,
        columns: list[str],
        headers: list[str],
        start_row: int,
        num_rows: int,
    ) -> None:
        """Auto-fit column widths based on header and data content."""
        for col_idx, header in enumerate(headers, 1):
            max_len = len(str(header))
            # Sample first 50 rows for width
            for row_offset in range(min(num_rows, 50)):
                cell = ws.cell(row=start_row + 1 + row_offset, column=col_idx)
                if cell.value is not None:
                    max_len = max(max_len, len(str(cell.value)))
            ws.column_dimensions[get_column_letter(col_idx)].width = min(max_len + 3, 50)
