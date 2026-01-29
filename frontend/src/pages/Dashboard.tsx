import { useQuery } from '@tanstack/react-query'
import {
  TrendingUp,
  TrendingDown,
  DollarSign,
  Package,
  ShoppingCart,
  Target,
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
import { formatCurrency, formatNumber, formatPercent, getDateRange } from '@/lib/utils'
import type { DashboardKPIs, TrendData, AccountSummary } from '@/types'

function KPICard({
  title,
  value,
  change,
  trend,
  icon: Icon,
  format = 'number',
}: {
  title: string
  value: number
  change?: number | null
  trend?: 'up' | 'down' | 'stable'
  icon: React.ElementType
  format?: 'number' | 'currency' | 'percent'
}) {
  const formattedValue =
    format === 'currency'
      ? formatCurrency(value)
      : format === 'percent'
      ? `${value.toFixed(1)}%`
      : formatNumber(value)

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium">{title}</CardTitle>
        <Icon className="h-4 w-4 text-muted-foreground" />
      </CardHeader>
      <CardContent>
        <div className="text-2xl font-bold">{formattedValue}</div>
        {change !== null && change !== undefined && (
          <div className="flex items-center text-xs text-muted-foreground mt-1">
            {trend === 'up' ? (
              <TrendingUp className="h-3 w-3 mr-1 text-green-500" />
            ) : trend === 'down' ? (
              <TrendingDown className="h-3 w-3 mr-1 text-red-500" />
            ) : null}
            <span className={trend === 'up' ? 'text-green-500' : trend === 'down' ? 'text-red-500' : ''}>
              {formatPercent(change)}
            </span>
            <span className="ml-1">vs previous period</span>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

export default function Dashboard() {
  const dateRange = getDateRange(30)

  const { data: kpis, isLoading: kpisLoading } = useQuery<DashboardKPIs>({
    queryKey: ['dashboard-kpis', dateRange],
    queryFn: () => analyticsApi.getDashboard({
      start_date: dateRange.start,
      end_date: dateRange.end,
    }),
  })

  const { data: trends, isLoading: trendsLoading } = useQuery<TrendData[]>({
    queryKey: ['dashboard-trends', dateRange],
    queryFn: () => analyticsApi.getTrends({
      metrics: ['revenue', 'units'],
      start_date: dateRange.start,
      end_date: dateRange.end,
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

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Dashboard</h1>
        <p className="text-muted-foreground">
          Overview of your Amazon accounts performance
        </p>
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
        />
        <KPICard
          title="Units Sold"
          value={kpis?.total_units.value || 0}
          change={kpis?.total_units.change_percent}
          trend={kpis?.total_units.trend}
          icon={Package}
        />
        <KPICard
          title="Total Orders"
          value={kpis?.total_orders.value || 0}
          change={kpis?.total_orders.change_percent}
          trend={kpis?.total_orders.trend}
          icon={ShoppingCart}
        />
        <KPICard
          title="ROAS"
          value={kpis?.roas.value || 0}
          change={null}
          trend={kpis?.roas.trend}
          icon={Target}
        />
      </div>

      {/* Charts */}
      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Revenue Trend</CardTitle>
            <CardDescription>Daily revenue over the last 30 days</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="h-[300px]">
              {revenueTrend && revenueTrend.data_points.length > 0 ? (
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={revenueTrend.data_points}>
                    <CartesianGrid strokeDasharray="3 3" />
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
                <div className="flex items-center justify-center h-full text-muted-foreground">
                  No data available
                </div>
              )}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Units Trend</CardTitle>
            <CardDescription>Daily units sold over the last 30 days</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="h-[300px]">
              {unitsTrend && unitsTrend.data_points.length > 0 ? (
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={unitsTrend.data_points}>
                    <CartesianGrid strokeDasharray="3 3" />
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
                <div className="flex items-center justify-center h-full text-muted-foreground">
                  No data available
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Advertising KPIs */}
      <div className="grid gap-4 md:grid-cols-4">
        <KPICard
          title="ACoS"
          value={kpis?.acos.value || 0}
          change={null}
          trend={kpis?.acos.trend}
          icon={Target}
          format="percent"
        />
        <KPICard
          title="CTR"
          value={kpis?.ctr.value || 0}
          change={null}
          trend={kpis?.ctr.trend}
          icon={Target}
          format="percent"
        />
        <KPICard
          title="Active ASINs"
          value={kpis?.active_asins || 0}
          icon={Package}
        />
        <KPICard
          title="Accounts Synced"
          value={kpis?.accounts_synced || 0}
          icon={ShoppingCart}
        />
      </div>
    </div>
  )
}
