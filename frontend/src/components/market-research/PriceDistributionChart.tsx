import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { useTranslation } from '@/i18n'
import type { MarketSearchResult } from '@/types'

interface PriceDistributionChartProps {
  results: MarketSearchResult[]
}

function buildBuckets(prices: number[]): { label: string; count: number; midpoint: number }[] {
  if (prices.length === 0) return []

  const min = Math.min(...prices)
  const max = Math.max(...prices)

  if (min === max) {
    return [{ label: `$${min.toFixed(0)}`, count: prices.length, midpoint: min }]
  }

  const range = max - min
  const bucketCount = Math.min(Math.max(Math.ceil(prices.length / 2), 3), 8)
  const bucketSize = range / bucketCount

  const buckets: { label: string; count: number; midpoint: number }[] = []
  for (let i = 0; i < bucketCount; i++) {
    const lo = min + i * bucketSize
    const hi = min + (i + 1) * bucketSize
    const count = prices.filter((p) =>
      i === bucketCount - 1 ? p >= lo && p <= hi : p >= lo && p < hi
    ).length
    buckets.push({
      label: `$${lo.toFixed(0)}-${hi.toFixed(0)}`,
      count,
      midpoint: (lo + hi) / 2,
    })
  }

  return buckets
}

export default function PriceDistributionChart({ results }: PriceDistributionChartProps) {
  const { t } = useTranslation()
  const prices = results.map((r) => r.price).filter((p): p is number => p != null)

  if (prices.length < 2) return null

  const data = buildBuckets(prices)
  const avgPrice = prices.reduce((a, b) => a + b, 0) / prices.length

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium">{t('marketTracker.priceDistribution')}</CardTitle>
      </CardHeader>
      <CardContent>
        <ResponsiveContainer width="100%" height={220}>
          <BarChart data={data} margin={{ top: 5, right: 10, left: -10, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" className="opacity-30" />
            <XAxis
              dataKey="label"
              tick={{ fontSize: 11 }}
              tickLine={false}
              axisLine={false}
            />
            <YAxis
              allowDecimals={false}
              tick={{ fontSize: 11 }}
              tickLine={false}
              axisLine={false}
              width={30}
            />
            <Tooltip
              contentStyle={{
                fontSize: 12,
                borderRadius: 8,
                border: '1px solid hsl(var(--border))',
                background: 'hsl(var(--popover))',
                color: 'hsl(var(--popover-foreground))',
              }}
              formatter={(value: number) => [`${value} ${t('marketTracker.products')}`, '']}
            />
            <Bar dataKey="count" radius={[4, 4, 0, 0]} maxBarSize={40}>
              {data.map((entry, idx) => (
                <Cell
                  key={idx}
                  fill={
                    entry.midpoint <= avgPrice
                      ? 'hsl(var(--primary))'
                      : 'hsl(var(--primary) / 0.5)'
                  }
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  )
}
