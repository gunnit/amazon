import { useEffect, useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link, useSearchParams } from 'react-router-dom'
import {
  TrendingUp,
  TrendingDown,
  DollarSign,
  Package,
  ShoppingCart,
  Loader2,
  ArrowLeft,
  Globe,
  ArrowRight,
  ChevronRight,
  Megaphone,
  Target,
  Info,
  AlertCircle,
  AlertTriangle,
} from 'lucide-react'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  AreaChart,
  Area,
  ComposedChart,
  BarChart,
  Bar,
  Legend,
} from 'recharts'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Alert, AlertTitle, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { analyticsApi, accountsApi } from '@/services/api'
import { formatCurrency, formatNumber, formatPercent, cn } from '@/lib/utils'
import { AREA_FILL, CHART_PRIMARY, CHART_SERIES } from '@/lib/chart-theme'
import { buildDashboardSearchParams, resolveDashboardScope } from '@/lib/dashboardScope'
import { FilterBar, DateRangeFilter, AccountFilter, ComparisonFilter } from '@/components/filters'
import ProductTrendBadge from '@/components/analytics/ProductTrendBadge'
import ProductTrendSparkline from '@/components/analytics/ProductTrendSparkline'
import { PeriodComparisonCard } from '@/components/PeriodComparisonCard'
import { useFilterStore, getComparisonPeriods, getFilterDateRange } from '@/store/filterStore'
import { useTranslation } from '@/i18n'
import { useToast } from '@/components/ui/use-toast'
import type {
  AmazonAccount,
  DashboardKPIs,
  TrendData,
  AccountSummary,
  ComparisonResponse,
  ProductTrendItem,
  ProductTrendsResponse,
} from '@/types'

