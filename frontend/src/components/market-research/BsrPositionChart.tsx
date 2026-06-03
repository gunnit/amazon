import {
  ScatterChart,
  Scatter,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { CHART_PRIMARY } from '@/lib/chart-theme'
import { useTranslation } from '@/i18n'
import { formatEur, formatEurCompact, isUsablePrice } from '@/lib/market-research'
import type { MarketSearchResult } from '@/types'

interface BsrPositionChartProps {
  results: MarketSearchResult[]
  referenceAsin: string | null
}

interface DataPoint {
  price: number
  bsr: number
  asin: string
  title: string
  isReference: boolean
}

function CustomTooltip({
  active,
  payload,
  priceLabel,
}: {
  active?: boolean
  payload?: Array<{ payload: DataPoint }>
  priceLabel: string
}) {
  if (!active || !payload || payload.length === 0) return null

  const data = payload[0].payload
  return (
    <div className="rounded-lg border bg-popover px-3 py-2 text-popover-foreground shadow-md">
      <p className="text-xs font-mono mb-0.5">{data.asin}</p>
      <p className="text-xs text-muted-foreground truncate max-w-[200px]">{data.title}</p>
      <div className="flex gap-3 mt-1 text-xs">
        <span>{priceLabel}: <strong>{formatEur(data.price)}</strong></span>
        <span>BSR: <strong>{data.bsr.toLocaleString()}</strong></span>
      </div>
    </div>
  )
}

export default function BsrPositionChart({ results, referenceAsin }: BsrPositionChartProps) {
  const { t } = useTranslation()
  const priceLabel = t('marketResearch.price')

  const data: DataPoint[] = results
    .filter((r) => r.bsr != null && isUsablePrice(r.price, results))
    .map((r) => ({
      price: r.price!,
      bsr: r.bsr!,
      asin: r.asin,
      title: r.title || r.asin,
      isReference: r.asin === referenceAsin,
    }))

  if (data.length < 2) return null

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium">{t('marketTracker.bsrVsPrice')}</CardTitle>
      </CardHeader>
      <CardContent>
        <ResponsiveContainer width="100%" height={220}>
          <ScatterChart margin={{ top: 5, right: 10, left: -10, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" className="opacity-30" />
            <XAxis
              type="number"
              dataKey="price"
              name={priceLabel}
              tick={{ fontSize: 11 }}
              tickLine={false}
              axisLine={false}
              tickFormatter={(v: number) => formatEurCompact(v)}
              label={{ value: priceLabel, position: 'bottom', fontSize: 11, offset: -5 }}
            />
            <YAxis
              type="number"
              dataKey="bsr"
              name="BSR"
              tick={{ fontSize: 11 }}
              tickLine={false}
              axisLine={false}
              reversed
              tickFormatter={(v: number) => v >= 1000 ? `${(v / 1000).toFixed(0)}k` : v.toString()}
              label={{ value: 'BSR', angle: -90, position: 'insideLeft', fontSize: 11, offset: 20 }}
            />
            <Tooltip content={<CustomTooltip priceLabel={priceLabel} />} />
            <Scatter data={data}>
              {data.map((entry, idx) => (
                <Cell
                  key={idx}
                  fill={entry.isReference ? CHART_PRIMARY : 'hsl(var(--muted-foreground) / 0.5)'}
                  r={entry.isReference ? 8 : 5}
                  stroke={entry.isReference ? CHART_PRIMARY : 'transparent'}
                  strokeWidth={entry.isReference ? 2 : 0}
                />
              ))}
            </Scatter>
          </ScatterChart>
        </ResponsiveContainer>
        <div className="flex items-center justify-center gap-4 mt-2 text-[11px] text-muted-foreground">
          <div className="flex items-center gap-1.5">
            <div className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: CHART_PRIMARY }} />
            <span>{t('marketTracker.reference')}</span>
          </div>
          <div className="flex items-center gap-1.5">
            <div className="w-2 h-2 rounded-full bg-muted-foreground/50" />
            <span>{t('marketResearch.competitors')}</span>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
