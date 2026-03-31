"""PDF generation service for Market Research reports using ReportLab."""
from __future__ import annotations

import base64
import io
import math
from datetime import datetime
from typing import Any, Dict, List, Optional

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    Image,
    KeepTogether,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.doctemplate import NextPageTemplate
from reportlab.graphics.shapes import Drawing, Circle, Wedge, String, Line, Rect
from reportlab.graphics import renderPDF

from app.services.pdf_translations import t, Language

# ── Color palette ──
PRIMARY = colors.HexColor("#1B2631")
ACCENT = colors.HexColor("#2E86C1")
ACCENT_LIGHT = colors.HexColor("#EBF5FB")
TEXT_DARK = colors.HexColor("#2C3E50")
TEXT_MUTED = colors.HexColor("#7F8C8D")
POSITIVE = colors.HexColor("#27AE60")
NEGATIVE = colors.HexColor("#E74C3C")
WARNING = colors.HexColor("#F39C12")
BG_LIGHT = colors.HexColor("#F8F9FA")
BG_WHITE = colors.white
TABLE_HEADER_BG = colors.HexColor("#2E86C1")
TABLE_ALT_ROW = colors.HexColor("#F2F8FD")
DIVIDER = colors.HexColor("#D5DBDB")

PAGE_W, PAGE_H = A4  # 595.27 x 841.89 pt
MARGIN = 2 * cm
CONTENT_W = PAGE_W - 2 * MARGIN           # ~481.88 pt = 17.0 cm
HEADER_SPACE = 20                          # pt reserved below header on body pages
BODY_FRAME_H = PAGE_H - 2 * MARGIN - HEADER_SPACE - 10

# Spacing rhythm
SPACE_SM = 0.3 * cm
SPACE_MD = 0.5 * cm
SPACE_LG = 0.8 * cm

# Metric cards
CARD_COL_W = CONTENT_W / 4
CARD_INNER_W = CARD_COL_W - 0.3 * cm


def _fmt_price(value: Optional[float]) -> str:
    if value is None:
        return "—"
    return f"\u20ac{value:,.2f}"


def _fmt_number(value: Optional[int | float], decimals: int = 0) -> str:
    if value is None:
        return "—"
    if decimals == 0:
        return f"{int(value):,}"
    return f"{value:,.{decimals}f}"


def _fmt_pct_diff(product_val: Optional[float], avg_val: Optional[float]) -> tuple[str, str]:
    """Return (formatted_diff, tone) where tone is 'positive', 'negative', or 'neutral'."""
    if product_val is None or avg_val is None or avg_val == 0:
        return "—", "neutral"
    diff = ((product_val - avg_val) / abs(avg_val)) * 100
    if abs(diff) < 3:
        return "~0%", "neutral"
    sign = "+" if diff > 0 else ""
    return f"{sign}{diff:.1f}%", "positive" if diff > 0 else "negative"


def _truncate(text: Optional[str], max_len: int = 60) -> str:
    if not text:
        return "—"
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "\u2026"


