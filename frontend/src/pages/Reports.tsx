import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  Download,
  Loader2,
} from 'lucide-react'
import {
  ResponsiveContainer,
  ComposedChart,
  AreaChart,
  BarChart,
  Area,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
} from 'recharts'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { accountsApi, reportsApi } from '@/services/api'
import { formatCurrency, formatNumber } from '@/lib/utils'
import { AREA_FILL, CHART_PRIMARY, CHART_SERIES } from '@/lib/chart-theme'
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
import type { AdvertisingMetricsItem, AmazonAccount, InventoryReportItem, SalesAggregated } from '@/types'

type ReportTab = 'sales' | 'inventory' | 'advertising'

type SalesRow = SalesAggregated & { origin: 'daily' | 'monthly' }

const VENDOR_COLOR = CHART_SERIES[2]

function ContextField({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className="mt-0.5 font-medium text-foreground">{value}</p>
    </div>
  )
}

export default function Reports() {
  const [activeTab, setActiveTab] = useState<ReportTab>('sales')
  const [exportModalOpen, setExportModalOpen] = useState(false)
  const { t, language } = useTranslation()

  const filterState = useFilterStore()
  const {
    datePreset,
    customStartDate,
    customEndDate,
    accountIds,
    reportsGroupBy,
    reportsLowStockOnly,
    setReportsGroupBy,
    setReportsLowStockOnly,
    resetDashboard,
    resetReports,
  } = filterState

  const dateRange = getFilterDateRange({ datePreset, customStartDate, customEndDate })

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

  const handleResetAll = () => {
    resetDashboard()
    resetReports()
  }

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
  })

  // When seller (daily) and vendor (monthly) are both in scope the combined rows
  // merge a vendor monthly lump onto a date that looks like a single day. Fetch
  // each cadence separately so the table and chart can label its true origin and
  // a vendor month doesn't read as "1528 sales in one day".
  const { data: sellerSales } = useQuery<SalesAggregated[]>({
    queryKey: ['sales-aggregated-seller', dateRange, sellerAccountIds, reportsGroupBy],
    queryFn: () => reportsApi.getSalesAggregated({
      start_date: dateRange.start,
      end_date: dateRange.end,
      account_ids: sellerAccountIds,
      group_by: reportsGroupBy !== 'day' ? reportsGroupBy : undefined,
    }),
    enabled: isMixed && hasSeller,
  })

  const { data: vendorSales } = useQuery<SalesAggregated[]>({
    queryKey: ['sales-aggregated-vendor', dateRange, vendorAccountIds, reportsGroupBy],
    queryFn: () => reportsApi.getSalesAggregated({
      start_date: dateRange.start,
      end_date: dateRange.end,
      account_ids: vendorAccountIds,
      // Vendor data is monthly regardless of the requested cadence.
      group_by: 'month',
    }),
    enabled: isMixed && hasVendor,
  })

  const { data: inventoryData = [], isLoading: inventoryLoading } = useQuery<InventoryReportItem[]>({
    queryKey: ['inventory', accountIds, reportsLowStockOnly],
    queryFn: () => reportsApi.getInventory({
      account_ids: accountIds.length > 0 ? accountIds : undefined,
      low_stock_only: reportsLowStockOnly || undefined,
    }),
    enabled: activeTab === 'inventory',
  })

  const { data: inventoryAccounts = [], isLoading: inventoryAccountsLoading } = useQuery<AmazonAccount[]>({
    queryKey: ['accounts', 'inventory'],
    queryFn: () => accountsApi.list(),
    enabled: activeTab === 'inventory',
  })

  const { data: advertisingData = [], isLoading: advertisingLoading } = useQuery<AdvertisingMetricsItem[]>({
    queryKey: ['advertising', dateRange, accountIds],
    queryFn: () => reportsApi.getAdvertising({
      start_date: dateRange.start,
      end_date: dateRange.end,
      account_ids: accountIds.length > 0 ? accountIds : undefined,
    }),
    enabled: activeTab === 'advertising',
  })

  // Totals always come from the combined query so the cards stay reconciled with
  // the rest of the platform, no matter how the rows are split below.
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

  // Table rows. In the mixed case we tag each row with its true cadence; otherwise
  // the single in-scope cadence carries the whole table.
  const salesRows: SalesRow[] = isMixed
    ? [
        ...(sellerSales ?? []).map((row): SalesRow => ({ ...row, origin: 'daily' })),
        ...(vendorSales ?? []).map((row): SalesRow => ({ ...row, origin: 'monthly' })),
      ].sort((a, b) => a.date.localeCompare(b.date) || a.origin.localeCompare(b.origin))
    : (() => {
        const origin: SalesRow['origin'] =
          salesGranularity === 'monthly' || reportsGroupBy === 'month' ? 'monthly' : 'daily'
        const rows = (combinedSales ?? []).map((row): SalesRow => ({ ...row, origin }))
        // Monthly view: keep zeroed months visible instead of dropping the line.
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

  const groupByLabel =
    reportsGroupBy === 'week'
      ? t('reports.weeklySales')
      : reportsGroupBy === 'month'
      ? t('reports.monthlySales')
      : t('reports.dailySales')

  // Chart series. Vendor cadence is always monthly; in the mixed case we merge the
  // seller daily line and vendor monthly bars on a shared date axis so a vendor
  // month never renders as a false daily spike.
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

  // Context-bar values.
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
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">{t('reports.title')}</h1>
          <p className="text-muted-foreground">
            {t('reports.subtitle')}
          </p>
        </div>
        <div className="flex items-center gap-3 flex-wrap">
          <FilterBar onReset={handleResetAll}>
            <DateRangeFilter />
            <AccountFilter />
            {activeTab === 'sales' && (
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
          </FilterBar>
          <Button variant="outline" size="sm" onClick={() => setExportModalOpen(true)} className="h-9">
            <Download className="mr-2 h-4 w-4" />
            {t('export.button')}
          </Button>
        </div>
      </div>

      <Tabs value={activeTab} onValueChange={(value) => setActiveTab(value as ReportTab)} className="space-y-4">
        <TabsList>
          <TabsTrigger value="sales">{t('reports.sales')}</TabsTrigger>
          <TabsTrigger value="inventory">{t('reports.inventory')}</TabsTrigger>
          <TabsTrigger value="advertising">{t('reports.advertising')}</TabsTrigger>
        </TabsList>

        <TabsContent value="sales" className="space-y-4">
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
              ) : salesRows.length > 0 ? (
                <div className="overflow-x-auto">
                  <table className="w-full">
                    <thead>
                      <tr className="border-b">
                        <th className="text-left py-3 px-4 font-medium">{t('reports.date')}</th>
                        {showOriginColumn && (
                          <th className="text-left py-3 px-4 font-medium">{t('reports.colOrigin')}</th>
                        )}
                        <th className="text-right py-3 px-4 font-medium">{t('common.units')}</th>
                        <th className="text-right py-3 px-4 font-medium">{t('common.revenue')}</th>
                        <th className="text-right py-3 px-4 font-medium">{t('common.orders')}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {salesRows.map((row) => (
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
              ) : (
                <div className="text-center py-8 text-muted-foreground">
                  {t('reports.noSalesData')}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="inventory">
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
        </TabsContent>

        <TabsContent value="advertising">
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
                          <td className="py-3 px-4 text-right">{formatCurrency(Number(item.cost), salesCurrency)}</td>
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
        </TabsContent>
      </Tabs>

      <ExportModal open={exportModalOpen} onOpenChange={setExportModalOpen} />
      <ScheduledReportsPanel />
    </div>
  )
}
