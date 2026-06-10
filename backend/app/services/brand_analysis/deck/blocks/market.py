"""Market section: market share, competitive distribution, search visibility.

Gated strictly on real data — market share needs an external market export and
search visibility needs the Brand Analytics search-terms signal. When a gate
fails the block is skipped (no "N/A" placeholder slide); the omission is
recorded in the methodology appendix instead.
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


class SearchVisibilityBlock(BaseBlock):
    """Brand Analytics search-terms signal: where shoppers' searches click.

    Renders only when the analysis carried a real Brand Analytics fetch
    (Brand Registry accounts). Shares are search-level proxies and are never
    presented as revenue market share.
    """

    id = "search_visibility"
    section = Section.MARKET
    required_keys = ("market_analysis",)

    def _market(self, ctx) -> dict:
        return ctx.m("market_analysis") or {}

    def is_available(self, ctx) -> bool:
        market = self._market(ctx)
        if market.get("search_share_source") != "brand_analytics_search_terms":
            return False
        return (
            market.get("search_click_share") is not None
            or bool(market.get("search_term_competitors"))
        )

    def skip_reason(self, ctx) -> str:
        return self._market(ctx).get("search_share_limitation") or ctx.t("skip_no_data")

    def render(self, ctx, deck, page: int) -> BlockResult:
        slide = deck.blank_slide()
        deck.chrome(slide, page)
        deck.heading(slide, ctx.t("search_visibility_title"), ctx.t("search_visibility_subtitle"))
        market = self._market(ctx)
        chip = ctx.quality("search_click_share")

        competitor_terms = market.get("terms_with_competitor_top_click")
        terms_total = market.get("search_terms_total")
        competitor_kpi = (
            f"{fmt.integer(competitor_terms)} / {fmt.integer(terms_total)}"
            if competitor_terms is not None and terms_total
            else fmt.EMPTY
        )
        kpis = [
            (ctx.t("kpi_search_click_share"), fmt.share(market.get("search_click_share")), chip),
            (ctx.t("kpi_search_purchase_share"), fmt.share(market.get("search_purchase_share")), chip),
            (ctx.t("kpi_competitor_top_terms"), competitor_kpi, chip),
        ]
        gap = 0.28
        card_w = (DeckTheme.content_w() - gap * 2) / 3
        for idx, (label, value, q) in enumerate(kpis):
            deck.kpi(slide, DeckTheme.MARGIN + idx * (card_w + gap), 1.9, card_w, 1.0,
                     label, value, chip=q)

        rows = []
        for term in (market.get("search_term_competitors") or [])[:8]:
            top_clicked = (term.get("top_clicked_asins") or [{}])[0]
            owner = fmt.EMPTY
            if term.get("top_click_is_competitor") is True:
                owner = ctx.t("label_competitor")
            elif term.get("top_click_is_competitor") is False:
                owner = ctx.t("label_own_brand")
            rows.append([
                fmt.integer(term.get("search_frequency_rank")),
                fmt.truncate(term.get("search_term"), 32),
                fmt.truncate(top_clicked.get("product_title") or top_clicked.get("asin"), 38),
                fmt.share(top_clicked.get("click_share")),
                owner,
            ])
        if rows:
            deck.table(
                slide, DeckTheme.MARGIN, 3.3,
                [ctx.t("table_search_rank"), ctx.t("table_search_term"),
                 ctx.t("table_top_clicked"), ctx.t("table_click_share"), ctx.t("table_owner")],
                rows, [1.1, 3.4, 4.3, 1.2, 1.4],
            )

        period = market.get("search_share_period") or {}
        footnote = ctx.t("search_visibility_footnote")
        if period.get("start_date") and period.get("end_date"):
            footnote = f"{footnote} ({period['start_date']} – {period['end_date']})"
        deck.text(slide, DeckTheme.MARGIN, DeckTheme.FOOTER_Y - 0.18, DeckTheme.content_w(), 0.3,
                  footnote, size=8, color=DeckTheme.MUTED)
        return BlockResult(rendered=True)
