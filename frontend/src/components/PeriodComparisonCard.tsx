import { Minus, TrendingDown, TrendingUp } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { formatCurrency, formatDate, formatNumber, formatPercent } from '@/lib/utils'
import { useTranslation } from '@/i18n'
import type { ComparisonMetric, ComparisonResponse } from '@/types'

function formatMetricValue(metric: ComparisonMetric, value: number | null) {
  if (value == null) {
    return '—'
  }

  if (metric.format === 'currency') {
    return formatCurrency(value)
  }

  if (metric.format === 'percent') {
    return `${value.toFixed(1)}%`
  }

  if (metric.format === 'ratio') {
    return `${value.toFixed(2)}x`
  }

  return formatNumber(Math.round(value))
}

function MetricTrend({
  trend,
  changePercent,
}: {
  trend: ComparisonMetric['trend']
  changePercent: number | null
}) {
  if (changePercent == null) {
    return null
  }

  if (trend === 'up') {
    return (
      <Badge variant="outline" className="border-emerald-200 bg-emerald-50 text-emerald-700">
        <TrendingUp className="mr-1 h-3 w-3" />
        {formatPercent(changePercent)}
      </Badge>
    )
  }

  if (trend === 'down') {
    return (
      <Badge variant="outline" className="border-rose-200 bg-rose-50 text-rose-700">
        <TrendingDown className="mr-1 h-3 w-3" />
        {formatPercent(changePercent)}
      </Badge>
    )
  }

  return (
    <Badge variant="outline" className="text-muted-foreground">
      <Minus className="mr-1 h-3 w-3" />
      {formatPercent(changePercent)}
    </Badge>
  )
}

export function PeriodComparisonCard({
  comparison,
  title,
  description,
}: {
  comparison?: ComparisonResponse
  title: string
  description: string
}) {
  const { t } = useTranslation()

  return (
    <Card>
      <CardHeader className="gap-4">
        <div className="space-y-1">
          <CardTitle>{title}</CardTitle>
          <CardDescription>{description}</CardDescription>
        </div>

        {comparison ? (
          <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
            <Badge variant="outline" className="font-normal">
              {t('comparison.period1Label')}: {formatDate(comparison.period_1.start)} - {formatDate(comparison.period_1.end)}
            </Badge>
            <Badge variant="outline" className="font-normal">
              {t('comparison.period2Label')}: {formatDate(comparison.period_2.start)} - {formatDate(comparison.period_2.end)}
            </Badge>
          </div>
        ) : null}
      </CardHeader>

      <CardContent>
        {comparison ? (
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {comparison.metrics.map((metric) => {
              const unavailableReason = metric.unavailable_reason
                ? t(`comparison.unavailable.${metric.unavailable_reason}`)
                : t('comparison.unavailable.generic')

              return (
                <div
                  key={metric.metric_name}
                  className="rounded-lg border border-border/60 bg-muted/20 p-4"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                        {t(`comparison.metric.${metric.metric_name}`)}
                      </p>
                      <p className="mt-2 text-2xl font-semibold text-foreground">
                        {metric.is_available
                          ? formatMetricValue(metric, metric.current_value)
                          : '—'}
                      </p>
                    </div>
                    <MetricTrend trend={metric.trend} changePercent={metric.change_percent} />
                  </div>

                  {metric.is_available ? (
                    <div className="mt-3 space-y-1 text-xs text-muted-foreground">
                      <p>
                        <span className="mr-1">{t('comparison.period1Label')}:</span>
                        <span className="font-medium text-foreground/90">
                          {formatMetricValue(metric, metric.current_value)}
                        </span>
                      </p>
                      <p>
                        <span className="mr-1">{t('comparison.period2Label')}:</span>
                        <span className="font-medium text-foreground/90">
                          {formatMetricValue(metric, metric.previous_value)}
                        </span>
                      </p>
                    </div>
                  ) : (
                    <p className="mt-3 text-xs text-muted-foreground">
                      {unavailableReason}
                    </p>
                  )}
                </div>
              )
            })}
          </div>
        ) : (
          <div className="flex h-32 items-center justify-center text-sm text-muted-foreground">
            {t('common.loading')}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
