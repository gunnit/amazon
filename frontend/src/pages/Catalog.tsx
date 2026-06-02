import { useEffect, useMemo, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ChevronLeft, ChevronRight, Loader2, Package } from 'lucide-react'
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
import { useToast } from '@/components/ui/use-toast'
import { accountsApi, catalogApi } from '@/services/api'
import { useTranslation } from '@/i18n'
import { BulkUpdateCard } from '@/components/catalog/BulkUpdateCard'
import { PricesCard } from '@/components/catalog/PricesCard'
import { AvailabilityCard } from '@/components/catalog/AvailabilityCard'
import { ImagesCard } from '@/components/catalog/ImagesCard'

export default function Catalog() {
  const { t } = useTranslation()
  const { toast } = useToast()
  const queryClient = useQueryClient()

  const [search, setSearch] = useState('')
  const [activeOnly, setActiveOnly] = useState(true)
  const [activeAccountId, setActiveAccountId] = useState<string>('')
  const [page, setPage] = useState(0)
  const pageSize = 50

  const accountsQuery = useQuery({
    queryKey: ['accounts'],
    queryFn: () => accountsApi.list(),
  })

  const productsQuery = useQuery({
    queryKey: ['catalog', 'products', search, activeOnly, activeAccountId],
    queryFn: () =>
      catalogApi.getProducts({
        search: search || undefined,
        active_only: activeOnly,
        limit: 500,
        account_ids: activeAccountId ? [activeAccountId] : undefined,
      }),
  })

  const products = productsQuery.data ?? []
  const totalPages = Math.ceil(products.length / pageSize)
  const pagedProducts = useMemo(
    () => products.slice(page * pageSize, page * pageSize + pageSize),
    [products, page],
  )

  useEffect(() => {
    setPage(0)
  }, [search, activeOnly, activeAccountId])

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
                <Button
                  variant={activeOnly ? 'default' : 'outline'}
                  onClick={() => setActiveOnly((v) => !v)}
                >
                  {activeOnly
                    ? t('catalog.products.showingActive')
                    : t('catalog.products.showingAll')}
                </Button>
              </div>

              <div className="rounded-md border">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>ASIN</TableHead>
                      <TableHead>{t('catalog.products.col.title')}</TableHead>
                      <TableHead>SKU</TableHead>
                      <TableHead>{t('catalog.products.col.brand')}</TableHead>
                      <TableHead>{t('catalog.products.col.price')}</TableHead>
                      <TableHead>{t('catalog.products.col.bsr')}</TableHead>
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
                      <TableRow key={p.id}>
                        <TableCell className="font-mono text-xs">{p.asin}</TableCell>
                        <TableCell className="max-w-[320px] truncate">{p.title ?? '—'}</TableCell>
                        <TableCell className="font-mono text-xs">
                          {p.sku
                            ? p.sku
                            : p.account_type === 'vendor'
                              ? <span className="text-muted-foreground" title={t('catalog.products.skuVendorNa')}>N/A</span>
                              : '—'}
                        </TableCell>
                        <TableCell>{p.brand ?? '—'}</TableCell>
                        <TableCell>
                          {p.current_price != null ? Number(p.current_price).toFixed(2) : '—'}
                        </TableCell>
                        <TableCell>{p.current_bsr ?? '—'}</TableCell>
                        <TableCell>
                          <Badge variant={p.is_active ? 'default' : 'secondary'}>
                            {p.is_active ? t('catalog.products.active') : t('catalog.products.inactive')}
                          </Badge>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>

              {products.length > 0 && (
                <div className="flex items-center justify-between">
                  <span className="text-xs text-muted-foreground">
                    {products.length} {t('catalog.tab.products').toLowerCase()}
                  </span>
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
    </div>
  )
}
