// Central chart theming. Every Recharts color lives here so the data-viz
// palette stays cohesive across the app. Tuned for the dark dashboard: a
// refined indigo lead instead of the old neon blue, a categorical set kept at
// the same luminance so series read as a family rather than a rainbow, and
// gradient defs that give bars and areas depth instead of flat fills.

export const CHART_PRIMARY = '#818cf8'
export const CHART_PRIMARY_BRIGHT = '#a5b4fc'
export const CHART_PRIMARY_DEEP = '#6366f1'

// Categorical palette (pie segments, multi-series charts).
export const CHART_SERIES = [
  '#818cf8', // indigo
  '#2dd4bf', // teal
  '#fbbf24', // amber
  '#f472b6', // pink
  '#38bdf8', // sky
  '#a78bfa', // violet
]

// Semantic accents.
export const CHART_POSITIVE = '#34d399' // emerald
export const CHART_NEGATIVE = '#fb7185' // rose
export const CHART_NEUTRAL = '#94a3b8' // slate

// Gradient fills — resolve against the defs mounted once by <ChartGradients/>.
export const BAR_H_FILL = 'url(#chart-bar-h)' // horizontal bars (deep → bright)
export const BAR_V_FILL = 'url(#chart-bar-v)' // vertical bars (bright → deep)
export const AREA_FILL = 'url(#chart-area)' // area fill (solid → transparent)

// Shared gradient definitions, mounted once near the app root. Recharts drops
// child components it doesn't recognize (it only keeps raw SVG-tag children),
// so defining these inside a chart via a wrapper leaves the url(#…) fills
// pointing at nothing — invisible bars. SVG paint references resolve by id
// across the whole document, so a single offscreen <defs> serves every chart.
export function ChartGradients() {
  return (
    <svg
      aria-hidden="true"
      focusable="false"
      style={{ position: 'absolute', width: 0, height: 0, overflow: 'hidden' }}
    >
      <defs>
        <linearGradient id="chart-bar-h" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor={CHART_PRIMARY_DEEP} />
          <stop offset="100%" stopColor={CHART_PRIMARY_BRIGHT} />
        </linearGradient>
        <linearGradient id="chart-bar-v" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={CHART_PRIMARY_BRIGHT} />
          <stop offset="100%" stopColor={CHART_PRIMARY_DEEP} />
        </linearGradient>
        <linearGradient id="chart-area" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={CHART_PRIMARY} stopOpacity={0.35} />
          <stop offset="95%" stopColor={CHART_PRIMARY} stopOpacity={0.02} />
        </linearGradient>
      </defs>
    </svg>
  )
}
