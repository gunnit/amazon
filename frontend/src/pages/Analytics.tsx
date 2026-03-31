import { useQuery } from '@tanstack/react-query'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts'
import { ArrowDownRight, ArrowUpRight, Loader2, Minus } from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import { analyticsApi } from '@/services/api'
import { formatCurrency, formatNumber } from '@/lib/utils'
import {
  FilterBar,
  DateRangeFilter,
  AccountFilter,
  CategoryFilter,
} from '@/components/filters'
import { useFilterStore, getFilterDateRange } from '@/store/filterStore'
import { useTranslation } from '@/i18n'
import ProductTrendList from '@/components/analytics/ProductTrendList'
import TrendInsightsCard from '@/components/analytics/TrendInsightsCard'
import type { CategorySalesData, HourlyOrdersData, ProductTrendItem } from '@/types'

function truncateLabel(value: string, maxLength: number): string {
  if (value.length <= maxLength) {
    return value
  }

  return `${value.slice(0, maxLength - 3)}...`
}

function getChartAxisMax(values: number[]): number {
  const maxValue = Math.max(...values, 0)

  if (maxValue <= 0) {
    return 100
  }

  return Math.ceil(maxValue * 1.1)
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

function SummaryHighlight({
  label,
  product,
  tone,
}: {
  label: string
  product: ProductTrendItem | null
  tone: 'up' | 'down' | 'stable'
}) {
  const iconClass =
    tone === 'up'
      ? 'text-green-600 dark:text-green-400'
      : tone === 'down'
        ? 'text-red-600 dark:text-red-400'
        : 'text-muted-foreground'
  const Icon = tone === 'up' ? ArrowUpRight : tone === 'down' ? ArrowDownRight : Minus

  return (
    <div className="rounded-lg border p-4">
      <div className="mb-2 flex items-center gap-2">
        <Icon className={`h-4 w-4 ${iconClass}`} />
        <p className="text-sm font-medium">{label}</p>
      </div>
      {product ? (
        <>
          <p className="truncate text-sm font-semibold">{product.title || product.asin}</p>
          <p className="mt-1 text-xs text-muted-foreground">
            {product.asin} · {product.trend_score > 0 ? '+' : ''}{product.trend_score.toFixed(1)}
          </p>
        </>
      ) : (
        <p className="text-sm text-muted-foreground">-</p>
      )}
    </div>
  )
}

export default function Analytics() {
  const { t, language } = useTranslation()
  const filterState = useFilterStore()
  const {
    datePreset,
    customStartDate,
    customEndDate,
    accountIds,
    analyticsCategory,
    setAnalyticsCategory,
    resetAnalytics,
    resetDashboard,
  } = filterState
  const dateRange = getFilterDateRange({ datePreset, customStartDate, customEndDate })

  const handleResetAll = () => {
    resetDashboard()
    resetAnalytics()
  }

  const { data: topPerformers, isLoading: topPerformersLoading } = useQuery({
    queryKey: ['top-performers', dateRange, accountIds],
    queryFn: () => analyticsApi.getTopPerformers({
      start_date: dateRange.start,
      end_date: dateRange.end,
      limit: 10,
      account_ids: accountIds.length > 0 ? accountIds : undefined,
    }),
  })

  const { data: salesByCategory, isLoading: categoryLoading } = useQuery<CategorySalesData[]>({
    queryKey: ['sales-by-category', dateRange, accountIds],
    queryFn: () => analyticsApi.getSalesByCategory({
      start_date: dateRange.start,
      end_date: dateRange.end,
      account_ids: accountIds.length > 0 ? accountIds : undefined,
      limit: 12,
    }),
  })

  const { data: ordersByHour, isLoading: hourlyLoading } = useQuery<HourlyOrdersData[]>({
    queryKey: ['orders-by-hour', dateRange, accountIds],
    queryFn: () => analyticsApi.getOrdersByHour({
      start_date: dateRange.start,
      end_date: dateRange.end,
      account_ids: accountIds.length > 0 ? accountIds : undefined,
    }),
  })

  const { data: kpis, isLoading: kpisLoading } = useQuery({
    queryKey: ['dashboard-kpis-analytics', dateRange, accountIds],
    queryFn: () => analyticsApi.getDashboard({
      start_date: dateRange.start,
      end_date: dateRange.end,
      account_ids: accountIds.length > 0 ? accountIds : undefined,
    }),
  })

  const { data: productTrends, isLoading: productTrendsLoading } = useQuery({
    queryKey: ['product-trends', dateRange, accountIds, language],
    queryFn: () => analyticsApi.getProductTrends({
      start_date: dateRange.start,
      end_date: dateRange.end,
      account_ids: accountIds.length > 0 ? accountIds : undefined,
      language,
      limit: 8,
    }),
  })

  const loadingStates = [
    topPerformersLoading,
    categoryLoading,
    hourlyLoading,
    kpisLoading,
    productTrendsLoading,
  ]
  const completedRequests = loadingStates.filter((loading) => !loading).length
  const loadingProgress = (completedRequests / loadingStates.length) * 100
  const isLoading = loadingStates.some(Boolean)

  if (isLoading) {
    return (
      <div className="flex h-96 items-center justify-center">
        <div className="w-full max-w-md rounded-lg border bg-card p-6 shadow-sm">
          <div className="flex items-center justify-center gap-3">
            <Loader2 className="h-8 w-8 animate-spin text-primary" />
            <div className="space-y-1">
              <p className="text-sm font-medium">{t('analytics.title')}</p>
              <p className="text-xs text-muted-foreground">{Math.round(loadingProgress)}% loaded</p>
            </div>
          </div>
          <Progress value={loadingProgress} className="mt-4 h-2" />
        </div>
      </div>
    )
  }

  const categoryOptions = Array.from(
    new Set((salesByCategory || []).map((row) => row.category).filter(Boolean))
  )
  const categoryChartData = analyticsCategory
    ? (salesByCategory || []).filter((row) => row.category === analyticsCategory)
    : (salesByCategory || [])
  const topProductsChartData = (topPerformers?.by_revenue || []).slice(0, 5).map((product) => ({
    ...product,
    displayLabel: truncateLabel(product.title || product.asin, 22),
  }))
  const categoryRevenueChartData = categoryChartData.slice(0, 8).map((row) => ({
    ...row,
    displayCategory: truncateLabel(row.category, 14),
  }))
  const topProductsAxisMax = getChartAxisMax(
    topProductsChartData.map((product) => Number(product.total_revenue) || 0)
  )
  const categoryRevenueAxisMax = getChartAxisMax(
    categoryRevenueChartData.map((row) => Number(row.total_revenue) || 0)
  )

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">{t('analytics.title')}</h1>
          <p className="text-muted-foreground">
            {t('analytics.subtitle')}
          </p>
        </div>
        <FilterBar onReset={handleResetAll}>
          <DateRangeFilter />
          <AccountFilter />
          <CategoryFilter
            value={analyticsCategory}
            onChange={setAnalyticsCategory}
            options={categoryOptions}
          />
        </FilterBar>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        {/* Top Products by Revenue */}
        <Card className="col-span-2 md:col-span-1">
          <CardHeader>
            <CardTitle>{t('analytics.topProducts')}</CardTitle>
            <CardDescription>{t('analytics.topProductsDesc')}</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="h-[300px]">
              {topProductsChartData.length > 0 ? (
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart
                    data={topProductsChartData}
                    layout="vertical"
                    margin={{ top: 8, right: 16, bottom: 8, left: 8 }}
                  >
                    <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                    <XAxis
                      type="number"
                      domain={[0, topProductsAxisMax]}
                      tickCount={6}
                      axisLine={false}
                      tickLine={false}
                      tickFormatter={(value) => formatAxisCurrency(Number(value))}
                    />
                    <YAxis
                      type="category"
                      dataKey="displayLabel"
                      width={132}
                      axisLine={false}
                      tickLine={false}
                    />
                    <Tooltip
                      labelFormatter={(_label, payload) => {
                        const product = payload?.[0]?.payload
                        if (!product) {
                          return ''
                        }

                        return product.title ? `${product.title} (${product.asin})` : product.asin
                      }}
                      formatter={(value: number) => [formatCurrency(Number(value)), t('common.revenue')]}
                    />
                    <Bar
                      dataKey="total_revenue"
                      fill="hsl(var(--primary))"
                      radius={[0, 4, 4, 0]}
                    />
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
                  {t('analytics.topProductsDesc')}
                </div>
              )}
            </div>
          </CardContent>
        </Card>

        {/* Sales by Category */}
        <Card className="col-span-2 md:col-span-1">
          <CardHeader>
            <CardTitle>{t('analytics.salesByCategory')}</CardTitle>
            <CardDescription>
              {analyticsCategory
                ? t('analytics.showing', { category: analyticsCategory })
                : t('analytics.salesByCategoryDesc')}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="h-[300px]">
              {categoryRevenueChartData.length > 0 ? (
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={categoryRevenueChartData} margin={{ top: 8, right: 12, left: 8, bottom: 12 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                    <XAxis
                      dataKey="displayCategory"
                      interval={0}
                      angle={-18}
                      height={74}
                      textAnchor="end"
                      axisLine={false}
                      tickLine={false}
                    />
                    <YAxis
                      domain={[0, categoryRevenueAxisMax]}
                      tickCount={6}
                      axisLine={false}
                      tickLine={false}
                      tickFormatter={(value) => formatAxisCurrency(Number(value))}
                    />
                    <Tooltip
                      labelFormatter={(_label, payload) => payload?.[0]?.payload?.category || ''}
                      formatter={(value: number) => [formatCurrency(Number(value)), t('common.revenue')]}
                    />
                    <Bar
                      dataKey="total_revenue"
                      fill="hsl(var(--primary))"
                      radius={[4, 4, 0, 0]}
                    />
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <div className="h-full flex items-center justify-center text-sm text-muted-foreground">
                  {t('analytics.salesByCategoryDesc')}
                </div>
              )}
            </div>
          </CardContent>
        </Card>

        {/* Orders by Hour */}
        <Card className="col-span-2">
          <CardHeader>
            <CardTitle>{t('analytics.ordersByHour')}</CardTitle>
            <CardDescription>{t('analytics.ordersByHourDesc')}</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="h-[300px]">
              {ordersByHour && ordersByHour.some((d) => d.orders > 0) ? (
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={ordersByHour}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="hour" tickFormatter={(hour) => `${String(hour).padStart(2, '0')}:00`} />
                    <YAxis />
                    <Tooltip
                      labelFormatter={(hour) => `${String(hour).padStart(2, '0')}:00`}
                      formatter={(value: number) => [formatNumber(value), t('common.orders')]}
                    />
                    <Bar dataKey="orders" fill="hsl(var(--primary))" />
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <div className="h-full flex items-center justify-center text-sm text-muted-foreground">
                  {t('analytics.ordersByHourDesc')}
                </div>
              )}
            </div>
          </CardContent>
        </Card>

        {/* Performance Metrics */}
        <Card className="col-span-2">
          <CardHeader>
            <CardTitle>{t('analytics.performanceSummary')}</CardTitle>
            <CardDescription>{t('analytics.keyMetrics')}</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid gap-4 md:grid-cols-4">
              <div className="space-y-2">
                <p className="text-sm text-muted-foreground">{t('analytics.avgOrderValue')}</p>
                <p className="text-2xl font-bold">
                  {formatCurrency(kpis?.average_order_value.value || 0)}
                </p>
              </div>
              <div className="space-y-2">
                <p className="text-sm text-muted-foreground">{t('analytics.conversionRate')}</p>
                <p className="text-2xl font-bold">3.2%</p>
              </div>
              <div className="space-y-2">
                <p className="text-sm text-muted-foreground">{t('analytics.returnRate')}</p>
                <p className="text-2xl font-bold">
                  {(kpis?.return_rate.value || 0).toFixed(1)}%
                </p>
              </div>
              <div className="space-y-2">
                <p className="text-sm text-muted-foreground">{t('analytics.activeProducts')}</p>
                <p className="text-2xl font-bold">{formatNumber(kpis?.active_asins || 0)}</p>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="col-span-2">
          <CardHeader>
            <div className="flex items-start justify-between gap-3">
              <div>
                <CardTitle>{t('analytics.productTrends')}</CardTitle>
                <CardDescription>{t('analytics.productTrendsDesc')}</CardDescription>
              </div>
              <Badge variant="outline">
                {t('analytics.eligibleProducts', {
                  count: productTrends?.summary.eligible_products || 0,
                })}
              </Badge>
            </div>
          </CardHeader>
          <CardContent>
            {productTrends && productTrends.summary.eligible_products > 0 ? (
              <div className="grid gap-4 md:grid-cols-4">
                <div className="rounded-lg border p-4">
                  <p className="text-sm text-muted-foreground">{t('analytics.risingProducts')}</p>
                  <p className="mt-2 text-2xl font-bold">{formatNumber(productTrends.summary.rising_count)}</p>
                </div>
                <div className="rounded-lg border p-4">
                  <p className="text-sm text-muted-foreground">{t('analytics.decliningProducts')}</p>
                  <p className="mt-2 text-2xl font-bold">{formatNumber(productTrends.summary.declining_count)}</p>
                </div>
                <div className="rounded-lg border p-4">
                  <p className="text-sm text-muted-foreground">{t('analytics.stableProducts')}</p>
                  <p className="mt-2 text-2xl font-bold">{formatNumber(productTrends.summary.stable_count)}</p>
                </div>
                <div className="rounded-lg border p-4">
                  <p className="text-sm text-muted-foreground">{t('analytics.avgTrendScore')}</p>
                  <p className="mt-2 text-2xl font-bold">
                    {productTrends.summary.average_trend_score > 0 ? '+' : ''}
                    {productTrends.summary.average_trend_score.toFixed(1)}
                  </p>
                </div>
                <SummaryHighlight
                  label={t('analytics.strongestRiser')}
                  product={productTrends.summary.strongest_riser}
                  tone="up"
                />
                <SummaryHighlight
                  label={t('analytics.strongestDecliner')}
                  product={productTrends.summary.strongest_decliner}
                  tone="down"
                />
              </div>
            ) : (
              <div className="flex min-h-[160px] items-center justify-center text-sm text-muted-foreground">
                {t('analytics.noTrendData')}
              </div>
            )}
          </CardContent>
        </Card>

        <div className="col-span-2 grid gap-4 lg:grid-cols-2">
          <ProductTrendList
            title={t('analytics.risingProducts')}
            description={t('analytics.risingProductsDesc')}
            direction="up"
            products={productTrends?.rising_products || []}
          />
          <ProductTrendList
            title={t('analytics.decliningProducts')}
            description={t('analytics.decliningProductsDesc')}
            direction="down"
            products={productTrends?.declining_products || []}
          />
        </div>

        {productTrends && (
          <TrendInsightsCard
            insights={productTrends.insights}
            generatedWithAi={productTrends.generated_with_ai}
            aiAvailable={productTrends.ai_available}
          />
        )}
      </div>
    </div>
  )
}
