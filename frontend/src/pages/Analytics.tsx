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
import { Loader2 } from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
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
import type { CategorySalesData, HourlyOrdersData } from '@/types'

export default function Analytics() {
  const { t } = useTranslation()
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

  const { data: kpis } = useQuery({
    queryKey: ['dashboard-kpis-analytics', dateRange, accountIds],
    queryFn: () => analyticsApi.getDashboard({
      start_date: dateRange.start,
      end_date: dateRange.end,
      account_ids: accountIds.length > 0 ? accountIds : undefined,
    }),
  })

  const isLoading = topPerformersLoading || categoryLoading || hourlyLoading

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-96">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    )
  }

  const categoryOptions = Array.from(
    new Set((salesByCategory || []).map((row) => row.category).filter(Boolean))
  )
  const categoryChartData = analyticsCategory
    ? (salesByCategory || []).filter((row) => row.category === analyticsCategory)
    : (salesByCategory || [])

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
              {topPerformers?.by_revenue && topPerformers.by_revenue.length > 0 ? (
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
                    <Tooltip formatter={(value: number) => [formatCurrency(value), t('common.revenue')]} />
                    <Bar dataKey="total_revenue" fill="hsl(var(--primary))" />
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
              {categoryChartData.length > 0 ? (
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={categoryChartData.slice(0, 8)} margin={{ left: 24, right: 12 }}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis
                      dataKey="category"
                      interval={0}
                      angle={-20}
                      height={70}
                      textAnchor="end"
                      tickFormatter={(value) => String(value).slice(0, 12)}
                    />
                    <YAxis tickFormatter={(value) => `$${(Number(value) / 1000).toFixed(0)}k`} />
                    <Tooltip formatter={(value: number) => [formatCurrency(value), t('common.revenue')]} />
                    <Bar dataKey="total_revenue" fill="hsl(var(--primary))" />
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
      </div>
    </div>
  )
}
