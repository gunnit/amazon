import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  Download,
  Loader2,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { reportsApi } from '@/services/api'
import { formatCurrency, formatDate, formatNumber } from '@/lib/utils'
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
import type { AdvertisingMetricsItem, InventoryReportItem, SalesAggregated } from '@/types'

type ReportTab = 'sales' | 'inventory' | 'advertising'

export default function Reports() {
  const [activeTab, setActiveTab] = useState<ReportTab>('sales')
  const [exportModalOpen, setExportModalOpen] = useState(false)
  const { t } = useTranslation()

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

  const handleResetAll = () => {
    resetDashboard()
    resetReports()
  }

  const { data: salesData, isLoading } = useQuery<SalesAggregated[]>({
    queryKey: ['sales-aggregated', dateRange, accountIds, reportsGroupBy],
    queryFn: () => reportsApi.getSalesAggregated({
      start_date: dateRange.start,
      end_date: dateRange.end,
      account_ids: accountIds.length > 0 ? accountIds : undefined,
      group_by: reportsGroupBy !== 'day' ? reportsGroupBy : undefined,
    }),
  })

  const { data: inventoryData = [], isLoading: inventoryLoading } = useQuery<InventoryReportItem[]>({
    queryKey: ['inventory', accountIds, reportsLowStockOnly],
    queryFn: () => reportsApi.getInventory({
      account_ids: accountIds.length > 0 ? accountIds : undefined,
      low_stock_only: reportsLowStockOnly || undefined,
    }),
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

  const totals = salesData?.reduce(
    (acc, row) => ({
      totalUnits: acc.totalUnits + Number(row.total_units),
      totalSales: acc.totalSales + Number(row.total_sales),
      totalOrders: acc.totalOrders + Number(row.total_orders),
    }),
    { totalUnits: 0, totalSales: 0, totalOrders: 0 }
  ) || { totalUnits: 0, totalSales: 0, totalOrders: 0 }

  const groupByLabel =
    reportsGroupBy === 'week'
      ? t('reports.weeklySales')
      : reportsGroupBy === 'month'
      ? t('reports.monthlySales')
      : t('reports.dailySales')

  const salesCurrency = salesData?.[0]?.currency || 'EUR'

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
              <GroupByFilter value={reportsGroupBy} onChange={setReportsGroupBy} />
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
            <CardHeader>
              <CardTitle>{groupByLabel}</CardTitle>
              <CardDescription>
                {dateRange.start} to {dateRange.end}
              </CardDescription>
            </CardHeader>
            <CardContent>
              {isLoading ? (
                <div className="flex items-center justify-center h-32">
                  <Loader2 className="h-8 w-8 animate-spin text-primary" />
                </div>
              ) : salesData && salesData.length > 0 ? (
                <div className="overflow-x-auto">
                  <table className="w-full">
                    <thead>
                      <tr className="border-b">
                        <th className="text-left py-3 px-4 font-medium">{t('reports.date')}</th>
                        <th className="text-right py-3 px-4 font-medium">{t('common.units')}</th>
                        <th className="text-right py-3 px-4 font-medium">{t('common.revenue')}</th>
                        <th className="text-right py-3 px-4 font-medium">{t('common.orders')}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {salesData.map((row) => (
                        <tr key={row.date} className="border-b last:border-0">
                          <td className="py-3 px-4">{formatDate(row.date)}</td>
                          <td className="py-3 px-4 text-right">{formatNumber(Number(row.total_units))}</td>
                          <td className="py-3 px-4 text-right">{formatCurrency(Number(row.total_sales), row.currency || 'EUR')}</td>
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
              {inventoryLoading ? (
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
                <div className="text-center py-8 text-muted-foreground">
                  {reportsLowStockOnly
                    ? t('reports.noLowStock')
                    : t('reports.noInventory')}
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
