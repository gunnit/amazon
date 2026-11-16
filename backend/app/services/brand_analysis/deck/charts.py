"""Brand-themed matplotlib charts rendered to in-memory PNG.

Uses the non-interactive Agg backend (no display needed on the worker). Each
helper returns transparent PNG bytes that a block embeds with
``DeckBuilder.picture``. Pure rectangles-as-bars are gone.
"""
from __future__ import annotations

import io

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402

from app.services.brand_analysis.deck.theme import RGB, DeckTheme  # noqa: E402

_DPI = 220
plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Nunito", "DejaVu Sans", "Arial"],
    "svg.fonttype": "none",
    "axes.edgecolor": DeckTheme.hex(DeckTheme.HAIRLINE),
})


def _hex(color: RGB) -> str:
    return DeckTheme.hex(color)


def _render(fig) -> bytes:
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", transparent=True, bbox_inches="tight",
                pad_inches=0.04, dpi=_DPI)
    plt.close(fig)
    return buffer.getvalue()


def donut(segments: list[tuple[str, float, RGB]], *, center: str = "", w_in=3.4, h_in=3.0) -> bytes:
    """Active/inactive or any 2-3 way split as a ring with a centre label."""
    labels = [s[0] for s in segments]
    values = [max(float(s[1]), 0.0) for s in segments]
    colors = [_hex(s[2]) for s in segments]
    if sum(values) <= 0:
        values = [1.0 for _ in segments]
    fig, ax = plt.subplots(figsize=(w_in, h_in))
    wedges, _ = ax.pie(values, colors=colors, startangle=90, counterclock=False,
                       wedgeprops=dict(width=0.34, edgecolor="white", linewidth=2))
    if center:
        ax.text(0, 0, center, ha="center", va="center",
                fontsize=18, fontweight="bold", color=_hex(DeckTheme.INK))
    ax.legend(wedges, labels, loc="center", bbox_to_anchor=(0.5, -0.06),
              ncol=len(labels), frameon=False, fontsize=9,
              handlelength=0.9, columnspacing=1.1)
    ax.set_aspect("equal")
    return _render(fig)


def hbar(labels: list[str], values: list[float], *, value_fmt=None,
         color: RGB = DeckTheme.BRAND_PRIMARY, colors: list[RGB] | None = None,
         sort: bool = True, w_in=7.2, h_in=3.2) -> bytes:
    """Horizontal bars, largest on top, value annotated at the bar end.

    ``colors`` (aligned with ``labels``) colours each bar, e.g. by Buy Box owner.
    ``sort=False`` keeps the given order top to bottom (an "Other" bar stays last)."""
    if sort:
        order = sorted(range(len(values)), key=lambda i: values[i])
    else:
        order = list(reversed(range(len(values))))
    bar_colors = [_hex(colors[i]) for i in order] if colors else _hex(color)
    labels = [labels[i] for i in order]
    values = [float(values[i] or 0) for i in order]
    fig, ax = plt.subplots(figsize=(w_in, h_in))
    bars = ax.barh(range(len(values)), values, color=bar_colors, height=0.62)
    ax.set_yticks(range(len(values)))
    ax.set_yticklabels(labels, fontsize=9, color=_hex(DeckTheme.INK))
    ax.set_xticks([])
    for spine in ("top", "right", "bottom"):
        ax.spines[spine].set_visible(False)
    ax.spines["left"].set_color(_hex(DeckTheme.HAIRLINE))
    span = max(values) or 1
    for bar, value in zip(bars, values):
        ax.text(bar.get_width() + span * 0.015, bar.get_y() + bar.get_height() / 2,
                value_fmt(value) if value_fmt else f"{value:,.0f}",
                va="center", ha="left", fontsize=8.5, color=_hex(DeckTheme.SUBTLE_INK))
    ax.set_xlim(0, span * 1.18)
    return _render(fig)


