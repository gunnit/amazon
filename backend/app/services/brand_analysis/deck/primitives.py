"""Thin python-pptx drawing layer driven by :class:`DeckTheme`.

Blocks call these instead of touching python-pptx directly, so geometry, colour
and type are consistent. All coordinates are inches on a 13.333 x 7.5 slide.
"""
from __future__ import annotations

import io
from typing import Optional

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt

from app.services.brand_analysis.deck.theme import RGB, DeckTheme

_ALIGN = {"left": PP_ALIGN.LEFT, "center": PP_ALIGN.CENTER, "right": PP_ALIGN.RIGHT}
_ANCHOR = {"top": MSO_ANCHOR.TOP, "middle": MSO_ANCHOR.MIDDLE, "bottom": MSO_ANCHOR.BOTTOM}


class DeckBuilder:
    """Owns the Presentation and exposes themed drawing primitives."""

    def __init__(self, brand: str) -> None:
        self.theme = DeckTheme
        self.brand = brand
        self.prs = Presentation()
        self.prs.slide_width = Inches(DeckTheme.SLIDE_W)
        self.prs.slide_height = Inches(DeckTheme.SLIDE_H)

    # Slide lifecycle ---------------------------------------------------------
    def blank_slide(self):
        return self.prs.slides.add_slide(self.prs.slide_layouts[6])

    def chrome(self, slide, page: int) -> None:
        """Top hairline brand band + page number. Replaces the rainbow footer."""
        self.rect(slide, 0, 0, DeckTheme.SLIDE_W, DeckTheme.HEADER_H, DeckTheme.BRAND_PRIMARY)
        self.text(slide, DeckTheme.MARGIN, 0.11, 4.0, 0.24, self.brand,
                  size=9, bold=True, color=DeckTheme.WHITE)
        self.text(slide, DeckTheme.SLIDE_W - 1.1, 0.11, 0.4, 0.24, str(page),
                  size=9, bold=True, color=DeckTheme.WHITE, align="right")
        self.rect(slide, 0, DeckTheme.FOOTER_Y + 0.18, DeckTheme.SLIDE_W, 0.012, DeckTheme.HAIRLINE)

    def heading(self, slide, title: str, subtitle: str = "") -> None:
        self.text(slide, DeckTheme.MARGIN, 0.74, DeckTheme.content_w(), 0.46, title,
                  size=DeckTheme.TYPE["h2"], bold=True, color=DeckTheme.INK)
        if subtitle:
            self.text(slide, DeckTheme.MARGIN, 1.22, DeckTheme.content_w(), 0.26, subtitle,
                      size=10, color=DeckTheme.MUTED)
        self.rect(slide, DeckTheme.MARGIN, 1.56, 0.62, 0.045, DeckTheme.BRAND_PRIMARY)

    # Drawing primitives ------------------------------------------------------
    def rect(self, slide, x, y, w, h, fill: RGB, *, line: Optional[RGB] = None, radius: bool = False):
        shape_type = MSO_SHAPE.ROUNDED_RECTANGLE if radius else MSO_SHAPE.RECTANGLE
        shape = slide.shapes.add_shape(shape_type, Inches(x), Inches(y), Inches(w), Inches(h))
        shape.shadow.inherit = False
        shape.fill.solid()
        shape.fill.fore_color.rgb = RGBColor(*fill)
        if line is None:
            shape.line.fill.background()
        else:
            shape.line.color.rgb = RGBColor(*line)
            shape.line.width = Pt(0.75)
        return shape

    def text(self, slide, x, y, w, h, value, *, size, bold=False,
             color: RGB = DeckTheme.INK, align="left", anchor="top"):
        box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
        frame = box.text_frame
        frame.clear()
        frame.word_wrap = True
        frame.margin_left = frame.margin_right = 0
        frame.margin_top = frame.margin_bottom = 0
        frame.vertical_anchor = _ANCHOR.get(anchor, MSO_ANCHOR.TOP)
        paragraph = frame.paragraphs[0]
        paragraph.alignment = _ALIGN.get(align, PP_ALIGN.LEFT)
        run = paragraph.add_run()
        run.text = str(value or "")
        run.font.name = DeckTheme.FONT
        run.font.size = Pt(size)
        run.font.bold = bold
        run.font.color.rgb = RGBColor(*color)
        return box

    def bullets(self, slide, x, y, w, h, items, *, size, color: RGB = DeckTheme.SUBTLE_INK):
        box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
        frame = box.text_frame
        frame.clear()
        frame.word_wrap = True
        frame.margin_left = frame.margin_right = 0
        frame.margin_top = frame.margin_bottom = 0
        for idx, item in enumerate(items):
            paragraph = frame.paragraphs[0] if idx == 0 else frame.add_paragraph()
            paragraph.space_after = Pt(3)
            run = paragraph.add_run()
            run.text = f"•  {item}"
            run.font.name = DeckTheme.FONT
            run.font.size = Pt(size)
            run.font.color.rgb = RGBColor(*color)
        return box

    def kpi(self, slide, x, y, w, h, label: str, value: str, *,
            accent: Optional[RGB] = None, chip: str = "") -> None:
        self.rect(slide, x, y, w, h, DeckTheme.CARD, line=DeckTheme.HAIRLINE, radius=True)
        self.rect(slide, x, y, 0.06, h, accent or DeckTheme.BRAND_PRIMARY)
        label_text = f"{label}  ·  {chip}" if chip else label
        self.text(slide, x + 0.18, y + 0.12, w - 0.3, 0.2, label_text,
                  size=DeckTheme.TYPE["kpi_label"], bold=True, color=DeckTheme.MUTED)
        self.text(slide, x + 0.18, y + 0.36, w - 0.3, h - 0.42, value,
                  size=DeckTheme.TYPE["kpi_value"], bold=True, color=DeckTheme.INK)

    def callout(self, slide, x, y, w, h, title: str, body, *,
                accent: Optional[RGB] = None) -> None:
        """A titled body card. ``body`` may be a string or a list of bullets."""
        self.rect(slide, x, y, w, h, DeckTheme.SURFACE, line=DeckTheme.HAIRLINE, radius=True)
        self.rect(slide, x, y, w, 0.05, accent or DeckTheme.BRAND_PRIMARY)
        self.text(slide, x + 0.2, y + 0.14, w - 0.4, 0.26, title,
                  size=DeckTheme.TYPE["body"], bold=True, color=DeckTheme.INK)
        if isinstance(body, (list, tuple)):
            self.bullets(slide, x + 0.2, y + 0.48, w - 0.4, h - 0.6,
                         [b for b in body if str(b).strip()], size=DeckTheme.TYPE["bullet"])
        elif body:
            self.text(slide, x + 0.2, y + 0.48, w - 0.4, h - 0.6, body,
                      size=DeckTheme.TYPE["bullet"], color=DeckTheme.SUBTLE_INK)

    def table(self, slide, x, y, headers, rows, widths, *,
              accent_columns=None, max_rows: int = 12) -> None:
        rows = rows[:max_rows]
        row_h = 0.34
        total_w = sum(widths)
        table_shape = slide.shapes.add_table(
            len(rows) + 1, len(headers), Inches(x), Inches(y),
            Inches(total_w), Inches(row_h * (len(rows) + 1)),
        )
        table = table_shape.table
        table.first_row = False
        table.horz_banding = False
        for idx, width in enumerate(widths):
            table.columns[idx].width = Inches(width)
        for col, header in enumerate(headers):
            cell = table.cell(0, col)
            cell.text = str(header)
            cell.fill.solid()
            cell.fill.fore_color.rgb = RGBColor(*DeckTheme.INK)
            self._cell_font(cell, bold=True, size=DeckTheme.TYPE["table_header"],
                            color=DeckTheme.WHITE)
        for r, row in enumerate(rows, start=1):
            band = DeckTheme.WHITE if r % 2 else DeckTheme.SURFACE
            for c, value in enumerate(row):
                cell = table.cell(r, c)
                cell.text = str(value)
                cell.fill.solid()
                cell.fill.fore_color.rgb = RGBColor(*band)
                color = None
                if accent_columns and c in accent_columns:
                    color = _signed_color(value)
                self._cell_font(cell, size=DeckTheme.TYPE["table_cell"], color=color)

    def picture(self, slide, png: bytes, x, y, w, h) -> None:
        slide.shapes.add_picture(io.BytesIO(png), Inches(x), Inches(y), Inches(w), Inches(h))

    def _cell_font(self, cell, *, bold=False, size=8, color: Optional[RGB] = None) -> None:
        cell.margin_left = Inches(0.07)
        cell.margin_right = Inches(0.05)
        cell.margin_top = Inches(0.03)
        cell.margin_bottom = Inches(0.03)
        cell.vertical_anchor = MSO_ANCHOR.MIDDLE
        for paragraph in cell.text_frame.paragraphs:
            for run in paragraph.runs:
                run.font.name = DeckTheme.FONT
                run.font.size = Pt(size)
                run.font.bold = bold
                if color is not None:
                    run.font.color.rgb = RGBColor(*color)

    def to_bytes(self) -> bytes:
        output = io.BytesIO()
        self.prs.save(output)
        return output.getvalue()


def _signed_color(value) -> Optional[RGB]:
    text = str(value).strip().replace("–", "-").replace("−", "-")
    if not text or text in {"—", "N/A"}:
        return None
    if text.startswith("+"):
        return DeckTheme.POSITIVE
    if text.startswith("-") and len(text) > 1 and text[1].isdigit():
        return DeckTheme.NEGATIVE
    return None
