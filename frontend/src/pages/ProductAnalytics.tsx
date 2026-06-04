import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, Loader2 } from 'lucide-react'
import { Link, useParams } from 'react-router-dom'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { analyticsApi } from '@/services/api'
import { formatChangePercent, formatCurrency, formatNumber } from '@/lib/utils'
import { AREA_FILL, CHART_PRIMARY, CHART_SERIES } from '@/lib/chart-theme'
import { FilterBar, DateRangeFilter, AccountFilter } from '@/components/filters'
import { useFilterStore, getFilterDateRange } from '@/store/filterStore'
import { useTranslation } from '@/i18n'
import ProductTrendBadge from '@/components/analytics/ProductTrendBadge'
import ProductTrendSparkline from '@/components/analytics/ProductTrendSparkline'
import TrendInsightsCard from '@/components/analytics/TrendInsightsCard'

function getChartAxisMax(values: number[]): number {
  const maxValue = Math.max(...values, 0)
  return maxValue <= 0 ? 100 : Math.ceil(maxValue * 1.1)
}

function formatAxisCurrency(value: number): string {
  const absoluteValue = Math.abs(value)

  if (absoluteValue >= 1000) {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'EUR',
      notation: 'compact',
      maximumFractionDigits: absoluteValue >= 10000 ? 0 : 1,
    })
      .format(value)
      .replace('K', 'k')
  }

  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'EUR',
    maximumFractionDigits: 0,
  }).format(value)
}

function formatOptionalPercent(value: number | null | undefined): string {
  return value == null ? '-' : `${value.toFixed(1)}%`
}

function formatDayLabel(value: string, language: 'en' | 'it'): string {
  const locale = language === 'it' ? 'it-IT' : 'en-US'
  return new Date(`${value}T00:00:00`).toLocaleDateString(locale, {
    month: 'short',
    day: 'numeric',
  })
}

function KpiCell({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border p-4">
      <p className="text-sm text-muted-foreground">{label}</p>
      <p className="mt-2 text-2xl font-bold tabular-nums">{value}</p>
    </div>
  )
}

