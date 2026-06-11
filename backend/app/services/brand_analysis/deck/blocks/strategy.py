"""Strategy section: priority actions, roadmap, conclusions."""
from __future__ import annotations

from app.services.brand_analysis.deck.block import BaseBlock, BlockResult, Section
from app.services.brand_analysis.deck.theme import DeckTheme


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
