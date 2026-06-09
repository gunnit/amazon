"""Dynamic block-registry engine for the Brand Analysis PPTX deck.

The deck is composed from independent blocks; each block declares its own
``is_available`` gate, so a section only renders when its data exists. Empty
placeholders and header-only tables can no longer reach a slide.
"""
from app.services.brand_analysis.deck.composer import DeckComposer, build_deck, section_manifest
from app.services.brand_analysis.deck.context import DeckContext

__all__ = ["DeckComposer", "DeckContext", "build_deck", "section_manifest"]
