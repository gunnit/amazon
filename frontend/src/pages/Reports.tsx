import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  FileSpreadsheet,
  Presentation,
  Loader2,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useToast } from '@/components/ui/use-toast'
import { reportsApi, exportsApi } from '@/services/api'
import { formatCurrency, formatNumber, formatDate } from '@/lib/utils'
import {
  FilterBar,
  DateRangeFilter,
  AccountFilter,
  GroupByFilter,
  ToggleFilter,
} from '@/components/filters'
import { useFilterStore, getFilterDateRange } from '@/store/filterStore'
import type { SalesAggregated } from '@/types'

export default function Reports() {
  const [activeTab, setActiveTab] = useState('sales')
  const [isExporting, setIsExporting] = useState(false)
  const { toast } = useToast()

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

  const { data: inventoryData, isLoading: inventoryLoading } = useQuery({
    queryKey: ['inventory', accountIds, reportsLowStockOnly],
    queryFn: () => reportsApi.getInventory({
      account_ids: accountIds.length > 0 ? accountIds : undefined,
      low_stock_only: reportsLowStockOnly || undefined,
    }),
    enabled: activeTab === 'inventory',
  })

  const { data: advertisingData, isLoading: advertisingLoading } = useQuery({
    queryKey: ['advertising', dateRange, accountIds],
    queryFn: () => reportsApi.getAdvertising({
      start_date: dateRange.start,
      end_date: dateRange.end,
      account_ids: accountIds.length > 0 ? accountIds : undefined,
    }),
    enabled: activeTab === 'advertising',
  })

  const handleExportExcel = async () => {
    setIsExporting(true)
    try {
      const blob = await exportsApi.exportExcel({
        start_date: dateRange.start,
        end_date: dateRange.end,
        include_sales: true,
        include_advertising: true,
      })

      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `inthezon_report_${dateRange.start}_${dateRange.end}.xlsx`
      document.body.appendChild(a)
      a.click()
      window.URL.revokeObjectURL(url)
      document.body.removeChild(a)

      toast({ title: 'Excel report downloaded' })
    } catch {
      toast({
        variant: 'destructive',
        title: 'Export failed',
        description: 'Please try again.',
      })
    } finally {
      setIsExporting(false)
    }
  }

  const handleExportPowerPoint = async () => {
    setIsExporting(true)
    try {
      const blob = await exportsApi.exportPowerPoint({
        start_date: dateRange.start,
        end_date: dateRange.end,
      })

      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `inthezon_presentation_${dateRange.start}_${dateRange.end}.pptx`
      document.body.appendChild(a)
      a.click()
      window.URL.revokeObjectURL(url)
      document.body.removeChild(a)

      toast({ title: 'PowerPoint presentation downloaded' })
    } catch {
      toast({
        variant: 'destructive',
        title: 'Export failed',
        description: 'Please try again.',
      })
    } finally {
      setIsExporting(false)
    }
  }

  // Calculate totals
  const totals = salesData?.reduce(
    (acc, day) => ({
      totalUnits: acc.totalUnits + day.total_units,
      totalSales: acc.totalSales + day.total_sales,
      totalOrders: acc.totalOrders + day.total_orders,
    }),
    { totalUnits: 0, totalSales: 0, totalOrders: 0 }
  ) || { totalUnits: 0, totalSales: 0, totalOrders: 0 }

  const groupByLabel =
    reportsGroupBy === 'week' ? 'Weekly' : reportsGroupBy === 'month' ? 'Monthly' : 'Daily'

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Reports</h1>
          <p className="text-muted-foreground">
            View and export your Amazon performance data
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
                label="Low stock only"
                checked={reportsLowStockOnly}
                onChange={setReportsLowStockOnly}
                id="low-stock-toggle"
              />
            )}
          </FilterBar>
          <Button variant="outline" size="sm" onClick={handleExportExcel} disabled={isExporting} className="h-9">
            <FileSpreadsheet className="mr-2 h-4 w-4" />
            Excel
          </Button>
          <Button variant="outline" size="sm" onClick={handleExportPowerPoint} disabled={isExporting} className="h-9">
            <Presentation className="mr-2 h-4 w-4" />
            PowerPoint
          </Button>
        </div>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-4">
        <TabsList>
          <TabsTrigger value="sales">Sales</TabsTrigger>
          <TabsTrigger value="inventory">Inventory</TabsTrigger>
          <TabsTrigger value="advertising">Advertising</TabsTrigger>
        </TabsList>

        <TabsContent value="sales" className="space-y-4">
          {/* Summary Cards */}
          <div className="grid gap-4 md:grid-cols-3">
            <Card>
              <CardContent className="pt-6">
                <div className="text-2xl font-bold">{formatCurrency(totals.totalSales)}</div>
                <p className="text-sm text-muted-foreground">Total Revenue</p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-6">
                <div className="text-2xl font-bold">{formatNumber(totals.totalUnits)}</div>
                <p className="text-sm text-muted-foreground">Units Sold</p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-6">
                <div className="text-2xl font-bold">{formatNumber(totals.totalOrders)}</div>
                <p className="text-sm text-muted-foreground">Total Orders</p>
              </CardContent>
            </Card>
          </div>

          {/* Data Table */}
          <Card>
            <CardHeader>
              <CardTitle>{groupByLabel} Sales</CardTitle>
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
                        <th className="text-left py-3 px-4 font-medium">Date</th>
                        <th className="text-right py-3 px-4 font-medium">Units</th>
                        <th className="text-right py-3 px-4 font-medium">Revenue</th>
                        <th className="text-right py-3 px-4 font-medium">Orders</th>
                      </tr>
                    </thead>
                    <tbody>
                      {salesData.map((day, index) => (
                        <tr key={index} className="border-b last:border-0">
                          <td className="py-3 px-4">{formatDate(day.date)}</td>
                          <td className="py-3 px-4 text-right">{formatNumber(day.total_units)}</td>
                          <td className="py-3 px-4 text-right">{formatCurrency(day.total_sales)}</td>
                          <td className="py-3 px-4 text-right">{formatNumber(day.total_orders)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="text-center py-8 text-muted-foreground">
                  No sales data available for this period
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="inventory">
          <Card>
            <CardHeader>
              <CardTitle>Inventory Status</CardTitle>
              <CardDescription>Current stock levels across all accounts</CardDescription>
            </CardHeader>
            <CardContent>
              {inventoryLoading ? (
                <div className="flex items-center justify-center h-32">
                  <Loader2 className="h-8 w-8 animate-spin text-primary" />
                </div>
              ) : inventoryData && (inventoryData as unknown[]).length > 0 ? (
                <div className="overflow-x-auto">
                  <table className="w-full">
                    <thead>
                      <tr className="border-b">
                        <th className="text-left py-3 px-4 font-medium">ASIN</th>
                        <th className="text-left py-3 px-4 font-medium">SKU</th>
                        <th className="text-right py-3 px-4 font-medium">On Hand</th>
                        <th className="text-right py-3 px-4 font-medium">Inbound</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(inventoryData as Array<{ asin: string; sku: string; on_hand: number; inbound: number }>).map(
                        (item, index) => (
                          <tr key={index} className="border-b last:border-0">
                            <td className="py-3 px-4 font-mono text-sm">{item.asin}</td>
                            <td className="py-3 px-4">{item.sku}</td>
                            <td className="py-3 px-4 text-right">{formatNumber(item.on_hand)}</td>
                            <td className="py-3 px-4 text-right">{formatNumber(item.inbound)}</td>
                          </tr>
                        )
                      )}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="text-center py-8 text-muted-foreground">
                  {reportsLowStockOnly
                    ? 'No low-stock items found'
                    : 'Connect an account and sync to view inventory data'}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="advertising">
          <Card>
            <CardHeader>
              <CardTitle>Advertising Performance</CardTitle>
              <CardDescription>PPC campaign metrics</CardDescription>
            </CardHeader>
            <CardContent>
              {advertisingLoading ? (
                <div className="flex items-center justify-center h-32">
                  <Loader2 className="h-8 w-8 animate-spin text-primary" />
                </div>
              ) : advertisingData && (advertisingData as unknown[]).length > 0 ? (
                <div className="overflow-x-auto">
                  <table className="w-full">
                    <thead>
                      <tr className="border-b">
                        <th className="text-left py-3 px-4 font-medium">Campaign</th>
                        <th className="text-right py-3 px-4 font-medium">Spend</th>
                        <th className="text-right py-3 px-4 font-medium">Clicks</th>
                        <th className="text-right py-3 px-4 font-medium">ACoS</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(advertisingData as Array<{ campaign: string; spend: number; clicks: number; acos: number }>).map(
                        (item, index) => (
                          <tr key={index} className="border-b last:border-0">
                            <td className="py-3 px-4">{item.campaign}</td>
                            <td className="py-3 px-4 text-right">{formatCurrency(item.spend)}</td>
                            <td className="py-3 px-4 text-right">{formatNumber(item.clicks)}</td>
                            <td className="py-3 px-4 text-right">{(item.acos * 100).toFixed(1)}%</td>
                          </tr>
                        )
                      )}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="text-center py-8 text-muted-foreground">
                  Connect an account and sync to view advertising data
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  )
}
