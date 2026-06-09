"""Section divider — rendered only when its section has visible content."""
from __future__ import annotations

from app.services.brand_analysis.deck.block import SECTION_TITLES, BaseBlock, BlockResult, Section
from app.services.brand_analysis.deck.theme import DeckTheme


class SectionDivider(BaseBlock):
    def __init__(self, section: Section, index: int) -> None:
        self.section = section
        self._index = index
        self.id = f"divider_{section.value}"

    def is_available(self, ctx) -> bool:
        # Availability is decided by the composer (does the section have content);
        # the divider itself never gates on metric keys.
        return True

    def render(self, ctx, deck, page: int) -> BlockResult:
        en, it = SECTION_TITLES[self.section]
        title = it if ctx.language == "it" else en
        accent = DeckTheme.accent(self._index)
        slide = deck.blank_slide()
        deck.rect(slide, 0, 0, DeckTheme.SLIDE_W, DeckTheme.SLIDE_H, DeckTheme.SURFACE)
        deck.rect(slide, 0, 3.05, DeckTheme.SLIDE_W, 1.4, DeckTheme.WHITE)
        deck.rect(slide, DeckTheme.MARGIN, 3.05, 0.14, 1.4, accent)
        deck.text(slide, DeckTheme.MARGIN + 0.5, 3.2, DeckTheme.content_w(), 0.4,
                  f"{self._index:02d}", size=16, bold=True, color=accent)
        deck.text(slide, DeckTheme.MARGIN + 0.5, 3.55, DeckTheme.content_w(), 0.7,
                  title, size=DeckTheme.TYPE["section"], bold=True, color=DeckTheme.INK)
        ctx.section_titles[self.section.value] = title
        return BlockResult(rendered=True)
