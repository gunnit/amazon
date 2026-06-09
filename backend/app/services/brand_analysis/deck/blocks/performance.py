"""Performance section blocks: revenue, catalog health, active split, top ASINs."""
from __future__ import annotations

from app.services.brand_analysis.deck import charts
from app.services.brand_analysis.deck import format as fmt
from app.services.brand_analysis.deck.block import BaseBlock, BlockResult, Section
from app.services.brand_analysis.deck.theme import DeckTheme


def _insight_strip(ctx, deck, slide, block_id: str, fallback: str, y: float = 6.5) -> None:
    insight = ctx.block_insight(block_id)
    text = insight.get("insight") or fallback
    rec = insight.get("recommendation")
    deck.rect(slide, DeckTheme.MARGIN, y, DeckTheme.content_w(), 0.5, DeckTheme.SURFACE,
              line=DeckTheme.HAIRLINE, radius=True)
    line = text if not rec else f"{text}   ·   {ctx.t('recommendation')}: {rec}"
    deck.text(slide, DeckTheme.MARGIN + 0.18, y + 0.13, DeckTheme.content_w() - 0.36, 0.3,
              fmt.truncate(line, 200), size=10, color=DeckTheme.SUBTLE_INK)


class RevenueYoYBlock(BaseBlock):
    id = "revenue_yoy"
    section = Section.PERFORMANCE
    required_keys = ("total_revenue_2025", "total_revenue_2024")

    def is_available(self, ctx) -> bool:
        return float(ctx.m("total_revenue_2025") or 0) > 0 or float(ctx.m("total_revenue_2024") or 0) > 0

    def render(self, ctx, deck, page: int) -> BlockResult:
        slide = deck.blank_slide()
        deck.chrome(slide, page)
        deck.heading(slide, ctx.t("revenue_yoy_title"), ctx.t("revenue_yoy_subtitle"))
        rev24 = float(ctx.m("total_revenue_2024") or 0)
        rev25 = float(ctx.m("total_revenue_2025") or 0)
        png = charts.waterfall("2024", rev24, "2025", rev25,
                               value_fmt=lambda v: fmt.currency(v))
        deck.picture(slide, png, DeckTheme.MARGIN, 1.85, 7.4, 3.6)
        deck.kpi(slide, 8.6, 2.1, 3.4, 1.0, ctx.t("kpi_yoy"),
                 fmt.percent_signed(ctx.m("yoy_percent")), chip=ctx.quality("yoy_percent"))
        deck.kpi(slide, 8.6, 3.3, 3.4, 1.0, ctx.t("kpi_revenue_2025"),
                 fmt.currency(rev25), chip=ctx.quality("total_revenue_2025"))
        fallback = (f"Revenue moved {fmt.currency(rev24)} → {fmt.currency(rev25)} "
                    f"({fmt.percent_signed(ctx.m('yoy_percent'))}).")
        _insight_strip(ctx, deck, slide, self.id, fallback)
        return BlockResult(rendered=True)


class CatalogHealthBlock(BaseBlock):
    id = "catalog_health"
    section = Section.PERFORMANCE
    required_keys = ("total_asins_2025",)

    def is_available(self, ctx) -> bool:
        return int(ctx.m("total_asins_2025") or 0) > 0

    def render(self, ctx, deck, page: int) -> BlockResult:
        slide = deck.blank_slide()
        deck.chrome(slide, page)
        deck.heading(slide, ctx.t("catalog_health_title"), ctx.t("catalog_health_subtitle"))
        kpis = [
            (ctx.t("kpi_asins_2025"), fmt.integer(ctx.m("total_asins_2025"))),
            (ctx.t("kpi_active_2025"), fmt.integer(ctx.m("active_asins_2025"))),
            (ctx.t("kpi_inactive_2025"), fmt.integer(ctx.m("inactive_asins_2025"))),
            (ctx.t("kpi_new_yoy"), fmt.integer(ctx.m("new_asins_yoy"))),
        ]
        gap = 0.24
        card_w = (DeckTheme.content_w() - gap * 3) / 4
        for idx, (label, value) in enumerate(kpis):
            deck.kpi(slide, DeckTheme.MARGIN + idx * (card_w + gap), 1.9, card_w, 1.0, label, value)

        completeness = ctx.metrics.get("data_completeness") or {}
        missing = completeness.get("missing_optional_fields_2025") or []
        limitations = (ctx.metrics.get("limitations") or {}).get("items") or []
        none_bullet = ctx.t("value_none")
        deck.callout(slide, DeckTheme.MARGIN, 3.25, 5.9, 3.0, ctx.t("missing_optional_fields_2025"),
                     [str(item) for item in missing[:6]] or [none_bullet])
        deck.callout(slide, DeckTheme.MARGIN + 6.2, 3.25, 5.9, 3.0, ctx.t("source_limitations"),
                     [str(item.get("area")) for item in limitations[:6]] or [none_bullet],
                     accent=DeckTheme.MUTED)
        return BlockResult(rendered=True)


