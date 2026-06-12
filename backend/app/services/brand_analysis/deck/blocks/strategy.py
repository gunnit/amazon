"""Strategy section: approach, priority actions, roadmap, projection, conclusions."""
from __future__ import annotations

from app.services.brand_analysis.deck import format as fmt
from app.services.brand_analysis.deck.block import BaseBlock, BlockResult, Section
from app.services.brand_analysis.deck.theme import DeckTheme


class ApproachBlock(BaseBlock):
    id = "approach"
    section = Section.STRATEGY
    required_keys = ()

    def _pillars(self, ctx) -> list[dict]:
        return [p for p in (ctx.narrative.get("approach_pillars") or [])
                if (p or {}).get("title")][:3]

    def is_available(self, ctx) -> bool:
        return len(self._pillars(ctx)) >= 3

    def render(self, ctx, deck, page: int) -> BlockResult:
        slide = deck.blank_slide()
        deck.chrome(slide, page)
        deck.heading(slide, ctx.t("approach_title"), ctx.t("approach_subtitle"))
        gap = 0.3
        col_w = (DeckTheme.content_w() - 2 * gap) / 3
        y, card_h = 1.95, 2.95
        for idx, pillar in enumerate(self._pillars(ctx)):
            x = DeckTheme.MARGIN + idx * (col_w + gap)
            deck.rect(slide, x, y, col_w, card_h, DeckTheme.NAVY)
            deck.rect(slide, x, y, col_w, 0.09, DeckTheme.BRAND_PRIMARY)
            deck.text(slide, x + 0.28, y + 0.32, col_w - 0.56, 0.62,
                      pillar.get("title", ""), size=16, bold=True, color=DeckTheme.WHITE)
            deck.text(slide, x + 0.28, y + 1.02, col_w - 0.56, card_h - 1.3,
                      pillar.get("body", ""), size=11, color=DeckTheme.WHITE)
        banners = (
            (ctx.t("approach_visibility"), ctx.t("approach_visibility_sub"), DeckTheme.STEEL_BLUE),
            (ctx.t("approach_conversion"), ctx.t("approach_conversion_sub"), DeckTheme.ORANGE),
            (ctx.t("approach_loyalty"), ctx.t("approach_loyalty_sub"), DeckTheme.POSITIVE),
        )
        by = y + card_h + 0.35
        for idx, (title, sub, color) in enumerate(banners):
            x = DeckTheme.MARGIN + idx * (col_w + gap)
            deck.rect(slide, x, by, col_w, 0.95, color)
            deck.text(slide, x, by + 0.17, col_w, 0.3, title,
                      size=14, bold=True, color=DeckTheme.WHITE, align="center")
            deck.text(slide, x, by + 0.55, col_w, 0.25, sub,
                      size=10, color=DeckTheme.WHITE, align="center")
        return BlockResult(rendered=True)


