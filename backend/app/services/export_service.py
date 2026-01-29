"""Export service for generating Excel, PowerPoint, etc."""
from datetime import date
from typing import List, Optional
from uuid import UUID
import io

from sqlalchemy.ext.asyncio import AsyncSession


class ExportService:
    """Service for exporting data to various formats."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def generate_excel_report(
        self,
        account_ids: List[UUID],
        start_date: date,
        end_date: date,
        include_sales: bool = True,
        include_inventory: bool = True,
        include_advertising: bool = True,
    ) -> bytes:
        """Generate comprehensive Excel report."""
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        from openpyxl.utils.dataframe import dataframe_to_rows
        import pandas as pd

        wb = Workbook()

        # Create styles
        header_font = Font(bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
        thin_border = Border(
            left=Side(style="thin"),
            right=Side(style="thin"),
            top=Side(style="thin"),
            bottom=Side(style="thin"),
        )

        # Summary sheet
        ws = wb.active
        ws.title = "Summary"
        ws["A1"] = "Inthezon Performance Report"
        ws["A1"].font = Font(bold=True, size=16)
        ws["A3"] = f"Report Period: {start_date} to {end_date}"

        # Add more sheets as needed...

        # Save to bytes
        output = io.BytesIO()
        wb.save(output)
        output.seek(0)

        return output.getvalue()

    async def generate_powerpoint_report(
        self,
        account_ids: List[UUID],
        start_date: date,
        end_date: date,
        template: str = "default",
    ) -> bytes:
        """Generate PowerPoint presentation."""
        from pptx import Presentation
        from pptx.util import Inches, Pt

        prs = Presentation()

        # Title slide
        title_slide_layout = prs.slide_layouts[0]
        slide = prs.slides.add_slide(title_slide_layout)
        title = slide.shapes.title
        subtitle = slide.placeholders[1]

        title.text = "Amazon Performance Report"
        subtitle.text = f"{start_date} to {end_date}"

        # Add more slides...

        # Save to bytes
        output = io.BytesIO()
        prs.save(output)
        output.seek(0)

        return output.getvalue()

    async def export_to_csv(
        self,
        data: List[dict],
        filename: str,
    ) -> bytes:
        """Export data to CSV."""
        import csv
        import io

        if not data:
            return b""

        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=data[0].keys())
        writer.writeheader()
        writer.writerows(data)

        return output.getvalue().encode()
