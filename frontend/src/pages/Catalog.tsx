import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowDown, ArrowUp, ArrowUpDown, ChevronLeft, ChevronRight, Download, ImageOff, Info, Loader2, Package } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
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
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { useToast } from '@/components/ui/use-toast'
import { accountsApi, catalogApi } from '@/services/api'
import { useTranslation } from '@/i18n'
import { DateRangeFilter } from '@/components/filters'
import { useFilterStore, getFilterDateRange } from '@/store/filterStore'
import type { Product } from '@/types'
import { BulkUpdateCard } from '@/components/catalog/BulkUpdateCard'
import { ImportCard } from '@/components/catalog/ImportCard'
import { PricesCard } from '@/components/catalog/PricesCard'
import { AvailabilityCard } from '@/components/catalog/AvailabilityCard'
import { ImagesCard } from '@/components/catalog/ImagesCard'

type StringSortKey = 'asin' | 'title' | 'sku' | 'brand'
type NumberSortKey = 'current_price' | 'current_bsr'
type SortKey = StringSortKey | NumberSortKey
type SortDirection = 'asc' | 'desc'

const STRING_SORT_KEYS: StringSortKey[] = ['asin', 'title', 'sku', 'brand']

const priceFormatter = new Intl.NumberFormat('it-IT', {
  style: 'currency',
  currency: 'EUR',
})

function isStringSortKey(key: SortKey): key is StringSortKey {
  return (STRING_SORT_KEYS as SortKey[]).includes(key)
}

function compareProducts(left: Product, right: Product, sortKey: SortKey, sortDirection: SortDirection) {
  const modifier = sortDirection === 'asc' ? 1 : -1

  if (isStringSortKey(sortKey)) {
    return modifier * (left[sortKey] ?? '').localeCompare(right[sortKey] ?? '')
  }

  return modifier * ((left[sortKey] ?? 0) - (right[sortKey] ?? 0))
}