export default function ProductAnalytics() {
  const { asin = '' } = useParams()
  const { t, language } = useTranslation()
  const { datePreset, customStartDate, customEndDate, accountIds, resetDashboard } = useFilterStore()
  const dateRange = getFilterDateRange({ datePreset, customStartDate, customEndDate })
  const accountParam = accountIds.length > 0 ? accountIds : undefined

  const { data: kpiData, isLoading: kpiLoading } = useQuery({
    queryKey: ['product-kpi', asin, dateRange, accountIds],
    queryFn: () =>
      analyticsApi.getPerProductPerformance({
        asin,
        start_date: dateRange.start,
        end_date: dateRange.end,
        account_ids: accountParam,
        limit: 1,
      }),
    enabled: !!asin,
  })

  const { data: trendsData, isLoading: trendsLoading } = useQuery({
    queryKey: ['product-trends-single', asin, dateRange, accountIds, language],
    queryFn: () =>
      analyticsApi.getProductTrends({
        asin,
        start_date: dateRange.start,
        end_date: dateRange.end,
        account_ids: accountParam,
        language,
        limit: 1,
      }),
    enabled: !!asin,
  })

  const trendProduct = trendsData?.products?.[0] ?? null

  const { data: insightsData, isFetching: insightsFetching } = useQuery({
    queryKey: ['product-trend-insights-single', asin, dateRange, accountIds, language],
    queryFn: () =>
      analyticsApi.getProductTrendInsights({
        asin,
        start_date: dateRange.start,
        end_date: dateRange.end,
        account_ids: accountParam,
        language,
        limit: 1,
      }),
    enabled: !!asin && !!trendProduct,
  })

  const { data: adsData, isLoading: adsLoading } = useQuery({
    queryKey: ['product-ads-vs-organic', asin, dateRange, accountIds],
    queryFn: () =>
      analyticsApi.getAdsVsOrganic({
        asin,
        date_from: dateRange.start,
        date_to: dateRange.end,
        group_by: 'day',
        account_ids: accountParam,
      }),
    enabled: !!asin,
  })

  const { data: returnsData, isLoading: returnsLoading } = useQuery({
    queryKey: ['product-returns', asin, dateRange, accountIds],
    queryFn: () =>
      analyticsApi.getReturnsAnalysis({
        asin,
        date_from: dateRange.start,
        date_to: dateRange.end,
        account_ids: accountParam,
        limit: 10,
      }),
    enabled: !!asin,
  })

  const kpiRow = kpiData?.items.find((item) => item.asin === asin) ?? kpiData?.items[0] ?? null
  const productTitle = kpiRow?.title ?? trendProduct?.title ?? asin
  const avgPrice =
    kpiRow && kpiRow.total_units > 0 ? Number(kpiRow.total_revenue) / kpiRow.total_units : null

  const revenueChartData = (adsData?.time_series || []).map((point) => ({
    ...point,
    displayDate: formatDayLabel(point.date, language),
    chartTotal: point.ad_sales + point.organic_sales,
  }))
  const revenueAxisMax = getChartAxisMax(revenueChartData.map((point) => point.total_sales))
  const adsAxisMax = getChartAxisMax(
    revenueChartData.map((point) => Math.max(point.chartTotal, point.total_sales))
  )

  const reasonChartData = (returnsData?.reason_breakdown || []).slice(0, 6).map((entry) => ({
    ...entry,
    reason: entry.reason === 'Unknown' ? t('analytics.returns.unknownReason') : entry.reason,
  }))
  const returnTrendData = (returnsData?.return_rate_over_time || []).map((point) => ({
    ...point,
    displayDate: formatDayLabel(point.date, language),
  }))
  const returnTrendAxisMax = getChartAxisMax(returnTrendData.map((point) => point.returned_units || 0))

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div className="space-y-2">
          <Link
            to="/performance?tab=per-asin"
            className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
          >
            <ArrowLeft className="h-4 w-4" />
            {t('analytics.productPage.back')}
          </Link>
          <h1 className="text-3xl font-bold tracking-tight">{productTitle}</h1>
          <p className="font-mono text-sm text-muted-foreground">{asin}</p>
        </div>
        <FilterBar onReset={resetDashboard}>
          <DateRangeFilter />
          <AccountFilter />
        </FilterBar>
      </div>

      {kpiLoading ? (
        <Card>
          <CardContent className="flex min-h-[320px] items-center justify-center">
            <div className="flex items-center gap-3 text-sm text-muted-foreground">
              <Loader2 className="h-5 w-5 animate-spin" />
              <span>{t('common.loading')}</span>
            </div>
          </CardContent>
        </Card>
      ) : !kpiRow ? (
        <Card>
          <CardContent className="flex min-h-[320px] items-center justify-center text-sm text-muted-foreground">
            {t('analytics.productPage.noData')}
          </CardContent>
        </Card>
      ) : (
        <>
          <Card>
            <CardHeader>
              <CardTitle>{t('analytics.performanceSummary')}</CardTitle>
              <CardDescription>{t('common.selectedPeriod')}</CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
                <KpiCell label={t('common.revenue')} value={formatCurrency(Number(kpiRow.total_revenue))} />
                <KpiCell label={t('common.units')} value={formatNumber(kpiRow.total_units)} />
                <KpiCell label={t('common.orders')} value={formatNumber(kpiRow.total_orders)} />
                <KpiCell
                  label={t('analytics.productPage.avgPrice')}
                  value={avgPrice != null ? formatCurrency(avgPrice) : '—'}
                />
                <KpiCell
                  label="BSR"
                  value={kpiRow.current_bsr != null ? kpiRow.current_bsr.toLocaleString() : '—'}
                />
                <KpiCell
                  label={t('analytics.tableAdSpend')}
                  value={kpiRow.ad_spend ? formatCurrency(kpiRow.ad_spend) : '—'}
                />
                <KpiCell label="ACoS" value={kpiRow.acos != null ? `${kpiRow.acos.toFixed(1)}%` : '—'} />
                <KpiCell label="ROAS" value={kpiRow.roas != null ? kpiRow.roas.toFixed(2) : '—'} />
              </div>

              <div className="rounded-lg border p-4">
                <div className="mb-3 flex items-center justify-between gap-3">
                  <div>
                    <p className="text-sm font-medium">{t('analytics.productPage.momentum')}</p>
                    <p className="text-xs text-muted-foreground">
                      {t('analytics.productPage.momentumDesc')}
                    </p>
                  </div>
                  {trendProduct && <ProductTrendBadge trendClass={trendProduct.trend_class} />}
                </div>

                {trendsLoading ? (
                  <div className="flex min-h-[140px] items-center justify-center">
                    <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
                  </div>
                ) : trendProduct ? (
                  <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]">
                    <div className="grid gap-3 sm:grid-cols-2">
                      <div className="rounded-lg border p-3">
                        <p className="text-xs text-muted-foreground">{t('analytics.tableSalesDelta')}</p>
                        <p className="mt-2 text-xl font-semibold tabular-nums">
                          {formatChangePercent(trendProduct.sales_delta_percent) || '—'}
                        </p>
                      </div>
                      <div className="rounded-lg border p-3">
                        <p className="text-xs text-muted-foreground">{t('analytics.tableScore')}</p>
                        <p className="mt-2 text-xl font-semibold tabular-nums">
                          {trendProduct.trend_score > 0 ? '+' : ''}
                          {trendProduct.trend_score.toFixed(1)}
                        </p>
                      </div>
                      <div className="rounded-lg border p-3">
                        <p className="text-xs text-muted-foreground">{t('analytics.current7DaySales')}</p>
                        <p className="mt-2 text-xl font-semibold tabular-nums">
                          {formatCurrency(trendProduct.current_revenue)}
                        </p>
                      </div>
                      <div className="rounded-lg border p-3">
                        <p className="text-xs text-muted-foreground">{t('analytics.previous7DaySales')}</p>
                        <p className="mt-2 text-xl font-semibold tabular-nums">
                          {formatCurrency(trendProduct.previous_revenue)}
                        </p>
                      </div>
                    </div>
                    <div className="space-y-3">
                      <div className="h-32 rounded-lg border p-3">
                        <ProductTrendSparkline
                          data={trendProduct.recent_sales}
                          trendClass={trendProduct.trend_class}
                          metric="revenue"
                          height={104}
                          showTooltip
                        />
                      </div>
                      {trendProduct.supporting_signals.length > 0 && (
                        <div className="space-y-2">
                          {trendProduct.supporting_signals.map((signal) => (
                            <div
                              key={signal}
                              className="rounded-lg border p-3 text-sm text-muted-foreground"
                            >
                              {signal}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                ) : (
                  <p className="text-sm text-muted-foreground">
                    {t('analytics.productPage.noMomentum')}
                  </p>
                )}
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>{t('analytics.productPage.revenueOverTime')}</CardTitle>
              <CardDescription>{t('analytics.productPage.revenueOverTimeDesc')}</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="h-[320px]">
                {adsLoading ? (
                  <div className="flex h-full items-center justify-center">
                    <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
                  </div>
                ) : revenueChartData.length > 0 ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={revenueChartData} margin={{ top: 8, right: 16, bottom: 8, left: 8 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                      <XAxis dataKey="displayDate" axisLine={false} tickLine={false} />
                      <YAxis
                        domain={[0, revenueAxisMax]}
                        tickCount={6}
                        axisLine={false}
                        tickLine={false}
                        tickFormatter={(value) => formatAxisCurrency(Number(value))}
                      />
                      <Tooltip
                        labelFormatter={(_label, payload) => payload?.[0]?.payload?.displayDate || ''}
                        formatter={(value: number) => [formatCurrency(Number(value)), t('common.revenue')]}
                      />
                      <Area
                        type="monotone"
                        dataKey="total_sales"
                        stroke={CHART_PRIMARY}
                        strokeWidth={2.5}
                        fill={AREA_FILL}
                      />
                    </AreaChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
                    {t('analytics.productPage.noData')}
                  </div>
                )}
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>{t('analytics.adsVsOrganic')}</CardTitle>
              <CardDescription>{t('analytics.adsVsOrganicDesc')}</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
                <p className="font-medium">{t('analytics.accountLevelAttribution')}</p>
                <p className="mt-1">{t('analytics.asinAttributionNotice')}</p>
                {(adsData?.attribution_notes || []).length > 0 && (
                  <ul className="mt-2 list-disc pl-5 text-xs">
                    {adsData?.attribution_notes.map((note, idx) => (
                      <li key={idx}>{note}</li>
                    ))}
                  </ul>
                )}
              </div>
              <div className="h-[360px]">
                {adsLoading ? (
                  <div className="flex h-full items-center justify-center">
                    <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
                  </div>
                ) : revenueChartData.length > 0 ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={revenueChartData} margin={{ top: 8, right: 12, left: 8, bottom: 12 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                      <XAxis dataKey="displayDate" axisLine={false} tickLine={false} />
                      <YAxis
                        domain={[0, adsAxisMax]}
                        tickCount={6}
                        axisLine={false}
                        tickLine={false}
                        tickFormatter={(value) => formatAxisCurrency(Number(value))}
                      />
                      <Tooltip
                        labelFormatter={(_label, payload) => payload?.[0]?.payload?.displayDate || ''}
                        formatter={(value: number, name: string) => [formatCurrency(Number(value)), name]}
                      />
                      <Legend />
                      <Bar
                        dataKey="ad_sales"
                        name={t('analytics.advertisingSales')}
                        stackId="sales"
                        fill={CHART_SERIES[2]}
                        maxBarSize={42}
                      />
                      <Bar
                        dataKey="organic_sales"
                        name={t('analytics.organicSales')}
                        stackId="sales"
                        fill={CHART_SERIES[1]}
                        radius={[4, 4, 0, 0]}
                        maxBarSize={42}
                      />
                    </BarChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
                    {t('analytics.noAdsVsOrganicData')}
                  </div>
                )}
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>{t('analytics.productPage.returnsTitle')}</CardTitle>
              <CardDescription>{t('analytics.productPage.returnsDesc')}</CardDescription>
            </CardHeader>
            <CardContent>
              {returnsLoading ? (
                <div className="flex min-h-[280px] items-center justify-center">
                  <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
                </div>
              ) : (
                <div className="space-y-6">
                  <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
                    <div className="rounded-lg border p-4">
                      <p className="text-sm text-muted-foreground">{t('analytics.returns.totalReturns')}</p>
                      <p className="mt-2 text-2xl font-bold tabular-nums">
                        {formatNumber(returnsData?.summary.total_returns || 0)}
                      </p>
                    </div>
                    <div className="rounded-lg border p-4">
                      <p className="text-sm text-muted-foreground">{t('analytics.returns.overallRate')}</p>
                      <p className="mt-2 text-2xl font-bold tabular-nums">
                        {formatOptionalPercent(returnsData?.summary.return_rate)}
                      </p>
                    </div>
                    <div className="rounded-lg border p-4">
                      <p className="text-sm text-muted-foreground">{t('analytics.returns.topReason')}</p>
                      <p className="mt-2 text-2xl font-bold">
                        {returnsData?.summary.top_reason && returnsData.summary.top_reason !== 'Unknown'
                          ? returnsData.summary.top_reason
                          : t('analytics.returns.unknownReason')}
                      </p>
                    </div>
                  </div>

                  <div className="grid gap-4 xl:grid-cols-2">
                    <div className="rounded-lg border p-4">
                      <p className="mb-3 text-sm font-medium">{t('analytics.returns.reasonBreakdown')}</p>
                      <div className="h-[280px]">
                        {reasonChartData.length > 0 ? (
                          <ResponsiveContainer width="100%" height="100%">
                            <PieChart>
                              <Pie
                                data={reasonChartData}
                                dataKey="quantity"
                                nameKey="reason"
                                innerRadius={60}
                                outerRadius={96}
                                paddingAngle={3}
                                stroke="hsl(var(--card))"
                                strokeWidth={2}
                              >
                                {reasonChartData.map((entry, index) => (
                                  <Cell key={entry.reason} fill={CHART_SERIES[index % CHART_SERIES.length]} />
                                ))}
                              </Pie>
                              <Tooltip
                                formatter={(value: number) => [
                                  formatNumber(Number(value)),
                                  t('analytics.returns.quantityReturned'),
                                ]}
                              />
                              <Legend />
                            </PieChart>
                          </ResponsiveContainer>
                        ) : (
                          <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
                            {t('analytics.returns.noReasonData')}
                          </div>
                        )}
                      </div>
                    </div>

                    <div className="rounded-lg border p-4">
                      <p className="mb-3 text-sm font-medium">{t('analytics.returns.trend')}</p>
                      <div className="h-[280px]">
                        {returnTrendData.length > 0 ? (
                          <ResponsiveContainer width="100%" height="100%">
                            <LineChart data={returnTrendData} margin={{ top: 8, right: 16, bottom: 8, left: 8 }}>
                              <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                              <XAxis dataKey="displayDate" axisLine={false} tickLine={false} />
                              <YAxis
                                domain={[0, returnTrendAxisMax]}
                                tickCount={6}
                                axisLine={false}
                                tickLine={false}
                              />
                              <Tooltip
                                labelFormatter={(_label, payload) => payload?.[0]?.payload?.displayDate || ''}
                                formatter={(value: number) => [
                                  formatNumber(Number(value)),
                                  t('analytics.returns.quantityReturned'),
                                ]}
                              />
                              <Line
                                type="monotone"
                                dataKey="returned_units"
                                stroke={CHART_PRIMARY}
                                strokeWidth={2.5}
                                dot={false}
                                activeDot={{ r: 4 }}
                              />
                            </LineChart>
                          </ResponsiveContainer>
                        ) : (
                          <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
                            {t('analytics.returns.noData')}
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>

          {trendProduct && trendsData && (
            <TrendInsightsCard
              insights={insightsData?.insights ?? trendsData.insights}
              generatedWithAi={insightsData?.generated_with_ai ?? false}
              aiAvailable={trendsData.ai_available}
              loading={!insightsData && insightsFetching}
            />
          )}
        </>
      )}
    </div>
  )
}