class GrowthProjectionBlock(BaseBlock):
    id = "growth_projection"
    section = Section.STRATEGY
    required_keys = ("growth_projection_scenarios", "total_revenue_2025")

    _SCENARIOS = (
        ("scenario_conservative", "conservative", DeckTheme.NAVY),
        ("scenario_realistic", "realistic", DeckTheme.POSITIVE),
        ("scenario_optimistic", "optimistic", DeckTheme.BRAND_PRIMARY),
    )

    def _scenarios(self, ctx) -> dict:
        return ctx.m("growth_projection_scenarios") or {}

    def is_available(self, ctx) -> bool:
        scenarios = self._scenarios(ctx)
        has_bands = all(
            (scenarios.get(key) or {}).get("revenue_high") is not None
            for _, key, _ in self._SCENARIOS
        )
        return has_bands and float(ctx.m("total_revenue_2025") or 0) > 0

    @staticmethod
    def _signed_pct(value) -> str:
        number = int(value or 0)
        return f"+{number}%" if number >= 0 else f"{number}%"

    def render(self, ctx, deck, page: int) -> BlockResult:
        slide = deck.blank_slide()
        deck.chrome(slide, page)
        scenarios = self._scenarios(ctx)
        derived = scenarios.get("basis") == "derived_from_yoy_history"
        deck.heading(slide, ctx.t("projection_title"),
                     ctx.t("projection_subtitle_derived" if derived else "projection_subtitle"))

        # Current-situation strip: where the brand starts from.
        y = 1.95
        deck.rect(slide, DeckTheme.MARGIN, y, DeckTheme.content_w(), 0.9,
                  DeckTheme.SURFACE, line=DeckTheme.HAIRLINE)
        deck.text(slide, DeckTheme.MARGIN + 0.25, y + 0.32, 2.5, 0.3,
                  ctx.t("current_situation"), size=12, bold=True, color=DeckTheme.SUBTLE_INK)
        deck.text(slide, DeckTheme.MARGIN + 2.85, y + 0.17, 3.2, 0.56,
                  ctx.fmt.currency(ctx.m("total_revenue_2025")), size=26, bold=True,
                  color=DeckTheme.BRAND_PRIMARY)
        detail = (f"{ctx.fmt.percent_signed(ctx.m('yoy_percent'))} YoY   ·   "
                  f"{ctx.fmt.integer(ctx.m('active_asins_2025'))} "
                  f"{ctx.t('projection_active_asins')} "
                  f"{ctx.fmt.integer(ctx.m('total_asins_2025'))}")
        deck.text(slide, DeckTheme.MARGIN + 6.3, y + 0.32, DeckTheme.content_w() - 6.55, 0.3,
                  detail, size=12, color=DeckTheme.SUBTLE_INK)

        gap = 0.3
        col_w = (DeckTheme.content_w() - 2 * gap) / 3
        cy, card_h = 3.15, 2.6
        for idx, (label_key, key, color) in enumerate(self._SCENARIOS):
            scenario = scenarios.get(key) or {}
            x = DeckTheme.MARGIN + idx * (col_w + gap)
            deck.rect(slide, x, cy, col_w, card_h, DeckTheme.SURFACE, line=DeckTheme.HAIRLINE)
            deck.rect(slide, x, cy, col_w, 0.09, color)
            deck.text(slide, x + 0.25, cy + 0.32, col_w - 0.5, 0.3,
                      ctx.t(label_key), size=13, bold=True, color=color)
            band = (f"{self._signed_pct(scenario.get('growth_low'))} – "
                    f"{self._signed_pct(scenario.get('growth_high'))}")
            deck.text(slide, x + 0.25, cy + 0.72, col_w - 0.5, 0.55,
                      band, size=28, bold=True, color=color)
            revenue_range = (f"{ctx.fmt.currency(scenario.get('revenue_low'))} – "
                             f"{ctx.fmt.currency(scenario.get('revenue_high'))}")
            deck.text(slide, x + 0.25, cy + 1.5, col_w - 0.5, 0.32,
                      revenue_range, size=14, bold=True, color=DeckTheme.INK)
            deck.text(slide, x + 0.25, cy + 1.95, col_w - 0.5, 0.5,
                      ctx.t("projection_revenue_at_12m"), size=10, color=DeckTheme.MUTED)

        # Honest framing: derived bands vs illustrative defaults, never a forecast.
        deck.text(slide, DeckTheme.MARGIN, cy + card_h + 0.25, DeckTheme.content_w(), 0.4,
                  ctx.t("projection_disclaimer_derived" if derived else "projection_disclaimer"),
                  size=9, color=DeckTheme.MUTED)
        return BlockResult(rendered=True)


class PriorityActionsBlock(BaseBlock):
    id = "priority_actions"
    section = Section.STRATEGY

    def is_available(self, ctx) -> bool:
        return len(ctx.priority_actions()) >= 1

    def render(self, ctx, deck, page: int) -> BlockResult:
        slide = deck.blank_slide()
        deck.chrome(slide, page)
        deck.heading(slide, ctx.t("projection_actions_title"),
                     ctx.t("projection_actions_subtitle"))
        actions = ctx.priority_actions()[:6]
        y = 1.95
        row_h = 0.78
        for idx, action in enumerate(actions):
            accent = DeckTheme.accent(idx)
            deck.rect(slide, DeckTheme.MARGIN, y, DeckTheme.content_w(), 0.66,
                      DeckTheme.SURFACE, line=DeckTheme.HAIRLINE)
            deck.rect(slide, DeckTheme.MARGIN, y, 0.5, 0.66, accent)
            deck.text(slide, DeckTheme.MARGIN, y + 0.18, 0.5, 0.3, str(idx + 1),
                      size=14, bold=True, color=DeckTheme.WHITE, align="center")
            deck.text(slide, DeckTheme.MARGIN + 0.7, y + 0.17, DeckTheme.content_w() - 0.9, 0.34,
                      action, size=12, color=DeckTheme.INK, anchor="middle")
            y += row_h
        return BlockResult(rendered=True)