export default function Catalog() {
  const { t } = useTranslation()
  const { toast } = useToast()
  const queryClient = useQueryClient()

  const [search, setSearch] = useState('')
  const [activeOnly, setActiveOnly] = useState(true)
  const [activeAccountId, setActiveAccountId] = useState<string>('')
  const [page, setPage] = useState(0)
  const [sortKey, setSortKey] = useState<SortKey>('title')
  const [sortDirection, setSortDirection] = useState<SortDirection>('asc')
  const [selectedProduct, setSelectedProduct] = useState<Product | null>(null)
  const pageSize = 50

  const { datePreset, customStartDate, customEndDate } = useFilterStore()
  const dateRange = getFilterDateRange({ datePreset, customStartDate, customEndDate })

  const accountsQuery = useQuery({
    queryKey: ['accounts'],
    queryFn: () => accountsApi.list(),
  })

  const productsQuery = useQuery({
    queryKey: ['catalog', 'products', search, activeOnly, activeAccountId, dateRange.start, dateRange.end],
    queryFn: () =>
      catalogApi.getProducts({
        search: search || undefined,
        active_only: activeOnly,
        date_from: dateRange.start,
        date_to: dateRange.end,
        limit: 500,
        account_ids: activeAccountId ? [activeAccountId] : undefined,
      }),
  })

  const products = productsQuery.data ?? []
  const syncedCount = products.length
  const withSalesCount = useMemo(
    () => products.filter((p) => p.has_sales_in_period === true).length,
    [products],
  )
  const withoutSalesCount = syncedCount - withSalesCount
  const sortedProducts = useMemo(
    () => [...products].sort((a, b) => compareProducts(a, b, sortKey, sortDirection)),
    [products, sortKey, sortDirection],
  )
  const totalPages = Math.ceil(sortedProducts.length / pageSize)
  const pagedProducts = useMemo(
    () => sortedProducts.slice(page * pageSize, page * pageSize + pageSize),
    [sortedProducts, page],
  )

  useEffect(() => {
    setPage(0)
  }, [search, activeOnly, activeAccountId, dateRange.start, dateRange.end])

  const handleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDirection((current) => (current === 'asc' ? 'desc' : 'asc'))
      return
    }
    setSortKey(key)
    setSortDirection(isStringSortKey(key) ? 'asc' : 'desc')
  }

  const handleExport = () => {
    const headers = ['ASIN', 'SKU', t('catalog.products.col.title'), t('catalog.products.col.brand'), t('catalog.products.col.price'), t('catalog.products.col.bsr'), t('catalog.products.col.status')]
    const escape = (value: unknown) => {
      const str = value == null ? '' : String(value)
      return /[",\n]/.test(str) ? `"${str.replace(/"/g, '""')}"` : str
    }
    const rows = sortedProducts.map((p) => [
      p.asin,
      p.sku ?? '',
      p.title ?? '',
      p.brand ?? '',
      p.current_price ?? '',
      p.current_bsr ?? '',
      p.is_active ? t('catalog.products.active') : t('catalog.products.inactive'),
    ])
    const csv = [headers, ...rows].map((row) => row.map(escape).join(',')).join('\n')
    const blob = new Blob(['﻿' + csv], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = `catalog-products-${new Date().toISOString().slice(0, 10)}.csv`
    document.body.appendChild(anchor)
    anchor.click()
    document.body.removeChild(anchor)
    URL.revokeObjectURL(url)
  }

  const accounts = accountsQuery.data ?? []
  const selectedAccountId = activeAccountId || accounts[0]?.id || ''

  const sharedProps = {
    accountId: selectedAccountId,
    accounts,
    onAccountChange: setActiveAccountId,
    toast,
    t,
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Package className="h-6 w-6 text-primary" />
        <div>
          <h1 className="text-2xl font-bold">{t('catalog.title')}</h1>
          <p className="text-muted-foreground text-sm">{t('catalog.subtitle')}</p>
        </div>
      </div>

      <Tabs defaultValue="products" className="space-y-4">
        <TabsList>
          <TabsTrigger value="products">{t('catalog.tab.products')}</TabsTrigger>
          <TabsTrigger value="import">{t('catalog.tab.import')}</TabsTrigger>
          <TabsTrigger value="bulk">{t('catalog.tab.bulk')}</TabsTrigger>
          <TabsTrigger value="prices">{t('catalog.tab.prices')}</TabsTrigger>
          <TabsTrigger value="availability">{t('catalog.tab.availability')}</TabsTrigger>
          <TabsTrigger value="images">{t('catalog.tab.images')}</TabsTrigger>
        </TabsList>

        <TabsContent value="products">
          <Card>
            <CardHeader>
              <CardTitle>{t('catalog.products.title')}</CardTitle>
              <CardDescription>{t('catalog.products.description')}</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex flex-wrap items-end gap-3">
                <div className="flex-1 min-w-[220px]">
                  <Label>{t('catalog.products.search')}</Label>
                  <Input
                    placeholder={t('catalog.products.searchPlaceholder')}
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                  />
                </div>
                <div className="min-w-[220px]">
                  <Label>{t('catalog.products.account')}</Label>
                  <Select
                    value={activeAccountId || '__all__'}
                    onValueChange={(val) => setActiveAccountId(val === '__all__' ? '' : val)}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="__all__">{t('filter.allAccounts')}</SelectItem>
                      {accounts.map((acc) => (
                        <SelectItem key={acc.id} value={acc.id}>
                          {acc.account_name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label>{t('filter.period')}</Label>
                  <div className="mt-1">
                    <DateRangeFilter />
                  </div>
                </div>
                <Button
                  variant={activeOnly ? 'default' : 'outline'}
                  onClick={() => setActiveOnly((v) => !v)}
                >
                  {activeOnly
                    ? t('catalog.products.showingActive')
                    : t('catalog.products.showingAll')}
                </Button>
                <Button
                  variant="outline"
                  onClick={handleExport}
                  disabled={products.length === 0}
                >
                  <Download className="mr-2 h-4 w-4" />
                  {t('export.button')}
                </Button>
              </div>

              <div className="rounded-md border">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <SortableHead sortKey="asin" activeKey={sortKey} direction={sortDirection} onSort={handleSort}>
                        ASIN
                      </SortableHead>
                      <SortableHead sortKey="title" activeKey={sortKey} direction={sortDirection} onSort={handleSort}>
                        {t('catalog.products.col.title')}
                      </SortableHead>
                      <SortableHead sortKey="sku" activeKey={sortKey} direction={sortDirection} onSort={handleSort}>
                        SKU
                      </SortableHead>
                      <SortableHead sortKey="brand" activeKey={sortKey} direction={sortDirection} onSort={handleSort}>
                        {t('catalog.products.col.brand')}
                      </SortableHead>
                      <SortableHead sortKey="current_price" activeKey={sortKey} direction={sortDirection} onSort={handleSort}>
                        {t('catalog.products.col.price')}
                      </SortableHead>
                      <SortableHead sortKey="current_bsr" activeKey={sortKey} direction={sortDirection} onSort={handleSort}>
                        {t('catalog.products.col.bsr')}
                      </SortableHead>
                      <TableHead>{t('catalog.products.col.status')}</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {productsQuery.isLoading && (
                      <TableRow>
                        <TableCell colSpan={7} className="text-center py-8">
                          <Loader2 className="mx-auto h-5 w-5 animate-spin" />
                        </TableCell>
                      </TableRow>
                    )}
                    {products.length === 0 && !productsQuery.isLoading && (
                      <TableRow>
                        <TableCell colSpan={7} className="text-center py-8 text-muted-foreground">
                          {t('catalog.products.empty')}
                        </TableCell>
                      </TableRow>
                    )}
                    {pagedProducts.map((p) => (
                      <TableRow
                        key={p.id}
                        className="cursor-pointer"
                        onClick={() => setSelectedProduct(p)}
                      >
                        <TableCell className="font-mono text-xs">{p.asin}</TableCell>
                        <TableCell className="max-w-[320px] truncate" title={p.title ?? p.asin}>
                          {p.title ? (
                            p.title
                          ) : (
                            <span className="text-muted-foreground italic">
                              {t('catalog.products.titleMissing')}
                            </span>
                          )}
                        </TableCell>
                        <TableCell className="font-mono text-xs">
                          {p.sku
                            ? p.sku
                            : p.account_type === 'vendor'
                              ? <span className="text-muted-foreground" title={t('catalog.products.skuVendorNa')}>N/A</span>
                              : '—'}
                        </TableCell>
                        <TableCell>{p.brand ?? '—'}</TableCell>
                        <TableCell>
                          {p.current_price != null ? priceFormatter.format(Number(p.current_price)) : '—'}
                        </TableCell>
                        <TableCell>{p.current_bsr ?? '—'}</TableCell>
                        <TableCell>
                          <div className="flex flex-wrap items-center gap-1.5">
                            <Badge variant={p.is_active ? 'default' : 'secondary'}>
                              {p.is_active ? t('catalog.products.active') : t('catalog.products.inactive')}
                            </Badge>
                            {p.has_sales_in_period === false && (
                              <Badge variant="outline" className="text-muted-foreground">
                                {t('catalog.products.noSalesBadge')}
                              </Badge>
                            )}
                          </div>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>

              {products.length > 0 && (
                <div className="flex items-center justify-between">
                  <div className="space-y-0.5">
                    {withSalesCount > 0 ? (
                      <div className="flex items-center gap-1.5 text-xs">
                        <span>
                          {t('catalog.products.countSummary', {
                            conVendite: withSalesCount,
                            sincronizzati: syncedCount,
                          })}
                        </span>
                        <span
                          className="text-muted-foreground"
                          title={t('catalog.products.countTooltip')}
                          aria-label={t('catalog.products.countTooltip')}
                        >
                          <Info className="h-3.5 w-3.5" />
                        </span>
                      </div>
                    ) : (
                      <div className="flex items-center gap-1.5 text-xs">
                        <span>
                          {t('catalog.products.emptyPeriod', { sincronizzati: syncedCount })}
                        </span>
                        <span
                          className="text-muted-foreground"
                          title={t('catalog.products.countTooltip')}
                          aria-label={t('catalog.products.countTooltip')}
                        >
                          <Info className="h-3.5 w-3.5" />
                        </span>
                      </div>
                    )}
                    {withoutSalesCount > 0 && (
                      <p className="text-xs text-muted-foreground">
                        {t('catalog.products.countWithoutSales', { senzaVendite: withoutSalesCount })}
                      </p>
                    )}
                  </div>
                  {totalPages > 1 && (
                    <div className="flex items-center gap-2">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => setPage((p) => Math.max(0, p - 1))}
                        disabled={page === 0}
                      >
                        <ChevronLeft className="h-4 w-4" />
                      </Button>
                      <span className="text-xs text-muted-foreground">
                        {page + 1} / {totalPages}
                      </span>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
                        disabled={page >= totalPages - 1}
                      >
                        <ChevronRight className="h-4 w-4" />
                      </Button>
                    </div>
                  )}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="import">
          <ImportCard
            {...sharedProps}
            onSuccess={() => queryClient.invalidateQueries({ queryKey: ['catalog', 'products'] })}
          />
        </TabsContent>

        <TabsContent value="bulk">
          <BulkUpdateCard
            {...sharedProps}
            onSuccess={() => queryClient.invalidateQueries({ queryKey: ['catalog', 'products'] })}
          />
        </TabsContent>

        <TabsContent value="prices">
          <PricesCard {...sharedProps} />
        </TabsContent>

        <TabsContent value="availability">
          <AvailabilityCard {...sharedProps} />
        </TabsContent>

        <TabsContent value="images">
          <ImagesCard {...sharedProps} />
        </TabsContent>
      </Tabs>

      <Dialog open={selectedProduct !== null} onOpenChange={(open) => !open && setSelectedProduct(null)}>
        <DialogContent>
          {selectedProduct && (
            <>
              <DialogHeader>
                <DialogTitle>{selectedProduct.title ?? selectedProduct.asin}</DialogTitle>
                <DialogDescription className="font-mono">{selectedProduct.asin}</DialogDescription>
              </DialogHeader>
              <dl className="grid grid-cols-[140px_1fr] gap-x-4 gap-y-2 text-sm">
                <dt className="text-muted-foreground">SKU</dt>
                <dd>{selectedProduct.sku ?? '—'}</dd>
                <dt className="text-muted-foreground">{t('catalog.products.col.title')}</dt>
                <dd>{selectedProduct.title ?? '—'}</dd>
                <dt className="text-muted-foreground">{t('catalog.products.col.brand')}</dt>
                <dd>{selectedProduct.brand ?? '—'}</dd>
                <dt className="text-muted-foreground">{t('catalog.products.col.price')}</dt>
                <dd>
                  {selectedProduct.current_price != null
                    ? priceFormatter.format(Number(selectedProduct.current_price))
                    : '—'}
                </dd>
                <dt className="text-muted-foreground">{t('catalog.products.col.bsr')}</dt>
                <dd>{selectedProduct.current_bsr ?? '—'}</dd>
                <dt className="text-muted-foreground">{t('catalog.products.col.status')}</dt>
                <dd>
                  <Badge variant={selectedProduct.is_active ? 'default' : 'secondary'}>
                    {selectedProduct.is_active
                      ? t('catalog.products.active')
                      : t('catalog.products.inactive')}
                  </Badge>
                </dd>
              </dl>
              {selectedProduct.account_type === 'vendor' && (
                <p className="mt-3 flex items-start gap-2 rounded-md bg-muted px-3 py-2 text-xs text-muted-foreground">
                  <ImageOff className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                  {t('catalog.products.vendorDataUnavailable')}
                </p>
              )}
            </>
          )}
        </DialogContent>
      </Dialog>
    </div>
  )
}

function SortableHead({
  sortKey,
  activeKey,
  direction,
  onSort,
  children,
}: {
  sortKey: SortKey
  activeKey: SortKey
  direction: SortDirection
  onSort: (key: SortKey) => void
  children: ReactNode
}) {
  const isActive = activeKey === sortKey
  const Icon = !isActive ? ArrowUpDown : direction === 'asc' ? ArrowUp : ArrowDown
  return (
    <TableHead>
      <button
        type="button"
        onClick={() => onSort(sortKey)}
        className="flex items-center gap-1.5 font-medium"
      >
        {children}
        <Icon className={`h-3.5 w-3.5 ${isActive ? 'text-foreground' : 'text-muted-foreground'}`} />
      </button>
    </TableHead>
  )
}
