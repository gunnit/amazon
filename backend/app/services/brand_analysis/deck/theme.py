"""Single source of truth for deck colours, type scale and layout geometry.

Replaces the ~40 inline RGB literals scattered across the old builder. Every
block reads its palette and sizes from here so the deck stays coherent.
"""
from __future__ import annotations

RGB = tuple[int, int, int]


class DeckTheme:
    # Palette -----------------------------------------------------------------
    BRAND_PRIMARY: RGB = (212, 39, 45)
    INK: RGB = (23, 23, 27)
    SUBTLE_INK: RGB = (74, 78, 84)
    MUTED: RGB = (110, 116, 124)
    HAIRLINE: RGB = (228, 230, 233)
    SURFACE: RGB = (248, 249, 250)
    CARD: RGB = (252, 252, 253)
    WHITE: RGB = (255, 255, 255)
    POSITIVE: RGB = (22, 163, 74)
    NEGATIVE: RGB = (212, 39, 45)
    NEUTRAL_BAR: RGB = (148, 156, 166)
    NAVY: RGB = (29, 41, 61)

    # Accent ramp for section dividers and chart categories (replaces the
    # 7-colour rainbow footer; used intentionally, not on every slide).
    ACCENTS: tuple[RGB, ...] = (
        (29, 78, 216),
        (234, 88, 12),
        (22, 163, 74),
        (147, 51, 234),
        (14, 165, 233),
        (110, 116, 124),
    )

    # Typography --------------------------------------------------------------
    FONT = "Nunito"
    TYPE = {
        "h1": 30,
        "h2": 22,
        "section": 26,
        "kpi_value": 17,
        "kpi_label": 9,
        "body": 11,
        "bullet": 10,
        "caption": 8,
        "table_header": 8,
        "table_cell": 8,
        "chip": 7,
    }

    # Layout (true 16:9, deck-grade) -----------------------------------------
    SLIDE_W = 13.333
    SLIDE_H = 7.5
    MARGIN = 0.7
    HEADER_H = 0.46
    FOOTER_Y = 7.18

    @classmethod
    def content_w(cls) -> float:
        return cls.SLIDE_W - 2 * cls.MARGIN

    @classmethod
    def accent(cls, index: int) -> RGB:
        return cls.ACCENTS[index % len(cls.ACCENTS)]

    @staticmethod
    def hex(color: RGB) -> str:
        return "#{:02x}{:02x}{:02x}".format(*color)
