import { useQuery } from '@tanstack/react-query'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
} from 'recharts'
import { Loader2 } from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { analyticsApi } from '@/services/api'
import { formatCurrency, formatNumber } from '@/lib/utils'
import { useDemoStore } from '@/store/demoStore'
import { mockCategoryData, mockHourlyOrders } from '@/mocks/mockData'
import {
  FilterBar,
  DateRangeFilter,
  AccountFilter,
  GroupByFilter,
  CategoryFilter,
} from '@/components/filters'
import { useFilterStore, getFilterDateRange } from '@/store/filterStore'

const COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899']

function ChartDisabledState({
  title,
  description,
}: {
  title: string
  description: string
}) {
  const bars = [4, 7, 3, 8, 5, 6, 4, 7, 3]

  return (
    <div className="flex h-full flex-col items-center justify-center gap-4 text-center">
      <div className="w-full max-w-sm rounded-md border border-dashed border-border/60 bg-muted/20 p-4">
        <div className="grid grid-cols-9 items-end gap-2 h-16">
          {bars.map((height, index) => (
            <div
              key={`${title}-bar-${index}`}
              className="w-full rounded-sm bg-muted/40"
              style={{ height: `${height * 8}%` }}
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

export default function Analytics() {
  const { mockDataEnabled } = useDemoStore()
  const filterState = useFilterStore()
  const {
    datePreset,
    customStartDate,
    customEndDate,
    accountIds,
    analyticsGroupBy,
    analyticsCategory,
    setAnalyticsGroupBy,
    setAnalyticsCategory,
    resetAnalytics,
    resetDashboard,
  } = filterState
  const dateRange = getFilterDateRange({ datePreset, customStartDate, customEndDate })

  const handleResetAll = () => {
    resetDashboard()
    resetAnalytics()
  }

  const { data: topPerformers, isLoading } = useQuery({
    queryKey: ['top-performers', dateRange, accountIds],
    queryFn: () => analyticsApi.getTopPerformers({
      start_date: dateRange.start,
      end_date: dateRange.end,
      limit: 10,
      account_ids: accountIds.length > 0 ? accountIds : undefined,
    }),
    enabled: mockDataEnabled,
  })

  const { data: kpis } = useQuery({
    queryKey: ['dashboard-kpis-analytics', dateRange, accountIds],
    queryFn: () => analyticsApi.getDashboard({
      start_date: dateRange.start,
      end_date: dateRange.end,
      account_ids: accountIds.length > 0 ? accountIds : undefined,
    }),
  })

  if (isLoading && mockDataEnabled) {
    return (
      <div className="flex items-center justify-center h-96">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    )
  }

  const filteredCategoryData = analyticsCategory
    ? mockCategoryData.filter((c) => c.name === analyticsCategory)
    : mockCategoryData

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Analytics</h1>
          <p className="text-muted-foreground">
            Deep dive into your Amazon performance metrics
          </p>
        </div>
        <FilterBar onReset={handleResetAll}>
          <DateRangeFilter />
          <AccountFilter />
          <GroupByFilter value={analyticsGroupBy} onChange={setAnalyticsGroupBy} />
          <CategoryFilter value={analyticsCategory} onChange={setAnalyticsCategory} />
        </FilterBar>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        {/* Top Products by Revenue */}
        <Card className="col-span-2 md:col-span-1">
          <CardHeader>
            <CardTitle>Top Products by Revenue</CardTitle>
            <CardDescription>Best performing products this period</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="h-[300px]">
              {mockDataEnabled && topPerformers?.by_revenue && topPerformers.by_revenue.length > 0 ? (
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart
                    data={topPerformers.by_revenue.slice(0, 5)}
                    layout="vertical"
                    margin={{ left: 80 }}
                  >
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis type="number" tickFormatter={(value) => `$${(value / 1000).toFixed(0)}k`} />
                    <YAxis
                      type="category"
                      dataKey="asin"
                      width={70}
                      tickFormatter={(value) => value.slice(0, 8)}
                    />
                    <Tooltip formatter={(value: number) => [formatCurrency(value), 'Revenue']} />
                    <Bar dataKey="total_revenue" fill="hsl(var(--primary))" />
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <ChartDisabledState
                  title="Enable demo data to view analytics charts."
                  description="Go to Settings → Data and turn on Demo Data Mode."
                />
              )}
            </div>
          </CardContent>
        </Card>

        {/* Sales by Category */}
        <Card className="col-span-2 md:col-span-1">
          <CardHeader>
            <CardTitle>Sales by Category</CardTitle>
            <CardDescription>
              {analyticsCategory
                ? `Showing: ${analyticsCategory}`
                : 'Revenue distribution across categories'}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="h-[300px]">
              {mockDataEnabled ? (
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={filteredCategoryData}
                      cx="50%"
                      cy="50%"
                      labelLine={false}
                      label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
                      outerRadius={100}
                      fill="#8884d8"
                      dataKey="value"
                    >
                      {filteredCategoryData.map((_, index) => (
                        <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip />
                  </PieChart>
                </ResponsiveContainer>
              ) : (
                <ChartDisabledState
                  title="Category insights are available in demo mode."
                  description="Enable Demo Data Mode to preview this chart."
                />
              )}
            </div>
          </CardContent>
        </Card>

        {/* Orders by Hour */}
        <Card className="col-span-2">
          <CardHeader>
            <CardTitle>Orders by Hour</CardTitle>
            <CardDescription>When your customers are most active</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="h-[300px]">
              {mockDataEnabled ? (
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={mockHourlyOrders}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="hour" />
                    <YAxis />
                    <Tooltip />
                    <Bar dataKey="orders" fill="hsl(var(--primary))" />
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <ChartDisabledState
                  title="Hourly demand is hidden by default."
                  description="Turn on Demo Data Mode to see how orders trend."
                />
              )}
            </div>
          </CardContent>
        </Card>

        {/* Performance Metrics */}
        <Card className="col-span-2">
          <CardHeader>
            <CardTitle>Performance Summary</CardTitle>
            <CardDescription>Key metrics comparison</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid gap-4 md:grid-cols-4">
              <div className="space-y-2">
                <p className="text-sm text-muted-foreground">Average Order Value</p>
                <p className="text-2xl font-bold">
                  {formatCurrency(kpis?.average_order_value.value || 0)}
                </p>
              </div>
              <div className="space-y-2">
                <p className="text-sm text-muted-foreground">Conversion Rate</p>
                <p className="text-2xl font-bold">3.2%</p>
              </div>
              <div className="space-y-2">
                <p className="text-sm text-muted-foreground">Return Rate</p>
                <p className="text-2xl font-bold">
                  {(kpis?.return_rate.value || 0).toFixed(1)}%
                </p>
              </div>
              <div className="space-y-2">
                <p className="text-sm text-muted-foreground">Active Products</p>
                <p className="text-2xl font-bold">{formatNumber(kpis?.active_asins || 0)}</p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
