"""Cover, executive summary and agenda — the always-on front matter."""
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
        deck.rect(slide, 0, DeckTheme.SLIDE_H - 0.12, DeckTheme.SLIDE_W, 0.12, DeckTheme.NAVY)
        deck.text(slide, 1.2, 2.9, DeckTheme.SLIDE_W - 2.4, 0.9,
                  f"{ctx.brand} {ctx.t('cover_on_amazon')}",
                  size=DeckTheme.TYPE["h1"] + 8, bold=True, color=DeckTheme.WHITE,
                  align="center", anchor="middle")
        deck.text(slide, 1.2, 3.95, DeckTheme.SLIDE_W - 2.4, 0.4, ctx.t("cover_subtitle"),
                  size=14, color=DeckTheme.WHITE, align="center")
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
        deck.callout(slide, DeckTheme.MARGIN, 1.85, DeckTheme.content_w(), 1.1,
                     ctx.t("so_what"), headline)

        kpis = [
            (ctx.t("kpi_revenue_2025"), fmt.currency(ctx.m("total_revenue_2025")), ctx.quality("total_revenue_2025")),
            (ctx.t("kpi_yoy_change"), fmt.percent_signed(ctx.m("yoy_percent")), ctx.quality("yoy_percent")),
            (ctx.t("kpi_active_2025"), fmt.integer(ctx.m("active_asins_2025")), ""),
            (ctx.t("kpi_pct_inactive"), fmt.share(ctx.m("percentage_inactive_asins")), ""),
            (ctx.t("kpi_top_5_revenue_share"), fmt.share(ctx.m("top_5_revenue_share")), ""),
        ]
        gap = 0.2
        card_w = (DeckTheme.content_w() - gap * (len(kpis) - 1)) / len(kpis)
        for idx, (label, value, chip) in enumerate(kpis):
            x = DeckTheme.MARGIN + idx * (card_w + gap)
            deck.kpi(slide, x, 3.2, card_w, 1.0, label, value, chip=chip)

        bullets = insight.get("bullets") or ctx.narrative.get("conclusions", {}).get("current_situation") or []
        bullets = [b for b in bullets if str(b).strip()][:4]
        if bullets:
            deck.callout(slide, DeckTheme.MARGIN, 4.5, DeckTheme.content_w(), 2.2,
                         ctx.t("conclusions_current_situation"), bullets)
        return BlockResult(rendered=True)

    @staticmethod
    def _fallback_headline(ctx) -> str:
        rev = fmt.currency(ctx.m("total_revenue_2025"))
        yoy = fmt.percent_signed(ctx.m("yoy_percent"))
        inactive = fmt.share(ctx.m("percentage_inactive_asins"))
        return (f"{ctx.brand} generated {rev} in 2025 ({yoy} YoY) with {inactive} of the "
                f"catalog inactive.")


class AgendaBlock(BaseBlock):
    id = "agenda"
    section = Section.FRONT
    always = True

    def is_available(self, ctx) -> bool:
        return True

    def render(self, ctx, deck, page: int) -> BlockResult:
        slide = deck.blank_slide()
        deck.chrome(slide, page)
        deck.heading(slide, ctx.t("agenda_title"), ctx.t("agenda_subtitle"))
        sections = list(ctx.section_titles.values()) or [ctx.t("exec_summary_title")]
        y = 2.0
        for idx, name in enumerate(sections):
            accent = DeckTheme.accent(idx)
            deck.rect(slide, DeckTheme.MARGIN, y, 0.42, 0.42, accent, radius=True)
            deck.text(slide, DeckTheme.MARGIN, y + 0.08, 0.42, 0.26, f"{idx + 1:02d}",
                      size=11, bold=True, color=DeckTheme.WHITE, align="center")
            deck.text(slide, DeckTheme.MARGIN + 0.62, y + 0.04, DeckTheme.content_w() - 0.62, 0.34,
                      name, size=14, bold=True, color=DeckTheme.INK)
            y += 0.7
        return BlockResult(rendered=True)
