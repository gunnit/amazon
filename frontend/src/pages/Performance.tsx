import { useEffect, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  Cell,
  ComposedChart,
  Line,
  LineChart,
  Pie,
  PieChart,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts'
import {
  AlertTriangle,
  ArrowDownRight,
  ArrowUpDown,
  ArrowUpRight,
  ChevronLeft,
  ChevronRight,
  Download,
  Loader2,
  Minus,
} from 'lucide-react'
import { Link, useSearchParams } from 'react-router-dom'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
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
import { accountsApi, analyticsApi, catalogApi, reportsApi } from '@/services/api'
import { formatChangePercent, formatCurrency, formatNumber } from '@/lib/utils'
import {
  AREA_FILL,
  BAR_H_FILL,
  BAR_V_FILL,
  CHART_PRIMARY,
  CHART_SERIES,
} from '@/lib/chart-theme'
import {
  FilterBar,
  DateRangeFilter,
  AccountFilter,
  GroupByFilter,
  ToggleFilter,
} from '@/components/filters'
import { useFilterStore, getFilterDateRange } from '@/store/filterStore'
import { useTranslation } from '@/i18n'
import { ExportModal } from '@/components/ExportModal'
import { ScheduledReportsPanel } from '@/components/ScheduledReportsPanel'
import {
  granularityForSelection,
  formatPeriodLabel,
  fillMonthlyGaps,
} from '@/lib/granularity'
import { GranularityBadge } from '@/components/GranularityBadge'
import ProductTrendBadge from '@/components/analytics/ProductTrendBadge'
import ProductTrendSparkline from '@/components/analytics/ProductTrendSparkline'
import TrendInsightsCard from '@/components/analytics/TrendInsightsCard'
import { PerProductPerformanceTable } from '@/components/analytics/PerProductPerformanceTable'
import type {
  AdsConnectionState,
  AdsVsOrganicAsinBreakdownItem,
  AdsVsOrganicResponse,
  AdvertisingMetricsItem,
  AmazonAccount,
  HourlyOrdersData,
  InventoryReportItem,
  MetricValue,
  Product,
  ProductTrendClass,
  ProductTrendItem,
  ReturnsAnalyticsResponse,
  SalesAggregated,
} from '@/types'

type PerformanceTab = 'overview' | 'per-product' | 'returns' | 'ads-vs-organic' | 'inventory' | 'export'

const ALL_ASINS_VALUE = '__all_asins__'
const RETURN_REASON_COLORS = CHART_SERIES
const VENDOR_COLOR = CHART_SERIES[2]

type SalesRow = SalesAggregated & { origin: 'daily' | 'monthly' }

// Map old ?tab= deep-links and origin pages onto the merged tab set.
const TAB_ALIASES: Record<string, PerformanceTab> = {
  overview: 'overview',
  panoramica: 'overview',
  sales: 'overview',
  vendite: 'overview',
  'per-product': 'per-product',
  'per-asin': 'per-product',
  perasin: 'per-product',
  returns: 'returns',
  resi: 'returns',
  'ads-vs-organic': 'ads-vs-organic',
  advertising: 'ads-vs-organic',
  pubblicita: 'ads-vs-organic',
  inventory: 'inventory',
  inventario: 'inventory',
  export: 'export',
}

function ContextField({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className="mt-0.5 font-medium text-foreground">{value}</p>
    </div>
  )
}

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

function formatOptionalPercent(value: number | null | undefined): string {
  if (value == null) {
    return '-'
  }

  return `${value.toFixed(1)}%`
}

function resolveAdsState(account: AmazonAccount): AdsConnectionState {
  if (account.ads_connection_state) return account.ads_connection_state
  if (account.has_ads_client_credentials === false) return 'missing_client_credentials'
  if (!account.has_advertising_refresh_token) return 'missing_refresh_token'
  if (!account.advertising_profile_id) return 'missing_profile'
  return 'ok'
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

type SalesSortKey = 'date' | 'total_units' | 'total_sales' | 'total_orders'
type SalesSortDirection = 'asc' | 'desc'
const SALES_PAGE_SIZE = 20

function compareSalesRows(
  left: SalesRow,
  right: SalesRow,
  sortKey: SalesSortKey,
  sortDirection: SalesSortDirection
) {
  const modifier = sortDirection === 'asc' ? 1 : -1

  if (sortKey === 'date') {
    return modifier * (left.date.localeCompare(right.date) || left.origin.localeCompare(right.origin))
  }

  return modifier * (Number(left[sortKey]) - Number(right[sortKey]))
}

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

interface TabProps {
  active: boolean
  dateRange: { start: string; end: string }
  accountIds: string[]
}

// ── Panoramica: org sales KPI/trend + analytics overview ─────────────────────

interface PanoramicaTabProps extends TabProps {
  trendAccountIds: string[]
  scopedAccountId?: string
  trendAsinFilter: string
  trendClassFilter: ProductTrendClass | 'all'
  setTrendSearchParam: (key: 'asin' | 'trend_class', value: string | null) => void
}

function PanoramicaTab({
  active,
  dateRange,
  accountIds,
  trendAccountIds,
  scopedAccountId,
  trendAsinFilter,
  trendClassFilter,
  setTrendSearchParam,
}: PanoramicaTabProps) {
  const { t, language } = useTranslation()
  const { reportsGroupBy } = useFilterStore()
  const [trendSortKey, setTrendSortKey] = useState<TrendSortKey>('sales_delta_percent')
  const [trendSortDirection, setTrendSortDirection] = useState<TrendSortDirection>('desc')
  const [selectedTrendAsin, setSelectedTrendAsin] = useState<string | null>(null)
  const [trendPage, setTrendPage] = useState(0)
  const TREND_PAGE_SIZE = 5
  const [salesSortKey, setSalesSortKey] = useState<SalesSortKey>('date')
  const [salesSortDirection, setSalesSortDirection] = useState<SalesSortDirection>('desc')
  const [salesPage, setSalesPage] = useState(0)

  const { data: allAccounts = [] } = useQuery<AmazonAccount[]>({
    queryKey: ['accounts'],
    queryFn: () => accountsApi.list(),
  })
  const salesGranularity = granularityForSelection(allAccounts, accountIds)

  const inScopeAccounts =
    accountIds.length > 0
      ? allAccounts.filter((account) => accountIds.includes(account.id))
      : allAccounts
  const sellerAccountIds = inScopeAccounts
    .filter((account) => account.account_type === 'seller')
    .map((account) => account.id)
  const vendorAccountIds = inScopeAccounts
    .filter((account) => account.account_type === 'vendor')
    .map((account) => account.id)
  const hasSeller = sellerAccountIds.length > 0
  const hasVendor = vendorAccountIds.length > 0
  const isMixed = salesGranularity === 'mixed'

  // Combined query drives the headline totals. It keeps the org-level aggregation
  // intact, so the KPI cards match Dashboard/exports to the cent.
  const { data: combinedSales, isLoading } = useQuery<SalesAggregated[]>({
    queryKey: ['sales-aggregated', dateRange, accountIds, reportsGroupBy],
    queryFn: () => reportsApi.getSalesAggregated({
      start_date: dateRange.start,
      end_date: dateRange.end,
      account_ids: accountIds.length > 0 ? accountIds : undefined,
      group_by: reportsGroupBy !== 'day' ? reportsGroupBy : undefined,
    }),
    enabled: active,
  })

  const { data: sellerSales } = useQuery<SalesAggregated[]>({
    queryKey: ['sales-aggregated-seller', dateRange, sellerAccountIds, reportsGroupBy],
    queryFn: () => reportsApi.getSalesAggregated({
      start_date: dateRange.start,
      end_date: dateRange.end,
      account_ids: sellerAccountIds,
      group_by: reportsGroupBy !== 'day' ? reportsGroupBy : undefined,
    }),
    enabled: active && isMixed && hasSeller,
  })

  const { data: vendorSales } = useQuery<SalesAggregated[]>({
    queryKey: ['sales-aggregated-vendor', dateRange, vendorAccountIds, reportsGroupBy],
    queryFn: () => reportsApi.getSalesAggregated({
      start_date: dateRange.start,
      end_date: dateRange.end,
      account_ids: vendorAccountIds,
      group_by: 'month',
    }),
    enabled: active && isMixed && hasVendor,
  })

  const { data: topPerformers, isLoading: topPerformersLoading } = useQuery({
    queryKey: ['top-performers', dateRange, trendAccountIds],
    queryFn: () => analyticsApi.getTopPerformers({
      start_date: dateRange.start,
      end_date: dateRange.end,
      limit: 10,
      account_ids: trendAccountIds.length > 0 ? trendAccountIds : undefined,
    }),
    enabled: active,
  })

  const { data: ordersByHour, isLoading: hourlyLoading } = useQuery<HourlyOrdersData[]>({
    queryKey: ['orders-by-hour', dateRange, trendAccountIds],
    queryFn: () => analyticsApi.getOrdersByHour({
      start_date: dateRange.start,
      end_date: dateRange.end,
      account_ids: trendAccountIds.length > 0 ? trendAccountIds : undefined,
    }),
    enabled: active,
  })

  const { data: kpis, isLoading: kpisLoading } = useQuery({
    queryKey: ['dashboard-kpis-analytics', dateRange, trendAccountIds],
    queryFn: () => analyticsApi.getDashboard({
      start_date: dateRange.start,
      end_date: dateRange.end,
      account_ids: trendAccountIds.length > 0 ? trendAccountIds : undefined,
    }),
    enabled: active,
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
    enabled: active,
  })

  const { data: productTrendInsights, isFetching: productTrendInsightsFetching } = useQuery({
    queryKey: ['product-trend-insights', dateRange, trendAccountIds, trendAsinFilter, trendClassFilter, language],
    queryFn: () => analyticsApi.getProductTrendInsights({
      start_date: dateRange.start,
      end_date: dateRange.end,
      account_id: scopedAccountId,
      account_ids: scopedAccountId ? undefined : trendAccountIds.length > 0 ? trendAccountIds : undefined,
      asin: trendAsinFilter || undefined,
      trend_class: trendClassFilter === 'all' ? undefined : trendClassFilter,
      language,
      limit: 100,
    }),
    enabled: active && (productTrends?.summary.eligible_products ?? 0) > 0,
  })

  const handleTrendSort = (sortKey: TrendSortKey) => {
    if (trendSortKey === sortKey) {
      setTrendSortDirection((current) => (current === 'desc' ? 'asc' : 'desc'))
      return
    }

    setTrendSortKey(sortKey)
    setTrendSortDirection(sortKey === 'title' ? 'asc' : 'desc')
  }

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
    hourlyLoading,
    kpisLoading,
    productTrendsLoading,
  ]
  const completedRequests = overviewLoadingStates.filter((loading) => !loading).length
  const loadingProgress = (completedRequests / overviewLoadingStates.length) * 100
  const overviewLoading = overviewLoadingStates.some(Boolean)

  const totals = combinedSales?.reduce(
    (acc, row) => ({
      totalUnits: acc.totalUnits + Number(row.total_units),
      totalSales: acc.totalSales + Number(row.total_sales),
      totalOrders: acc.totalOrders + Number(row.total_orders),
    }),
    { totalUnits: 0, totalSales: 0, totalOrders: 0 }
  ) || { totalUnits: 0, totalSales: 0, totalOrders: 0 }

  const salesCurrency =
    combinedSales?.[0]?.currency || sellerSales?.[0]?.currency || vendorSales?.[0]?.currency || 'EUR'

  const salesRows: SalesRow[] = isMixed
    ? [
        ...(sellerSales ?? []).map((row): SalesRow => ({ ...row, origin: 'daily' })),
        ...(vendorSales ?? []).map((row): SalesRow => ({ ...row, origin: 'monthly' })),
      ].sort((a, b) => a.date.localeCompare(b.date) || a.origin.localeCompare(b.origin))
    : (() => {
        const origin: SalesRow['origin'] =
          salesGranularity === 'monthly' || reportsGroupBy === 'month' ? 'monthly' : 'daily'
        const rows = (combinedSales ?? []).map((row): SalesRow => ({ ...row, origin }))
        if (reportsGroupBy === 'month' || salesGranularity === 'monthly') {
          return fillMonthlyGaps(rows, (monthKey) => ({
            date: monthKey,
            total_units: 0,
            total_sales: 0,
            total_orders: 0,
            currency: salesCurrency,
            origin,
          }))
        }
        return rows
      })()

  const showOriginColumn = isMixed

  const sortedSalesRows = useMemo(
    () => [...salesRows].sort((left, right) => compareSalesRows(left, right, salesSortKey, salesSortDirection)),
    [salesRows, salesSortKey, salesSortDirection]
  )
  const salesTotalPages = Math.max(1, Math.ceil(sortedSalesRows.length / SALES_PAGE_SIZE))
  const pagedSalesRows = useMemo(
    () => sortedSalesRows.slice(salesPage * SALES_PAGE_SIZE, (salesPage + 1) * SALES_PAGE_SIZE),
    [sortedSalesRows, salesPage]
  )

  useEffect(() => {
    setSalesPage(0)
  }, [sortedSalesRows.length, salesSortKey, salesSortDirection])

  const handleSalesSort = (sortKey: SalesSortKey) => {
    if (salesSortKey === sortKey) {
      setSalesSortDirection((current) => (current === 'desc' ? 'asc' : 'desc'))
      return
    }

    setSalesSortKey(sortKey)
    setSalesSortDirection('desc')
  }

  const groupByLabel =
    reportsGroupBy === 'week'
      ? t('reports.weeklySales')
      : reportsGroupBy === 'month'
      ? t('reports.monthlySales')
      : t('reports.dailySales')

  const sumBy = (rows: SalesAggregated[] | undefined, key: 'total_sales' | 'total_units') => {
    const map = new Map<string, number>()
    for (const row of rows ?? []) {
      map.set(row.date, (map.get(row.date) ?? 0) + Number(row[key]))
    }
    return map
  }
  const mixedRevenue = (() => {
    const seller = sumBy(sellerSales, 'total_sales')
    const vendor = sumBy(vendorSales, 'total_sales')
    const dates = new Set([...seller.keys(), ...vendor.keys()])
    return Array.from(dates)
      .sort()
      .map((date) => ({ date, seller: seller.get(date), vendor: vendor.get(date) }))
  })()
  const singleSeries = salesRows.map((row) => ({
    date: row.date,
    value: Number(row.total_sales),
  }))
  const hasChartData = isMixed ? mixedRevenue.length > 0 : singleSeries.length > 0
  const chartGroupBy: 'day' | 'week' | 'month' =
    reportsGroupBy === 'month' || salesGranularity === 'monthly' ? 'month' : reportsGroupBy
  const axisLabel = (value: string) =>
    formatPeriodLabel(value, isMixed ? 'day' : chartGroupBy, language)
  const compactCurrency = new Intl.NumberFormat('it-IT', {
    style: 'currency',
    currency: salesCurrency,
    notation: 'compact',
    maximumFractionDigits: 1,
  })

  const salesTrendDescription = isMixed
    ? t('reports.trendDescMixed')
    : salesGranularity === 'monthly' || reportsGroupBy === 'month'
    ? t('reports.trendDescMonthly')
    : t('reports.trendDescDaily')

  const contextAccounts =
    accountIds.length === 0
      ? t('reports.context.allAccounts')
      : inScopeAccounts.map((account) => account.account_name).join(', ')
  const contextMarketplaces =
    Array.from(new Set(inScopeAccounts.map((account) => account.marketplace_country))).join(', ') || '—'
  const contextType =
    hasSeller && hasVendor
      ? t('reports.type.mixed')
      : hasVendor
      ? t('reports.type.vendor')
      : hasSeller
      ? t('reports.type.seller')
      : '—'
  const contextGranularity =
    salesGranularity === 'mixed'
      ? t('reports.granularity.mixed')
      : salesGranularity === 'monthly'
      ? t('reports.granularity.monthly')
      : salesGranularity === 'daily'
      ? t('reports.granularity.daily')
      : '—'

  const topProductsChartData = (topPerformers?.by_revenue || []).slice(0, 5).map((product) => ({
    ...product,
    displayLabel: truncateLabel(product.title || product.asin, 22),
  }))
  const topProductsAxisMax = getChartAxisMax(
    topProductsChartData.map((product) => Number(product.total_revenue) || 0)
  )

  if (overviewLoading) {
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

  return (
    <div className="space-y-6">
      {/* Data context — keeps the team from misreading a client's numbers */}
      <Card>
        <CardContent className="flex flex-wrap gap-x-8 gap-y-3 py-4 text-sm">
          <ContextField label={t('reports.context.accounts')} value={contextAccounts} />
          <ContextField label={t('reports.context.marketplace')} value={contextMarketplaces} />
          <ContextField label={t('reports.context.type')} value={contextType} />
          <ContextField label={t('reports.context.granularity')} value={contextGranularity} />
          <ContextField
            label={t('reports.context.period')}
            value={`${formatPeriodLabel(dateRange.start, 'day', language)} – ${formatPeriodLabel(dateRange.end, 'day', language)}`}
          />
        </CardContent>
      </Card>

      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardContent className="pt-6">
            <div className="text-2xl font-bold">{formatCurrency(totals.totalSales, salesCurrency)}</div>
            <p className="text-sm text-muted-foreground">{t('reports.totalRevenue')}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="text-2xl font-bold">{formatNumber(totals.totalUnits)}</div>
            <p className="text-sm text-muted-foreground">{t('reports.unitsSold')}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="text-2xl font-bold">{formatNumber(totals.totalOrders)}</div>
            <p className="text-sm text-muted-foreground">{t('reports.totalOrders')}</p>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-start justify-between gap-2">
            <CardTitle className="text-base">{t('reports.salesTrend')}</CardTitle>
            <GranularityBadge granularity={salesGranularity} />
          </div>
          <CardDescription className="text-xs">{salesTrendDescription}</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="h-[280px]">
            {isLoading ? (
              <div className="flex h-full items-center justify-center">
                <Loader2 className="h-8 w-8 animate-spin text-primary" />
              </div>
            ) : !hasChartData ? (
              <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
                {t('reports.noSalesData')}
              </div>
            ) : isMixed ? (
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={mixedRevenue}>
                  <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                  <XAxis dataKey="date" tickFormatter={axisLabel} />
                  <YAxis tickFormatter={(value) => compactCurrency.format(value)} />
                  <Tooltip
                    formatter={(value: number) => formatCurrency(value, salesCurrency)}
                    labelFormatter={(label: string) => formatPeriodLabel(label, 'day', language)}
                  />
                  <Legend />
                  <Bar
                    dataKey="vendor"
                    name={t('reports.type.vendor')}
                    fill={VENDOR_COLOR}
                    fillOpacity={0.85}
                    radius={[4, 4, 0, 0]}
                    maxBarSize={36}
                  />
                  <Area
                    type="monotone"
                    dataKey="seller"
                    name={t('reports.type.seller')}
                    stroke={CHART_PRIMARY}
                    strokeWidth={2}
                    fill={AREA_FILL}
                  />
                </ComposedChart>
              </ResponsiveContainer>
            ) : chartGroupBy === 'month' ? (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={singleSeries}>
                  <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                  <XAxis dataKey="date" tickFormatter={axisLabel} />
                  <YAxis tickFormatter={(value) => compactCurrency.format(value)} />
                  <Tooltip
                    formatter={(value: number) => [formatCurrency(value, salesCurrency), t('common.revenue')]}
                    labelFormatter={axisLabel}
                  />
                  <Bar dataKey="value" fill={VENDOR_COLOR} fillOpacity={0.85} radius={[4, 4, 0, 0]} maxBarSize={36} />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={singleSeries}>
                  <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                  <XAxis dataKey="date" tickFormatter={axisLabel} />
                  <YAxis tickFormatter={(value) => compactCurrency.format(value)} />
                  <Tooltip
                    formatter={(value: number) => [formatCurrency(value, salesCurrency), t('common.revenue')]}
                    labelFormatter={axisLabel}
                  />
                  <Area type="monotone" dataKey="value" stroke={CHART_PRIMARY} strokeWidth={2} fill={AREA_FILL} />
                </AreaChart>
              </ResponsiveContainer>
            )}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div className="flex items-start justify-between gap-2">
            <CardTitle>{groupByLabel}</CardTitle>
            <GranularityBadge granularity={salesGranularity} />
          </div>
          <CardDescription>
            {formatPeriodLabel(dateRange.start, 'day', language)} – {formatPeriodLabel(dateRange.end, 'day', language)}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="flex items-center justify-center h-32">
              <Loader2 className="h-8 w-8 animate-spin text-primary" />
            </div>
          ) : sortedSalesRows.length > 0 ? (
            <div className="space-y-3">
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className="border-b">
                      <th className="py-3 px-4 font-medium">
                        <button
                          type="button"
                          onClick={() => handleSalesSort('date')}
                          className="flex items-center gap-1.5 font-medium"
                        >
                          {t('reports.date')}
                          <ArrowUpDown className="h-3.5 w-3.5 text-muted-foreground" />
                        </button>
                      </th>
                      {showOriginColumn && (
                        <th className="text-left py-3 px-4 font-medium">{t('reports.colOrigin')}</th>
                      )}
                      <th className="py-3 px-4 font-medium">
                        <button
                          type="button"
                          onClick={() => handleSalesSort('total_units')}
                          className="ml-auto flex items-center gap-1.5 font-medium"
                        >
                          {t('common.units')}
                          <ArrowUpDown className="h-3.5 w-3.5 text-muted-foreground" />
                        </button>
                      </th>
                      <th className="py-3 px-4 font-medium">
                        <button
                          type="button"
                          onClick={() => handleSalesSort('total_sales')}
                          className="ml-auto flex items-center gap-1.5 font-medium"
                        >
                          {t('common.revenue')}
                          <ArrowUpDown className="h-3.5 w-3.5 text-muted-foreground" />
                        </button>
                      </th>
                      <th className="py-3 px-4 font-medium">
                        <button
                          type="button"
                          onClick={() => handleSalesSort('total_orders')}
                          className="ml-auto flex items-center gap-1.5 font-medium"
                        >
                          {t('common.orders')}
                          <ArrowUpDown className="h-3.5 w-3.5 text-muted-foreground" />
                        </button>
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {pagedSalesRows.map((row) => (
                      <tr key={`${row.date}-${row.origin}`} className="border-b last:border-0">
                        <td className="py-3 px-4">
                          {formatPeriodLabel(row.date, row.origin === 'monthly' ? 'month' : 'day', language)}
                        </td>
                        {showOriginColumn && (
                          <td className="py-3 px-4">
                            <Badge variant={row.origin === 'monthly' ? 'secondary' : 'outline'}>
                              {t(row.origin === 'monthly' ? 'reports.origin.monthly' : 'reports.origin.daily')}
                            </Badge>
                          </td>
                        )}
                        <td className="py-3 px-4 text-right">{formatNumber(Number(row.total_units))}</td>
                        <td className="py-3 px-4 text-right">{formatCurrency(Number(row.total_sales), row.currency || salesCurrency)}</td>
                        <td className="py-3 px-4 text-right">{formatNumber(Number(row.total_orders))}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {salesTotalPages > 1 && (
                <div className="flex items-center justify-between border-t pt-3 text-sm">
                  <span className="text-muted-foreground">
                    {t('reports.salesRowsShowing', {
                      from: salesPage * SALES_PAGE_SIZE + 1,
                      to: Math.min((salesPage + 1) * SALES_PAGE_SIZE, sortedSalesRows.length),
                      total: sortedSalesRows.length,
                    })}
                  </span>
                  <div className="flex items-center gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setSalesPage((p) => Math.max(0, p - 1))}
                      disabled={salesPage === 0}
                    >
                      <ChevronLeft className="h-4 w-4" />
                    </Button>
                    <span className="tabular-nums">
                      {salesPage + 1} / {salesTotalPages}
                    </span>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setSalesPage((p) => Math.min(salesTotalPages - 1, p + 1))}
                      disabled={salesPage >= salesTotalPages - 1}
                    >
                      <ChevronRight className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="text-center py-8 text-muted-foreground">
              {t('reports.noSalesData')}
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
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
                    fill={BAR_H_FILL}
                    radius={[0, 4, 4, 0]}
                    maxBarSize={26}
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

      <Card>
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
                  <Bar dataKey="orders" fill={BAR_V_FILL} radius={[4, 4, 0, 0]} maxBarSize={32} />
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

      <Card>
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
              <p className="text-2xl font-bold">
                {kpis?.conversion_rate.is_available
                  ? `${(kpis.conversion_rate.value || 0).toFixed(1)}%`
                  : 'N/A'}
              </p>
            </div>
            <div className="space-y-2">
              <p className="text-sm text-muted-foreground">{t('analytics.returnRate')}</p>
              <p className="text-2xl font-bold">
                {kpis?.return_rate.is_available
                  ? `${(kpis.return_rate.value || 0).toFixed(1)}%`
                  : 'N/A'}
              </p>
            </div>
            <div className="space-y-2">
              <p className="text-sm text-muted-foreground">{t('analytics.activeProducts')}</p>
              <p className="text-2xl font-bold">{formatNumber(kpis?.active_asins || 0)}</p>
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
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

              <div className="space-y-4">
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
                          <th className="px-4 py-3 font-semibold">{t('analytics.tableAdSpend')}</th>
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
                              <div className="min-w-[280px] max-w-[640px]">
                                <p className="font-medium" title={product.title || product.asin}>
                                  {product.title || product.asin}
                                </p>
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
                            <td className="px-4 py-3 tabular-nums text-right">
                              {product.ad_spend > 0 ? (
                                <div>
                                  <span className="text-sm">{formatCurrency(product.ad_spend)}</span>
                                  {product.acos != null && (
                                    <p className="text-xs text-muted-foreground mt-0.5">
                                      ACoS {product.acos.toFixed(1)}%
                                    </p>
                                  )}
                                </div>
                              ) : (
                                <span className="text-muted-foreground">-</span>
                              )}
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
          insights={productTrendInsights?.insights ?? productTrends.insights}
          generatedWithAi={productTrendInsights?.generated_with_ai ?? false}
          aiAvailable={productTrends.ai_available}
          loading={
            productTrends.summary.eligible_products > 0 &&
            !productTrendInsights &&
            productTrendInsightsFetching
          }
        />
      )}
    </div>
  )
}

// ── Resi: returns analysis ───────────────────────────────────────────────────

function ResiTab({ active, dateRange, accountIds }: TabProps) {
  const { t, language } = useTranslation()

  const { data: returnsAnalytics, isLoading: returnsLoading } = useQuery<ReturnsAnalyticsResponse>({
    queryKey: ['returns-analysis', dateRange, accountIds],
    queryFn: () => analyticsApi.getReturnsAnalysis({
      date_from: dateRange.start,
      date_to: dateRange.end,
      account_ids: accountIds.length > 0 ? accountIds : undefined,
      limit: 10,
    }),
    enabled: active,
  })

  const returnReasonChartData = (returnsAnalytics?.reason_breakdown || []).slice(0, 6).map((entry) => ({
    ...entry,
    reason: entry.reason === 'Unknown' ? t('analytics.returns.unknownReason') : entry.reason,
  }))
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

  if (returnsLoading) {
    return (
      <Card>
        <CardContent className="flex min-h-[320px] items-center justify-center">
          <div className="flex items-center gap-3 text-sm text-muted-foreground">
            <Loader2 className="h-5 w-5 animate-spin" />
            <span>{t('common.loading')}</span>
          </div>
        </CardContent>
      </Card>
    )
  }

  return (
    <div className="space-y-6">
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
            {returnsAnalytics?.summary.top_reason && returnsAnalytics.summary.top_reason !== 'Unknown'
              ? returnsAnalytics.summary.top_reason
              : t('analytics.returns.unknownReason')}
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
                      stroke="hsl(var(--card))"
                      strokeWidth={2}
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
                      fill={BAR_H_FILL}
                      radius={[0, 4, 4, 0]}
                      maxBarSize={26}
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
    </div>
  )
}

// ── Ads vs Organic: analytics ads-vs-organic + reports advertising table ─────

interface AdsVsOrganicTabProps extends TabProps {
  trendAccountIds: string[]
  selectedAsin: string
  selectedAsinTitle?: string
  setSelectedAsin: (asin: string) => void
}

function AdsVsOrganicTab({
  active,
  dateRange,
  trendAccountIds,
  selectedAsin,
  selectedAsinTitle,
  setSelectedAsin,
}: AdsVsOrganicTabProps) {
  const { t, language } = useTranslation()
  const { analyticsGroupBy } = useFilterStore()

  const { data: adsVsOrganicData, isLoading: adsVsOrganicLoading } = useQuery<AdsVsOrganicResponse>({
    queryKey: ['ads-vs-organic', dateRange, trendAccountIds, analyticsGroupBy, selectedAsin, language],
    queryFn: () => analyticsApi.getAdsVsOrganic({
      date_from: dateRange.start,
      date_to: dateRange.end,
      group_by: analyticsGroupBy,
      account_ids: trendAccountIds.length > 0 ? trendAccountIds : undefined,
      language,
      ...(selectedAsin !== ALL_ASINS_VALUE ? { asin: selectedAsin } : {}),
    }),
    enabled: active,
  })

  const { data: accountsList = [] } = useQuery<AmazonAccount[]>({
    queryKey: ['accounts'],
    queryFn: () => accountsApi.list(),
    enabled: active,
  })

  const { data: advertisingData = [], isLoading: advertisingLoading } = useQuery<AdvertisingMetricsItem[]>({
    queryKey: ['advertising', dateRange, trendAccountIds],
    queryFn: () => reportsApi.getAdvertising({
      start_date: dateRange.start,
      end_date: dateRange.end,
      account_ids: trendAccountIds.length > 0 ? trendAccountIds : undefined,
    }),
    enabled: active,
  })

  const adsScopedAccounts = trendAccountIds.length > 0
    ? accountsList.filter((account) => trendAccountIds.includes(account.id))
    : accountsList
  const showNoAdsBanner =
    adsScopedAccounts.length > 0 &&
    adsScopedAccounts.every((account) => resolveAdsState(account) !== 'ok')

  const advertisingCurrency = 'EUR'

  const adsEffectiveGroupBy = adsVsOrganicData?.group_by ?? analyticsGroupBy
  const adsChartData = (adsVsOrganicData?.time_series || []).map((point) => ({
    ...point,
    displayDate: formatTimeBucketLabel(point.date, adsEffectiveGroupBy, language),
    chartTotal: point.ad_sales + point.organic_sales,
  }))
  const adsChartAxisMax = getChartAxisMax(
    adsChartData.map((point) => Math.max(point.chartTotal, point.total_sales))
  )

  if (adsVsOrganicLoading) {
    return (
      <Card>
        <CardContent className="flex min-h-[320px] items-center justify-center">
          <div className="flex items-center gap-3 text-sm text-muted-foreground">
            <Loader2 className="h-5 w-5 animate-spin" />
            <span>{t('common.loading')}</span>
          </div>
        </CardContent>
      </Card>
    )
  }

  return (
    <div className="space-y-6">
      {showNoAdsBanner && (
        <Alert variant="warning">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>{t('advertising.noAdsConnectionsTitle')}</AlertTitle>
          <AlertDescription>
            {t('advertising.noAdsConnectionsDesc')}{' '}
            <Link to="/accounts" className="font-medium underline">
              {t('advertising.openAccounts')}
            </Link>
          </AlertDescription>
        </Alert>
      )}
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
          {(adsVsOrganicData?.attribution_notes || []).length > 0 && (
            <ul className="mt-2 list-disc pl-5 text-xs">
              {adsVsOrganicData?.attribution_notes.map((note, idx) => (
                <li key={idx}>{note}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>{t('analytics.adsVsOrganic')}</CardTitle>
            <CardDescription>
              {selectedAsin !== ALL_ASINS_VALUE
                ? `${selectedAsinTitle || selectedAsin} (${selectedAsin})`
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
                      fill={CHART_SERIES[2]}
                      radius={[0, 0, 0, 0]}
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

        {selectedAsin === ALL_ASINS_VALUE && (adsVsOrganicData?.asin_breakdown?.length || 0) > 0 ? (
          <Card>
            <CardHeader>
              <CardTitle>{t('analytics.topAsinSales')}</CardTitle>
              <CardDescription>{t('analytics.topAsinSalesDesc')}</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              {(adsVsOrganicData?.breakdown_notes || []).map((note, idx) => (
                <p key={idx} className="text-xs text-muted-foreground">
                  {note}
                </p>
              ))}
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

      <Card>
        <CardHeader>
          <CardTitle>{t('reports.advertisingPerformance')}</CardTitle>
          <CardDescription>{t('reports.ppcMetrics')}</CardDescription>
        </CardHeader>
        <CardContent>
          {advertisingLoading ? (
            <div className="flex items-center justify-center h-32">
              <Loader2 className="h-8 w-8 animate-spin text-primary" />
            </div>
          ) : advertisingData.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b">
                    <th className="text-left py-3 px-4 font-medium">{t('reports.campaign')}</th>
                    <th className="text-right py-3 px-4 font-medium">{t('reports.spend')}</th>
                    <th className="text-right py-3 px-4 font-medium">{t('reports.clicks')}</th>
                    <th className="text-right py-3 px-4 font-medium">{t('reports.acos')}</th>
                  </tr>
                </thead>
                <tbody>
                  {advertisingData.map((item) => (
                    <tr key={`${item.campaign_id}-${item.date}`} className="border-b last:border-0">
                      <td className="py-3 px-4">{item.campaign_name || '-'}</td>
                      <td className="py-3 px-4 text-right">{formatCurrency(Number(item.cost), advertisingCurrency)}</td>
                      <td className="py-3 px-4 text-right">{formatNumber(Number(item.clicks))}</td>
                      <td className="py-3 px-4 text-right">{(Number(item.acos || 0) * 100).toFixed(1)}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="text-center py-8 text-muted-foreground">
              {t('reports.noAdvertising')}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

// ── Inventario: reports inventory ─────────────────────────────────────────────

function InventarioTab({ active, accountIds }: TabProps) {
  const { t } = useTranslation()
  const { reportsLowStockOnly } = useFilterStore()

  const { data: inventoryData = [], isLoading: inventoryLoading } = useQuery<InventoryReportItem[]>({
    queryKey: ['inventory', accountIds, reportsLowStockOnly],
    queryFn: () => reportsApi.getInventory({
      account_ids: accountIds.length > 0 ? accountIds : undefined,
      low_stock_only: reportsLowStockOnly || undefined,
    }),
    enabled: active,
  })

  const { data: inventoryAccounts = [], isLoading: inventoryAccountsLoading } = useQuery<AmazonAccount[]>({
    queryKey: ['accounts', 'inventory'],
    queryFn: () => accountsApi.list(),
    enabled: active,
  })

  const scopedInventoryAccounts =
    accountIds.length > 0
      ? inventoryAccounts.filter((account) => accountIds.includes(account.id))
      : inventoryAccounts
  const sellerInventoryAccounts = scopedInventoryAccounts.filter((account) => account.account_type === 'seller')
  const inventoryErrorAccounts = sellerInventoryAccounts.filter(
    (account) =>
      account.sync_error_message &&
      account.sync_error_message.toLowerCase().includes('inventory'),
  )
  const inventoryEmptyMessage =
    inventoryErrorAccounts.length > 0
      ? t('reports.inventoryUnavailable')
      : scopedInventoryAccounts.length > 0 && sellerInventoryAccounts.length === 0
      ? t('reports.inventorySellerOnly')
      : reportsLowStockOnly
      ? t('reports.noLowStock')
      : sellerInventoryAccounts.length > 0
      ? t('reports.inventoryUnavailableGeneric')
      : t('reports.noInventory')
  const inventoryDetailMessage =
    inventoryErrorAccounts.length > 0
      ? inventoryErrorAccounts
          .map((account) => `${account.account_name}: ${account.sync_error_message}`)
          .join(' ')
      : null

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('reports.inventoryStatus')}</CardTitle>
        <CardDescription>{t('reports.inventoryDesc')}</CardDescription>
      </CardHeader>
      <CardContent>
        {inventoryLoading || inventoryAccountsLoading ? (
          <div className="flex items-center justify-center h-32">
            <Loader2 className="h-8 w-8 animate-spin text-primary" />
          </div>
        ) : inventoryData.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b">
                  <th className="text-left py-3 px-4 font-medium">{t('reports.asin')}</th>
                  <th className="text-left py-3 px-4 font-medium">{t('reports.sku')}</th>
                  <th className="text-right py-3 px-4 font-medium">{t('reports.onHand')}</th>
                  <th className="text-right py-3 px-4 font-medium">{t('reports.inbound')}</th>
                </tr>
              </thead>
              <tbody>
                {inventoryData.map((item) => (
                  <tr key={`${item.snapshot_date}-${item.asin}`} className="border-b last:border-0">
                    <td className="py-3 px-4 font-mono text-sm">{item.asin}</td>
                    <td className="py-3 px-4">{item.sku || '-'}</td>
                    <td className="py-3 px-4 text-right">
                      {formatNumber(item.afn_fulfillable_quantity + item.mfn_fulfillable_quantity)}
                    </td>
                    <td className="py-3 px-4 text-right">
                      {formatNumber(item.afn_inbound_working_quantity + item.afn_inbound_shipped_quantity)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="py-8 text-center text-muted-foreground space-y-2">
            <p>{inventoryEmptyMessage}</p>
            {inventoryDetailMessage && (
              <p className="text-sm text-destructive">{inventoryDetailMessage}</p>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

// ── Export: export modal trigger + scheduled reports ──────────────────────────

function ExportTab() {
  const { t } = useTranslation()
  const [exportModalOpen, setExportModalOpen] = useState(false)

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>{t('performance.exportTitle')}</CardTitle>
          <CardDescription>{t('performance.exportDesc')}</CardDescription>
        </CardHeader>
        <CardContent>
          <Button variant="outline" size="sm" onClick={() => setExportModalOpen(true)} className="h-9">
            <Download className="mr-2 h-4 w-4" />
            {t('export.button')}
          </Button>
        </CardContent>
      </Card>
      <ScheduledReportsPanel />
      <ExportModal open={exportModalOpen} onOpenChange={setExportModalOpen} />
    </div>
  )
}

export default function Performance() {
  const { t } = useTranslation()
  const [searchParams, setSearchParams] = useSearchParams()
  const filterState = useFilterStore()
  const {
    datePreset,
    customStartDate,
    customEndDate,
    accountIds,
    reportsGroupBy,
    reportsLowStockOnly,
    analyticsGroupBy,
    setReportsGroupBy,
    setReportsLowStockOnly,
    setAnalyticsGroupBy,
    resetDashboard,
    resetReports,
    resetAnalytics,
  } = filterState

  const tabParam = (searchParams.get('tab') || '').toLowerCase()
  const initialTab: PerformanceTab = TAB_ALIASES[tabParam] || 'overview'
  const [activeTab, setActiveTab] = useState<PerformanceTab>(initialTab)
  const [selectedAsin, setSelectedAsin] = useState(ALL_ASINS_VALUE)

  const dateRange = getFilterDateRange({ datePreset, customStartDate, customEndDate })
  const scopedAccountId = searchParams.get('account_id') || undefined
  const trendAsinFilter = searchParams.get('asin') || ''
  const trendClassFilter = (searchParams.get('trend_class') || 'all') as ProductTrendClass | 'all'
  const trendAccountIds = scopedAccountId ? [scopedAccountId] : accountIds

  // Deep-links carrying an asin (Dashboard trend cards) land on Per ASIN; an
  // explicit ?tab= wins when present.
  useEffect(() => {
    if (tabParam && TAB_ALIASES[tabParam]) {
      setActiveTab(TAB_ALIASES[tabParam])
      return
    }
    if (trendAsinFilter) {
      setActiveTab('overview')
    }
  }, [tabParam, trendAsinFilter])

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
    resetReports()
    resetAnalytics()
    setSelectedAsin(ALL_ASINS_VALUE)
    setSearchParams({}, { replace: true })
  }

  const { data: allAccounts = [] } = useQuery<AmazonAccount[]>({
    queryKey: ['accounts'],
    queryFn: () => accountsApi.list(),
  })
  const salesGranularity = granularityForSelection(allAccounts, accountIds)
  const adsGranularity = granularityForSelection(allAccounts, trendAccountIds)

  const { data: products } = useQuery<Product[]>({
    queryKey: ['analytics-products', trendAccountIds],
    queryFn: () => catalogApi.getProducts({
      active_only: true,
      limit: 200,
      account_ids: trendAccountIds.length > 0 ? trendAccountIds : undefined,
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

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">{t('nav.performance')}</h1>
          <p className="text-muted-foreground">{t('performance.subtitle')}</p>
        </div>
        <FilterBar onReset={handleResetAll}>
          <DateRangeFilter />
          <AccountFilter />
          {activeTab === 'overview' && (
            <GroupByFilter
              value={reportsGroupBy}
              onChange={setReportsGroupBy}
              granularity={salesGranularity}
            />
          )}
          {activeTab === 'inventory' && (
            <ToggleFilter
              label={t('filter.lowStockOnly')}
              checked={reportsLowStockOnly}
              onChange={setReportsLowStockOnly}
              id="low-stock-toggle"
            />
          )}
          {activeTab === 'ads-vs-organic' && (
            <>
              <GroupByFilter
                value={analyticsGroupBy}
                onChange={setAnalyticsGroupBy}
                granularity={adsGranularity}
              />
              <GranularityBadge granularity={adsGranularity} />
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
          )}
        </FilterBar>
      </div>

      <Tabs value={activeTab} onValueChange={(value) => setActiveTab(value as PerformanceTab)} className="space-y-4">
        <TabsList>
          <TabsTrigger value="overview">{t('analytics.overviewTab')}</TabsTrigger>
          <TabsTrigger value="per-product">{t('performance.perAsinTab')}</TabsTrigger>
          <TabsTrigger value="returns">{t('analytics.returnsTab')}</TabsTrigger>
          <TabsTrigger value="ads-vs-organic">{t('analytics.adsVsOrganicTab')}</TabsTrigger>
          <TabsTrigger value="inventory">{t('reports.inventory')}</TabsTrigger>
          <TabsTrigger value="export">{t('performance.exportTab')}</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="space-y-4">
          <PanoramicaTab
            active={activeTab === 'overview'}
            dateRange={dateRange}
            accountIds={accountIds}
            trendAccountIds={trendAccountIds}
            scopedAccountId={scopedAccountId}
            trendAsinFilter={trendAsinFilter}
            trendClassFilter={trendClassFilter}
            setTrendSearchParam={setTrendSearchParam}
          />
        </TabsContent>

        <TabsContent value="per-product" className="space-y-6">
          <PerProductPerformanceTable
            dateRange={dateRange}
            accountIds={trendAccountIds}
            enabled={activeTab === 'per-product'}
          />
        </TabsContent>

        <TabsContent value="returns" className="space-y-6">
          <ResiTab
            active={activeTab === 'returns'}
            dateRange={dateRange}
            accountIds={trendAccountIds}
          />
        </TabsContent>

        <TabsContent value="ads-vs-organic" className="space-y-6">
          <AdsVsOrganicTab
            active={activeTab === 'ads-vs-organic'}
            dateRange={dateRange}
            accountIds={trendAccountIds}
            trendAccountIds={trendAccountIds}
            selectedAsin={selectedAsin}
            selectedAsinTitle={asinOptions.find((product) => product.asin === selectedAsin)?.title ?? undefined}
            setSelectedAsin={setSelectedAsin}
          />
        </TabsContent>

        <TabsContent value="inventory">
          <InventarioTab
            active={activeTab === 'inventory'}
            dateRange={dateRange}
            accountIds={accountIds}
          />
        </TabsContent>

        <TabsContent value="export" className="space-y-6">
          <ExportTab />
        </TabsContent>
      </Tabs>
    </div>
  )
}
