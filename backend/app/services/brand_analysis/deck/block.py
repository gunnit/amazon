"""Block protocol and section taxonomy.

A block is a self-contained slide unit that decides for itself whether it has
enough data to render. The composer renders only available blocks, so empty
placeholders are structurally impossible.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Optional, Protocol, runtime_checkable


class Section(enum.Enum):
    FRONT = "front"
    PERFORMANCE = "performance"
    CATALOG = "catalog"
    CHANNEL = "channel"
    MARKET = "market"
    STRATEGY = "strategy"
    APPENDIX = "appendix"


SECTION_TITLES = {
    Section.PERFORMANCE: ("Performance", "Performance"),
    Section.CATALOG: ("Catalog & Content", "Catalogo e contenuti"),
    Section.CHANNEL: ("Channel & Risk", "Canale e rischio"),
    Section.MARKET: ("Market", "Mercato"),
    Section.STRATEGY: ("Strategy", "Strategia"),
}


@dataclass
class BlockResult:
    rendered: bool
    skipped_reason: Optional[str] = None


@runtime_checkable
class Block(Protocol):
    id: str
    section: Section
    title_key: str
    always: bool

    def is_available(self, ctx) -> bool: ...

    def skip_reason(self, ctx) -> str: ...

    def render(self, ctx, deck, page: int) -> BlockResult: ...


class BaseBlock:
    """Shared block behaviour. Subclasses set ``id``/``section`` and override
    ``is_available``/``render``; ``required_keys`` documents the contract."""

    id: str = ""
    section: Section = Section.FRONT
    title_key: str = ""
    always: bool = False
    required_keys: tuple[str, ...] = ()

    def is_available(self, ctx) -> bool:  # pragma: no cover - overridden
        return self.always

    def skip_reason(self, ctx) -> str:
        return ctx.t("skip_no_data")

    def render(self, ctx, deck, page: int) -> BlockResult:  # pragma: no cover
        raise NotImplementedError
