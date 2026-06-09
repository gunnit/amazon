"""Methodology & provenance appendix.

Turns the "missing data" story into a feature: lists which sections rendered,
which were skipped and why, and the provenance quality of key metrics. Always
renders, reads ``ctx.skipped_blocks`` populated by the composer.
"""
from __future__ import annotations

from app.services.brand_analysis.deck import format as fmt
from app.services.brand_analysis.deck.block import BaseBlock, BlockResult, Section
from app.services.brand_analysis.deck.theme import DeckTheme

_PROVENANCE_KEYS = (
    "total_revenue_2025", "total_revenue_2024", "yoy_percent",
    "weighted_average_rating", "market_revenue_share",
)


class MethodologyAppendixBlock(BaseBlock):
    id = "methodology"
    section = Section.APPENDIX
    always = True

    def is_available(self, ctx) -> bool:
        return True

    def render(self, ctx, deck, page: int) -> BlockResult:
        slide = deck.blank_slide()
        deck.chrome(slide, page)
        deck.heading(slide, ctx.t("methodology_title"), ctx.t("methodology_subtitle"))

        shown = list(ctx.section_titles.values())
        deck.callout(slide, DeckTheme.MARGIN, 1.9, 5.9, 2.3, ctx.t("method_what_we_show"),
                     shown or [ctx.t("no_sections")], accent=DeckTheme.POSITIVE)

        skipped = [f"{name}: {reason}" for name, reason in ctx.skipped_blocks]
        deck.callout(slide, DeckTheme.MARGIN + 6.2, 1.9, 5.9, 2.3, ctx.t("method_skipped"),
                     [fmt.truncate(item, 90) for item in skipped] or [ctx.t("value_none")],
                     accent=DeckTheme.MUTED)

        registry = ctx.metrics.get("metric_source_registry") or {}
        rows = []
        for key in _PROVENANCE_KEYS:
            entry = registry.get(key)
            if not entry:
                continue
            rows.append([key.replace("_", " "), str(entry.get("quality") or fmt.EMPTY).upper(),
                         fmt.truncate(str(entry.get("source") or fmt.EMPTY), 48)])
        if rows:
            deck.text(slide, DeckTheme.MARGIN, 4.45, DeckTheme.content_w(), 0.3,
                      ctx.t("method_provenance"), size=13, bold=True, color=DeckTheme.BRAND_PRIMARY)
            deck.table(slide, DeckTheme.MARGIN, 4.8,
                       [ctx.t("method_metric"), ctx.t("method_quality"), "Source"],
                       rows, [3.5, 2.0, 6.4])
        return BlockResult(rendered=True)
