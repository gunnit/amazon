"""Market section: market share & competitive distribution.

Gated strictly on a real external market export — the deck never invents market
size. When the gate fails the whole block is skipped (no "N/A" placeholder
slide); the omission is recorded in the methodology appendix instead.
"""
from __future__ import annotations

from app.services.brand_analysis.deck import charts
from app.services.brand_analysis.deck import format as fmt
from app.services.brand_analysis.deck.block import BaseBlock, BlockResult, Section
from app.services.brand_analysis.deck.theme import DeckTheme


class MarketShareBlock(BaseBlock):
    id = "market_share"
    section = Section.MARKET
    required_keys = ("market_analysis",)

    def is_available(self, ctx) -> bool:
        return (ctx.m("market_analysis") or {}).get("status") == "calculated_from_external_market_export"

    def skip_reason(self, ctx) -> str:
        return (ctx.m("market_analysis") or {}).get("limitation") or ctx.t("market_share_no_base")

    def render(self, ctx, deck, page: int) -> BlockResult:
        slide = deck.blank_slide()
        deck.chrome(slide, page)
        deck.heading(slide, ctx.t("market_share_title"), ctx.t("market_share_subtitle"))
        market = ctx.m("market_analysis") or {}
        chip = ctx.quality("market_revenue_share")
        kpis = [
            (ctx.t("kpi_market_size_2025"), fmt.currency(market.get("market_size_2025")), chip),
            (ctx.t("kpi_revenue_share_2025"), fmt.share(market.get("market_share_2025")), chip),
            (ctx.t("kpi_revenue_share_2024"), fmt.share(market.get("market_share_2024")), chip),
        ]
        gap = 0.28
        card_w = (DeckTheme.content_w() - gap * 2) / 3
        for idx, (label, value, q) in enumerate(kpis):
            deck.kpi(slide, DeckTheme.MARGIN + idx * (card_w + gap), 1.9, card_w, 1.0, label, value, chip=q)

        competitors = (market.get("competitive_brand_distribution") or [])[:7]
        if competitors:
            labels = [fmt.truncate(c.get("brand"), 22) for c in competitors]
            values = [float(c.get("revenue") or 0) for c in competitors]
            png = charts.hbar(labels, values, value_fmt=lambda v: fmt.currency(v),
                              color=DeckTheme.accent(0), w_in=11.0, h_in=3.0)
            deck.picture(slide, png, DeckTheme.MARGIN, 3.3, 11.4, 3.0)
        return BlockResult(rendered=True)