class ActiveInactiveBlock(BaseBlock):
    id = "active_inactive"
    section = Section.PERFORMANCE
    required_keys = ("active_asins_2025",)

    def is_available(self, ctx) -> bool:
        active = int(ctx.m("active_asins_2025") or 0)
        inactive = int(ctx.m("inactive_asins_2025") or 0)
        return (active + inactive) > 0

    def render(self, ctx, deck, page: int) -> BlockResult:
        slide = deck.blank_slide()
        deck.chrome(slide, page)
        deck.heading(slide, ctx.t("active_inactive_title"), ctx.t("active_inactive_subtitle"))
        active = int(ctx.m("active_asins_2025") or 0)
        inactive = int(ctx.m("inactive_asins_2025") or 0)
        total = active + inactive
        png = charts.donut(
            [(ctx.t("kpi_active"), active, DeckTheme.POSITIVE),
             (ctx.t("kpi_inactive"), inactive, DeckTheme.NEGATIVE)],
            center=fmt.share(ctx.m("percentage_inactive_asins")),
        )
        deck.picture(slide, png, DeckTheme.MARGIN, 1.9, 4.0, 3.6)
        deck.kpi(slide, 5.4, 2.1, 3.2, 1.0, ctx.t("kpi_active"), fmt.integer(active),
                 accent=DeckTheme.POSITIVE)
        deck.kpi(slide, 8.8, 2.1, 3.2, 1.0, ctx.t("kpi_inactive"), fmt.integer(inactive),
                 accent=DeckTheme.NEGATIVE)
        deck.kpi(slide, 5.4, 3.3, 6.6, 1.0, ctx.t("kpi_pct_inactive"),
                 fmt.share(ctx.m("percentage_inactive_asins")))
        fallback = (f"{fmt.integer(inactive)} of {fmt.integer(total)} ASINs are inactive "
                    f"({fmt.share(ctx.m('percentage_inactive_asins'))}) — {ctx.t('latent_value')}.")
        _insight_strip(ctx, deck, slide, self.id, fallback)
        return BlockResult(rendered=True)


class TopPerformersBlock(BaseBlock):
    id = "top_performers"
    section = Section.PERFORMANCE
    required_keys = ("top_5_asins",)

    def is_available(self, ctx) -> bool:
        return len(ctx.m("top_5_asins") or []) >= 3

    def render(self, ctx, deck, page: int) -> BlockResult:
        slide = deck.blank_slide()
        deck.chrome(slide, page)
        deck.heading(slide, ctx.t("top_performers_title"), ctx.t("top_performers_subtitle"))
        items = (ctx.m("top_5_asins") or [])[:5]
        labels = [fmt.truncate(item.get("product_name") or item.get("asin"), 34) for item in items]
        values = [float(item.get("revenue_2025") or 0) for item in items]
        png = charts.hbar(labels, values, value_fmt=lambda v: fmt.currency(v), w_in=11.0, h_in=3.6)
        deck.picture(slide, png, DeckTheme.MARGIN, 1.95, 11.4, 3.8)
        share = fmt.share(ctx.m("top_5_revenue_share"))
        fallback = f"Top {len(items)} ASINs drive {share} {ctx.t('of_revenue')}."
        _insight_strip(ctx, deck, slide, self.id, fallback)
        return BlockResult(rendered=True)
