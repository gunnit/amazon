import { useQuery } from '@tanstack/react-query'
import {
  TrendingUp,
  TrendingDown,
  DollarSign,
  Package,
  ShoppingCart,
  Loader2,
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
import { analyticsApi, accountsApi } from '@/services/api'
import { formatCurrency, formatNumber, formatPercent, cn } from '@/lib/utils'
import { FilterBar, DateRangeFilter, AccountFilter } from '@/components/filters'
import { useFilterStore, getFilterDateRange } from '@/store/filterStore'
import type { DashboardKPIs, TrendData, AccountSummary } from '@/types'

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
            <span className="ml-1">vs previous period</span>
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

export default function Dashboard() {
  const filterState = useFilterStore()
  const { datePreset, customStartDate, customEndDate, accountIds, resetDashboard } = filterState
  const dateRange = getFilterDateRange({ datePreset, customStartDate, customEndDate })

  const { data: kpis, isLoading: kpisLoading } = useQuery<DashboardKPIs>({
    queryKey: ['dashboard-kpis', dateRange, accountIds],
    queryFn: () => analyticsApi.getDashboard({
      start_date: dateRange.start,
      end_date: dateRange.end,
      account_ids: accountIds.length > 0 ? accountIds : undefined,
    }),
  })

  const { data: trends, isLoading: trendsLoading } = useQuery<TrendData[]>({
    queryKey: ['dashboard-trends', dateRange, accountIds],
    queryFn: () => analyticsApi.getTrends({
      metrics: ['revenue', 'units'],
      start_date: dateRange.start,
      end_date: dateRange.end,
      account_ids: accountIds.length > 0 ? accountIds : undefined,
    }),
  })

  const { data: accountSummary, isLoading: accountsLoading } = useQuery<AccountSummary>({
    queryKey: ['accounts-summary'],
    queryFn: () => accountsApi.getSummary(),
  })

  const isLoading = kpisLoading || trendsLoading || accountsLoading

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-96">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    )
  }

  const revenueTrend = trends?.find((t) => t.metric_name === 'revenue')
  const unitsTrend = trends?.find((t) => t.metric_name === 'units')

  const days = datePreset === 'custom' ? 'selected period' : `last ${datePreset} days`

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Dashboard</h1>
          <p className="text-muted-foreground">
            Track revenue and order volume across your connected Amazon accounts.
          </p>
        </div>
        <FilterBar onReset={resetDashboard}>
          <DateRangeFilter />
          <AccountFilter />
        </FilterBar>
      </div>

      {/* Account Status */}
      <div className="flex gap-4 flex-wrap">
        <Badge variant="success" className="text-sm py-1 px-3">
          {accountSummary?.active_accounts || 0} Active Accounts
        </Badge>
        {accountSummary?.syncing_accounts ? (
          <Badge variant="secondary" className="text-sm py-1 px-3">
            {accountSummary.syncing_accounts} Syncing
          </Badge>
        ) : null}
        {accountSummary?.error_accounts ? (
          <Badge variant="destructive" className="text-sm py-1 px-3">
            {accountSummary.error_accounts} Errors
          </Badge>
        ) : null}
      </div>

      {/* KPI Cards */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <KPICard
          title="Total Revenue"
          value={kpis?.total_revenue.value || 0}
          change={kpis?.total_revenue.change_percent}
          trend={kpis?.total_revenue.trend}
          icon={DollarSign}
          format="currency"
          emphasis="primary"
          className="md:col-span-2"
        />
        <KPICard
          title="Total Orders"
          value={kpis?.total_orders.value || 0}
          change={kpis?.total_orders.change_percent}
          trend={kpis?.total_orders.trend}
          icon={ShoppingCart}
        />
        <KPICard
          title="Units Sold"
          value={kpis?.total_units.value || 0}
          change={kpis?.total_units.change_percent}
          trend={kpis?.total_units.trend}
          icon={Package}
        />
      </div>

      {/* Charts */}
      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">Revenue Trend</CardTitle>
            <CardDescription className="text-xs">
              Daily revenue over the {days}
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
                      tickFormatter={(value) => new Date(value).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
                    />
                    <YAxis tickFormatter={(value) => `$${(value / 1000).toFixed(0)}k`} />
                    <Tooltip
                      formatter={(value: number) => [formatCurrency(value), 'Revenue']}
                      labelFormatter={(label) => new Date(label).toLocaleDateString()}
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
                  title="We're still syncing revenue data."
                  description="Once your account is connected, daily revenue will appear here within a few hours."
                />
              )}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">Units Trend</CardTitle>
            <CardDescription className="text-xs">
              Daily units sold over the {days}
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
                      tickFormatter={(value) => new Date(value).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
                    />
                    <YAxis />
                    <Tooltip
                      formatter={(value: number) => [formatNumber(value), 'Units']}
                      labelFormatter={(label) => new Date(label).toLocaleDateString()}
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
                  title="Units will populate after the next sync."
                  description="Connect an account or wait for the next data refresh to see unit volume."
                />
              )}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
