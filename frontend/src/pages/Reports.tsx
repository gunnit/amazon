import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  FileSpreadsheet,
  Presentation,
  Calendar,
  Loader2,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { useToast } from '@/components/ui/use-toast'
import { reportsApi, exportsApi } from '@/services/api'
import { formatCurrency, formatNumber, formatDate, getDateRange } from '@/lib/utils'
import type { SalesAggregated } from '@/types'

export default function Reports() {
  const [dateRangeDays, setDateRangeDays] = useState('30')
  const [isExporting, setIsExporting] = useState(false)
  const { toast } = useToast()

  const dateRange = getDateRange(parseInt(dateRangeDays))

  const { data: salesData, isLoading } = useQuery<SalesAggregated[]>({
    queryKey: ['sales-aggregated', dateRange],
    queryFn: () => reportsApi.getSalesAggregated({
      start_date: dateRange.start,
      end_date: dateRange.end,
    }),
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
    } catch (error) {
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
    } catch (error) {
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

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Reports</h1>
          <p className="text-muted-foreground">
            View and export your Amazon performance data
          </p>
        </div>
        <div className="flex items-center gap-4">
          <Select value={dateRangeDays} onValueChange={setDateRangeDays}>
            <SelectTrigger className="w-[180px]">
              <Calendar className="mr-2 h-4 w-4" />
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="7">Last 7 days</SelectItem>
              <SelectItem value="30">Last 30 days</SelectItem>
              <SelectItem value="60">Last 60 days</SelectItem>
              <SelectItem value="90">Last 90 days</SelectItem>
            </SelectContent>
          </Select>
          <Button variant="outline" onClick={handleExportExcel} disabled={isExporting}>
            <FileSpreadsheet className="mr-2 h-4 w-4" />
            Excel
          </Button>
          <Button variant="outline" onClick={handleExportPowerPoint} disabled={isExporting}>
            <Presentation className="mr-2 h-4 w-4" />
            PowerPoint
          </Button>
        </div>
      </div>

      <Tabs defaultValue="sales" className="space-y-4">
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
              <CardTitle>Daily Sales</CardTitle>
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
              <div className="text-center py-8 text-muted-foreground">
                Connect an account and sync to view inventory data
              </div>
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
              <div className="text-center py-8 text-muted-foreground">
                Connect an account and sync to view advertising data
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  )
}
