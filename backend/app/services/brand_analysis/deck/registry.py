"""Ordered block registry. The composer walks this list in order."""
from __future__ import annotations

from app.services.brand_analysis.deck.block import Block, Section
from app.services.brand_analysis.deck.blocks.catalog import (
    ContentAuditBlock,
    ReviewImageBlock,
    SubcategoryBlock,
)
from app.services.brand_analysis.deck.blocks.channel import (
    ChannelGapBlock,
    ConcentrationRiskBlock,
    OperationalGapBlock,
)
from app.services.brand_analysis.deck.blocks.front_matter import (
    AgendaBlock,
    CoverBlock,
    ExecSummaryBlock,
)
from app.services.brand_analysis.deck.blocks.market import MarketShareBlock, SearchVisibilityBlock
from app.services.brand_analysis.deck.blocks.methodology import MethodologyAppendixBlock
from app.services.brand_analysis.deck.blocks.performance import (
    ActiveInactiveBlock,
    CatalogHealthBlock,
    RevenueYoYBlock,
    TopPerformersBlock,
)
from app.services.brand_analysis.deck.blocks.strategy import (
    ConclusionsBlock,
    PriorityActionsBlock,
    RoadmapBlock,
)

# Order in which sections introduce their dividers and number their agenda entries.
SECTION_ORDER = (
    Section.PERFORMANCE,
    Section.CATALOG,
    Section.CHANNEL,
    Section.MARKET,
    Section.STRATEGY,
)


def default_blocks() -> list[Block]:
    return [
        CoverBlock(),
        ExecSummaryBlock(),
        AgendaBlock(),
        RevenueYoYBlock(),
        CatalogHealthBlock(),
        ActiveInactiveBlock(),
        TopPerformersBlock(),
        ContentAuditBlock(),
        ReviewImageBlock(),
        SubcategoryBlock(),
        OperationalGapBlock(),
        ChannelGapBlock(),
        ConcentrationRiskBlock(),
        MarketShareBlock(),
        SearchVisibilityBlock(),
        PriorityActionsBlock(),
        RoadmapBlock(),
        ConclusionsBlock(),
        MethodologyAppendixBlock(),
    ]
