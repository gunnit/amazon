"""Catalog & content section: combined SEO/content/review audit and subcategory mix."""
from __future__ import annotations

from app.services.brand_analysis.deck import charts
from app.services.brand_analysis.deck import format as fmt
from app.services.brand_analysis.deck.block import BaseBlock, BlockResult, Section
from app.services.brand_analysis.deck.blocks.performance import _insight_strip
from app.services.brand_analysis.deck.theme import DeckTheme


class ContentAuditBlock(BaseBlock):
    """Single content-quality slide, mirroring the reference deck: listing,
    image and review signals as one tile row, with the weak-ASIN detail table
    (or the content-gap chart) underneath. Zero-count issue tiles are dropped —
    a tile only earns its place when there is something to act on."""

    id = "content_audit"
    section = Section.CATALOG
    required_keys = ("content_health",)

    @staticmethod
    def _weaknesses(ctx) -> dict:
        return ctx.m("review_rating_weaknesses") or {}

    def is_available(self, ctx) -> bool:
        content = ctx.m("content_health") or {}
        weaknesses = self._weaknesses(ctx)
        signals = (
            content.get("asins_missing_bullets"),
            content.get("asins_missing_description"),
            content.get("short_title_count"),
            ctx.m("average_images_per_asin"),
            ctx.m("asins_with_fewer_than_5_images"),
            weaknesses.get("asins_with_fewer_than_15_reviews"),
            weaknesses.get("asins_with_rating_below_4"),
        )
        return any(value not in (None, 0) for value in signals) or bool(weaknesses.get("weak_asins"))

    def render(self, ctx, deck, page: int) -> BlockResult:
        slide = deck.blank_slide()
        deck.chrome(slide, page)
        deck.heading(slide, ctx.t("content_audit_title"), ctx.t("content_audit_subtitle"))
        content = ctx.m("content_health") or {}
        weaknesses = self._weaknesses(ctx)

        def issue(value) -> str:
            return ctx.fmt.integer(value) if int(value or 0) > 0 else fmt.EMPTY

        kpis = [
            (ctx.t("kpi_avg_images_per_asin"), ctx.fmt.number(ctx.m("average_images_per_asin"), 1)),
            (ctx.t("kpi_asins_few_images"), issue(ctx.m("asins_with_fewer_than_5_images"))),
            (ctx.t("kpi_asins_few_reviews"), issue(weaknesses.get("asins_with_fewer_than_15_reviews"))),
            (ctx.t("kpi_rating_below_4"), issue(weaknesses.get("asins_with_rating_below_4"))),
            (ctx.t("kpi_missing_bullets"), issue(content.get("asins_missing_bullets"))),
            (ctx.t("kpi_missing_description"), issue(content.get("asins_missing_description"))),
            (ctx.t("kpi_short_titles"), issue(content.get("short_title_count"))),
        ]
        kpis = [k for k in kpis if k[1] != fmt.EMPTY][:4]
        gap = 0.28
        max_card = 4.2 if len(kpis) >= 3 else 6.16
        card_w = min((DeckTheme.content_w() - gap * (max(len(kpis), 1) - 1)) / max(len(kpis), 1), max_card)
        for idx, (label, value) in enumerate(kpis):
            deck.kpi(slide, DeckTheme.MARGIN + idx * (card_w + gap), 1.6, card_w, 1.45,
                     label, value, fill=DeckTheme.kpi_fill(idx))

        rows = [
            [fmt.product_label(item.get("product_name") or item.get("asin"), ctx.brand, 40),
             ctx.fmt.integer(item.get("reviews")), ctx.fmt.number(item.get("rating"), 2),
             fmt.truncate(", ".join(item.get("issues") or []), 40)]
            for item in (weaknesses.get("weak_asins") or [])[:8]
        ]
        if rows:
            deck.table(slide, DeckTheme.MARGIN, 3.3,
                       [ctx.t("table_product"), ctx.t("table_reviews"), ctx.t("table_rating"), ctx.t("table_issue")],
                       rows, [5.2, 1.5, 1.5, 4.41])
        else:
            gaps = [
                (content.get("asins_missing_bullets"), ctx.t("kpi_missing_bullets")),
                (content.get("asins_missing_description"), ctx.t("kpi_missing_description")),
                (content.get("short_title_count"), ctx.t("kpi_short_titles")),
                (content.get("asins_missing_aplus_content"), "A+"),
            ]
            gaps = [(int(v or 0), label) for v, label in gaps if v]
            # A single-category bar chart says nothing the tile above doesn't.
            if len(gaps) >= 2:
                png = charts.hbar([label for _, label in gaps], [v for v, _ in gaps],
                                  value_fmt=lambda v: ctx.fmt.integer(v), color=DeckTheme.accent(1),
                                  w_in=11.0, h_in=2.8)
                deck.picture(slide, png, DeckTheme.MARGIN, 3.3, 11.4, 3.0)

        few_images = int(ctx.m("asins_with_fewer_than_5_images") or 0)
        if few_images > 0:
            fallback = ctx.t("insight_content_images").format(
                n=ctx.fmt.integer(few_images), total=ctx.fmt.integer(ctx.m("total_asins_2025")))
        else:
            fallback = ctx.t("insight_content_generic")
        _insight_strip(ctx, deck, slide, self.id, fallback)
        return BlockResult(rendered=True)


class SubcategoryBlock(BaseBlock):
    id = "subcategory"
    section = Section.CATALOG
    required_keys = ("revenue_by_subcategory",)

    def is_available(self, ctx) -> bool:
        rows = [s for s in (ctx.m("revenue_by_subcategory") or [])
                if float(s.get("revenue_2025") or 0) > 0]
        return len(rows) >= 2

    def render(self, ctx, deck, page: int) -> BlockResult:
        slide = deck.blank_slide()
        deck.chrome(slide, page)
        deck.heading(slide, ctx.t("subcategory_title"), ctx.t("subcategory_subtitle"))
        items = sorted(
            [s for s in (ctx.m("revenue_by_subcategory") or []) if float(s.get("revenue_2025") or 0) > 0],
            key=lambda s: float(s.get("revenue_2025") or 0), reverse=True,
        )[:8]
        labels = [fmt.truncate(s.get("subcategory"), 26) for s in items]
        values = [float(s.get("revenue_2025") or 0) for s in items]
        png = charts.hbar(labels, values, value_fmt=lambda v: ctx.fmt.currency(v),
                          color=DeckTheme.accent(2), w_in=11.0, h_in=3.8)
        deck.picture(slide, png, DeckTheme.MARGIN, 1.95, 11.4, 4.0)
        return BlockResult(rendered=True)