def waterfall(start_label: str, start: float, end_label: str, end: float, *,
              value_fmt=None, w_in=7.0, h_in=3.2) -> bytes:
    """Two anchored bars plus a delta bar — a revenue bridge, not faux rects."""
    delta = end - start
    up = delta >= 0
    delta_color = DeckTheme.POSITIVE if up else DeckTheme.NEGATIVE
    fig, ax = plt.subplots(figsize=(w_in, h_in))
    ax.bar(0, start, color=_hex(DeckTheme.NEUTRAL_BAR), width=0.55)
    base = min(start, end)
    ax.bar(1, abs(delta), bottom=base, color=_hex(delta_color), width=0.55)
    ax.bar(2, end, color=_hex(DeckTheme.BRAND_PRIMARY), width=0.55)
    ax.set_xticks([0, 1, 2])
    ax.set_xticklabels([start_label, "Δ", end_label], fontsize=9, color=_hex(DeckTheme.INK))
    ax.set_yticks([])
    for spine in ("top", "right", "left"):
        ax.spines[spine].set_visible(False)
    ax.spines["bottom"].set_color(_hex(DeckTheme.HAIRLINE))
    fmt = value_fmt or (lambda v: f"{v:,.0f}")
    headroom = max(start, end) or 1
    ax.text(0, start + headroom * 0.02, fmt(start), ha="center", va="bottom",
            fontsize=9, fontweight="bold", color=_hex(DeckTheme.INK))
    ax.text(2, end + headroom * 0.02, fmt(end), ha="center", va="bottom",
            fontsize=9, fontweight="bold", color=_hex(DeckTheme.BRAND_PRIMARY))
    sign = "+" if up else "−"
    ax.text(1, base + abs(delta) + headroom * 0.02, f"{sign}{fmt(abs(delta))}",
            ha="center", va="bottom", fontsize=9, fontweight="bold", color=_hex(delta_color))
    ax.set_ylim(0, headroom * 1.2)
    return _render(fig)


def columns(labels: list[str], values: list[float], *, value_fmt=None,
            colors: list[RGB] | None = None, color: RGB = DeckTheme.BRAND_PRIMARY,
            w_in=7.2, h_in=3.4) -> bytes:
    """Vertical bars in the given order (months, formats), value on top of each bar."""
    values = [float(v or 0) for v in values]
    bar_colors = [_hex(c) for c in colors] if colors else _hex(color)
    fig, ax = plt.subplots(figsize=(w_in, h_in))
    bars = ax.bar(range(len(values)), values, color=bar_colors, width=0.62)
    ax.set_xticks(range(len(values)))
    ax.set_xticklabels(labels, fontsize=9, color=_hex(DeckTheme.INK))
    ax.set_yticks([])
    for spine in ("top", "right", "left"):
        ax.spines[spine].set_visible(False)
    ax.spines["bottom"].set_color(_hex(DeckTheme.HAIRLINE))
    span = max(values) if values and max(values) > 0 else 1
    for bar, value in zip(bars, values):
        if value <= 0:
            continue
        ax.text(bar.get_x() + bar.get_width() / 2, value + span * 0.02,
                value_fmt(value) if value_fmt else f"{value:,.0f}",
                ha="center", va="bottom", fontsize=8.5, color=_hex(DeckTheme.SUBTLE_INK))
    ax.set_ylim(0, span * 1.18)
    return _render(fig)


def pareto(curve: list[float], *, mark_at: int | None = None, mark_label: str = "",
           x_label: str = "", w_in=7.2, h_in=3.4) -> bytes:
    """Cumulative share of revenue by ASIN rank, with the 80% line and its crossing marked."""
    xs = list(range(1, len(curve) + 1))
    fig, ax = plt.subplots(figsize=(w_in, h_in))
    ax.fill_between(xs, curve, color=_hex(DeckTheme.BRAND_PRIMARY), alpha=0.12, linewidth=0)
    ax.plot(xs, curve, color=_hex(DeckTheme.BRAND_PRIMARY), linewidth=2)
    ax.axhline(80, color=_hex(DeckTheme.MUTED), linewidth=1, linestyle="--")
    ax.text(xs[-1] if xs else 1, 81.5, "80%", ha="right", va="bottom", fontsize=8.5,
            color=_hex(DeckTheme.SUBTLE_INK))
    if mark_at:
        ax.axvline(mark_at, color=_hex(DeckTheme.INK), linewidth=1)
        ax.text(mark_at + max(len(xs) * 0.01, 0.3), 8, mark_label, ha="left", va="bottom",
                fontsize=9, fontweight="bold", color=_hex(DeckTheme.INK))
    ax.set_ylim(0, 105)
    ax.set_xlim(1, max(xs[-1] if xs else 1, 2))
    ax.set_yticks([0, 20, 40, 60, 80, 100])
    ax.set_yticklabels([f"{v}%" for v in (0, 20, 40, 60, 80, 100)], fontsize=8.5,
                       color=_hex(DeckTheme.SUBTLE_INK))
    ax.tick_params(axis="x", labelsize=8.5, colors=_hex(DeckTheme.SUBTLE_INK))
    if x_label:
        ax.set_xlabel(x_label, fontsize=9, color=_hex(DeckTheme.SUBTLE_INK))
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    return _render(fig)
