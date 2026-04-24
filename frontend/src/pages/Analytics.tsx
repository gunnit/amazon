import { useEffect, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  BarChart,
  Bar,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Line,
  LineChart,
  Pie,
  PieChart,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts'
import { ArrowDownRight, ArrowUpDown, ArrowUpRight, ChevronLeft, ChevronRight, Loader2, Minus } from 'lucide-react'
import { useSearchParams } from 'react-router-dom'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Progress } from '@/components/ui/progress'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { analyticsApi, catalogApi } from '@/services/api'
import { formatCurrency, formatNumber } from '@/lib/utils'
import {
  FilterBar,
  DateRangeFilter,
  AccountFilter,
  CategoryFilter,
  GroupByFilter,
} from '@/components/filters'
import { useFilterStore, getFilterDateRange } from '@/store/filterStore'
import { useTranslation } from '@/i18n'
import ProductTrendBadge from '@/components/analytics/ProductTrendBadge'
import ProductTrendSparkline from '@/components/analytics/ProductTrendSparkline'
import TrendInsightsCard from '@/components/analytics/TrendInsightsCard'
import type {
  AdsVsOrganicAsinBreakdownItem,
  AdsVsOrganicResponse,
  CategorySalesData,
  HourlyOrdersData,
  MetricValue,
  Product,
  ProductTrendClass,
  ProductTrendItem,
  ReturnsAnalyticsResponse,
} from '@/types'

const ALL_ASINS_VALUE = '__all_asins__'
const RETURN_REASON_COLORS = ['#0f766e', '#2563eb', '#d97706', '#dc2626', '#7c3aed', '#0891b2']

type AnalyticsTab = 'overview' | 'returns' | 'ads-vs-organic'

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

function formatPercentValue(value: number): string {
  return `${value.toFixed(1)}%`
}

function formatChangePercent(value: number | null | undefined): string {
  if (value == null) {
    return ''
  }

  return `${value > 0 ? '+' : ''}${value.toFixed(1)}%`
}

function formatOptionalPercent(value: number | null | undefined): string {
  if (value == null) {
    return '-'
  }

  return `${value.toFixed(1)}%`
}

