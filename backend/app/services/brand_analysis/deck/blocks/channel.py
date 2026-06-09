"""Channel & risk section: operational gap, channel/Buy Box gap, concentration risk."""
from __future__ import annotations

from app.services.brand_analysis.deck import format as fmt
from app.services.brand_analysis.deck.block import BaseBlock, BlockResult, Section
from app.services.brand_analysis.deck.theme import DeckTheme


class OperationalGapBlock(BaseBlock):
    id = "operational_gap"
    section = Section.CHANNEL

    def is_available(self, ctx) -> bool:
        signals = (
            ctx.m("percentage_inactive_asins"),
            ctx.m("percentage_declining_asins_among_active"),
            ctx.m("asins_with_more_than_1_seller"),
            ctx.m("top_5_revenue_share"),
        )
        return any(value not in (None, 0) for value in signals)

    def render(self, ctx, deck, page: int) -> BlockResult:
        slide = deck.blank_slide()
        deck.chrome(slide, page)
        deck.heading(slide, ctx.t("operational_gap_title"), ctx.t("operational_gap_subtitle"))
        decline = ctx.m("subcategory_with_largest_decline") or {}
        decline_label = (f"{decline.get('subcategory', '—')} "
                         f"{fmt.percent_signed(decline.get('yoy_percent'))}").strip() if decline else fmt.EMPTY
        kpis = [
            (ctx.t("kpi_pct_inactive_asins"), fmt.share(ctx.m("percentage_inactive_asins"))),
            (ctx.t("kpi_pct_declining_asins"), fmt.share(ctx.m("percentage_declining_asins_among_active"))),
            (ctx.t("kpi_asins_multi_seller"), fmt.integer(ctx.m("asins_with_more_than_1_seller"))),
            (ctx.t("kpi_largest_subcat_decline"), decline_label),
        ]
        gap = 0.24
        card_w = (DeckTheme.content_w() - gap * 3) / 4
        for idx, (label, value) in enumerate(kpis):
            deck.kpi(slide, DeckTheme.MARGIN + idx * (card_w + gap), 1.9, card_w, 1.1, label, value)

        deck.text(slide, DeckTheme.MARGIN, 3.4, DeckTheme.content_w(), 0.3,
                  ctx.t("revenue_concentration"), size=13, bold=True, color=DeckTheme.BRAND_PRIMARY)
        conc = [
            (ctx.t("kpi_top_5_asins"), fmt.share(ctx.m("top_5_revenue_share"))),
            (ctx.t("kpi_top_10_asins"), fmt.share(ctx.m("top_10_revenue_share"))),
            (ctx.t("kpi_avg_rev_per_active_asin"), fmt.currency(ctx.m("average_revenue_per_active_asin"))),
        ]
        conc_w = (DeckTheme.content_w() - gap * 2) / 3
        for idx, (label, value) in enumerate(conc):
            deck.kpi(slide, DeckTheme.MARGIN + idx * (conc_w + gap), 3.8, conc_w, 1.0, label, value)
        return BlockResult(rendered=True)


class ChannelGapBlock(BaseBlock):
    id = "channel_gap"
    section = Section.CHANNEL
    required_keys = ("seller_buy_box_summary",)

    def is_available(self, ctx) -> bool:
        summary = ctx.m("seller_buy_box_summary") or {}
        has_flags = any(summary.get(k) for k in (
            "seller_count_available", "offer_count_available",
            "buy_box_owner_available", "current_snapshot_available"))
        has_rows = bool(ctx.m("reseller_buy_box_distribution")) or bool(
            summary.get("current_buy_box_snapshot_distribution"))
        return has_flags and has_rows

    def render(self, ctx, deck, page: int) -> BlockResult:
        slide = deck.blank_slide()
        deck.chrome(slide, page)
        deck.heading(slide, ctx.t("channel_gap_title"), ctx.t("channel_gap_subtitle"))
        summary = ctx.m("seller_buy_box_summary") or {}
        kpis = [
            (ctx.t("kpi_avg_sellers"), fmt.number(summary.get("average_seller_count"), 1)),
            (ctx.t("kpi_avg_offers"), fmt.number(summary.get("average_offer_count"), 1)),
            (ctx.t("kpi_missing_buy_box"), fmt.integer(summary.get("asins_missing_buy_box_owner"))),
        ]
        gap = 0.28
        card_w = (DeckTheme.content_w() - gap * 2) / 3
        for idx, (label, value) in enumerate(kpis):
            deck.kpi(slide, DeckTheme.MARGIN + idx * (card_w + gap), 1.9, card_w, 1.0, label, value)

        rows = [
            [fmt.truncate(item.get("reseller"), 38), fmt.integer(item.get("asin_count")),
             fmt.currency(item.get("revenue")), fmt.share(item.get("share_percent"))]
            for item in (ctx.m("reseller_buy_box_distribution") or [])[:8]
        ]
        if not rows:
            rows = [
                [fmt.truncate(item.get("reseller"), 38), fmt.integer(item.get("asin_count")),
                 fmt.EMPTY, ctx.t("current_snapshot")]
                for item in (summary.get("current_buy_box_snapshot_distribution") or [])[:8]
            ]
        if rows:
            deck.table(slide, DeckTheme.MARGIN, 3.3,
                       [ctx.t("table_reseller_buy_box"), ctx.t("table_asins"),
                        ctx.t("table_revenue"), ctx.t("table_pct_impact")],
                       rows, [5.2, 1.6, 2.4, 1.6])
        return BlockResult(rendered=True)


class ConcentrationRiskBlock(BaseBlock):
    id = "concentration_risk"
    section = Section.CHANNEL
    required_keys = ("top_5_revenue_share", "top_5_asins")

    def is_available(self, ctx) -> bool:
        return ctx.m("top_5_revenue_share") is not None and len(ctx.m("top_5_asins") or []) >= 3

    def render(self, ctx, deck, page: int) -> BlockResult:
        slide = deck.blank_slide()
        deck.chrome(slide, page)
        deck.heading(slide, ctx.t("concentration_risk_title"), ctx.t("concentration_risk_subtitle"))
        kpis = [
            (ctx.t("kpi_top_5_revenue_share"), fmt.share(ctx.m("top_5_revenue_share"))),
            (ctx.t("kpi_top_10_revenue_share"), fmt.share(ctx.m("top_10_revenue_share"))),
            (ctx.t("kpi_avg_rev_per_active_asin"), fmt.currency(ctx.m("average_revenue_per_active_asin"))),
        ]
        gap = 0.28
        card_w = (DeckTheme.content_w() - gap * 2) / 3
        for idx, (label, value) in enumerate(kpis):
            deck.kpi(slide, DeckTheme.MARGIN + idx * (card_w + gap), 1.9, card_w, 1.0, label, value)

        rows = [
            [fmt.truncate(item.get("product_name") or item.get("asin"), 46),
             fmt.currency(item.get("revenue_2025")), fmt.percent_signed(item.get("yoy_percent"))]
            for item in (ctx.m("top_5_asins") or [])[:5]
        ]
        deck.table(slide, DeckTheme.MARGIN, 3.3,
                   [ctx.t("table_product"), ctx.t("table_revenue"), ctx.t("table_yoy")],
                   rows, [6.6, 2.4, 1.8], accent_columns=[2])
        return BlockResult(rendered=True)
