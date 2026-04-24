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
} from 'recharts'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { analyticsApi, accountsApi } from '@/services/api'
import { formatCurrency, formatNumber, formatPercent, cn } from '@/lib/utils'
import { buildDashboardSearchParams, resolveDashboardScope } from '@/lib/dashboardScope'
import { FilterBar, DateRangeFilter, AccountFilter, ComparisonFilter } from '@/components/filters'
import ProductTrendBadge from '@/components/analytics/ProductTrendBadge'
import ProductTrendSparkline from '@/components/analytics/ProductTrendSparkline'
import { PeriodComparisonCard } from '@/components/PeriodComparisonCard'
import { useFilterStore, getComparisonPeriods, getFilterDateRange } from '@/store/filterStore'
import { useTranslation } from '@/i18n'
import { useToast } from '@/components/ui/use-toast'
import type {
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
  emphasis = 'secondary',
  className,
}: {
  title: string
  value: number
  change?: number | null
  trend?: 'up' | 'down' | 'stable'
  icon: React.ElementType
  format?: 'number' | 'currency' | 'percent'
  emphasis?: 'primary' | 'secondary'
  className?: string
}) {
  const { t } = useTranslation()
  const formattedValue =
    format === 'currency'
      ? formatCurrency(value)
      : format === 'percent'
      ? `${value.toFixed(1)}%`
      : formatNumber(value)

  return (
    <Card
      className={cn(
        emphasis === 'primary'
          ? "border-border/70"
          : "border-border/60",
        className
      )}
    >
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle
          className={cn(
            "uppercase tracking-wide",
            emphasis === 'primary'
              ? "text-xs font-semibold text-foreground"
              : "text-[11px] font-medium text-muted-foreground"
          )}
        >
          {title}
        </CardTitle>
        <Icon className="h-3.5 w-3.5 text-muted-foreground/70" />
      </CardHeader>
      <CardContent>
        <div className={cn(emphasis === 'primary' ? "text-3xl font-semibold" : "text-2xl font-semibold")}>
          {formattedValue}
        </div>
        {change !== null && change !== undefined && (
          <div className="flex items-center text-xs text-muted-foreground mt-2">
            {trend === 'up' ? (
              <TrendingUp className="h-3 w-3 mr-1 text-emerald-500" />
            ) : trend === 'down' ? (
              <TrendingDown className="h-3 w-3 mr-1 text-rose-500" />
            ) : null}
            <span
              className={trend === 'up' ? 'text-emerald-500' : trend === 'down' ? 'text-rose-500' : ''}
            >
              {formatPercent(change)}
            </span>
            <span className="ml-1">{t('common.vsPreviousPeriod')}</span>
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
    queryKey: ['accounts-summary'],
    queryFn: () => accountsApi.getSummary(),
  })

  const scope = resolveDashboardScope(
    requestedAccountId,
    accountsLoading ? undefined : accountSummary?.accounts
  )
  const queriesEnabled = scope.mode !== 'resolving'
  const effectiveAccountIds = scope.mode === 'account' ? [scope.accountId] : accountIds

  const { data: kpis, isLoading: kpisLoading } = useQuery<DashboardKPIs>({
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

  const revenueTrend = trends?.find((t) => t.metric_name === 'revenue')
  const unitsTrend = trends?.find((t) => t.metric_name === 'units')

  const days = datePreset === 'custom' ? t('common.selectedPeriod') : t('common.lastNDays', { n: datePreset })
  const revenueTrendDescription =
    scope.mode === 'account'
      ? t('dashboard.revenueTrendDescAccount', { days, accountName: scope.accountName })
      : t('dashboard.revenueTrendDesc', { days })
  const unitsTrendDescription =
    scope.mode === 'account'
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
      {scope.mode === 'account' && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border/70 bg-muted/30 px-4 py-3">
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <span className="text-muted-foreground">{t('dashboard.breadcrumbOverview')}</span>
            <ChevronRight className="h-4 w-4 text-muted-foreground" />
            <span className="font-medium text-foreground">{scope.accountName}</span>
            <Badge variant="outline">{scope.marketplace}</Badge>
            <Badge variant="secondary">{t('dashboard.scopedToSingleAccount')}</Badge>
            <ScopeStatusBadge status={scope.status} />
          </div>
          <Button
            variant="ghost"
            size="sm"
            onClick={handleExitAccountView}
            className="gap-1.5"
          >
            <ArrowLeft className="h-4 w-4" />
            {t('dashboard.backToOverview')}
          </Button>
        </div>
      )}

      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          {scope.mode === 'account' && (
            <p className="text-sm font-medium text-muted-foreground">{t('dashboard.title')}</p>
          )}
          <h1 className="text-3xl font-bold tracking-tight">
            {scope.mode === 'account' ? scope.accountName : t('dashboard.title')}
          </h1>
          <p className="text-muted-foreground">
            {headerSubtitle}
          </p>
        </div>
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

      {/* Account Status */}
      {scope.mode !== 'account' && (
        <div className="flex gap-4 flex-wrap">
          <Badge variant="success" className="text-sm py-1 px-3">
            {accountSummary?.active_accounts || 0} {t('dashboard.activeAccounts')}
          </Badge>
          {accountSummary?.syncing_accounts ? (
            <Badge variant="secondary" className="text-sm py-1 px-3">
              {accountSummary.syncing_accounts} {t('dashboard.syncing')}
            </Badge>
          ) : null}
          {accountSummary?.error_accounts ? (
            <Badge variant="destructive" className="text-sm py-1 px-3">
              {accountSummary.error_accounts} {t('dashboard.errors')}
            </Badge>
          ) : null}
        </div>
      )}

      {/* KPI Cards */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <KPICard
          title={t('dashboard.totalRevenue')}
          value={kpis?.total_revenue.value || 0}
          change={kpis?.total_revenue.change_percent}
          trend={kpis?.total_revenue.trend}
          icon={DollarSign}
          format="currency"
          emphasis="primary"
          className="md:col-span-2"
        />
        <KPICard
          title={t('dashboard.totalOrders')}
          value={kpis?.total_orders.value || 0}
          change={kpis?.total_orders.change_percent}
          trend={kpis?.total_orders.trend}
          icon={ShoppingCart}
        />
        <KPICard
          title={t('dashboard.unitsSold')}
          value={kpis?.total_units.value || 0}
          change={kpis?.total_units.change_percent}
          trend={kpis?.total_units.trend}
          icon={Package}
        />
      </div>

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
              {revenueTrend && revenueTrend.data_points.length > 0 ? (
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={revenueTrend.data_points}>
                    <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                    <XAxis
                      dataKey="date"
                      tickFormatter={(value) => new Date(value + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
                    />
                    <YAxis tickFormatter={(value) => `$${(value / 1000).toFixed(0)}k`} />
                    <Tooltip
                      formatter={(value: number) => [formatCurrency(value), t('common.revenue')]}
                      labelFormatter={(label) => new Date(label + 'T00:00:00').toLocaleDateString()}
                    />
                    <Area
                      type="monotone"
                      dataKey="value"
                      stroke="hsl(var(--primary))"
                      fill="hsl(var(--primary))"
                      fillOpacity={0.2}
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
              {unitsTrend && unitsTrend.data_points.length > 0 ? (
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={unitsTrend.data_points}>
                    <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                    <XAxis
                      dataKey="date"
                      tickFormatter={(value) => new Date(value + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
                    />
                    <YAxis />
                    <Tooltip
                      formatter={(value: number) => [formatNumber(value), t('common.units')]}
                      labelFormatter={(label) => new Date(label + 'T00:00:00').toLocaleDateString()}
                    />
                    <Line
                      type="monotone"
                      dataKey="value"
                      stroke="hsl(var(--primary))"
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