class RoadmapBlock(BaseBlock):
    id = "roadmap"
    section = Section.STRATEGY
    required_keys = ()

    def is_available(self, ctx) -> bool:
        roadmap = [r for r in (ctx.narrative.get("roadmap") or []) if (r or {}).get("title")]
        return len(roadmap) >= 1

    def render(self, ctx, deck, page: int) -> BlockResult:
        slide = deck.blank_slide()
        deck.chrome(slide, page)
        deck.heading(slide, ctx.t("roadmap_title"), ctx.t("roadmap_subtitle"))
        roadmap = [r for r in (ctx.narrative.get("roadmap") or []) if (r or {}).get("title")][:3]
        y = 2.0
        for idx, phase in enumerate(roadmap):
            accent = DeckTheme.accent(idx)
            deck.oval(slide, DeckTheme.MARGIN, y, 0.72, 0.72, accent)
            deck.text(slide, DeckTheme.MARGIN, y + 0.22, 0.72, 0.3,
                      phase.get("phase", f"{idx + 1:02d}"), size=14, bold=True,
                      color=DeckTheme.WHITE, align="center")
            deck.text(slide, DeckTheme.MARGIN + 0.95, y + 0.02, DeckTheme.content_w() - 0.95, 0.34,
                      phase.get("title", ""), size=14, bold=True, color=DeckTheme.INK)
            deck.text(slide, DeckTheme.MARGIN + 0.95, y + 0.42, DeckTheme.content_w() - 0.95, 0.6,
                      phase.get("body", ""), size=10, color=DeckTheme.SUBTLE_INK)
            y += 1.45
        return BlockResult(rendered=True)


class ConclusionsBlock(BaseBlock):
    id = "conclusions"
    section = Section.STRATEGY
    required_keys = ()

    _GROUPS = (
        ("conclusions_current_situation", "current_situation", DeckTheme.BRAND_PRIMARY),
        ("conclusions_strengths", "strengths", DeckTheme.POSITIVE),
        ("conclusions_plan", "plan", DeckTheme.STEEL_BLUE),
        ("conclusions_urgency", "urgency", DeckTheme.ORANGE),
    )

    def _conclusions(self, ctx) -> dict:
        return ctx.narrative.get("conclusions") or {}

    def is_available(self, ctx) -> bool:
        conclusions = self._conclusions(ctx)
        return any(conclusions.get(key) for _, key, _ in self._GROUPS)

    def render(self, ctx, deck, page: int) -> BlockResult:
        slide = deck.blank_slide()
        deck.chrome(slide, page)
        deck.heading(slide, ctx.t("conclusions_title"), ctx.t("conclusions_subtitle"))
        conclusions = self._conclusions(ctx)
        col_w = (DeckTheme.content_w() - 0.3) / 2
        row_h = 2.3
        positions = [
            (DeckTheme.MARGIN, 1.9), (DeckTheme.MARGIN + col_w + 0.3, 1.9),
            (DeckTheme.MARGIN, 1.9 + row_h + 0.2), (DeckTheme.MARGIN + col_w + 0.3, 1.9 + row_h + 0.2),
        ]
        for (title_key, data_key, accent), (x, y) in zip(self._GROUPS, positions):
            bullets = [b for b in (conclusions.get(data_key) or [])
                       if str(b).strip() and not str(b).strip().endswith(("N/A", ": —"))][:4]
            if not bullets:
                continue
            deck.callout(slide, x, y, col_w, row_h, ctx.t(title_key), bullets, accent=accent)
        return BlockResult(rendered=True)
