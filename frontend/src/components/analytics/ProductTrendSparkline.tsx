import { Line, LineChart, ResponsiveContainer, Tooltip } from 'recharts'
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
  if (!data.length) {
    return <div className="h-full w-full rounded bg-muted/40" />
  }

  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data}>
        {showTooltip ? (
          <Tooltip
            formatter={(value: number) => [
              metric === 'revenue' ? formatCurrency(Number(value)) : formatNumber(Number(value)),
              metric === 'revenue' ? 'Revenue' : 'Units',
            ]}
            labelFormatter={(value) => new Date(`${value}T00:00:00`).toLocaleDateString()}
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
