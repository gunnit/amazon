"""Channel & risk section: operational gap, channel/Buy Box gap, concentration risk."""
from __future__ import annotations

from app.services.brand_analysis.deck import format as fmt
from app.services.brand_analysis.deck.block import BaseBlock, BlockResult, Section
from app.services.brand_analysis.deck.blocks.performance import _insight_strip
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
        decline_subcat = fmt.real_category(decline.get("subcategory"))
        # Subcategory name goes in the small label, the percentage is the KPI
        # value — a long name can never overflow the tile.
        decline_kpi = (
            (f"{ctx.t('kpi_largest_subcat_decline')} · {fmt.truncate(decline_subcat, 24)}",
             ctx.fmt.percent_signed(decline.get("yoy_percent")))
            if decline_subcat and decline.get("yoy_percent") is not None
            else (ctx.t("kpi_largest_subcat_decline"), fmt.EMPTY)
        )
        kpis = [
            (ctx.t("kpi_pct_inactive_asins"), ctx.fmt.share(ctx.m("percentage_inactive_asins"))),
            (ctx.t("kpi_pct_declining_asins"), ctx.fmt.share(ctx.m("percentage_declining_asins_among_active"))),
            (ctx.t("kpi_asins_multi_seller"), ctx.fmt.integer(ctx.m("asins_with_more_than_1_seller"))),
            decline_kpi,
        ]
        kpis = [k for k in kpis if k[1] != fmt.EMPTY]
        gap = 0.24
        max_card = 4.2 if len(kpis) >= 3 else 6.16
        card_w = min((DeckTheme.content_w() - gap * (max(len(kpis), 1) - 1)) / max(len(kpis), 1), max_card)
        for idx, (label, value) in enumerate(kpis):
            deck.kpi(slide, DeckTheme.MARGIN + idx * (card_w + gap), 1.6, card_w, 1.45,
                     label, value, fill=DeckTheme.kpi_fill(idx))

        fragments = []
        if ctx.m("percentage_inactive_asins") not in (None, 0):
            fragments.append(ctx.t("frag_inactive").format(pct=ctx.fmt.share(ctx.m("percentage_inactive_asins"))))
        if ctx.m("percentage_declining_asins_among_active") not in (None, 0):
            fragments.append(ctx.t("frag_declining").format(
                pct=ctx.fmt.share(ctx.m("percentage_declining_asins_among_active"))))
        if fragments:
            _insight_strip(ctx, deck, slide, self.id,
                           f"{ctx.t('frag_gap_prefix')} {'; '.join(fragments)}.")

        # The Concentration Risk slide carries the same trio plus the product
        # table; repeat it here only when that slide will not render.
        if not ConcentrationRiskBlock().is_available(ctx):
            deck.text(slide, DeckTheme.MARGIN, 3.3, DeckTheme.content_w(), 0.3,
                      ctx.t("revenue_concentration"), size=13, bold=True, color=DeckTheme.BRAND_PRIMARY)
            conc_all = [
                (ctx.t("kpi_top_5_asins"), ctx.fmt.share(ctx.m("top_5_revenue_share"))),
                (ctx.t("kpi_top_10_asins"), ctx.fmt.share(ctx.m("top_10_revenue_share"))),
                (ctx.t("kpi_avg_rev_per_active_asin"), ctx.fmt.currency(ctx.m("average_revenue_per_active_asin"))),
            ]
            conc = [k for k in conc_all if k[1] != fmt.EMPTY]
            conc_w = (DeckTheme.content_w() - gap * 2) / 3
            for idx, (label, value) in enumerate(conc):
                deck.kpi(slide, DeckTheme.MARGIN + idx * (conc_w + gap), 3.7, conc_w, 1.45, label, value)
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
            (ctx.t("kpi_avg_sellers"), ctx.fmt.number(summary.get("average_seller_count"), 1)),
            (ctx.t("kpi_avg_offers"), ctx.fmt.number(summary.get("average_offer_count"), 1)),
            (ctx.t("kpi_missing_buy_box"), ctx.fmt.integer(summary.get("asins_missing_buy_box_owner"))),
        ]
        kpis = [k for k in kpis if k[1] != fmt.EMPTY]
        gap = 0.28
        card_w = min((DeckTheme.content_w() - gap * (max(len(kpis), 1) - 1)) / max(len(kpis), 1), 4.2)
        for idx, (label, value) in enumerate(kpis):
            deck.kpi(slide, DeckTheme.MARGIN + idx * (card_w + gap), 1.6, card_w, 1.45,
                     label, value, fill=DeckTheme.kpi_fill(idx))

        rows = [
            [fmt.truncate(item.get("reseller"), 38), ctx.fmt.integer(item.get("asin_count")),
             ctx.fmt.currency(item.get("revenue")), ctx.fmt.share(item.get("share_percent"))]
            for item in (ctx.m("reseller_buy_box_distribution") or [])[:8]
        ]
        if not rows:
            rows = [
                [fmt.truncate(item.get("reseller"), 38), ctx.fmt.integer(item.get("asin_count")),
                 fmt.EMPTY, ctx.t("current_snapshot")]
                for item in (summary.get("current_buy_box_snapshot_distribution") or [])[:8]
            ]
        if rows:
            deck.table(slide, DeckTheme.MARGIN, 3.3,
                       [ctx.t("table_reseller_buy_box"), ctx.t("table_asins"),
                        ctx.t("table_revenue"), ctx.t("table_pct_impact")],
                       rows, [6.21, 1.8, 2.8, 1.8])
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
            (ctx.t("kpi_top_5_revenue_share"), ctx.fmt.share(ctx.m("top_5_revenue_share"))),
            (ctx.t("kpi_top_10_revenue_share"), ctx.fmt.share(ctx.m("top_10_revenue_share"))),
            (ctx.t("kpi_avg_rev_per_active_asin"), ctx.fmt.currency(ctx.m("average_revenue_per_active_asin"))),
        ]
        kpis = [k for k in kpis if k[1] != fmt.EMPTY]
        gap = 0.28
        card_w = min((DeckTheme.content_w() - gap * (max(len(kpis), 1) - 1)) / max(len(kpis), 1), 4.2)
        for idx, (label, value) in enumerate(kpis):
            deck.kpi(slide, DeckTheme.MARGIN + idx * (card_w + gap), 1.6, card_w, 1.45,
                     label, value, fill=DeckTheme.kpi_fill(idx))

        rows = [
            [item.get("asin") or fmt.EMPTY,
             fmt.product_label(item.get("product_name") or item.get("asin"), ctx.brand, 52),
             ctx.fmt.currency(item.get("revenue_2025")), ctx.fmt.percent_signed(item.get("yoy_percent"))]
            for item in (ctx.m("top_5_asins") or [])[:5]
        ]
        deck.table(slide, DeckTheme.MARGIN, 3.3,
                   ["ASIN", ctx.t("table_product"), ctx.t("table_revenue"), ctx.t("table_yoy")],
                   rows, [1.7, 6.31, 2.8, 1.8], accent_columns=[3])
        return BlockResult(rendered=True)
