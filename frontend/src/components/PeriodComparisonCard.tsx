import { ArrowDownRight, ArrowUpRight, Minus } from 'lucide-react'
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
import { cn, formatCurrency, formatDate, formatDecimal, formatNumber, formatRatio } from '@/lib/utils'
import { CHART_NEUTRAL, CHART_PRIMARY } from '@/lib/chart-theme'
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
    return `${formatDecimal(value, 1)}%`
  }

  if (metric.format === 'ratio') {
    return formatRatio(value)
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

  const isUp = trend === 'up'
  const isDown = trend === 'down'
  const Icon = isUp ? ArrowUpRight : isDown ? ArrowDownRight : Minus
  const tone = isUp
    ? 'text-emerald-600 bg-emerald-500/10 dark:text-emerald-400'
    : isDown
      ? 'text-rose-600 bg-rose-500/10 dark:text-rose-400'
      : 'text-muted-foreground bg-muted/60'

  return (
    <span
      className={cn(
        'inline-flex items-center gap-0.5 rounded-md px-1.5 py-0.5 text-xs font-semibold tabular-nums',
        tone,
      )}
    >
      <Icon className="h-3.5 w-3.5" />
      {formatDecimal(Math.abs(changePercent), 1)}%
    </span>
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
  adsCoverage,
}: {
  comparison?: ComparisonResponse
  title: string
  description: string
  /** Ads data coverage from the KPI response; undefined = unknown (no suppression). */
  adsCoverage?: { from: string | null; until: string | null }
}) {
  const { t, language } = useTranslation()

  // The backend pads the aligned series to the full length of the longer
  // period, filling days without data with zeros. On long presets this drew a
  // mostly-empty grid, so trim the axis to the populated extent.
  const rawSeries = comparison?.daily_series || []
  let firstPopulated = -1
  let lastPopulated = -1
  rawSeries.forEach((point, index) => {
    if ((point.period_1_revenue ?? 0) > 0 || (point.period_2_revenue ?? 0) > 0) {
      if (firstPopulated === -1) firstPopulated = index
      lastPopulated = index
    }
  })
  const visibleSeries =
    firstPopulated === -1 ? rawSeries : rawSeries.slice(firstPopulated, lastPopulated + 1)

  const tickDate = (value: string | null) =>
    value
      ? new Date(value + 'T00:00:00').toLocaleDateString(language === 'it' ? 'it-IT' : 'en-US', {
          day: 'numeric',
          month: 'short',
        })
      : null

  const chartData = visibleSeries.map((point) => {
    const day_label = t('comparison.chartDay', { day: point.day_offset + 1 })
    return {
      ...point,
      day_label,
      tick_label: tickDate(point.period_1_date) ?? day_label,
    }
  })

  // ROAS/CTR read as a meaningless 0 when neither compared period overlaps the
  // ads data coverage (or ads are not connected at all): show n/d instead.
  const adsUntil = adsCoverage?.until ?? '9999-12-31'
  const periodCoversAds = (period: { start: string; end: string }) =>
    !!adsCoverage?.from && period.start <= adsUntil && period.end >= adsCoverage.from
  const noAdsCoverage =
    adsCoverage !== undefined &&
    !!comparison &&
    !periodCoversAds(comparison.period_1) &&
    !periodCoversAds(comparison.period_2)

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
                const isAdsMetricWithoutCoverage =
                  noAdsCoverage && (metric.metric_name === 'roas' || metric.metric_name === 'ctr')
                const isAvailable = metric.is_available && !isAdsMetricWithoutCoverage
                const unavailableReason = isAdsMetricWithoutCoverage
                  ? t('comparison.unavailable.no_ads_coverage')
                  : metric.unavailable_reason
                    ? t(`comparison.unavailable.${metric.unavailable_reason}`)
                    : t('comparison.unavailable.generic')

                return (
                  <div
                    key={metric.metric_name}
                    className="rounded-xl border border-border/60 bg-muted/20 p-4 transition-colors hover:bg-muted/30"
                  >
                    <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                      {t(`comparison.metric.${metric.metric_name}`)}
                    </p>

                    <div className="mt-2 flex items-center justify-between gap-3">
                      <p className="text-3xl font-semibold tracking-tight text-foreground tabular-nums">
                        {isAvailable
                          ? formatMetricValue(metric, metric.current_value)
                          : isAdsMetricWithoutCoverage
                            ? t('comparison.valueNotAvailable')
                            : '—'}
                      </p>
                      {isAvailable && (
                        <MetricTrend trend={metric.trend} changePercent={metric.change_percent} />
                      )}
                    </div>

                    {isAvailable ? (
                      <p className="mt-2 text-xs text-muted-foreground">
                        {t('comparison.vsLabel')}{' '}
                        <span className="font-medium text-foreground/80 tabular-nums">
                          {formatMetricValue(metric, metric.previous_value)}
                        </span>
                      </p>
                    ) : (
                      <p className="mt-2 text-xs text-muted-foreground">{unavailableReason}</p>
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
                  {/* key: remount on dataset change — Recharts' update diff intermittently
                      drops line paths when the series length changes (empty chart with
                      populated axes). A fresh mount always draws. */}
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart
                      key={`${comparison.period_1.start}_${comparison.period_2.start}_${chartData.length}`}
                      data={chartData}
                      margin={{ top: 8, right: 16, bottom: 8, left: 8 }}
                    >
                      <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                      <XAxis dataKey="tick_label" axisLine={false} tickLine={false} minTickGap={24} />
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
                                  <p className="font-medium" style={{ color: CHART_PRIMARY }}>{t('comparison.period1Label')}</p>
                                  <p className="text-muted-foreground">{formatChartDate(point.period_1_date)}</p>
                                  <p className="text-foreground">{formatChartRevenue(point.period_1_revenue)}</p>
                                </div>
                                <div>
                                  <p className="font-medium" style={{ color: CHART_NEUTRAL }}>{t('comparison.period2Label')}</p>
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
                        stroke={CHART_PRIMARY}
                        strokeWidth={2.5}
                        dot={false}
                        activeDot={{ r: 4 }}
                      />
                      <Line
                        type="monotone"
                        dataKey="period_2_revenue"
                        name={t('comparison.period2Label')}
                        stroke={CHART_NEUTRAL}
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