function formatTimeBucketLabel(
  value: string,
  groupBy: 'day' | 'week' | 'month',
  language: 'en' | 'it'
): string {
  const locale = language === 'it' ? 'it-IT' : 'en-US'
  const dateValue = new Date(`${value}T00:00:00`)

  if (groupBy === 'month') {
    return dateValue.toLocaleDateString(locale, {
      month: 'short',
      year: 'numeric',
    })
  }

  return dateValue.toLocaleDateString(locale, {
    month: 'short',
    day: 'numeric',
  })
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

function AdsVsOrganicKpiCard({
  label,
  metric,
  formatter,
  comparisonLabel,
}: {
  label: string
  metric: MetricValue | undefined
  formatter: (value: number) => string
  comparisonLabel: string
}) {
  const trend = metric?.trend || 'stable'
  const Icon = trend === 'up' ? ArrowUpRight : trend === 'down' ? ArrowDownRight : Minus
  const iconClass =
    trend === 'up'
      ? 'text-green-600 dark:text-green-400'
      : trend === 'down'
        ? 'text-red-600 dark:text-red-400'
        : 'text-muted-foreground'

  return (
    <div className="rounded-lg border p-4">
      <p className="text-sm text-muted-foreground">{label}</p>
      <p className="mt-2 text-2xl font-bold">{formatter(metric?.value || 0)}</p>
      {metric?.change_percent != null && (
        <div className="mt-3 flex items-center gap-2 text-xs text-muted-foreground">
          <Icon className={`h-3.5 w-3.5 ${iconClass}`} />
          <span>
            {formatChangePercent(metric.change_percent)} {comparisonLabel}
          </span>
        </div>
      )}
    </div>
  )
}

function AsinBreakdownList({
  items,
  onSelectAsin,
}: {
  items: AdsVsOrganicAsinBreakdownItem[]
  onSelectAsin: (asin: string) => void
}) {
  return (
    <div className="space-y-3">
      {items.map((item) => (
        <button
          key={item.asin}
          type="button"
          onClick={() => onSelectAsin(item.asin)}
          className="flex w-full items-center justify-between gap-3 rounded-lg border px-3 py-3 text-left transition-colors hover:bg-accent"
        >
          <div className="min-w-0">
            <p className="truncate text-sm font-medium">{item.title || item.asin}</p>
            <p className="mt-1 font-mono text-xs text-muted-foreground">{item.asin}</p>
          </div>
          <div className="shrink-0 text-right">
            <p className="text-sm font-semibold">{formatCurrency(item.total_sales)}</p>
            <p className="mt-1 text-xs text-muted-foreground">{formatPercentValue(item.sales_share_pct)}</p>
          </div>
        </button>
      ))}
    </div>
  )
}

type TrendSortKey = 'title' | 'sales_delta_percent' | 'trend_score' | 'current_revenue' | 'current_units'
type TrendSortDirection = 'asc' | 'desc'

function compareTrendProducts(
  left: ProductTrendItem,
  right: ProductTrendItem,
  sortKey: TrendSortKey,
  sortDirection: TrendSortDirection
) {
  const modifier = sortDirection === 'asc' ? 1 : -1

  if (sortKey === 'title') {
    return modifier * (left.title || left.asin).localeCompare(right.title || right.asin)
  }

  return modifier * ((left[sortKey] || 0) - (right[sortKey] || 0))
}

export default function Analytics() {
  const { t, language } = useTranslation()
  const [searchParams, setSearchParams] = useSearchParams()
  const filterState = useFilterStore()
  const {
    datePreset,
    customStartDate,
    customEndDate,
    accountIds,
    analyticsCategory,
    analyticsGroupBy,
    setAnalyticsCategory,
    setAnalyticsGroupBy,
    resetAnalytics,
    resetDashboard,
  } = filterState
  const [activeTab, setActiveTab] = useState<AnalyticsTab>('overview')
  const [selectedAsin, setSelectedAsin] = useState(ALL_ASINS_VALUE)
  const [trendSortKey, setTrendSortKey] = useState<TrendSortKey>('sales_delta_percent')
  const [trendSortDirection, setTrendSortDirection] = useState<TrendSortDirection>('desc')
  const [selectedTrendAsin, setSelectedTrendAsin] = useState<string | null>(null)
  const [trendPage, setTrendPage] = useState(0)
  const TREND_PAGE_SIZE = 5
  const dateRange = getFilterDateRange({ datePreset, customStartDate, customEndDate })
  const scopedAccountId = searchParams.get('account_id') || undefined
  const trendAsinFilter = searchParams.get('asin') || ''
  const trendClassFilter = (searchParams.get('trend_class') || 'all') as ProductTrendClass | 'all'
  const trendAccountIds = scopedAccountId ? [scopedAccountId] : accountIds

  const setTrendSearchParam = (key: 'asin' | 'trend_class', value: string | null) => {
    const nextParams = new URLSearchParams(searchParams)
    if (value && value !== 'all') {
      nextParams.set(key, value)
    } else {
      nextParams.delete(key)
    }
    setSearchParams(nextParams, { replace: true })
  }

  const handleResetAll = () => {
    resetDashboard()
    resetAnalytics()
    setSelectedAsin(ALL_ASINS_VALUE)
    setSelectedTrendAsin(null)
    setSearchParams({}, { replace: true })
  }

  const handleTrendSort = (sortKey: TrendSortKey) => {
    if (trendSortKey === sortKey) {
      setTrendSortDirection((current) => (current === 'desc' ? 'asc' : 'desc'))
      return
    }

    setTrendSortKey(sortKey)
    setTrendSortDirection(sortKey === 'title' ? 'asc' : 'desc')
  }

  const { data: topPerformers, isLoading: topPerformersLoading } = useQuery({
    queryKey: ['top-performers', dateRange, trendAccountIds],
    queryFn: () => analyticsApi.getTopPerformers({
      start_date: dateRange.start,
      end_date: dateRange.end,
      limit: 10,
      account_ids: trendAccountIds.length > 0 ? trendAccountIds : undefined,
    }),
    enabled: activeTab === 'overview',
  })

  const { data: salesByCategory, isLoading: categoryLoading } = useQuery<CategorySalesData[]>({
    queryKey: ['sales-by-category', dateRange, trendAccountIds],
    queryFn: () => analyticsApi.getSalesByCategory({
      start_date: dateRange.start,
      end_date: dateRange.end,
      account_ids: trendAccountIds.length > 0 ? trendAccountIds : undefined,
      limit: 12,
    }),
    enabled: activeTab === 'overview',
  })

  const { data: ordersByHour, isLoading: hourlyLoading } = useQuery<HourlyOrdersData[]>({
    queryKey: ['orders-by-hour', dateRange, trendAccountIds],
    queryFn: () => analyticsApi.getOrdersByHour({
      start_date: dateRange.start,
      end_date: dateRange.end,
      account_ids: trendAccountIds.length > 0 ? trendAccountIds : undefined,
    }),
    enabled: activeTab === 'overview',
  })

  const { data: kpis, isLoading: kpisLoading } = useQuery({
    queryKey: ['dashboard-kpis-analytics', dateRange, trendAccountIds],
    queryFn: () => analyticsApi.getDashboard({
      start_date: dateRange.start,
      end_date: dateRange.end,
      account_ids: trendAccountIds.length > 0 ? trendAccountIds : undefined,
    }),
    enabled: activeTab === 'overview',
  })

  const { data: productTrends, isLoading: productTrendsLoading } = useQuery({
    queryKey: ['product-trends', dateRange, trendAccountIds, trendAsinFilter, trendClassFilter, language],
    queryFn: () => analyticsApi.getProductTrends({
      start_date: dateRange.start,
      end_date: dateRange.end,
      account_id: scopedAccountId,
      account_ids: scopedAccountId ? undefined : trendAccountIds.length > 0 ? trendAccountIds : undefined,
      asin: trendAsinFilter || undefined,
      trend_class: trendClassFilter === 'all' ? undefined : trendClassFilter,
      language,
      limit: 100,
    }),
    enabled: activeTab === 'overview',
  })

  const { data: returnsAnalytics, isLoading: returnsLoading } = useQuery<ReturnsAnalyticsResponse>({
    queryKey: ['returns-analysis', dateRange, trendAccountIds],
    queryFn: () => analyticsApi.getReturnsAnalysis({
      date_from: dateRange.start,
      date_to: dateRange.end,
      account_ids: trendAccountIds.length > 0 ? trendAccountIds : undefined,
      limit: 10,
    }),
    enabled: activeTab === 'returns',
  })

  const { data: products } = useQuery<Product[]>({
    queryKey: ['analytics-products', trendAccountIds],
    queryFn: () => catalogApi.getProducts({
      active_only: true,
      limit: 200,
      account_ids: trendAccountIds.length > 0 ? trendAccountIds : undefined,
    }),
    enabled: activeTab === 'ads-vs-organic',
  })

  const { data: adsVsOrganicData, isLoading: adsVsOrganicLoading } = useQuery<AdsVsOrganicResponse>({
    queryKey: ['ads-vs-organic', dateRange, trendAccountIds, analyticsGroupBy, selectedAsin],
    queryFn: () => analyticsApi.getAdsVsOrganic({
      date_from: dateRange.start,
      date_to: dateRange.end,
      group_by: analyticsGroupBy,
      account_ids: trendAccountIds.length > 0 ? trendAccountIds : undefined,
      ...(selectedAsin !== ALL_ASINS_VALUE ? { asin: selectedAsin } : {}),
    }),
    enabled: activeTab === 'ads-vs-organic',
  })

  const asinOptions = useMemo(() => {
    const deduped = new Map<string, Product>()
    for (const product of products || []) {
      if (!deduped.has(product.asin)) {
        deduped.set(product.asin, product)
      }
    }
    return Array.from(deduped.values()).sort((a, b) =>
      (a.title || a.asin).localeCompare(b.title || b.asin)
    )
  }, [products])

  useEffect(() => {
    if (
      selectedAsin !== ALL_ASINS_VALUE &&
      !asinOptions.some((product) => product.asin === selectedAsin)
    ) {
      setSelectedAsin(ALL_ASINS_VALUE)
    }
  }, [asinOptions, selectedAsin])

  useEffect(() => {
    if (trendAsinFilter) {
      setSelectedTrendAsin(trendAsinFilter)
    }
  }, [trendAsinFilter])

  const sortedTrendProducts = useMemo(() => {
    return [...(productTrends?.products || [])].sort((left, right) =>
      compareTrendProducts(left, right, trendSortKey, trendSortDirection)
    )
  }, [productTrends?.products, trendSortDirection, trendSortKey])

  const trendTotalPages = Math.max(1, Math.ceil(sortedTrendProducts.length / TREND_PAGE_SIZE))
  const pagedTrendProducts = useMemo(
    () => sortedTrendProducts.slice(trendPage * TREND_PAGE_SIZE, (trendPage + 1) * TREND_PAGE_SIZE),
    [sortedTrendProducts, trendPage]
  )

  useEffect(() => {
    setTrendPage(0)
  }, [sortedTrendProducts.length, trendAsinFilter, trendClassFilter, trendSortKey, trendSortDirection])

  useEffect(() => {
    if (!sortedTrendProducts.length) {
      setSelectedTrendAsin(null)
      return
    }

    if (selectedTrendAsin && sortedTrendProducts.some((product) => product.asin === selectedTrendAsin)) {
      return
    }

    setSelectedTrendAsin(sortedTrendProducts[0].asin)
  }, [selectedTrendAsin, sortedTrendProducts])

  const selectedTrendProduct = useMemo(
    () => sortedTrendProducts.find((product) => product.asin === selectedTrendAsin) || null,
    [selectedTrendAsin, sortedTrendProducts]
  )

  const overviewLoadingStates = [
    topPerformersLoading,
    categoryLoading,
    hourlyLoading,
    kpisLoading,
    productTrendsLoading,
  ]
  const completedRequests = overviewLoadingStates.filter((loading) => !loading).length
  const loadingProgress = (completedRequests / overviewLoadingStates.length) * 100
  const overviewLoading = overviewLoadingStates.some(Boolean)

  if (activeTab === 'overview' && overviewLoading) {
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

  const adsChartData = (adsVsOrganicData?.time_series || []).map((point) => ({
    ...point,
    displayDate: formatTimeBucketLabel(point.date, analyticsGroupBy, language),
    chartTotal: point.ad_sales + point.organic_sales,
  }))
  const adsChartAxisMax = getChartAxisMax(
    adsChartData.map((point) => Math.max(point.chartTotal, point.total_sales))
  )

  const selectedAsinProduct = asinOptions.find((product) => product.asin === selectedAsin)
  const returnReasonChartData = (returnsAnalytics?.reason_breakdown || []).slice(0, 6)
  const returnAsinChartData = (returnsAnalytics?.top_asins_by_returns || []).slice(0, 8).map((item) => ({
    ...item,
    displayLabel: truncateLabel(item.asin, 16),
  }))
  const returnTrendChartData = (returnsAnalytics?.return_rate_over_time || []).map((point) => ({
    ...point,
    displayDate: formatTimeBucketLabel(point.date, 'day', language),
  }))
  const returnAsinAxisMax = getChartAxisMax(
    returnAsinChartData.map((item) => item.quantity_returned || 0)
  )
  const returnTrendAxisMax = getChartAxisMax(
    returnTrendChartData.map((point) => point.returned_units || 0)
  )
  const highestReturnRateAsin = returnsAnalytics?.top_asins_by_return_rate?.[0]

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">{t('analytics.title')}</h1>
          <p className="text-muted-foreground">{t('analytics.subtitle')}</p>
        </div>
        <FilterBar onReset={handleResetAll}>
          <DateRangeFilter />
          <AccountFilter />
          {activeTab === 'overview' ? (
            <CategoryFilter
              value={analyticsCategory}
              onChange={setAnalyticsCategory}
              options={categoryOptions}
            />
          ) : activeTab === 'ads-vs-organic' ? (
            <>
              <GroupByFilter value={analyticsGroupBy} onChange={setAnalyticsGroupBy} />
              <Select value={selectedAsin} onValueChange={setSelectedAsin}>
                <SelectTrigger className="h-9 w-[220px] text-sm">
                  <SelectValue placeholder={t('analytics.asinFilter')} />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={ALL_ASINS_VALUE}>{t('analytics.allAsins')}</SelectItem>
                  {asinOptions.length > 0 ? (
                    asinOptions.map((product) => (
                      <SelectItem key={product.asin} value={product.asin}>
                        <span className="font-mono text-xs mr-2">{product.asin}</span>
                        {product.title ? truncateLabel(product.title, 36) : product.asin}
                      </SelectItem>
                    ))
                  ) : (
                    <SelectItem value="__no_asins__" disabled>
                      {t('analytics.noAsinsAvailable')}
                    </SelectItem>
                  )}
                </SelectContent>
              </Select>
            </>
          ) : null}
        </FilterBar>
      </div>

      <Tabs value={activeTab} onValueChange={(value) => setActiveTab(value as AnalyticsTab)} className="space-y-4">
        <TabsList>
          <TabsTrigger value="overview">{t('analytics.overviewTab')}</TabsTrigger>
          <TabsTrigger value="returns">{t('analytics.returnsTab')}</TabsTrigger>
          <TabsTrigger value="ads-vs-organic">{t('analytics.adsVsOrganicTab')}</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="space-y-6">
          <div className="grid gap-4 md:grid-cols-2">
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
                          formatter={(value: number) => [
                            formatCurrency(Number(value)),
                            t('common.revenue'),
                          ]}
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
              <CardContent className="space-y-4">
                {productTrends && productTrends.summary.eligible_products > 0 ? (
                  <>
                    <div className="grid gap-4 md:grid-cols-3 xl:grid-cols-6">
                      <div className="rounded-lg border p-4">
                        <p className="text-sm text-muted-foreground">{t('analytics.fastRisers')}</p>
                        <p className="mt-2 text-2xl font-bold">
                          {formatNumber(productTrends.summary.trend_class_counts.rising_fast)}
                        </p>
                      </div>
                      <div className="rounded-lg border p-4">
                        <p className="text-sm text-muted-foreground">{t('analytics.fastDecliners')}</p>
                        <p className="mt-2 text-2xl font-bold">
                          {formatNumber(productTrends.summary.trend_class_counts.declining_fast)}
                        </p>
                      </div>
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
                    </div>

                    <div className="grid gap-4 xl:grid-cols-2">
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

                    <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_220px_auto]">
                      <Input
                        value={trendAsinFilter}
                        onChange={(event) => setTrendSearchParam('asin', event.target.value || null)}
                        placeholder={t('analytics.filterAsinPlaceholder')}
                      />
                      <Select
                        value={trendClassFilter}
                        onValueChange={(value) => setTrendSearchParam('trend_class', value)}
                      >
                        <SelectTrigger>
                          <SelectValue placeholder={t('analytics.trendClassFilter')} />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="all">{t('analytics.trendClass.all')}</SelectItem>
                          <SelectItem value="rising_fast">{t('analytics.trendClass.rising_fast')}</SelectItem>
                          <SelectItem value="rising">{t('analytics.trendClass.rising')}</SelectItem>
                          <SelectItem value="stable">{t('analytics.trendClass.stable')}</SelectItem>
                          <SelectItem value="declining">{t('analytics.trendClass.declining')}</SelectItem>
                          <SelectItem value="declining_fast">{t('analytics.trendClass.declining_fast')}</SelectItem>
                        </SelectContent>
                      </Select>
                      <div className="flex items-center justify-end gap-2">
                        {scopedAccountId ? (
                          <Badge variant="outline">{t('analytics.accountScopeApplied')}</Badge>
                        ) : null}
                        {(trendAsinFilter || trendClassFilter !== 'all') ? (
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => {
                              setTrendSearchParam('asin', null)
                              setTrendSearchParam('trend_class', null)
                            }}
                          >
                            {t('analytics.clearTrendFilters')}
                          </Button>
                        ) : null}
                      </div>
                    </div>

                    <div className="grid gap-4 xl:grid-cols-[minmax(0,1.8fr)_minmax(320px,1fr)]">
                      <div className="overflow-hidden rounded-lg border">
                        <div className="overflow-x-auto">
                          <table className="w-full text-sm">
                            <thead className="bg-muted/40 text-left">
                              <tr className="border-b">
                                <th className="px-4 py-3">
                                  <button
                                    type="button"
                                    onClick={() => handleTrendSort('title')}
                                    className="flex items-center gap-2 font-semibold"
                                  >
                                    {t('analytics.tableProduct')}
                                    <ArrowUpDown className="h-3.5 w-3.5" />
                                  </button>
                                </th>
                                <th className="px-4 py-3 font-semibold">{t('analytics.tableTrend')}</th>
                                <th className="px-4 py-3">
                                  <button
                                    type="button"
                                    onClick={() => handleTrendSort('sales_delta_percent')}
                                    className="flex items-center gap-2 font-semibold"
                                  >
                                    {t('analytics.tableSalesDelta')}
                                    <ArrowUpDown className="h-3.5 w-3.5" />
                                  </button>
                                </th>
                                <th className="px-4 py-3">
                                  <button
                                    type="button"
                                    onClick={() => handleTrendSort('trend_score')}
                                    className="flex items-center gap-2 font-semibold"
                                  >
                                    {t('analytics.tableScore')}
                                    <ArrowUpDown className="h-3.5 w-3.5" />
                                  </button>
                                </th>
                                <th className="px-4 py-3 font-semibold">{t('analytics.tableSignal')}</th>
                                <th className="px-4 py-3 font-semibold">{t('analytics.tableSparkline')}</th>
                              </tr>
                            </thead>
                            <tbody>
                              {pagedTrendProducts.map((product) => (
                                <tr
                                  key={product.asin}
                                  className="cursor-pointer border-b transition-colors hover:bg-muted/20"
                                  onClick={() => setSelectedTrendAsin(product.asin)}
                                >
                                  <td className="px-4 py-3">
                                    <div className="min-w-[180px]">
                                      <p className="truncate font-medium">{product.title || product.asin}</p>
                                      <p className="mt-1 font-mono text-xs text-muted-foreground">{product.asin}</p>
                                    </div>
                                  </td>
                                  <td className="px-4 py-3">
                                    <ProductTrendBadge trendClass={product.trend_class} />
                                  </td>
                                  <td className="px-4 py-3 font-semibold">
                                    {formatChangePercent(product.sales_delta_percent)}
                                  </td>
                                  <td className="px-4 py-3">
                                    {product.trend_score > 0 ? '+' : ''}
                                    {product.trend_score.toFixed(1)}
                                  </td>
                                  <td className="px-4 py-3 text-muted-foreground">
                                    <div className="max-w-[260px]">
                                      {product.supporting_signals[0] || '-'}
                                    </div>
                                  </td>
                                  <td className="px-4 py-3">
                                    <div className="w-[140px]">
                                      <ProductTrendSparkline
                                        data={product.recent_sales}
                                        trendClass={product.trend_class}
                                        metric="revenue"
                                        height={40}
                                      />
                                    </div>
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                        {trendTotalPages > 1 && (
                          <div className="flex items-center justify-between border-t px-4 py-3">
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => setTrendPage((p) => Math.max(0, p - 1))}
                              disabled={trendPage === 0}
                            >
                              <ChevronLeft className="h-4 w-4" />
                            </Button>
                            <span className="text-xs text-muted-foreground">
                              {trendPage + 1} / {trendTotalPages}
                            </span>
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => setTrendPage((p) => Math.min(trendTotalPages - 1, p + 1))}
                              disabled={trendPage >= trendTotalPages - 1}
                            >
                              <ChevronRight className="h-4 w-4" />
                            </Button>
                          </div>
                        )}
                      </div>

                      <Card>
                        <CardHeader>
                          <CardTitle>{t('analytics.productDrilldown')}</CardTitle>
                          <CardDescription>{t('analytics.productDrilldownDesc')}</CardDescription>
                        </CardHeader>
                        <CardContent>
                          {selectedTrendProduct ? (
                            <div className="space-y-4">
                              <div className="flex items-start justify-between gap-3">
                                <div className="min-w-0">
                                  <p className="truncate text-lg font-semibold">
                                    {selectedTrendProduct.title || selectedTrendProduct.asin}
                                  </p>
                                  <p className="mt-1 font-mono text-xs text-muted-foreground">
                                    {selectedTrendProduct.asin}
                                  </p>
                                </div>
                                <ProductTrendBadge trendClass={selectedTrendProduct.trend_class} />
                              </div>

                              <div className="grid gap-3 sm:grid-cols-2">
                                <div className="rounded-lg border p-3">
                                  <p className="text-xs text-muted-foreground">{t('analytics.tableSalesDelta')}</p>
                                  <p className="mt-2 text-xl font-semibold">
                                    {formatChangePercent(selectedTrendProduct.sales_delta_percent)}
                                  </p>
                                </div>
                                <div className="rounded-lg border p-3">
                                  <p className="text-xs text-muted-foreground">{t('analytics.tableScore')}</p>
                                  <p className="mt-2 text-xl font-semibold">
                                    {selectedTrendProduct.trend_score > 0 ? '+' : ''}
                                    {selectedTrendProduct.trend_score.toFixed(1)}
                                  </p>
                                </div>
                                <div className="rounded-lg border p-3">
                                  <p className="text-xs text-muted-foreground">{t('analytics.current7DaySales')}</p>
                                  <p className="mt-2 text-xl font-semibold">
                                    {formatCurrency(selectedTrendProduct.current_revenue)}
                                  </p>
                                </div>
                                <div className="rounded-lg border p-3">
                                  <p className="text-xs text-muted-foreground">{t('analytics.previous7DaySales')}</p>
                                  <p className="mt-2 text-xl font-semibold">
                                    {formatCurrency(selectedTrendProduct.previous_revenue)}
                                  </p>
                                </div>
                              </div>

                              <div className="h-36 rounded-lg border p-3">
                                <ProductTrendSparkline
                                  data={selectedTrendProduct.recent_sales}
                                  trendClass={selectedTrendProduct.trend_class}
                                  metric="revenue"
                                  height={120}
                                  showTooltip
                                />
                              </div>

                              <div className="space-y-2">
                                <p className="text-sm font-semibold">{t('analytics.supportingSignals')}</p>
                                <div className="space-y-2">
                                  {selectedTrendProduct.supporting_signals.map((signal) => (
                                    <div key={signal} className="rounded-lg border p-3 text-sm text-muted-foreground">
                                      {signal}
                                    </div>
                                  ))}
                                </div>
                              </div>
                            </div>
                          ) : (
                            <div className="flex min-h-[240px] items-center justify-center text-sm text-muted-foreground">
                              {t('analytics.noTrendData')}
                            </div>
                          )}
                        </CardContent>
                      </Card>
                    </div>
                  </>
                ) : (
                  <div className="flex min-h-[160px] items-center justify-center text-sm text-muted-foreground">
                    {t('analytics.noTrendData')}
                  </div>
                )}
              </CardContent>
            </Card>

            {productTrends && (
              <TrendInsightsCard
                insights={productTrends.insights}
                generatedWithAi={productTrends.generated_with_ai}
                aiAvailable={productTrends.ai_available}
              />
            )}
          </div>
        </TabsContent>

        <TabsContent value="returns" className="space-y-6">
          {returnsLoading ? (
            <Card>
              <CardContent className="flex min-h-[320px] items-center justify-center">
                <div className="flex items-center gap-3 text-sm text-muted-foreground">
                  <Loader2 className="h-5 w-5 animate-spin" />
                  <span>{t('common.loading')}</span>
                </div>
              </CardContent>
            </Card>
          ) : (
            <>
              <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
                <div className="rounded-lg border p-4">
                  <p className="text-sm text-muted-foreground">{t('analytics.returns.totalReturns')}</p>
                  <p className="mt-2 text-2xl font-bold">
                    {formatNumber(returnsAnalytics?.summary.total_returns || 0)}
                  </p>
                </div>
                <div className="rounded-lg border p-4">
                  <p className="text-sm text-muted-foreground">{t('analytics.returns.overallRate')}</p>
                  <p className="mt-2 text-2xl font-bold">
                    {formatOptionalPercent(returnsAnalytics?.summary.return_rate)}
                  </p>
                </div>
                <div className="rounded-lg border p-4">
                  <p className="text-sm text-muted-foreground">{t('analytics.returns.topReason')}</p>
                  <p className="mt-2 text-2xl font-bold">
                    {returnsAnalytics?.summary.top_reason || t('analytics.returns.unknownReason')}
                  </p>
                </div>
                <div className="rounded-lg border p-4">
                  <p className="text-sm text-muted-foreground">{t('analytics.returns.highestRateAsin')}</p>
                  {highestReturnRateAsin ? (
                    <>
                      <p className="mt-2 text-2xl font-bold">{highestReturnRateAsin.asin}</p>
                      <p className="mt-1 text-sm text-muted-foreground">
                        {formatOptionalPercent(highestReturnRateAsin.return_rate)}
                      </p>
                    </>
                  ) : (
                    <p className="mt-2 text-2xl font-bold">{t('analytics.returns.highestRateEmpty')}</p>
                  )}
                </div>
              </div>

              <div className="rounded-lg border bg-muted/30 px-4 py-3 text-sm text-muted-foreground">
                {returnsAnalytics?.summary.return_rate_available
                  ? t('analytics.returns.rateAvailable')
                  : t('analytics.returns.rateUnavailable')}
              </div>

              <div className="grid gap-4 xl:grid-cols-2">
                <Card>
                  <CardHeader>
                    <CardTitle>{t('analytics.returns.reasonBreakdown')}</CardTitle>
                    <CardDescription>{t('analytics.returns.reasonBreakdownDesc')}</CardDescription>
                  </CardHeader>
                  <CardContent>
                    <div className="h-[320px]">
                      {returnReasonChartData.length > 0 ? (
                        <ResponsiveContainer width="100%" height="100%">
                          <PieChart>
                            <Pie
                              data={returnReasonChartData}
                              dataKey="quantity"
                              nameKey="reason"
                              innerRadius={68}
                              outerRadius={108}
                              paddingAngle={3}
                            >
                              {returnReasonChartData.map((entry, index) => (
                                <Cell
                                  key={entry.reason}
                                  fill={RETURN_REASON_COLORS[index % RETURN_REASON_COLORS.length]}
                                />
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
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader>
                    <CardTitle>{t('analytics.returns.topReturnedAsins')}</CardTitle>
                    <CardDescription>{t('analytics.returns.topReturnedAsinsDesc')}</CardDescription>
                  </CardHeader>
                  <CardContent>
                    <div className="h-[320px]">
                      {returnAsinChartData.length > 0 ? (
                        <ResponsiveContainer width="100%" height="100%">
                          <BarChart
                            data={returnAsinChartData}
                            layout="vertical"
                            margin={{ top: 8, right: 16, bottom: 8, left: 8 }}
                          >
                            <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                            <XAxis
                              type="number"
                              domain={[0, returnAsinAxisMax]}
                              tickCount={6}
                              axisLine={false}
                              tickLine={false}
                            />
                            <YAxis
                              type="category"
                              dataKey="displayLabel"
                              width={118}
                              axisLine={false}
                              tickLine={false}
                            />
                            <Tooltip
                              labelFormatter={(_label, payload) => payload?.[0]?.payload?.asin || ''}
                              formatter={(value: number) => [
                                formatNumber(Number(value)),
                                t('analytics.returns.quantityReturned'),
                              ]}
                            />
                            <Bar
                              dataKey="quantity_returned"
                              fill="hsl(var(--primary))"
                              radius={[0, 4, 4, 0]}
                            />
                          </BarChart>
                        </ResponsiveContainer>
                      ) : (
                        <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
                          {t('analytics.returns.noAsinData')}
                        </div>
                      )}
                    </div>
                  </CardContent>
                </Card>
              </div>

              <Card>
                <CardHeader>
                  <CardTitle>{t('analytics.returns.trend')}</CardTitle>
                  <CardDescription>{t('analytics.returns.trendDesc')}</CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="h-[320px]">
                    {returnTrendChartData.length > 0 ? (
                      <ResponsiveContainer width="100%" height="100%">
                        <LineChart data={returnTrendChartData} margin={{ top: 8, right: 16, bottom: 8, left: 8 }}>
                          <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                          <XAxis dataKey="displayDate" axisLine={false} tickLine={false} />
                          <YAxis
                            domain={[0, returnTrendAxisMax]}
                            tickCount={6}
                            axisLine={false}
                            tickLine={false}
                          />
                          <Tooltip
                            labelFormatter={(_label, payload) => {
                              const point = payload?.[0]?.payload
                              if (!point) {
                                return ''
                              }

                              const rateLabel =
                                point.return_rate != null
                                  ? ` · ${formatOptionalPercent(point.return_rate)}`
                                  : ''
                              return `${point.displayDate}${rateLabel}`
                            }}
                            formatter={(value: number) => [
                              formatNumber(Number(value)),
                              t('analytics.returns.quantityReturned'),
                            ]}
                          />
                          <Line
                            type="monotone"
                            dataKey="returned_units"
                            stroke="#2563eb"
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
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle>{t('analytics.returns.detailTitle')}</CardTitle>
                  <CardDescription>{t('analytics.returns.detailDesc')}</CardDescription>
                </CardHeader>
                <CardContent>
                  {returnsAnalytics?.top_asins_by_returns?.length ? (
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="border-b">
                            <th className="px-2 py-3 text-left font-medium">{t('reports.asin')}</th>
                            <th className="px-2 py-3 text-right font-medium">{t('analytics.returns.quantityReturned')}</th>
                            <th className="px-2 py-3 text-left font-medium">{t('analytics.returns.primaryReason')}</th>
                            <th className="px-2 py-3 text-left font-medium">{t('analytics.returns.disposition')}</th>
                            <th className="px-2 py-3 text-right font-medium">{t('analytics.returns.overallRate')}</th>
                          </tr>
                        </thead>
                        <tbody>
                          {returnsAnalytics.top_asins_by_returns.map((item) => (
                            <tr key={item.asin} className="border-b last:border-0">
                              <td className="px-2 py-3 align-top">
                                <div className="font-mono">{item.asin}</div>
                                {item.sku && (
                                  <div className="text-xs text-muted-foreground">{item.sku}</div>
                                )}
                              </td>
                              <td className="px-2 py-3 text-right align-top">
                                {formatNumber(item.quantity_returned)}
                              </td>
                              <td className="px-2 py-3 align-top">
                                {item.primary_reason || t('analytics.returns.unknownReason')}
                              </td>
                              <td className="px-2 py-3 align-top">
                                {item.disposition || t('analytics.returns.unavailable')}
                              </td>
                              <td className="px-2 py-3 text-right align-top">
                                {formatOptionalPercent(item.return_rate)}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <div className="flex min-h-[180px] items-center justify-center text-sm text-muted-foreground">
                      {t('analytics.returns.noAsinData')}
                    </div>
                  )}
                </CardContent>
              </Card>
            </>
          )}
        </TabsContent>

        <TabsContent value="ads-vs-organic" className="space-y-6">
          {adsVsOrganicLoading ? (
            <Card>
              <CardContent className="flex min-h-[320px] items-center justify-center">
                <div className="flex items-center gap-3 text-sm text-muted-foreground">
                  <Loader2 className="h-5 w-5 animate-spin" />
                  <span>{t('common.loading')}</span>
                </div>
              </CardContent>
            </Card>
          ) : (
            <>
              <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
                <AdsVsOrganicKpiCard
                  label={t('analytics.totalSales')}
                  metric={adsVsOrganicData?.summary.total_sales}
                  formatter={formatCurrency}
                  comparisonLabel={t('analytics.vsPreviousPeriod')}
                />
                <AdsVsOrganicKpiCard
                  label={t('analytics.advertisingSales')}
                  metric={adsVsOrganicData?.summary.ad_sales}
                  formatter={formatCurrency}
                  comparisonLabel={t('analytics.vsPreviousPeriod')}
                />
                <AdsVsOrganicKpiCard
                  label={t('analytics.organicSales')}
                  metric={adsVsOrganicData?.summary.organic_sales}
                  formatter={formatCurrency}
                  comparisonLabel={t('analytics.vsPreviousPeriod')}
                />
                <AdsVsOrganicKpiCard
                  label={t('analytics.shareFromAds')}
                  metric={adsVsOrganicData?.summary.ad_share_pct}
                  formatter={formatPercentValue}
                  comparisonLabel={t('analytics.vsPreviousPeriod')}
                />
                <AdsVsOrganicKpiCard
                  label={t('analytics.shareOrganic')}
                  metric={adsVsOrganicData?.summary.organic_share_pct}
                  formatter={formatPercentValue}
                  comparisonLabel={t('analytics.vsPreviousPeriod')}
                />
              </div>

              {selectedAsin !== ALL_ASINS_VALUE && (
                <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
                  <p className="font-medium">{t('analytics.accountLevelAttribution')}</p>
                  <p className="mt-1">{t('analytics.asinAttributionNotice')}</p>
                </div>
              )}

              <div className="grid gap-4 lg:grid-cols-3">
                <Card className="lg:col-span-2">
                  <CardHeader>
                    <CardTitle>{t('analytics.adsVsOrganic')}</CardTitle>
                    <CardDescription>
                      {selectedAsin !== ALL_ASINS_VALUE
                        ? `${selectedAsinProduct?.title || selectedAsin} (${selectedAsin})`
                        : t('analytics.adsVsOrganicDesc')}
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    <div className="h-[360px]">
                      {adsChartData.length > 0 ? (
                        <ResponsiveContainer width="100%" height="100%">
                          <BarChart data={adsChartData} margin={{ top: 8, right: 12, left: 8, bottom: 12 }}>
                            <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                            <XAxis
                              dataKey="displayDate"
                              axisLine={false}
                              tickLine={false}
                            />
                            <YAxis
                              domain={[0, adsChartAxisMax]}
                              tickCount={6}
                              axisLine={false}
                              tickLine={false}
                              tickFormatter={(value) => formatAxisCurrency(Number(value))}
                            />
                            <Tooltip
                              labelFormatter={(_label, payload) => payload?.[0]?.payload?.displayDate || ''}
                              formatter={(value: number, name: string) => [
                                formatCurrency(Number(value)),
                                name,
                              ]}
                            />
                            <Legend />
                            <Bar
                              dataKey="ad_sales"
                              name={t('analytics.advertisingSales')}
                              stackId="sales"
                              fill="#d97706"
                              radius={[4, 4, 0, 0]}
                            />
                            <Bar
                              dataKey="organic_sales"
                              name={t('analytics.organicSales')}
                              stackId="sales"
                              fill="#0f766e"
                              radius={[4, 4, 0, 0]}
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

                {selectedAsin === ALL_ASINS_VALUE && (adsVsOrganicData?.asin_breakdown?.length || 0) > 0 ? (
                  <Card>
                    <CardHeader>
                      <CardTitle>{t('analytics.topAsinSales')}</CardTitle>
                      <CardDescription>{t('analytics.topAsinSalesDesc')}</CardDescription>
                    </CardHeader>
                    <CardContent>
                      <AsinBreakdownList
                        items={(adsVsOrganicData?.asin_breakdown || []).slice(0, 8)}
                        onSelectAsin={setSelectedAsin}
                      />
                    </CardContent>
                  </Card>
                ) : (
                  <Card>
                    <CardHeader>
                      <CardTitle>{t('analytics.topAsinSales')}</CardTitle>
                      <CardDescription>{t('analytics.topAsinSalesDesc')}</CardDescription>
                    </CardHeader>
                    <CardContent className="flex min-h-[220px] items-center justify-center text-sm text-muted-foreground">
                      {selectedAsin === ALL_ASINS_VALUE
                        ? t('analytics.noAdsVsOrganicData')
                        : t('analytics.asinBreakdownHidden')}
                    </CardContent>
                  </Card>
                )}
              </div>
            </>
          )}
        </TabsContent>
      </Tabs>
    </div>
  )
}
