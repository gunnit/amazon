"""Single source of truth for deck colours, type scale and layout geometry.

Palette, type scale and chrome follow the agency reference deck ("ZWILLING on
Amazon"): white slides with a small red brand bar top-left, big solid-colour
KPI tiles, a seven-segment colour strip along the bottom edge and Nunito
throughout. Sizes are the reference's, scaled from its 10in canvas to ours
(13.333in, x1.333).
"""
from __future__ import annotations

RGB = tuple[int, int, int]


class DeckTheme:
    # Palette (reference deck hex values) --------------------------------------
    BRAND_PRIMARY: RGB = (204, 1, 0)        # CC0100
    INK: RGB = (26, 26, 26)                 # 1A1A1A
    SUBTLE_INK: RGB = (85, 85, 85)          # 555555
    MUTED: RGB = (136, 136, 136)            # 888888
    HAIRLINE: RGB = (224, 224, 224)         # E0E0E0
    SURFACE: RGB = (245, 245, 245)          # F5F5F5
    CARD: RGB = (245, 245, 245)
    WHITE: RGB = (255, 255, 255)
    POSITIVE: RGB = (58, 125, 68)           # 3A7D44
    NEGATIVE: RGB = (204, 1, 0)
    NEUTRAL_BAR: RGB = (148, 156, 166)
    NAVY: RGB = (47, 66, 80)                # 2F4250 (reference slate)
    TABLE_HEADER: RGB = (68, 79, 73)        # 444F49
    STEEL_BLUE: RGB = (36, 113, 163)        # 2471A3
    TEAL: RGB = (66, 179, 175)              # 42B3AF
    ORANGE: RGB = (237, 125, 49)            # ED7D31
    GOLD: RGB = (214, 158, 21)              # D69E15

    # Accent ramp (reference order: roadmap circles are red/orange/green).
    ACCENTS: tuple[RGB, ...] = (
        (204, 1, 0),
        (237, 125, 49),
        (58, 125, 68),
        (33, 100, 126),
        (66, 179, 175),
        (47, 66, 80),
    )

    # Solid fills cycled across KPI tiles, as on the reference KPI grids.
    KPI_FILLS: tuple[RGB, ...] = (
        (204, 1, 0),
        (245, 245, 245),
        (36, 113, 163),
        (66, 179, 175),
        (58, 125, 68),
        (237, 125, 49),
    )

    # Bottom edge strip: seven segments, widths as fractions of slide width.
    FOOTER_STRIP: tuple[tuple[RGB, float], ...] = (
        ((204, 1, 0), 0.15),
        ((129, 113, 114), 0.10),
        ((66, 179, 175), 0.15),
        ((33, 100, 126), 0.15),
        ((47, 66, 80), 0.15),
        ((68, 79, 73), 0.15),
        ((214, 158, 21), 0.15),
    )

    # Typography (reference sizes x1.333) --------------------------------------
    FONT = "Nunito"
    TYPE = {
        "h1": 36,            # slide title (ref 28)
        "h2": 22,
        "subtitle": 14,      # ref 11
        "eyebrow": 11,       # ref 8.5
        "cover_title": 60,
        "cover_subtitle": 18,
        "kpi_value": 40,     # ref 36 on a wider tile; 40 fits our grid
        "kpi_value_small": 26,
        "kpi_label": 12,     # ref 10
        "body": 12,          # ref 9
        "bullet": 11,
        "caption": 9,
        "table_header": 11,
        "table_cell": 11,
        "chip": 7,
    }

    # Layout (true 16:9, deck-grade). Margin matches the reference deck's
    # 0.27in on a 10in canvas, scaled x1.333.
    SLIDE_W = 13.333
    SLIDE_H = 7.5
    MARGIN = 0.36
    HEADER_H = 0.46
    FOOTER_Y = 7.18
    STRIP_H = 0.12

    @classmethod
    def content_w(cls) -> float:
        return cls.SLIDE_W - 2 * cls.MARGIN

    @classmethod
    def accent(cls, index: int) -> RGB:
        return cls.ACCENTS[index % len(cls.ACCENTS)]

    @classmethod
    def kpi_fill(cls, index: int) -> RGB:
        return cls.KPI_FILLS[index % len(cls.KPI_FILLS)]

    @staticmethod
    def hex(color: RGB) -> str:
        return "#{:02x}{:02x}{:02x}".format(*color)
