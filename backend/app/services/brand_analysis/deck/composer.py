"""Compose a deck from the block registry.

Walks the ordered blocks, renders only those whose ``is_available`` gate passes,
inserts a section divider before the first available block of each section, and
records every skipped block for the methodology appendix. The composer also
produces a per-section manifest that ``validate_pptx_bytes`` asserts against — a
data-driven contract that replaces the old fixed slide-count gate.
"""
from __future__ import annotations

from typing import Any

from app.services.brand_analysis.deck.block import SECTION_TITLES, Block, Section
from app.services.brand_analysis.deck.blocks.divider import SectionDivider
from app.services.brand_analysis.deck.context import DeckContext
from app.services.brand_analysis.deck.primitives import DeckBuilder
from app.services.brand_analysis.deck.registry import SECTION_ORDER, default_blocks


class DeckComposer:
    def __init__(self, ctx: DeckContext, blocks: list[Block] | None = None) -> None:
        self.ctx = ctx
        self.blocks = blocks if blocks is not None else default_blocks()

    def _plan(self) -> tuple[list[Block], list[tuple[Block, str]], dict[str, bool]]:
        """Return (available_blocks, skipped_blocks, section_present)."""
        available: list[Block] = []
        skipped: list[tuple[Block, str]] = []
        for block in self.blocks:
            if block.always or block.is_available(self.ctx):
                available.append(block)
            else:
                skipped.append((block, block.skip_reason(self.ctx)))
        present_sections = {b.section for b in available}
        section_present = {s.value: (s in present_sections) for s in SECTION_ORDER}
        return available, skipped, section_present

    def build(self) -> bytes:
        deck = DeckBuilder(self.ctx.brand)
        available, skipped, section_present = self._plan()
        available_ids = {b.id for b in available}

        # Pre-seed agenda section titles so the AgendaBlock can list them even
        # though it renders before its dividers do.
        for idx, section in enumerate(SECTION_ORDER, start=1):
            if section_present.get(section.value):
                en, it = SECTION_TITLES[section]
                self.ctx.section_titles[section.value] = it if self.ctx.language == "it" else en

        page = 1
        rendered_ids: list[str] = []
        emitted_dividers: set[Section] = set()
        self.ctx.skipped_blocks = [
            (self._block_name(block), reason) for block, reason in skipped
        ]

        for block in available:
            section = block.section
            if section in SECTION_ORDER and section not in emitted_dividers:
                divider = SectionDivider(section, SECTION_ORDER.index(section) + 1)
                divider.render(self.ctx, deck, page)
                emitted_dividers.add(section)
                page += 1
            result = block.render(self.ctx, deck, page)
            if result.rendered:
                rendered_ids.append(block.id)
                page += 1

        self.ctx.rendered_block_ids = rendered_ids
        self._manifest = self._build_manifest(available_ids, section_present, skipped)
        return deck.to_bytes()

    def _build_manifest(self, available_ids, section_present, skipped) -> list[dict[str, Any]]:
        skip_reasons = {block.section.value: reason for block, reason in skipped}
        manifest = []
        for section in SECTION_ORDER:
            present = section_present.get(section.value, False)
            manifest.append({
                "section_id": section.value,
                "present": present,
                "reason": None if present else skip_reasons.get(section.value, "no_data"),
            })
        return manifest

    @property
    def manifest(self) -> list[dict[str, Any]]:
        return getattr(self, "_manifest", [])

    @staticmethod
    def _block_name(block: Block) -> str:
        return block.id.replace("_", " ").title()


def build_deck(metrics: dict[str, Any], narrative: dict[str, Any], language: str = "en") -> bytes:
    ctx = DeckContext(metrics, narrative, language)
    return DeckComposer(ctx).build()


def section_manifest(metrics: dict[str, Any], narrative: dict[str, Any], language: str = "en") -> list[dict[str, Any]]:
    """The planned section contract without rendering pixels (cheap, for tests)."""
    ctx = DeckContext(metrics, narrative, language)
    composer = DeckComposer(ctx)
    _, skipped, section_present = composer._plan()
    return composer._build_manifest(set(), section_present, skipped)
