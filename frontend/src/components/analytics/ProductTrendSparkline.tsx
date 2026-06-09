import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis } from 'recharts'
import { useTranslation } from '@/i18n'
import { formatCurrency, formatNumber } from '@/lib/utils'
import { CHART_NEGATIVE, CHART_NEUTRAL, CHART_POSITIVE } from '@/lib/chart-theme'
import type { ProductTrendClass, ProductTrendTimeseriesPoint } from '@/types'

const strokeByClass: Record<ProductTrendClass, string> = {
  rising_fast: CHART_POSITIVE,
  rising: '#6ee7b7',
  stable: CHART_NEUTRAL,
  declining: '#fbbf24',
  declining_fast: CHART_NEGATIVE,
}

// A trend line needs at least two points to draw a segment. With a single point
// Recharts has nothing to connect and falls back to rendering a lone floating
// dot, which reads as a broken chart rather than a trend. Products that only
// sold on one day inside the sparkline window hit this case, so below the
// threshold we show a muted placeholder instead of the misleading dot.
const MIN_SPARKLINE_POINTS = 2

// Trend points are ISO dates ('YYYY-MM-DD' daily, 'YYYY-MM-01' monthly). Vendor
// data only fills the first of the month, so format both safely and skip the
// rest as an empty label rather than rendering "Invalid Date". The locale is
// derived from the active UI language so the tooltip matches the Italian axis.
function formatTrendDate(value: unknown, language: 'en' | 'it'): string {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}/.test(value)) {
    return ''
  }

  const parsed = new Date(`${value.slice(0, 10)}T00:00:00`)
  if (Number.isNaN(parsed.getTime())) {
    return ''
  }

  const locale = language === 'it' ? 'it-IT' : 'en-US'
  const isMonthly = value.slice(8, 10) === '01'
  return parsed.toLocaleDateString(locale, {
    month: 'short',
    ...(isMonthly ? { year: 'numeric' } : { day: 'numeric' }),
  })
}

export default function ProductTrendSparkline({
  data,
  trendClass,
  metric = 'revenue',
  height = 44,
  showTooltip = false,
}: {
  data: ProductTrendTimeseriesPoint[]
  trendClass: ProductTrendClass
  metric?: 'revenue' | 'units'
  height?: number
  showTooltip?: boolean
}) {
  const { t, language } = useTranslation()

  if (data.length < MIN_SPARKLINE_POINTS) {
    return (
      <div
        className="flex w-full items-center justify-center rounded bg-muted/30"
        style={{ height }}
      >
        <span className="px-2 text-center text-[10px] font-medium uppercase tracking-wide text-muted-foreground/70">
          {t('analytics.sparkline.insufficient')}
        </span>
      </div>
    )
  }

  const metricLabel =
    metric === 'revenue' ? t('analytics.sparkline.revenue') : t('analytics.sparkline.units')

  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data}>
        <XAxis dataKey="date" hide />
        {showTooltip ? (
          <Tooltip
            formatter={(value: number) => [
              metric === 'revenue' ? formatCurrency(Number(value)) : formatNumber(Number(value)),
              metricLabel,
            ]}
            labelFormatter={(value) => formatTrendDate(value, language)}
          />
        ) : null}
        <Line
          type="monotone"
          dataKey={metric}
          stroke={strokeByClass[trendClass]}
          strokeWidth={2}
          dot={false}
          isAnimationActive={false}
        />
      </LineChart>
    </ResponsiveContainer>
  )
}
