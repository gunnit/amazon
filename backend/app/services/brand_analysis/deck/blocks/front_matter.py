"""Cover and executive summary — the always-on front matter."""
from __future__ import annotations

from app.services.brand_analysis.deck import format as fmt
from app.services.brand_analysis.deck.block import BaseBlock, BlockResult, Section
from app.services.brand_analysis.deck.theme import DeckTheme


class CoverBlock(BaseBlock):
    id = "cover"
    section = Section.FRONT
    always = True

    def is_available(self, ctx) -> bool:
        return True

    def render(self, ctx, deck, page: int) -> BlockResult:
        slide = deck.blank_slide()
        deck.rect(slide, 0, 0, DeckTheme.SLIDE_W, DeckTheme.SLIDE_H, DeckTheme.BRAND_PRIMARY)
        deck.text(slide, 1.0, 1.7, DeckTheme.SLIDE_W - 2.0, 2.2,
                  f"{ctx.brand} {ctx.t('cover_on_amazon')}".upper(),
                  size=DeckTheme.TYPE["cover_title"], bold=True, color=DeckTheme.WHITE,
                  align="center", anchor="middle")
        deck.text(slide, 1.0, 4.05, DeckTheme.SLIDE_W - 2.0, 0.5, ctx.t("cover_subtitle"),
                  size=DeckTheme.TYPE["cover_subtitle"], color=DeckTheme.WHITE, align="center")
        deck.footer_strip(slide)
        return BlockResult(rendered=True)


class ExecSummaryBlock(BaseBlock):
    id = "exec_summary"
    section = Section.FRONT
    always = True

    def is_available(self, ctx) -> bool:
        return True

    def render(self, ctx, deck, page: int) -> BlockResult:
        slide = deck.blank_slide()
        deck.chrome(slide, page)
        deck.heading(slide, ctx.t("exec_summary_title"), ctx.t("exec_summary_subtitle"))

        insight = ctx.block_insight("exec_summary")
        headline = insight.get("headline") or ctx.narrative.get("overview") or self._fallback_headline(ctx)
        deck.callout(slide, DeckTheme.MARGIN, 1.65, DeckTheme.content_w(), 1.15,
                     ctx.t("so_what"), headline)

        kpis = [
            (ctx.t("kpi_revenue_2025"), ctx.fmt.currency(ctx.m("total_revenue_2025")), ctx.quality_chip("total_revenue_2025")),
            (ctx.t("kpi_yoy_change"), ctx.fmt.percent_signed(ctx.m("yoy_percent")), ctx.quality_chip("yoy_percent")),
            (ctx.t("kpi_active_2025"), ctx.fmt.integer(ctx.m("active_asins_2025")), ""),
            (ctx.t("kpi_pct_inactive"), ctx.fmt.share(ctx.m("percentage_inactive_asins")), ""),
            (ctx.t("kpi_top_5_revenue_share"), ctx.fmt.share(ctx.m("top_5_revenue_share")), ""),
            (ctx.t("kpi_asins_2025"), ctx.fmt.integer(ctx.m("total_asins_2025")), ""),
        ]
        kpis = [(label, value, chip) for label, value, chip in kpis if value not in ("", "—", "N/A")]

        # Reference-style grid: up to three big solid tiles per row.
        gap = 0.3
        per_row = 3
        card_w = (DeckTheme.content_w() - gap * (per_row - 1)) / per_row
        card_h = 1.75
        for idx, (label, value, chip) in enumerate(kpis[:6]):
            row, col = divmod(idx, per_row)
            x = DeckTheme.MARGIN + col * (card_w + gap)
            y = 3.05 + row * (card_h + 0.22)
            deck.kpi(slide, x, y, card_w, card_h, label, value,
                     fill=DeckTheme.kpi_fill(idx), chip=chip)
        return BlockResult(rendered=True)

    @staticmethod
    def _fallback_headline(ctx) -> str:
        rev = ctx.fmt.currency(ctx.m("total_revenue_2025"))
        yoy = ctx.fmt.percent_signed(ctx.m("yoy_percent"))
        inactive = ctx.fmt.share(ctx.m("percentage_inactive_asins"))
        return (f"{ctx.brand} generated {rev} in 2025 ({yoy} YoY) with {inactive} of the "
                f"catalog inactive.")
