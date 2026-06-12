"""Per-deck context shared by every block.

Wraps the metrics + narrative dicts, the language, and the i18n lookup. Blocks
read everything they need from here so they stay stateless and testable.
"""
from __future__ import annotations

from typing import Any

# Extra deck-only strings layered on top of the service's PPTX_STATIC_STRINGS.
_DECK_STRINGS = {
    "en": {
        "exec_summary_title": "Executive Summary",
        "exec_summary_subtitle": "The whole story on one slide",
        "agenda_title": "Agenda",
        "agenda_subtitle": "Sections covered in this analysis",
        "methodology_title": "Methodology & Data Provenance",
        "methodology_subtitle": "What is measured, what is estimated, and what was skipped",
        "method_what_we_show": "What this deck shows",
        "method_skipped": "Sections not shown (insufficient source data)",
        "method_provenance": "Metric provenance",
        "method_quality": "Quality",
        "method_metric": "Metric",
        "skip_no_data": "Source data did not support this section.",
        "so_what": "So what",
        "recommendation": "Recommendation",
        "of_revenue": "of revenue",
        "latent_value": "latent value in inactive catalog",
        "no_sections": "No data-backed sections were available for this brand.",
        "insight_revenue_moved": "Revenue moved {a} → {b} ({pct}).",
        "insight_inactive_asins": "{n} of {total} ASINs are inactive ({pct}) — latent value in inactive catalog.",
        "insight_top_share": "Top {n} ASINs drive {share} of revenue.",
        "insight_content_images": "{n} of {total} ASINs carry fewer than 5 images — prioritize image upgrades on the top-revenue ASINs.",
        "insight_content_generic": "Listing content is broadly complete — keep titles, bullets and images aligned with category best practice.",
        "frag_gap_prefix": "Key gaps:",
        "frag_inactive": "{pct} of the catalog is inactive",
        "frag_declining": "{pct} of active ASINs are declining YoY",
    },
    "it": {
        "exec_summary_title": "Sintesi esecutiva",
        "exec_summary_subtitle": "L'intera storia in una slide",
        "agenda_title": "Agenda",
        "agenda_subtitle": "Sezioni trattate in questa analisi",
        "methodology_title": "Metodologia e provenienza dei dati",
        "methodology_subtitle": "Cosa è misurato, cosa è stimato e cosa è stato omesso",
        "method_what_we_show": "Cosa mostra questo deck",
        "method_skipped": "Sezioni non mostrate (dati di origine insufficienti)",
        "method_provenance": "Provenienza delle metriche",
        "method_quality": "Qualità",
        "method_metric": "Metrica",
        "skip_no_data": "I dati di origine non supportavano questa sezione.",
        "so_what": "Implicazione",
        "recommendation": "Raccomandazione",
        "of_revenue": "del fatturato",
        "latent_value": "valore latente nel catalogo inattivo",
        "no_sections": "Nessuna sezione supportata dai dati era disponibile per questa marca.",
        "insight_revenue_moved": "Il fatturato è passato da {a} a {b} ({pct}).",
        "insight_inactive_asins": "{n} ASIN su {total} sono inattivi ({pct}) — valore latente nel catalogo inattivo.",
        "insight_top_share": "I top {n} ASIN generano il {share} del fatturato.",
        "insight_content_images": "{n} ASIN su {total} hanno meno di 5 immagini — dare priorità all'upgrade immagini sugli ASIN a maggior fatturato.",
        "insight_content_generic": "I contenuti delle schede sono nel complesso completi — mantenere titoli, bullet e immagini allineati alle best practice di categoria.",
        "frag_gap_prefix": "Criticità principali:",
        "frag_inactive": "il {pct} del catalogo è inattivo",
        "frag_declining": "il {pct} degli ASIN attivi è in calo YoY",
    },
}


class DeckContext:
    def __init__(self, metrics: dict[str, Any], narrative: dict[str, Any], language: str = "en") -> None:
        from app.services.brand_analysis_service import PPTX_STATIC_STRINGS
        from app.services.brand_analysis.deck.format import Formatter

        self.metrics = metrics or {}
        self.narrative = narrative or {}
        self.language = "it" if str(language or "").lower().startswith("it") else "en"
        self.fmt = Formatter(self.language)
        self.brand = str(self.metrics.get("brand_name") or "Brand").upper()
        self._base_strings = PPTX_STATIC_STRINGS
        self.rendered_block_ids: list[str] = []
        self.skipped_blocks: list[tuple[str, str]] = []
        self.section_titles: dict[str, str] = {}

    def t(self, key: str) -> str:
        lang = self.language
        for table in (_DECK_STRINGS.get(lang, {}), self._base_strings.get(lang, {})):
            if key in table:
                return table[key]
        for table in (_DECK_STRINGS.get("en", {}), self._base_strings.get("en", {})):
            if key in table:
                return table[key]
        return key

    def m(self, key: str, default: Any = None) -> Any:
        return self.metrics.get(key, default)

    def block_insight(self, block_id: str) -> dict[str, Any]:
        """Structured insight for a block, if the narrative carries one.

        Tolerates the current flat narrative shape (no per-block dict) by
        returning an empty mapping, so blocks fall back to metric-grounded text.
        """
        blocks = self.narrative.get("blocks")
        if isinstance(blocks, dict) and isinstance(blocks.get(block_id), dict):
            return blocks[block_id]
        return {}

    def quality(self, metric_key: str) -> str:
        registry = self.metrics.get("metric_source_registry") or {}
        return str((registry.get(metric_key) or {}).get("quality") or "").upper()

    def quality_chip(self, metric_key: str) -> str:
        """Chip shown next to a KPI label on client tiles. Exact values are the
        norm and stay unflagged (the reference deck carries no chips); only
        estimated/partial provenance is surfaced. Full detail stays in the
        methodology appendix."""
        quality = self.quality(metric_key)
        return "" if quality in ("", "EXACT") else quality

    def priority_actions(self) -> list[str]:
        from app.services.brand_analysis_service import build_priority_actions

        return build_priority_actions(self.metrics, self.language)