class MarketResearchPdfBuilder:
    """Builds a professional PDF for a completed market research report."""

    def __init__(
        self,
        report: Any,
        chart_images: Optional[Dict[str, str]] = None,
        language: Language = "en",
    ):
        self.report = report
        self.chart_images = chart_images or {}
        self.lang = language
        self.product: dict = report.product_snapshot or {}
        self.competitors: list[dict] = report.competitor_data or []
        self.ai: dict = report.ai_analysis or {}
        self.is_market_search = (report.title or "").startswith("Market Search:")
        self._styles = self._build_styles()

    def _t(self, key: str) -> str:
        return t(key, self.lang)

    # ── Styles ──

    def _build_styles(self) -> dict[str, ParagraphStyle]:
        base = getSampleStyleSheet()
        return {
            "cover_brand": ParagraphStyle(
                "cover_brand", parent=base["Normal"],
                fontName="Helvetica-Bold", fontSize=28, textColor=ACCENT,
                alignment=TA_LEFT, leading=34, spaceAfter=4,
            ),
            "cover_tagline": ParagraphStyle(
                "cover_tagline", parent=base["Normal"],
                fontName="Helvetica", fontSize=11, textColor=TEXT_MUTED,
                alignment=TA_LEFT, leading=14, spaceAfter=16,
            ),
            "cover_title": ParagraphStyle(
                "cover_title", parent=base["Normal"],
                fontName="Helvetica-Bold", fontSize=20, textColor=PRIMARY,
                alignment=TA_LEFT, spaceAfter=12, leading=26,
            ),
            "cover_meta": ParagraphStyle(
                "cover_meta", parent=base["Normal"],
                fontName="Helvetica", fontSize=10, textColor=TEXT_MUTED,
                alignment=TA_LEFT, leading=14, spaceAfter=6,
            ),
            "h1": ParagraphStyle(
                "h1", parent=base["Normal"],
                fontName="Helvetica-Bold", fontSize=16, textColor=PRIMARY,
                leading=20, spaceAfter=10, spaceBefore=4,
                keepWithNext=True,
            ),
            "h2": ParagraphStyle(
                "h2", parent=base["Normal"],
                fontName="Helvetica-Bold", fontSize=12, textColor=ACCENT,
                leading=16, spaceAfter=8, spaceBefore=12,
                keepWithNext=True,
            ),
            "body": ParagraphStyle(
                "body", parent=base["Normal"],
                fontName="Helvetica", fontSize=9.5, textColor=TEXT_DARK,
                leading=14, spaceAfter=6,
            ),
            "body_muted": ParagraphStyle(
                "body_muted", parent=base["Normal"],
                fontName="Helvetica", fontSize=9, textColor=TEXT_MUTED,
                leading=13, spaceAfter=4,
            ),
            "caption": ParagraphStyle(
                "caption", parent=base["Normal"],
                fontName="Helvetica-Oblique", fontSize=8, textColor=TEXT_MUTED,
                leading=11, spaceAfter=8,
            ),
            "table_header": ParagraphStyle(
                "table_header", parent=base["Normal"],
                fontName="Helvetica-Bold", fontSize=8.5, textColor=BG_WHITE,
                leading=11,
            ),
            "table_cell": ParagraphStyle(
                "table_cell", parent=base["Normal"],
                fontName="Helvetica", fontSize=8.5, textColor=TEXT_DARK,
                leading=11,
            ),
            "table_cell_bold": ParagraphStyle(
                "table_cell_bold", parent=base["Normal"],
                fontName="Helvetica-Bold", fontSize=8.5, textColor=TEXT_DARK,
                leading=11,
            ),
            "metric_value": ParagraphStyle(
                "metric_value", parent=base["Normal"],
                fontName="Helvetica-Bold", fontSize=15, textColor=PRIMARY,
                alignment=TA_CENTER, leading=19, spaceAfter=2,
            ),
            "metric_label": ParagraphStyle(
                "metric_label", parent=base["Normal"],
                fontName="Helvetica", fontSize=8, textColor=TEXT_MUTED,
                alignment=TA_CENTER, spaceAfter=2,
            ),
            "metric_sub": ParagraphStyle(
                "metric_sub", parent=base["Normal"],
                fontName="Helvetica", fontSize=7.5, textColor=TEXT_MUTED,
                alignment=TA_CENTER,
            ),
            "badge_high": ParagraphStyle(
                "badge_high", parent=base["Normal"],
                fontName="Helvetica-Bold", fontSize=7, textColor=colors.HexColor("#922B21"),
                alignment=TA_CENTER,
            ),
            "badge_medium": ParagraphStyle(
                "badge_medium", parent=base["Normal"],
                fontName="Helvetica-Bold", fontSize=7, textColor=colors.HexColor("#7D6608"),
                alignment=TA_CENTER,
            ),
            "badge_low": ParagraphStyle(
                "badge_low", parent=base["Normal"],
                fontName="Helvetica-Bold", fontSize=7, textColor=colors.HexColor("#1E8449"),
                alignment=TA_CENTER,
            ),
            "bullet_positive": ParagraphStyle(
                "bullet_positive", parent=base["Normal"],
                fontName="Helvetica", fontSize=9, textColor=TEXT_DARK,
                leftIndent=14, leading=13, spaceAfter=4,
                bulletFontName="Helvetica", bulletFontSize=9,
                bulletColor=POSITIVE,
            ),
            "bullet_negative": ParagraphStyle(
                "bullet_negative", parent=base["Normal"],
                fontName="Helvetica", fontSize=9, textColor=TEXT_DARK,
                leftIndent=14, leading=13, spaceAfter=4,
                bulletFontName="Helvetica", bulletFontSize=9,
                bulletColor=NEGATIVE,
            ),
        }

    # ── Header / Footer ──

    def _header_footer(self, canvas, doc):
        canvas.saveState()
        title_text = _truncate(self.report.title, 70) or "Market Research Report"
        # Header
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(TEXT_MUTED)
        canvas.drawString(MARGIN, PAGE_H - MARGIN + 8, title_text)
        page_str = f"{self._t('footer_page')} {doc.page}"
        canvas.drawRightString(PAGE_W - MARGIN, PAGE_H - MARGIN + 8, page_str)
        canvas.setStrokeColor(ACCENT)
        canvas.setLineWidth(0.5)
        canvas.line(MARGIN, PAGE_H - MARGIN + 4, PAGE_W - MARGIN, PAGE_H - MARGIN + 4)

        # Footer
        canvas.setStrokeColor(DIVIDER)
        canvas.setLineWidth(0.3)
        canvas.line(MARGIN, MARGIN - 10, PAGE_W - MARGIN, MARGIN - 10)
        footer = f"{self._t('footer_confidential')}  |  {self._t('footer_generated_by')}  |  {datetime.utcnow().strftime('%Y-%m-%d')}"
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(TEXT_MUTED)
        canvas.drawCentredString(PAGE_W / 2, MARGIN - 22, footer)
        canvas.restoreState()

    def _cover_header_footer(self, canvas, doc):
        """Cover page has only footer, no header."""
        canvas.saveState()
        canvas.setStrokeColor(DIVIDER)
        canvas.setLineWidth(0.3)
        canvas.line(MARGIN, MARGIN - 10, PAGE_W - MARGIN, MARGIN - 10)
        footer = f"{self._t('cover_confidential')}  |  {self._t('footer_generated_by')}"
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(TEXT_MUTED)
        canvas.drawCentredString(PAGE_W / 2, MARGIN - 22, footer)
        canvas.restoreState()

    # ── Page builders ──

    def _cover_page(self) -> list:
        """Page 1: Cover."""
        elements = []
        s = self._styles

        elements.append(Spacer(1, 5 * cm))
        elements.append(Paragraph(self._t("cover_brand"), s["cover_brand"]))
        elements.append(Paragraph(self._t("cover_tagline"), s["cover_tagline"]))

        # Accent divider
        div = Drawing(PAGE_W - 2 * MARGIN, 3)
        div.add(Line(0, 1.5, 80, 1.5, strokeColor=ACCENT, strokeWidth=3))
        elements.append(div)
        elements.append(Spacer(1, 1.5 * cm))

        # Report type badge
        report_type = (
            self._t("cover_market_tracker") if self.is_market_search
            else self._t("cover_product_analysis")
        )
        badge_style = ParagraphStyle(
            "badge", parent=s["body"],
            fontName="Helvetica-Bold", fontSize=10, textColor=ACCENT,
            spaceBefore=0, spaceAfter=16,
        )
        elements.append(Paragraph(report_type.upper(), badge_style))

        # Title
        title = self.report.title or "Market Research Report"
        elements.append(Paragraph(title, s["cover_title"]))
        elements.append(Spacer(1, 1 * cm))

        # Metadata
        meta_items = []
        if self.product.get("asin"):
            label = self._t("cover_source_asin") if not self.is_market_search else self._t("cover_search_query")
            meta_items.append(f"<b>{label}:</b>  {self.product.get('asin', '—')}")
        if self.report.marketplace:
            meta_items.append(f"<b>{self._t('cover_marketplace')}:</b>  {self.report.marketplace}")
        if self.report.completed_at:
            dt = self.report.completed_at
            date_str = dt.strftime("%Y-%m-%d %H:%M") if hasattr(dt, "strftime") else str(dt)[:16]
            meta_items.append(f"<b>{self._t('cover_generated')}:</b>  {date_str}")
        meta_items.append(
            f"<b>{self._t('cover_language')}:</b>  {'English' if self.report.language == 'en' else 'Italiano'}"
        )

        for item in meta_items:
            elements.append(Paragraph(item, s["cover_meta"]))

        elements.append(PageBreak())
        return elements

    def _score_gauge(self, score: int, size: float = 80) -> Drawing:
        """Draw a circular score gauge."""
        d = Drawing(size + 10, size + 10)
        cx, cy = (size + 10) / 2, (size + 10) / 2
        radius = size / 2

        # Background circle
        d.add(Circle(cx, cy, radius, fillColor=BG_LIGHT, strokeColor=DIVIDER, strokeWidth=0.5))

        # Arc representing score
        if score >= 80:
            arc_color = POSITIVE
        elif score >= 50:
            arc_color = WARNING
        else:
            arc_color = NEGATIVE

        angle = (score / 100) * 360
        d.add(Wedge(cx, cy, radius - 2, 90, 90 - angle,
                     fillColor=arc_color, strokeColor=arc_color, strokeWidth=0))

        # Inner white circle
        inner_r = radius * 0.65
        d.add(Circle(cx, cy, inner_r, fillColor=BG_WHITE, strokeColor=BG_WHITE, strokeWidth=0))

        # Score text
        d.add(String(cx, cy - 6, str(score),
                      fontName="Helvetica-Bold", fontSize=20,
                      fillColor=arc_color, textAnchor="middle"))

        return d

    def _metric_card(self, label: str, value: str, sub: str = "") -> Table:
        """Build a single metric card as a small table."""
        s = self._styles
        data = [
            [Paragraph(value, s["metric_value"])],
            [Paragraph(label, s["metric_label"])],
        ]
        if sub:
            data.append([Paragraph(sub, s["metric_sub"])])

        card = Table(data, colWidths=[CARD_INNER_W])
        card.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), BG_LIGHT),
            ("ROUNDEDCORNERS", [4, 4, 4, 4]),
            ("TOPPADDING", (0, 0), (-1, 0), 8),
            ("BOTTOMPADDING", (0, -1), (-1, -1), 8),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        return card

    def _executive_summary(self) -> list:
        """Page 2: Executive Summary."""
        elements = []
        s = self._styles
        elements.append(Paragraph(self._t("exec_title"), s["h1"]))

        # Overall Score + Summary side by side
        if self.ai:
            score = self.ai.get("overall_score", 50)
            gauge = self._score_gauge(score)
            summary_text = self.ai.get("summary", "")

            score_label = Paragraph(
                f"<b>{self._t('exec_overall_score')}</b>", s["body"]
            )
            summary_para = Paragraph(summary_text, s["body"]) if summary_text else Spacer(1, 1)

            top_table = Table(
                [[gauge, [score_label, Spacer(1, 4), summary_para]]],
                colWidths=[3.5 * cm, CONTENT_W - 4 * cm],
            )
            top_table.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (0, 0), 0),
                ("LEFTPADDING", (1, 0), (1, 0), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]))
            elements.append(KeepTogether([top_table, Spacer(1, SPACE_LG)]))

        # Market Overview (4-metric grid)
        all_products = [self.product] + self.competitors if self.product else self.competitors
        if all_products:
            prices = [p.get("price") for p in all_products if p.get("price") is not None]
            bsrs = [p.get("bsr") for p in all_products if p.get("bsr") is not None]
            brands = set(p.get("brand") for p in all_products if p.get("brand"))

            avg_price = sum(prices) / len(prices) if prices else None
            avg_bsr = sum(bsrs) / len(bsrs) if bsrs else None
            price_range = f"{_fmt_price(min(prices))} – {_fmt_price(max(prices))}" if prices else "—"

            cards = [
                self._metric_card(self._t("exec_total_products"), str(len(all_products))),
                self._metric_card(
                    self._t("exec_avg_price"),
                    _fmt_price(avg_price),
                    f"{self._t('exec_price_range')}: {price_range}",
                ),
                self._metric_card(self._t("exec_avg_bsr"), _fmt_number(avg_bsr)),
                self._metric_card(self._t("exec_unique_brands"), str(len(brands))),
            ]

            card_table = Table([cards], colWidths=[CARD_COL_W] * 4)
            card_table.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 3),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3),
            ]))
            elements.append(KeepTogether([
                Paragraph(self._t("exec_market_overview"), s["h2"]),
                card_table,
                Spacer(1, SPACE_LG),
            ]))

            # Market Position (product vs averages)
            if self.product and (prices or bsrs):
                position_data = []

                metrics = [
                    ("exec_price", self.product.get("price"), avg_price, True),  # lower is better
                    ("exec_bsr", self.product.get("bsr"), avg_bsr, True),
                    ("exec_reviews", self.product.get("review_count"),
                     sum(p.get("review_count", 0) for p in self.competitors if p.get("review_count")) / max(len([p for p in self.competitors if p.get("review_count")]), 1) if self.competitors else None,
                     False),  # higher is better
                    ("exec_rating", self.product.get("rating"),
                     sum(p.get("rating", 0) for p in self.competitors if p.get("rating")) / max(len([p for p in self.competitors if p.get("rating")]), 1) if self.competitors else None,
                     False),
                ]

                position_cards = []
                for label_key, prod_val, avg_val, lower_is_better in metrics:
                    diff_text, tone = _fmt_pct_diff(
                        float(prod_val) if prod_val is not None else None,
                        float(avg_val) if avg_val is not None else None,
                    )
                    # Invert tone for "lower is better" metrics
                    if lower_is_better and tone == "positive":
                        tone = "negative"
                    elif lower_is_better and tone == "negative":
                        tone = "positive"

                    if label_key == "exec_price":
                        val_str = _fmt_price(prod_val)
                    elif label_key == "exec_rating":
                        val_str = _fmt_number(prod_val, 1) if prod_val else "—"
                    else:
                        val_str = _fmt_number(prod_val)

                    tone_label = {
                        "positive": self._t("exec_below_avg") if lower_is_better else self._t("exec_above_avg"),
                        "negative": self._t("exec_above_avg") if lower_is_better else self._t("exec_below_avg"),
                        "neutral": self._t("exec_at_avg"),
                    }.get(tone, "")

                    sub = f"{diff_text} ({tone_label})" if diff_text != "—" else self._t("exec_no_data")
                    position_cards.append(
                        self._metric_card(self._t(label_key), val_str, sub)
                    )

                pos_table = Table([position_cards], colWidths=[CARD_COL_W] * 4)
                pos_table.setStyle(TableStyle([
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 3),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                ]))
                elements.append(KeepTogether([
                    Paragraph(self._t("exec_market_position"), s["h2"]),
                    pos_table,
                ]))

        elements.append(PageBreak())
        return elements

    def _decode_chart_image(self, key: str, max_width: float = 14 * cm, max_height: float = 8 * cm) -> Optional[Image]:
        """Decode a base64 chart image and return a ReportLab Image flowable."""
        b64 = self.chart_images.get(key)
        if not b64:
            return None
        try:
            img_bytes = base64.b64decode(b64)
            img = Image(io.BytesIO(img_bytes))
            # Scale to fit
            ratio = min(max_width / img.drawWidth, max_height / img.drawHeight)
            img.drawWidth *= ratio
            img.drawHeight *= ratio
            return img
        except Exception:
            return None

    def _charts_page(self) -> list:
        """Page 3: Charts (Market Tracker 360 only)."""
        elements = []
        s = self._styles
        elements.append(Paragraph(self._t("charts_title"), s["h1"]))

        has_charts = False

        # Price Distribution
        price_img = self._decode_chart_image("price_distribution", max_width=14 * cm, max_height=9 * cm)
        if price_img:
            has_charts = True
            elements.append(KeepTogether([
                Paragraph(self._t("charts_price_dist"), s["h2"]),
                price_img,
                Paragraph(self._t("charts_price_dist_caption"), s["caption"]),
                Spacer(1, SPACE_MD),
            ]))

        # BSR Position
        bsr_img = self._decode_chart_image("bsr_position", max_width=14 * cm, max_height=9 * cm)
        if bsr_img:
            has_charts = True
            elements.append(KeepTogether([
                Paragraph(self._t("charts_bsr_position"), s["h2"]),
                bsr_img,
                Paragraph(self._t("charts_bsr_caption"), s["caption"]),
            ]))

        if not has_charts:
            elements.append(Paragraph("No chart data available.", s["body_muted"]))

        elements.append(PageBreak())
        return elements

    def _comparison_page(self) -> list:
        """Page 4: Competitive Comparison Table + Radar."""
        elements = []
        s = self._styles
        elements.append(Paragraph(self._t("comp_title"), s["h1"]))
        elements.append(Paragraph(
            f"{len(self.competitors)} {self._t('comp_competitors_analyzed')}",
            s["body_muted"],
        ))
        elements.append(Spacer(1, SPACE_SM))

        # Build table
        headers = [
            self._t("comp_asin"),
            self._t("comp_product"),
            self._t("comp_price"),
            self._t("comp_bsr"),
            self._t("comp_reviews"),
            self._t("comp_rating"),
        ]
        header_row = [Paragraph(h, s["table_header"]) for h in headers]

        col_widths = [2.4 * cm, 7.0 * cm, 2.0 * cm, 2.0 * cm, 1.8 * cm, 1.8 * cm]

        rows = [header_row]

        # Source product first
        if self.product:
            product_label = f"{self.product.get('asin', '—')}"
            rows.append([
                Paragraph(f"<b>{product_label}</b>", s["table_cell_bold"]),
                Paragraph(_truncate(self.product.get("title"), 70), s["table_cell_bold"]),
                Paragraph(_fmt_price(self.product.get("price")), s["table_cell_bold"]),
                Paragraph(_fmt_number(self.product.get("bsr")), s["table_cell_bold"]),
                Paragraph(_fmt_number(self.product.get("review_count")), s["table_cell_bold"]),
                Paragraph(_fmt_number(self.product.get("rating"), 1), s["table_cell_bold"]),
            ])

        # Competitors
        source_price = self.product.get("price") if self.product else None
        source_bsr = self.product.get("bsr") if self.product else None
        source_reviews = self.product.get("review_count") if self.product else None
        source_rating = self.product.get("rating") if self.product else None

        for comp in self.competitors:
            rows.append([
                Paragraph(comp.get("asin", "—"), s["table_cell"]),
                Paragraph(_truncate(comp.get("title"), 70), s["table_cell"]),
                Paragraph(_fmt_price(comp.get("price")), s["table_cell"]),
                Paragraph(_fmt_number(comp.get("bsr")), s["table_cell"]),
                Paragraph(_fmt_number(comp.get("review_count")), s["table_cell"]),
                Paragraph(_fmt_number(comp.get("rating"), 1), s["table_cell"]),
            ])

        table = Table(rows, colWidths=col_widths, repeatRows=1)

        # Table styling
        style_cmds: list = [
            # Header
            ("BACKGROUND", (0, 0), (-1, 0), TABLE_HEADER_BG),
            ("TEXTCOLOR", (0, 0), (-1, 0), BG_WHITE),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 8),
            # Source product row highlight
            ("BACKGROUND", (0, 1), (-1, 1), ACCENT_LIGHT),
            # Grid
            ("GRID", (0, 0), (-1, -1), 0.3, DIVIDER),
            ("ROWBACKGROUNDS", (0, 2), (-1, -1), [BG_WHITE, TABLE_ALT_ROW]),
            # Alignment
            ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            # Padding
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ]

        # Color-code competitor cells (green=better, red=worse vs source)
        for row_idx, comp in enumerate(self.competitors, start=2):
            # Price: lower is better
            cp = comp.get("price")
            if cp is not None and source_price is not None:
                if cp < source_price * 0.97:
                    style_cmds.append(("TEXTCOLOR", (2, row_idx), (2, row_idx), POSITIVE))
                elif cp > source_price * 1.03:
                    style_cmds.append(("TEXTCOLOR", (2, row_idx), (2, row_idx), NEGATIVE))
            # BSR: lower is better
            cb = comp.get("bsr")
            if cb is not None and source_bsr is not None:
                if cb < source_bsr * 0.97:
                    style_cmds.append(("TEXTCOLOR", (3, row_idx), (3, row_idx), POSITIVE))
                elif cb > source_bsr * 1.03:
                    style_cmds.append(("TEXTCOLOR", (3, row_idx), (3, row_idx), NEGATIVE))
            # Reviews: higher is better
            cr = comp.get("review_count")
            if cr is not None and source_reviews is not None:
                if cr > source_reviews * 1.03:
                    style_cmds.append(("TEXTCOLOR", (4, row_idx), (4, row_idx), POSITIVE))
                elif cr < source_reviews * 0.97:
                    style_cmds.append(("TEXTCOLOR", (4, row_idx), (4, row_idx), NEGATIVE))
            # Rating: higher is better
            crt = comp.get("rating")
            if crt is not None and source_rating is not None:
                if crt > source_rating + 0.1:
                    style_cmds.append(("TEXTCOLOR", (5, row_idx), (5, row_idx), POSITIVE))
                elif crt < source_rating - 0.1:
                    style_cmds.append(("TEXTCOLOR", (5, row_idx), (5, row_idx), NEGATIVE))

        table.setStyle(TableStyle(style_cmds))
        elements.append(table)
        elements.append(Spacer(1, SPACE_LG))

        # Radar chart
        radar_img = self._decode_chart_image("radar_comparison", max_width=10 * cm, max_height=8 * cm)
        if radar_img:
            elements.append(KeepTogether([
                Paragraph(self._t("charts_radar"), s["h2"]),
                radar_img,
                Paragraph(self._t("charts_radar_caption"), s["caption"]),
            ]))

        elements.append(PageBreak())
        return elements

    def _ai_analysis_page(self) -> list:
        """Page 5: AI Analysis."""
        elements = []
        s = self._styles
        elements.append(Paragraph(self._t("ai_title"), s["h1"]))

        if not self.ai:
            elements.append(Paragraph(self._t("ai_no_analysis"), s["body_muted"]))
            return elements

        # Strengths
        strengths = self.ai.get("strengths", [])
        if strengths:
            strengths_block = [Paragraph(self._t("ai_strengths"), s["h2"])]
            for item in strengths:
                strengths_block.append(Paragraph(
                    f"\u2713  {item}",
                    s["bullet_positive"],
                ))
            elements.append(KeepTogether(strengths_block))

        elements.append(Spacer(1, SPACE_SM))

        # Weaknesses
        weaknesses = self.ai.get("weaknesses", [])
        if weaknesses:
            weaknesses_block = [Paragraph(self._t("ai_weaknesses"), s["h2"])]
            for item in weaknesses:
                weaknesses_block.append(Paragraph(
                    f"\u2717  {item}",
                    s["bullet_negative"],
                ))
            elements.append(KeepTogether(weaknesses_block))

        elements.append(Spacer(1, SPACE_MD))

        # Recommendations table
        recs = self.ai.get("recommendations", [])
        if recs:
            elements.append(Paragraph(self._t("ai_recommendations"), s["h2"]))

            rec_headers = [
                self._t("ai_rec_priority"),
                self._t("ai_rec_area"),
                self._t("ai_rec_action"),
                self._t("ai_rec_impact"),
            ]
            rec_header_row = [Paragraph(h, s["table_header"]) for h in rec_headers]
            rec_rows = [rec_header_row]

            for rec in recs:
                priority = rec.get("priority", "medium").lower()
                priority_label = self._t(f"ai_priority_{priority}")
                badge_style_key = f"badge_{priority}" if f"badge_{priority}" in s else "badge_medium"

                rec_rows.append([
                    Paragraph(priority_label, s[badge_style_key]),
                    Paragraph(rec.get("area", "—"), s["table_cell_bold"]),
                    Paragraph(rec.get("action", "—"), s["table_cell"]),
                    Paragraph(rec.get("expected_impact", "—"), s["table_cell"]),
                ])

            rec_col_widths = [1.8 * cm, 2.8 * cm, 6.2 * cm, 6.2 * cm]
            rec_table = Table(rec_rows, colWidths=rec_col_widths, repeatRows=1)

            rec_style_cmds: list = [
                ("BACKGROUND", (0, 0), (-1, 0), TABLE_HEADER_BG),
                ("TEXTCOLOR", (0, 0), (-1, 0), BG_WHITE),
                ("GRID", (0, 0), (-1, -1), 0.3, DIVIDER),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [BG_WHITE, TABLE_ALT_ROW]),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("ALIGN", (0, 1), (0, -1), "CENTER"),
            ]

            # Color-code priority cells
            for row_idx, rec in enumerate(recs, start=1):
                priority = rec.get("priority", "medium").lower()
                if priority == "high":
                    rec_style_cmds.append(
                        ("BACKGROUND", (0, row_idx), (0, row_idx), colors.HexColor("#FADBD8"))
                    )
                elif priority == "medium":
                    rec_style_cmds.append(
                        ("BACKGROUND", (0, row_idx), (0, row_idx), colors.HexColor("#FEF9E7"))
                    )
                elif priority == "low":
                    rec_style_cmds.append(
                        ("BACKGROUND", (0, row_idx), (0, row_idx), colors.HexColor("#D5F5E3"))
                    )

            rec_table.setStyle(TableStyle(rec_style_cmds))
            elements.append(rec_table)

        return elements

    # ── Build ──

    def build(self) -> bytes:
        """Generate the full PDF and return as bytes."""
        buf = io.BytesIO()

        cover_frame = Frame(
            MARGIN, MARGIN,
            CONTENT_W, PAGE_H - 2 * MARGIN - 10,
            id="cover_content",
        )
        body_frame = Frame(
            MARGIN, MARGIN,
            CONTENT_W, BODY_FRAME_H,
            id="body_content",
            topPadding=6,
        )

        cover_template = PageTemplate(
            id="cover",
            frames=[cover_frame],
            onPage=self._cover_header_footer,
        )
        body_template = PageTemplate(
            id="body",
            frames=[body_frame],
            onPage=self._header_footer,
        )

        doc = BaseDocTemplate(
            buf,
            pagesize=A4,
            leftMargin=MARGIN,
            rightMargin=MARGIN,
            topMargin=MARGIN,
            bottomMargin=MARGIN,
            title=self.report.title or "Market Research Report",
            author="Inthezon",
        )
        doc.addPageTemplates([cover_template, body_template])

        # Assemble flowables
        story: list = []

        # Cover page (uses cover template)
        story.extend(self._cover_page())

        # Switch to body template for remaining pages
        story.insert(len(story) - 1, NextPageTemplate("body"))

        # Executive summary
        story.extend(self._executive_summary())

        # Charts page (Market Tracker 360 only)
        if self.is_market_search:
            story.extend(self._charts_page())

        # Comparison page
        if self.product or self.competitors:
            story.extend(self._comparison_page())

        # AI Analysis page
        story.extend(self._ai_analysis_page())

        doc.build(story)
        return buf.getvalue()