function KPICard({
  title,
  value,
  change,
  trend,
  icon: Icon,
  format = 'number',
  currency = 'EUR',
  emphasis = 'secondary',
  className,
}: {
  title: string
  value: number
  change?: number | null
  trend?: 'up' | 'down' | 'stable'
  icon: React.ElementType
  format?: 'number' | 'currency' | 'percent'
  currency?: string
  emphasis?: 'primary' | 'secondary'
  className?: string
}) {
  const { t } = useTranslation()
  const formattedValue =
    format === 'currency'
      ? formatCurrency(value, currency)
      : format === 'percent'
      ? `${value.toFixed(1)}%`
      : formatNumber(value)

  const isPrimary = emphasis === 'primary'

  // A zeroed current value against a non-zero baseline yields a misleading
  // "-100%" drop. Show a neutral placeholder instead of an alarming delta.
  const suppressChange = value === 0 && typeof change === 'number' && change < 0

  return (
    <Card
      className={cn(
        isPrimary
          ? "relative overflow-hidden border-0 bg-gradient-to-br from-slate-900 via-blue-950 to-indigo-950 text-white shadow-md"
          : "border-border/60",
        className
      )}
    >
      {isPrimary && (
        <div className="pointer-events-none absolute -right-12 -top-16 h-48 w-48 rounded-full bg-white/5 blur-3xl" />
      )}
      <CardHeader className="relative flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle
          className={cn(
            "uppercase tracking-wide",
            isPrimary
              ? "text-xs font-semibold text-white/70"
              : "text-[11px] font-medium text-muted-foreground"
          )}
        >
          {title}
        </CardTitle>
        <Icon className={cn("h-3.5 w-3.5", isPrimary ? "text-white/40" : "text-muted-foreground/70")} />
      </CardHeader>
      <CardContent className="relative">
        <div className={cn(isPrimary ? "text-3xl font-semibold" : "text-2xl font-semibold")}>
          {formattedValue}
        </div>
        {suppressChange ? (
          <div className={cn("flex items-center text-xs mt-2", isPrimary ? "text-white/60" : "text-muted-foreground")}>
            <span>—</span>
            <span className={cn("ml-1", isPrimary && "text-white/50")}>{t('common.vsPreviousPeriod')}</span>
          </div>
        ) : change !== null && change !== undefined && (
          <div className={cn("flex items-center text-xs mt-2", isPrimary ? "text-white/60" : "text-muted-foreground")}>
            {trend === 'up' ? (
              <TrendingUp className={cn("h-3 w-3 mr-1", isPrimary ? "text-emerald-400" : "text-emerald-500")} />
            ) : trend === 'down' ? (
              <TrendingDown className={cn("h-3 w-3 mr-1", isPrimary ? "text-rose-400" : "text-rose-500")} />
            ) : null}
            <span
              className={cn(
                trend === 'up'
                  ? isPrimary ? 'text-emerald-400' : 'text-emerald-500'
                  : trend === 'down'
                  ? isPrimary ? 'text-rose-400' : 'text-rose-500'
                  : ''
              )}
            >
              {formatPercent(change)}
            </span>
            <span className={cn("ml-1", isPrimary && "text-white/50")}>{t('common.vsPreviousPeriod')}</span>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

function ChartEmptyState({
  title,
  description,
}: {
  title: string
  description: string
}) {
  const bars = [5, 8, 3, 10, 6, 9, 4, 7, 5, 8]

  return (
    <div className="flex h-full flex-col items-center justify-center gap-4 text-center">
      <div className="w-full max-w-sm rounded-md border border-dashed border-border/60 bg-muted/20 p-4">
        <div className="grid grid-cols-10 items-end gap-2 h-16">
          {bars.map((height, index) => (
            <div
              key={`${title}-bar-${index}`}
              className="w-full rounded-sm bg-muted/40"
              style={{ height: `${height * 6}%` }}
            />
          ))}
        </div>
      </div>
      <div className="space-y-1 text-sm text-muted-foreground">
        <p className="text-foreground/90">{title}</p>
        <p className="text-xs">{description}</p>
      </div>
    </div>
  )
}

function ScopeStatusBadge({
  status,
}: {
  status: 'pending' | 'syncing' | 'success' | 'error'
}) {
  const { t } = useTranslation()

  if (status === 'success') {
    return null
  }

  if (status === 'error') {
    return <Badge variant="destructive">{t('dashboard.errors')}</Badge>
  }

  if (status === 'syncing') {
    return <Badge variant="warning">{t('dashboard.syncing')}</Badge>
  }

  return <Badge variant="secondary">{t('dashboard.pending')}</Badge>
}

function LockedAccountScope({
  accountName,
  marketplace,
  status,
  onExit,
}: {
  accountName: string
  marketplace: string
  status: 'pending' | 'syncing' | 'success' | 'error'
  onExit: () => void
}) {
  const { t } = useTranslation()

  return (
    <div className="flex h-9 max-w-full items-center gap-2 overflow-hidden rounded-md border border-border/70 bg-background px-3">
      <span className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
        {t('dashboard.viewingAccount')}
      </span>
      <span className="max-w-[180px] truncate text-sm font-medium">{accountName}</span>
      <Badge variant="outline" className="shrink-0">
        {marketplace}
      </Badge>
      <ScopeStatusBadge status={status} />
      <Button variant="ghost" size="sm" onClick={onExit} className="h-7 px-2 text-xs">
        {t('dashboard.exitAccountView')}
      </Button>
    </div>
  )
}

function buildAnalyticsTrendLink({
  asin,
  accountId,
}: {
  asin: string
  accountId?: string
}) {
  const params = new URLSearchParams()
  params.set('asin', asin)
  if (accountId) {
    params.set('account_id', accountId)
  }
  return `/analytics?${params.toString()}`
}

function TrendingProductsList({
  title,
  products,
  emptyKey,
  accountId,
}: {
  title: string
  products: ProductTrendItem[]
  emptyKey: 'dashboard.noRisingProducts' | 'dashboard.noDecliningProducts'
  accountId?: string
}) {
  const { t } = useTranslation()

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-sm font-semibold text-foreground">{title}</p>
        <Badge variant="outline">{products.length}</Badge>
      </div>
      {products.length ? (
        <div className="space-y-3">
          {products.map((product) => (
            <Link
              key={`${product.asin}-${title}`}
              to={buildAnalyticsTrendLink({ asin: product.asin, accountId })}
              className="block rounded-lg border border-border/70 p-3 transition-colors hover:border-primary/50"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="truncate text-sm font-semibold">{product.title || product.asin}</p>
                  <p className="mt-1 text-xs text-muted-foreground">{product.asin}</p>
                </div>
                <div className="text-right">
                  <ProductTrendBadge trendClass={product.trend_class} className="ml-auto" />
                  <p
                    className={cn(
                      'mt-2 text-sm font-semibold',
                      product.sales_delta_percent >= 0 ? 'text-emerald-600' : 'text-rose-600'
                    )}
                  >
                    {formatPercent(product.sales_delta_percent)}
                  </p>
                </div>
              </div>
              <div className="mt-3 h-12">
                <ProductTrendSparkline
                  data={product.recent_sales}
                  trendClass={product.trend_class}
                  metric="revenue"
                  height={48}
                />
              </div>
            </Link>
          ))}
        </div>
      ) : (
        <div className="flex min-h-[160px] items-center justify-center rounded-lg border border-dashed text-sm text-muted-foreground">
          {t(emptyKey)}
        </div>
      )}
    </div>
  )
}

export default function Dashboard() {
  const { t } = useTranslation()
  const { toast } = useToast()
  const [searchParams, setSearchParams] = useSearchParams()
  const requestedAccountId = searchParams.get('account')
  const invalidAccountToastRef = useRef<string | null>(null)

  const filterState = useFilterStore()
  const {
    datePreset,
    customStartDate,
    customEndDate,
    accountIds,
    resetDashboard,
    resetComparison,
  } = filterState
  const dateRange = getFilterDateRange({ datePreset, customStartDate, customEndDate })
  const comparisonPeriods = getComparisonPeriods(filterState)

  const handleReset = () => {
    resetDashboard()
    resetComparison()
  }

  const { data: accountSummary, isLoading: accountsLoading } = useQuery<AccountSummary>({
    queryKey: ['accounts-summary', dateRange],
    queryFn: () => accountsApi.getSummary({ start_date: dateRange.start, end_date: dateRange.end }),
  })

  const { data: accounts } = useQuery<AmazonAccount[]>({
    queryKey: ['accounts'],
    queryFn: () => accountsApi.list(),
  })

  const scope = resolveDashboardScope(
    requestedAccountId,
    accountsLoading ? undefined : accountSummary?.accounts
  )
  const queriesEnabled = scope.mode !== 'resolving'
  const effectiveAccountIds = scope.mode === 'account' ? [scope.accountId] : accountIds

  // Vendor accounts only get monthly, already-settled data, so a recent window can
  // legitimately read 0. Surface a note whenever the current scope includes a vendor.
  const vendorSelected = (() => {
    if (!accounts) return false
    const vendors = accounts.filter((a) => a.account_type === 'vendor')
    if (vendors.length === 0) return false
    if (scope.mode === 'account') {
      return vendors.some((v) => v.id === scope.accountId)
    }
    if (effectiveAccountIds.length === 0) {
      return true // "All accounts" selection includes the vendor(s)
    }
    return vendors.some((v) => effectiveAccountIds.includes(v.id))
  })()

  // Split the in-scope accounts by type so we can plot seller (daily) and vendor
  // (monthly) as separate series instead of fusing the vendor monthly lump into
  // the seller daily line (which renders as a false spike on the 1st of a month).
  // In "all" mode effectiveAccountIds is empty and means every account.
  const inScopeAccounts = (accounts ?? []).filter((a) =>
    effectiveAccountIds.length === 0 ? true : effectiveAccountIds.includes(a.id)
  )
  const sellerAccountIds = inScopeAccounts
    .filter((a) => a.account_type === 'seller')
    .map((a) => a.id)
  const vendorAccountIds = inScopeAccounts
    .filter((a) => a.account_type === 'vendor')
    .map((a) => a.id)
  const hasSeller = sellerAccountIds.length > 0
  const hasVendor = vendorAccountIds.length > 0
  const mixed = hasSeller && hasVendor

  const { data: kpis, isLoading: kpisLoading, isError: kpisError } = useQuery<DashboardKPIs>({
    queryKey: ['dashboard-kpis', dateRange, effectiveAccountIds],
    queryFn: () => analyticsApi.getDashboard({
      start_date: dateRange.start,
      end_date: dateRange.end,
      account_ids: effectiveAccountIds.length > 0 ? effectiveAccountIds : undefined,
    }),
    enabled: queriesEnabled,
  })

  const { data: trends, isLoading: trendsLoading } = useQuery<TrendData[]>({
    queryKey: ['dashboard-trends', dateRange, effectiveAccountIds],
    queryFn: () => analyticsApi.getTrends({
      metrics: ['revenue', 'units'],
      start_date: dateRange.start,
      end_date: dateRange.end,
      account_ids: effectiveAccountIds.length > 0 ? effectiveAccountIds : undefined,
    }),
    enabled: queriesEnabled,
  })

  // When both seller and vendor accounts are in scope, fetch the seller-only series
  // separately so we can render it as the daily Area/Line baseline.
  const { data: sellerTrends } = useQuery<TrendData[]>({
    queryKey: ['dashboard-trends-seller', dateRange, sellerAccountIds],
    queryFn: () => analyticsApi.getTrends({
      metrics: ['revenue', 'units'],
      start_date: dateRange.start,
      end_date: dateRange.end,
      account_ids: sellerAccountIds,
    }),
    enabled: queriesEnabled && mixed && hasSeller,
  })

  // Vendor-only series, used both in the vendor-only path and the mixed path.
  const { data: vendorTrends } = useQuery<TrendData[]>({
    queryKey: ['dashboard-trends-vendor', dateRange, vendorAccountIds],
    queryFn: () => analyticsApi.getTrends({
      metrics: ['revenue', 'units'],
      start_date: dateRange.start,
      end_date: dateRange.end,
      account_ids: vendorAccountIds,
    }),
    enabled: queriesEnabled && hasVendor,
  })

  const { data: trendingProducts, isLoading: trendingProductsLoading } = useQuery<ProductTrendsResponse>({
    queryKey: ['dashboard-product-trends', dateRange.end, effectiveAccountIds],
    queryFn: () => analyticsApi.getProductTrends({
      start_date: dateRange.start,
      end_date: dateRange.end,
      account_id: scope.mode === 'account' ? scope.accountId : undefined,
      account_ids: scope.mode === 'account'
        ? undefined
        : effectiveAccountIds.length > 0
          ? effectiveAccountIds
          : undefined,
      limit: 5,
    }),
    enabled: queriesEnabled,
  })

  useEffect(() => {
    if ((scope.mode === 'invalid' || scope.mode === 'missing') && requestedAccountId) {
      if (invalidAccountToastRef.current === requestedAccountId) {
        return
      }

      invalidAccountToastRef.current = requestedAccountId
      toast({
        title: t('dashboard.accountScopeCleared'),
        description:
          scope.mode === 'invalid'
            ? t('dashboard.accountParamInvalid')
            : t('dashboard.accountNotFound'),
      })
      setSearchParams(buildDashboardSearchParams(searchParams, null), { replace: true })
      return
    }

    if (scope.mode === 'all' || scope.mode === 'account') {
      invalidAccountToastRef.current = null
    }
  }, [requestedAccountId, scope, searchParams, setSearchParams, t, toast])

  const { data: comparison, isLoading: comparisonLoading } = useQuery<ComparisonResponse>({
    queryKey: ['dashboard-comparison', comparisonPeriods, effectiveAccountIds],
    queryFn: () => analyticsApi.getComparison({
      period1_start: comparisonPeriods.period1.start,
      period1_end: comparisonPeriods.period1.end,
      period2_start: comparisonPeriods.period2.start,
      period2_end: comparisonPeriods.period2.end,
      preset: comparisonPeriods.preset || undefined,
      account_ids: effectiveAccountIds.length > 0 ? effectiveAccountIds : undefined,
    }),
    enabled: queriesEnabled,
  })

  const handleExitAccountView = () => {
    setSearchParams(buildDashboardSearchParams(searchParams, null))
  }

  const isLoading =
    accountsLoading ||
    !queriesEnabled ||
    kpisLoading ||
    trendsLoading ||
    trendingProductsLoading

  const headerSubtitle =
    scope.mode === 'account'
      ? t('dashboard.accountSubtitle', {
          accountName: scope.accountName,
          marketplace: scope.marketplace,
        })
      : t('dashboard.subtitle')
  const comparisonDescription =
    scope.mode === 'account'
      ? t('comparison.dashboardDescriptionScoped', { accountName: scope.accountName })
      : t('comparison.dashboardDescription')

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-96">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    )
  }

  // The selected window genuinely has no sales (not a load error). Show an honest
  // empty-state instead of alarming "-100%" deltas on the zeroed KPI cards.
  const hasNoSalesData =
    !kpisError &&
    !!kpis &&
    kpis.total_revenue.value === 0 &&
    kpis.total_orders.value === 0 &&
    kpis.total_units.value === 0

  const revenueTrend = trends?.find((t) => t.metric_name === 'revenue')
  const unitsTrend = trends?.find((t) => t.metric_name === 'units')

  // Per-type series for the vendor-only and mixed chart paths.
  const sellerRevenue = sellerTrends?.find((t) => t.metric_name === 'revenue')
  const sellerUnits = sellerTrends?.find((t) => t.metric_name === 'units')
  const vendorRevenue = vendorTrends?.find((t) => t.metric_name === 'revenue')
  const vendorUnits = vendorTrends?.find((t) => t.metric_name === 'units')

  const vendorColor = CHART_SERIES[2]

  // Merge a seller daily series and a vendor monthly series into rows keyed by
  // date. Missing values stay undefined so Recharts skips them instead of
  // plotting a misleading 0.
  const mergeSeries = (
    seller: TrendData | undefined,
    vendor: TrendData | undefined
  ) => {
    const byDate = new Map<string, { date: string; seller?: number; vendor?: number }>()
    for (const point of seller?.data_points ?? []) {
      byDate.set(point.date, { ...(byDate.get(point.date) ?? { date: point.date }), seller: point.value })
    }
    for (const point of vendor?.data_points ?? []) {
      byDate.set(point.date, { ...(byDate.get(point.date) ?? { date: point.date }), vendor: point.value })
    }
    return Array.from(byDate.values()).sort((a, b) => a.date.localeCompare(b.date))
  }

  const revenueComposed = mergeSeries(sellerRevenue, vendorRevenue)
  const unitsComposed = mergeSeries(sellerUnits, vendorUnits)

  const tickFormatter = (value: string) =>
    new Date(value + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
  const labelFormatter = (label: string) => new Date(label + 'T00:00:00').toLocaleDateString()

  const currency = kpis?.currency || 'EUR'
  const compactCurrency = new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency,
    notation: 'compact',
    maximumFractionDigits: 1,
  })

  const days = datePreset === 'custom' ? t('common.selectedPeriod') : t('common.lastNDays', { n: datePreset })
  const revenueTrendDescription =
    mixed
      ? t('dashboard.trendDescMixed')
      : hasVendor && !hasSeller
        ? t('dashboard.revenueTrendDescVendor')
        : scope.mode === 'account'
          ? t('dashboard.revenueTrendDescAccount', { days, accountName: scope.accountName })
          : t('dashboard.revenueTrendDesc', { days })
  const unitsTrendDescription =
    mixed
      ? t('dashboard.trendDescMixed')
      : hasVendor && !hasSeller
        ? t('dashboard.unitsTrendDescVendor')
        : scope.mode === 'account'
          ? t('dashboard.unitsTrendDescAccount', { days, accountName: scope.accountName })
          : t('dashboard.unitsTrendDesc', { days })
  const revenueEmptyTitle =
    scope.mode === 'account' ? t('dashboard.accountRevenueEmptyTitle') : t('dashboard.revenueEmptyTitle')
  const revenueEmptyDescription =
    scope.mode === 'account'
      ? t('dashboard.accountRevenueEmptyDesc', { accountName: scope.accountName })
      : t('dashboard.revenueEmptyDesc')
  const unitsEmptyTitle =
    scope.mode === 'account' ? t('dashboard.accountUnitsEmptyTitle') : t('dashboard.unitsEmptyTitle')
  const unitsEmptyDescription =
    scope.mode === 'account'
      ? t('dashboard.accountUnitsEmptyDesc', { accountName: scope.accountName })
      : t('dashboard.unitsEmptyDesc')

  return (
    <div className="space-y-6">
      {/* Branded hero header — mirrors the login brand panel */}
      <div className="relative overflow-hidden rounded-xl bg-gradient-to-br from-slate-900 via-blue-950 to-indigo-950 px-6 py-6 text-white shadow-sm">
        <div className="pointer-events-none absolute -right-20 -top-24 h-72 w-72 rounded-full bg-white/5 blur-3xl" />
        <div className="pointer-events-none absolute -bottom-28 -left-16 h-72 w-72 rounded-full bg-indigo-400/10 blur-3xl" />
        <div className="relative space-y-4">
          {scope.mode === 'account' && (
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex flex-wrap items-center gap-2 text-sm text-white/70">
                <span>{t('dashboard.breadcrumbOverview')}</span>
                <ChevronRight className="h-4 w-4 text-white/40" />
                <span className="font-medium text-white">{scope.accountName}</span>
                <Badge variant="outline" className="border-white/30 text-white">
                  {scope.marketplace}
                </Badge>
                <ScopeStatusBadge status={scope.status} />
              </div>
              <Button
                variant="ghost"
                size="sm"
                onClick={handleExitAccountView}
                className="gap-1.5 text-white/80 hover:bg-white/10 hover:text-white"
              >
                <ArrowLeft className="h-4 w-4" />
                {t('dashboard.backToOverview')}
              </Button>
            </div>
          )}

          <div>
            {scope.mode === 'account' && (
              <p className="text-sm font-medium text-white/60">{t('dashboard.title')}</p>
            )}
            <h1 className="text-3xl font-bold tracking-tight">
              {scope.mode === 'account' ? scope.accountName : t('dashboard.title')}
            </h1>
            <p className="mt-1 text-white/70">{headerSubtitle}</p>
          </div>

          {scope.mode !== 'account' && (
            <div className="flex flex-wrap gap-2">
              <Badge className="border-white/20 bg-white/10 text-white hover:bg-white/15">
                {accountSummary?.active_accounts || 0} {t('dashboard.activeAccounts')}
              </Badge>
              {accountSummary?.syncing_accounts ? (
                <Badge className="border-white/20 bg-white/10 text-white hover:bg-white/15">
                  {accountSummary.syncing_accounts} {t('dashboard.syncing')}
                </Badge>
              ) : null}
              {accountSummary?.error_accounts ? (
                <Badge className="border-rose-300/30 bg-rose-500/20 text-rose-100 hover:bg-rose-500/25">
                  {accountSummary.error_accounts} {t('dashboard.errors')}
                </Badge>
              ) : null}
            </div>
          )}
        </div>
      </div>

      {/* Filters */}
      <div className="flex justify-start">
        <FilterBar onReset={handleReset}>
          <DateRangeFilter />
          {scope.mode === 'account' ? (
            <LockedAccountScope
              accountName={scope.accountName}
              marketplace={scope.marketplace}
              status={scope.status}
              onExit={handleExitAccountView}
            />
          ) : (
            <AccountFilter />
          )}
          <ComparisonFilter />
        </FilterBar>
      </div>

      {/* Vendor settlement-lag note */}
      {vendorSelected && (
        <div className="flex items-start gap-3 rounded-lg border border-border/60 bg-muted/30 px-4 py-3 text-sm">
          <Info className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
          <div>
            <p className="font-medium text-foreground">{t('dashboard.vendorDataNoteTitle')}</p>
            <p className="mt-0.5 text-muted-foreground">{t('dashboard.vendorDataNote')}</p>
          </div>
        </div>
      )}

      {/* KPI Cards */}
      {kpisError ? (
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertTitle>{t('dashboard.kpiLoadError')}</AlertTitle>
          <AlertDescription>{t('dashboard.kpiLoadErrorDesc')}</AlertDescription>
        </Alert>
      ) : (
      <>
      {hasNoSalesData && (
        <div className="flex items-start gap-3 rounded-lg border border-border/60 bg-muted/30 px-4 py-3 text-sm">
          <Info className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
          <div>
            <p className="font-medium text-foreground">{t('dashboard.noDataTitle')}</p>
            <p className="mt-0.5 text-muted-foreground">{t('dashboard.noDataDesc')}</p>
          </div>
        </div>
      )}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <KPICard
          title={t('dashboard.totalRevenue')}
          value={kpis?.total_revenue.value || 0}
          change={hasNoSalesData ? undefined : kpis?.total_revenue.change_percent}
          trend={hasNoSalesData ? undefined : kpis?.total_revenue.trend}
          icon={DollarSign}
          format="currency"
          currency={currency}
          emphasis="primary"
          className="md:col-span-2"
        />
        <KPICard
          title={t('dashboard.totalOrders')}
          value={kpis?.total_orders.value || 0}
          change={hasNoSalesData ? undefined : kpis?.total_orders.change_percent}
          trend={hasNoSalesData ? undefined : kpis?.total_orders.trend}
          icon={ShoppingCart}
        />
        <KPICard
          title={t('dashboard.unitsSold')}
          value={kpis?.total_units.value || 0}
          change={hasNoSalesData ? undefined : kpis?.total_units.change_percent}
          trend={hasNoSalesData ? undefined : kpis?.total_units.trend}
          icon={Package}
        />
      </div>

      {/* Advertising KPIs */}
      {kpis?.roas?.is_available === false ? (
        <Alert variant="warning">
          <AlertTriangle className="h-4 w-4" />
          <AlertDescription>
            {t('advertising.notConnected')}{' '}
            <Link to="/accounts" className="font-medium underline">
              {t('advertising.openAccounts')}
            </Link>
          </AlertDescription>
        </Alert>
      ) : (
        <div className="grid gap-4 md:grid-cols-3">
          <KPICard
            title={t('dashboard.adSpend')}
            value={kpis?.total_ad_spend.value || 0}
            change={kpis?.total_ad_spend.change_percent}
            trend={kpis?.total_ad_spend.trend}
            icon={DollarSign}
            format="currency"
            currency={currency}
          />
          <KPICard
            title="ROAS"
            value={kpis?.roas.value || 0}
            change={kpis?.roas.change_percent}
            trend={kpis?.roas.trend}
            icon={Target}
            format="number"
          />
          <KPICard
            title="ACoS"
            value={kpis?.acos.value || 0}
            change={kpis?.acos.change_percent}
            trend={kpis?.acos.trend}
            icon={Megaphone}
            format="percent"
          />
        </div>
      )}
      </>
      )}

      <PeriodComparisonCard
        comparison={comparisonLoading ? undefined : comparison}
        title={t('comparison.dashboardTitle')}
        description={comparisonDescription}
      />

      {/* Charts */}
      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">{t('dashboard.revenueTrend')}</CardTitle>
            <CardDescription className="text-xs">
              {revenueTrendDescription}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="h-[300px]">
              {mixed && revenueComposed.length > 0 ? (
                <ResponsiveContainer width="100%" height="100%">
                  <ComposedChart data={revenueComposed}>
                    <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                    <XAxis dataKey="date" tickFormatter={tickFormatter} />
                    <YAxis tickFormatter={(value) => compactCurrency.format(value)} />
                    <Tooltip
                      formatter={(value: number) => formatCurrency(value, currency)}
                      labelFormatter={labelFormatter}
                    />
                    <Legend />
                    <Bar
                      dataKey="vendor"
                      name={t('dashboard.seriesVendor')}
                      fill={vendorColor}
                      fillOpacity={0.85}
                      radius={[4, 4, 0, 0]}
                      maxBarSize={36}
                    />
                    <Area
                      type="monotone"
                      dataKey="seller"
                      name={t('dashboard.seriesSeller')}
                      stroke={CHART_PRIMARY}
                      strokeWidth={2}
                      fill={AREA_FILL}
                    />
                  </ComposedChart>
                </ResponsiveContainer>
              ) : hasVendor && !hasSeller && vendorRevenue && vendorRevenue.data_points.length > 0 ? (
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={vendorRevenue.data_points}>
                    <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                    <XAxis dataKey="date" tickFormatter={tickFormatter} />
                    <YAxis tickFormatter={(value) => compactCurrency.format(value)} />
                    <Tooltip
                      formatter={(value: number) => [formatCurrency(value, currency), t('dashboard.seriesVendor')]}
                      labelFormatter={labelFormatter}
                    />
                    <Bar dataKey="value" fill={vendorColor} fillOpacity={0.85} radius={[4, 4, 0, 0]} maxBarSize={36} />
                  </BarChart>
                </ResponsiveContainer>
              ) : revenueTrend && revenueTrend.data_points.length > 0 ? (
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={revenueTrend.data_points}>
                    <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                    <XAxis dataKey="date" tickFormatter={tickFormatter} />
                    <YAxis tickFormatter={(value) => compactCurrency.format(value)} />
                    <Tooltip
                      formatter={(value: number) => [formatCurrency(value, currency), t('common.revenue')]}
                      labelFormatter={labelFormatter}
                    />
                    <Area
                      type="monotone"
                      dataKey="value"
                      stroke={CHART_PRIMARY}
                      strokeWidth={2}
                      fill={AREA_FILL}
                    />
                  </AreaChart>
                </ResponsiveContainer>
              ) : (
                <ChartEmptyState
                  title={revenueEmptyTitle}
                  description={revenueEmptyDescription}
                />
              )}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">{t('dashboard.unitsTrend')}</CardTitle>
            <CardDescription className="text-xs">
              {unitsTrendDescription}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="h-[300px]">
              {mixed && unitsComposed.length > 0 ? (
                <ResponsiveContainer width="100%" height="100%">
                  <ComposedChart data={unitsComposed}>
                    <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                    <XAxis dataKey="date" tickFormatter={tickFormatter} />
                    <YAxis />
                    <Tooltip
                      formatter={(value: number) => formatNumber(value)}
                      labelFormatter={labelFormatter}
                    />
                    <Legend />
                    <Bar
                      dataKey="vendor"
                      name={t('dashboard.seriesVendor')}
                      fill={vendorColor}
                      fillOpacity={0.85}
                      radius={[4, 4, 0, 0]}
                      maxBarSize={36}
                    />
                    <Line
                      type="monotone"
                      dataKey="seller"
                      name={t('dashboard.seriesSeller')}
                      stroke={CHART_PRIMARY}
                      strokeWidth={2}
                      dot={false}
                    />
                  </ComposedChart>
                </ResponsiveContainer>
              ) : hasVendor && !hasSeller && vendorUnits && vendorUnits.data_points.length > 0 ? (
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={vendorUnits.data_points}>
                    <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                    <XAxis dataKey="date" tickFormatter={tickFormatter} />
                    <YAxis />
                    <Tooltip
                      formatter={(value: number) => [formatNumber(value), t('dashboard.seriesVendor')]}
                      labelFormatter={labelFormatter}
                    />
                    <Bar dataKey="value" fill={vendorColor} fillOpacity={0.85} radius={[4, 4, 0, 0]} maxBarSize={36} />
                  </BarChart>
                </ResponsiveContainer>
              ) : unitsTrend && unitsTrend.data_points.length > 0 ? (
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={unitsTrend.data_points}>
                    <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                    <XAxis dataKey="date" tickFormatter={tickFormatter} />
                    <YAxis />
                    <Tooltip
                      formatter={(value: number) => [formatNumber(value), t('common.units')]}
                      labelFormatter={labelFormatter}
                    />
                    <Line
                      type="monotone"
                      dataKey="value"
                      stroke={CHART_PRIMARY}
                      strokeWidth={2}
                      dot={false}
                    />
                  </LineChart>
                </ResponsiveContainer>
              ) : (
                <ChartEmptyState
                  title={unitsEmptyTitle}
                  description={unitsEmptyDescription}
                />
              )}
            </div>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <div className="flex items-start justify-between gap-3">
            <div>
              <CardTitle>{t('dashboard.trendingProducts')}</CardTitle>
              <CardDescription>{t('dashboard.trendingProductsDesc')}</CardDescription>
            </div>
            <Badge variant="outline">
              {formatNumber(trendingProducts?.summary.eligible_products || 0)}
            </Badge>
          </div>
        </CardHeader>
        <CardContent className="grid gap-4 lg:grid-cols-2">
          <TrendingProductsList
            title={t('dashboard.topRisingProducts')}
            products={trendingProducts?.rising_products || []}
            emptyKey="dashboard.noRisingProducts"
            accountId={scope.mode === 'account' ? scope.accountId : undefined}
          />
          <TrendingProductsList
            title={t('dashboard.topDecliningProducts')}
            products={trendingProducts?.declining_products || []}
            emptyKey="dashboard.noDecliningProducts"
            accountId={scope.mode === 'account' ? scope.accountId : undefined}
          />
        </CardContent>
      </Card>

      {/* Account Drill-Down Cards */}
      {scope.mode !== 'account' && accountSummary?.accounts && accountSummary.accounts.length > 1 && (
        <div>
          <div className="mb-3">
            <div className="flex items-center gap-2">
              <h2 className="text-lg font-semibold">{t('dashboard.accounts')}</h2>
              <Badge variant="outline">{accountSummary.accounts.length}</Badge>
            </div>
            <p className="mt-1 text-sm text-muted-foreground">{t('dashboard.selectAccountHint')}</p>
          </div>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {accountSummary.accounts.map((account) => {
              const statusColor =
                account.sync_status === 'success'
                  ? 'bg-emerald-500'
                  : account.sync_status === 'error'
                  ? 'bg-red-500'
                  : account.sync_status === 'syncing'
                  ? 'bg-amber-500'
                  : 'bg-muted-foreground'

              return (
                <Link
                  key={account.id}
                  to={{
                    pathname: '/',
                    search: `?${buildDashboardSearchParams(searchParams, account.id).toString()}`,
                  }}
                  className="block"
                >
                  <Card className="h-full cursor-pointer transition-colors hover:border-primary/50">
                    <CardContent className="py-4 px-5">
                      <div className="flex items-center justify-between mb-2">
                        <div className="flex items-center gap-2 min-w-0">
                          <div className={cn('h-2 w-2 rounded-full shrink-0', statusColor)} />
                          <span className="font-medium truncate">{account.account_name}</span>
                        </div>
                        <Badge variant="outline" className="text-xs shrink-0">
                          {account.marketplace_country}
                        </Badge>
                      </div>
                      <div className="grid grid-cols-3 gap-2 text-sm">
                        <div>
                          <p className="text-xs text-muted-foreground">{t('common.revenue')}</p>
                          <p className="font-medium">{formatCurrency(account.total_sales_30d)}</p>
                        </div>
                        <div>
                          <p className="text-xs text-muted-foreground">{t('common.units')}</p>
                          <p className="font-medium">{formatNumber(account.total_units_30d)}</p>
                        </div>
                        <div>
                          <p className="text-xs text-muted-foreground">ASINs</p>
                          <p className="font-medium">{account.active_asins}</p>
                        </div>
                      </div>
                      <div className="mt-4 flex items-center justify-between border-t border-border/60 pt-3 text-sm font-medium text-primary">
                        <span>{t('dashboard.viewAccountDashboard')}</span>
                        <div className="flex items-center gap-1">
                          <Globe className="h-3.5 w-3.5" />
                          <ArrowRight className="h-3.5 w-3.5" />
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                </Link>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
