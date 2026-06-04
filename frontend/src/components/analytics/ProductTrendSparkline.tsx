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

  if (!data.length) {
    return <div className="h-full w-full rounded bg-muted/40" />
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
