import { TrendingDown, TrendingUp, Minus } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { useTranslation } from '@/i18n'
import type { ProductSnapshot, CompetitorSnapshot } from '@/types'

interface MarketPositionSummaryProps {
  product: ProductSnapshot
  competitors: CompetitorSnapshot[]
}

interface MetricSummary {
  label: string
  value: string
  tone: 'good' | 'bad' | 'neutral'
  detail: string
}

function average(values: Array<number | null | undefined>): number | null {
  const present = values.filter((value): value is number => value != null)
  if (present.length === 0) return null
  return present.reduce((sum, value) => sum + value, 0) / present.length
}

function describeMetric(
  current: number | null | undefined,
  baseline: number | null,
  lowerIsBetter: boolean,
  t: (key: string) => string,
): Pick<MetricSummary, 'tone' | 'detail'> {
  if (current == null || baseline == null || baseline === 0) {
    return { tone: 'neutral', detail: t('marketResearch.notEnoughData') }
  }

  const pct = ((current - baseline) / baseline) * 100
  if (Math.abs(pct) < 3) {
    return { tone: 'neutral', detail: t('marketResearch.closeToAverage') }
  }

  const isGood = lowerIsBetter ? pct < 0 : pct > 0
  return {
    tone: isGood ? 'good' : 'bad',
    detail: `${Math.abs(Math.round(pct))}% ${
      pct > 0
        ? t('marketResearch.aboveMarketAverage')
        : t('marketResearch.belowMarketAverage')
    }`,
  }
}

function metricClass(tone: MetricSummary['tone']): string {
  if (tone === 'good') return 'text-emerald-600 dark:text-emerald-400'
  if (tone === 'bad') return 'text-red-600 dark:text-red-400'
  return 'text-muted-foreground'
}

function MetricIcon({ tone }: { tone: MetricSummary['tone'] }) {
  if (tone === 'good') return <TrendingUp className="h-4 w-4" />
  if (tone === 'bad') return <TrendingDown className="h-4 w-4" />
  return <Minus className="h-4 w-4" />
}

export default function MarketPositionSummary({
  product,
  competitors,
}: MarketPositionSummaryProps) {
  const { t } = useTranslation()

  const avgPrice = average(competitors.map((item) => item.price))
  const avgBsr = average(competitors.map((item) => item.bsr))
  const avgReviews = average(competitors.map((item) => item.review_count))
  const avgRating = average(competitors.map((item) => item.rating))

  const metrics: MetricSummary[] = [
    {
      label: t('marketResearch.price'),
      value: product.price != null ? `$${product.price.toFixed(2)}` : '—',
      ...describeMetric(product.price, avgPrice, true, t),
    },
    {
      label: t('marketResearch.bsr'),
      value: product.bsr != null ? product.bsr.toLocaleString() : '—',
      ...describeMetric(product.bsr, avgBsr, true, t),
    },
    {
      label: t('marketResearch.reviews'),
      value: product.review_count != null ? product.review_count.toLocaleString() : '—',
      ...describeMetric(product.review_count, avgReviews, false, t),
    },
    {
      label: t('marketResearch.rating'),
      value: product.rating != null ? product.rating.toFixed(1) : '—',
      ...describeMetric(product.rating, avgRating, false, t),
    },
  ]

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('marketResearch.marketPosition')}</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid gap-3 sm:grid-cols-2">
          {metrics.map((metric) => (
            <div key={metric.label} className="rounded-lg border p-3">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <p className="text-xs font-medium text-muted-foreground">{metric.label}</p>
                  <p className="text-lg font-semibold">{metric.value}</p>
                </div>
                <div className={metricClass(metric.tone)}>
                  <MetricIcon tone={metric.tone} />
                </div>
              </div>
              <p className={`mt-2 text-xs ${metricClass(metric.tone)}`}>
                {metric.detail}
              </p>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}
