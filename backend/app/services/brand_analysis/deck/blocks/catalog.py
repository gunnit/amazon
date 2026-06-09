"""Catalog & content section: SEO/content audit, review weaknesses, subcategory mix."""
from __future__ import annotations

from app.services.brand_analysis.deck import charts
from app.services.brand_analysis.deck import format as fmt
from app.services.brand_analysis.deck.block import BaseBlock, BlockResult, Section
from app.services.brand_analysis.deck.theme import DeckTheme


class ContentAuditBlock(BaseBlock):
    id = "content_audit"
    section = Section.CATALOG
    required_keys = ("content_health",)

    def is_available(self, ctx) -> bool:
        content = ctx.m("content_health") or {}
        signals = (
            content.get("asins_missing_bullets"),
            content.get("asins_missing_description"),
            content.get("short_title_count"),
            ctx.m("average_images_per_asin"),
        )
        return any(value not in (None, 0) for value in signals)

    def render(self, ctx, deck, page: int) -> BlockResult:
        slide = deck.blank_slide()
        deck.chrome(slide, page)
        deck.heading(slide, ctx.t("content_audit_title"), ctx.t("content_audit_subtitle"))
        content = ctx.m("content_health") or {}
        kpis = [
            (ctx.t("kpi_avg_images_per_asin"), fmt.number(ctx.m("average_images_per_asin"), 1)),
            (ctx.t("kpi_missing_bullets"), fmt.integer(content.get("asins_missing_bullets"))),
            (ctx.t("kpi_missing_description"), fmt.integer(content.get("asins_missing_description"))),
            (ctx.t("kpi_short_titles"), fmt.integer(content.get("short_title_count"))),
        ]
        gap = 0.24
        card_w = (DeckTheme.content_w() - gap * 3) / 4
        for idx, (label, value) in enumerate(kpis):
            deck.kpi(slide, DeckTheme.MARGIN + idx * (card_w + gap), 1.9, card_w, 1.0, label, value)

        gaps = [
            (content.get("asins_missing_bullets"), ctx.t("kpi_missing_bullets")),
            (content.get("asins_missing_description"), ctx.t("kpi_missing_description")),
            (content.get("short_title_count"), ctx.t("kpi_short_titles")),
            (content.get("asins_missing_aplus_content"), "A+"),
        ]
        gaps = [(int(v or 0), label) for v, label in gaps if v]
        if gaps:
            png = charts.hbar([label for _, label in gaps], [v for v, _ in gaps],
                              value_fmt=lambda v: fmt.integer(v), color=DeckTheme.accent(1),
                              w_in=11.0, h_in=2.8)
            deck.picture(slide, png, DeckTheme.MARGIN, 3.3, 11.4, 3.0)
        return BlockResult(rendered=True)


class ReviewImageBlock(BaseBlock):
    id = "review_image"
    section = Section.CATALOG
    required_keys = ("review_rating_weaknesses",)

    def is_available(self, ctx) -> bool:
        weak = (ctx.m("review_rating_weaknesses") or {}).get("weak_asins") or []
        return len(weak) >= 1 or int(ctx.m("asins_with_fewer_than_5_images") or 0) > 0

    def render(self, ctx, deck, page: int) -> BlockResult:
        slide = deck.blank_slide()
        deck.chrome(slide, page)
        deck.heading(slide, ctx.t("review_image_title"), ctx.t("review_image_subtitle"))
        weaknesses = ctx.m("review_rating_weaknesses") or {}
        kpis = [
            (ctx.t("kpi_asins_few_images"), fmt.integer(ctx.m("asins_with_fewer_than_5_images"))),
            (ctx.t("kpi_asins_few_reviews"), fmt.integer(weaknesses.get("asins_with_fewer_than_15_reviews"))),
            (ctx.t("kpi_rating_below_4"), fmt.integer(weaknesses.get("asins_with_rating_below_4"))),
        ]
        gap = 0.28
        card_w = (DeckTheme.content_w() - gap * 2) / 3
        for idx, (label, value) in enumerate(kpis):
            deck.kpi(slide, DeckTheme.MARGIN + idx * (card_w + gap), 1.9, card_w, 1.0, label, value)

        rows = [
            [fmt.truncate(item.get("product_name") or item.get("asin"), 40),
             fmt.integer(item.get("reviews")), fmt.number(item.get("rating"), 2),
             fmt.truncate(", ".join(item.get("issues") or []), 40)]
            for item in (weaknesses.get("weak_asins") or [])[:8]
        ]
        if rows:
            deck.table(slide, DeckTheme.MARGIN, 3.3,
                       [ctx.t("table_product"), ctx.t("table_reviews"), ctx.t("table_rating"), ctx.t("table_issue")],
                       rows, [4.5, 1.2, 1.2, 4.0])
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
        png = charts.hbar(labels, values, value_fmt=lambda v: fmt.currency(v),
                          color=DeckTheme.accent(2), w_in=11.0, h_in=3.8)
        deck.picture(slide, png, DeckTheme.MARGIN, 1.95, 11.4, 4.0)
        return BlockResult(rendered=True)
