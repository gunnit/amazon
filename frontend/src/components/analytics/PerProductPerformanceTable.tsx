import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, keepPreviousData } from '@tanstack/react-query'
import { ArrowDown, ArrowUp, ChevronLeft, ChevronRight, Loader2, Search } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { analyticsApi } from '@/services/api'
import { formatCurrency } from '@/lib/utils'
import { useTranslation } from '@/i18n'
import type { PerProductSortKey } from '@/types'

interface Props {
  dateRange: { start: string; end: string }
  accountIds: string[]
  enabled: boolean
}

const PAGE_SIZES = [25, 50, 100, 200]

export function PerProductPerformanceTable({ dateRange, accountIds, enabled }: Props) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [offset, setOffset] = useState(0)
  const [limit, setLimit] = useState(50)
  const [sortBy, setSortBy] = useState<PerProductSortKey>('revenue')
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc')
  const [searchInput, setSearchInput] = useState('')
  const [search, setSearch] = useState('')

  const query = useQuery({
    queryKey: [
      'per-product-performance',
      dateRange,
      accountIds,
      offset,
      limit,
      sortBy,
      sortDir,
      search,
    ],
    queryFn: () =>
      analyticsApi.getPerProductPerformance({
        start_date: dateRange.start,
        end_date: dateRange.end,
        account_ids: accountIds.length > 0 ? accountIds : undefined,
        offset,
        limit,
        sort_by: sortBy,
        sort_dir: sortDir,
        search: search || undefined,
      }),
    enabled,
    placeholderData: keepPreviousData,
  })

  const total = query.data?.total ?? 0
  const items = query.data?.items ?? []
  const page = Math.floor(offset / limit) + 1
  const lastPage = total === 0 ? 1 : Math.ceil(total / limit)

  const toggleSort = (key: PerProductSortKey) => {
    if (sortBy === key) {
      setSortDir((d) => (d === 'desc' ? 'asc' : 'desc'))
    } else {
      setSortBy(key)
      setSortDir(key === 'acos' ? 'asc' : 'desc')
    }
    setOffset(0)
  }

  const sortIcon = (key: PerProductSortKey) =>
    sortBy === key ? (
      sortDir === 'desc' ? (
        <ArrowDown className="ml-1 inline h-3 w-3" />
      ) : (
        <ArrowUp className="ml-1 inline h-3 w-3" />
      )
    ) : null

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('analytics.perProduct.title')}</CardTitle>
        <CardDescription>{t('analytics.perProduct.desc')}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap items-end gap-3">
          <div className="flex-1 min-w-[240px] relative">
            <Search className="absolute left-2 top-2.5 h-4 w-4 text-muted-foreground" />
            <Input
              className="pl-8"
              placeholder={t('analytics.perProduct.searchPlaceholder')}
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  setSearch(searchInput.trim())
                  setOffset(0)
                }
              }}
            />
          </div>
          <Button
            variant="outline"
            onClick={() => {
              setSearch(searchInput.trim())
              setOffset(0)
            }}
          >
            {t('analytics.perProduct.applySearch')}
          </Button>
          <div className="min-w-[120px]">
            <Select
              value={String(limit)}
              onValueChange={(val) => {
                setLimit(Number(val))
                setOffset(0)
              }}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {PAGE_SIZES.map((n) => (
                  <SelectItem key={n} value={String(n)}>
                    {t('analytics.perProduct.pageSize', { n })}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>

        <div className="rounded-md border overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>ASIN</TableHead>
                <TableHead>{t('analytics.perProduct.col.title')}</TableHead>
                <TableHead>SKU</TableHead>
                <TableHead
                  className="text-right cursor-pointer select-none"
                  onClick={() => toggleSort('units')}
                >
                  {t('analytics.perProduct.col.units')}
                  {sortIcon('units')}
                </TableHead>
                <TableHead
                  className="text-right cursor-pointer select-none"
                  onClick={() => toggleSort('revenue')}
                >
                  {t('analytics.perProduct.col.revenue')}
                  {sortIcon('revenue')}
                </TableHead>
                <TableHead
                  className="text-right cursor-pointer select-none"
                  onClick={() => toggleSort('orders')}
                >
                  {t('analytics.perProduct.col.orders')}
                  {sortIcon('orders')}
                </TableHead>
                <TableHead
                  className="text-right cursor-pointer select-none"
                  onClick={() => toggleSort('ad_spend')}
                >
                  {t('analytics.perProduct.col.adSpend')}
                  {sortIcon('ad_spend')}
                </TableHead>
                <TableHead
                  className="text-right cursor-pointer select-none"
                  onClick={() => toggleSort('acos')}
                >
                  ACoS
                  {sortIcon('acos')}
                </TableHead>
                <TableHead
                  className="text-right cursor-pointer select-none"
                  onClick={() => toggleSort('roas')}
                >
                  ROAS
                  {sortIcon('roas')}
                </TableHead>
                <TableHead className="text-right">BSR</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {query.isLoading && (
                <TableRow>
                  <TableCell colSpan={10} className="text-center py-8">
                    <Loader2 className="mx-auto h-5 w-5 animate-spin" />
                  </TableCell>
                </TableRow>
              )}
              {!query.isLoading && items.length === 0 && (
                <TableRow>
                  <TableCell colSpan={10} className="text-center py-8 text-muted-foreground">
                    {t('analytics.perProduct.empty')}
                  </TableCell>
                </TableRow>
              )}
              {items.map((item) => (
                <TableRow
                  key={item.asin}
                  className="cursor-pointer hover:bg-muted/40"
                  onClick={() => navigate(`/analytics/product/${item.asin}`)}
                >
                  <TableCell className="font-mono text-xs">{item.asin}</TableCell>
                  <TableCell className="max-w-[280px] truncate" title={item.title ?? ''}>
                    {item.title ?? '—'}
                  </TableCell>
                  <TableCell className="font-mono text-xs">{item.sku ?? '—'}</TableCell>
                  <TableCell className="text-right tabular-nums">
                    {item.total_units.toLocaleString()}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {formatCurrency(Number(item.total_revenue))}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {item.total_orders.toLocaleString()}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {item.ad_spend ? formatCurrency(item.ad_spend) : '—'}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {item.acos != null ? `${item.acos.toFixed(1)}%` : '—'}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {item.roas != null ? item.roas.toFixed(2) : '—'}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {item.current_bsr != null ? item.current_bsr.toLocaleString() : '—'}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>

        <div className="flex items-center justify-between text-sm">
          <span className="text-muted-foreground">
            {t('analytics.perProduct.showing', {
              from: total === 0 ? 0 : offset + 1,
              to: Math.min(offset + limit, total),
              total,
            })}
          </span>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={offset === 0 || query.isFetching}
              onClick={() => setOffset(Math.max(0, offset - limit))}
            >
              <ChevronLeft className="h-4 w-4" />
            </Button>
            <span className="tabular-nums">
              {page} / {lastPage}
            </span>
            <Button
              variant="outline"
              size="sm"
              disabled={offset + limit >= total || query.isFetching}
              onClick={() => setOffset(offset + limit)}
            >
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
