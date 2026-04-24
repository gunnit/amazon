import { Minus, TrendingDown, TrendingUp } from 'lucide-react'
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { formatCurrency, formatDate, formatNumber, formatPercent } from '@/lib/utils'
import { useTranslation } from '@/i18n'
import type { ComparisonDailyPoint, ComparisonMetric, ComparisonResponse } from '@/types'

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

function formatChartDate(value: string | null) {
  return value ? formatDate(value) : '—'
}

function formatChartRevenue(value: number | null) {
  return value == null ? '—' : formatCurrency(value)
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
  const chartData = (comparison?.daily_series || []).map((point) => ({
    ...point,
    day_label: t('comparison.chartDay', { day: point.day_offset + 1 }),
  }))

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
          <>
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

            {chartData.length > 0 ? (
              <div className="mt-6 rounded-lg border border-border/60 bg-muted/10 p-4">
                <div className="mb-4">
                  <p className="text-sm font-medium text-foreground">{t('comparison.chartTitle')}</p>
                  <p className="text-xs text-muted-foreground">{t('comparison.chartDescription')}</p>
                </div>

                <div className="h-[320px]">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={chartData} margin={{ top: 8, right: 16, bottom: 8, left: 8 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                      <XAxis dataKey="day_label" axisLine={false} tickLine={false} />
                      <YAxis
                        axisLine={false}
                        tickLine={false}
                        tickFormatter={(value) => formatCurrency(Number(value))}
                      />
                      <Tooltip
                        content={({ active, payload }) => {
                          const point = payload?.[0]?.payload as
                            | (ComparisonDailyPoint & { day_label: string })
                            | undefined

                          if (!active || !point) {
                            return null
                          }

                          return (
                            <div className="rounded-lg border border-border/70 bg-background px-3 py-2 shadow-md">
                              <p className="text-xs font-medium text-foreground">{point.day_label}</p>
                              <div className="mt-2 space-y-2 text-xs">
                                <div>
                                  <p className="font-medium text-[#2563eb]">{t('comparison.period1Label')}</p>
                                  <p className="text-muted-foreground">{formatChartDate(point.period_1_date)}</p>
                                  <p className="text-foreground">{formatChartRevenue(point.period_1_revenue)}</p>
                                </div>
                                <div>
                                  <p className="font-medium text-[#64748b]">{t('comparison.period2Label')}</p>
                                  <p className="text-muted-foreground">{formatChartDate(point.period_2_date)}</p>
                                  <p className="text-foreground">{formatChartRevenue(point.period_2_revenue)}</p>
                                </div>
                              </div>
                            </div>
                          )
                        }}
                      />
                      <Legend />
                      <Line
                        type="monotone"
                        dataKey="period_1_revenue"
                        name={t('comparison.period1Label')}
                        stroke="#2563eb"
                        strokeWidth={2.5}
                        dot={false}
                        activeDot={{ r: 4 }}
                      />
                      <Line
                        type="monotone"
                        dataKey="period_2_revenue"
                        name={t('comparison.period2Label')}
                        stroke="#64748b"
                        strokeWidth={2.5}
                        strokeDasharray="6 4"
                        dot={false}
                        activeDot={{ r: 4 }}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              </div>
            ) : null}
          </>
        ) : (
          <div className="flex h-32 items-center justify-center text-sm text-muted-foreground">
            {t('common.loading')}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
