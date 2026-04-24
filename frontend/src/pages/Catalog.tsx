import { useMemo, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Download, Image as ImageIcon, Loader2, Package, Plus, Star, Trash2, Upload, X } from 'lucide-react'
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
import { accountsApi, catalogApi, imagesApi, type ProductImage } from '@/services/api'
import { useTranslation } from '@/i18n'

type PriceRow = { asin: string; sku: string; price: string }

export default function Catalog() {
  const { t } = useTranslation()
  const { toast } = useToast()
  const queryClient = useQueryClient()

  const [search, setSearch] = useState('')
  const [activeOnly, setActiveOnly] = useState(true)
  const [activeAccountId, setActiveAccountId] = useState<string>('')

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
        limit: 100,
        account_ids: activeAccountId ? [activeAccountId] : undefined,
      }),
  })

  const accounts = accountsQuery.data ?? []
  // Resolve a default account id once accounts load
  const selectedAccountId = activeAccountId || accounts[0]?.id || ''

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
                    {productsQuery.data?.length === 0 && !productsQuery.isLoading && (
                      <TableRow>
                        <TableCell colSpan={7} className="text-center py-8 text-muted-foreground">
                          {t('catalog.products.empty')}
                        </TableCell>
                      </TableRow>
                    )}
                    {productsQuery.data?.map((p) => (
                      <TableRow key={p.id}>
                        <TableCell className="font-mono text-xs">{p.asin}</TableCell>
                        <TableCell className="max-w-[320px] truncate">{p.title ?? '—'}</TableCell>
                        <TableCell className="font-mono text-xs">{p.sku ?? '—'}</TableCell>
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
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="bulk">
          <BulkUpdateCard
            accountId={selectedAccountId}
            accounts={accounts}
            onAccountChange={setActiveAccountId}
            toast={toast}
            t={t}
            onSuccess={() => queryClient.invalidateQueries({ queryKey: ['catalog', 'products'] })}
          />
        </TabsContent>

        <TabsContent value="prices">
          <PricesCard
            accountId={selectedAccountId}
            accounts={accounts}
            onAccountChange={setActiveAccountId}
            toast={toast}
            t={t}
          />
        </TabsContent>

        <TabsContent value="availability">
          <AvailabilityCard
            accountId={selectedAccountId}
            accounts={accounts}
            onAccountChange={setActiveAccountId}
            toast={toast}
            t={t}
          />
        </TabsContent>

        <TabsContent value="images">
          <ImagesCard
            accountId={selectedAccountId}
            accounts={accounts}
            onAccountChange={setActiveAccountId}
            toast={toast}
            t={t}
          />
        </TabsContent>
      </Tabs>
    </div>
  )
}

// ────────────────────────────────────────────────────────────────────────────
// Bulk Update tab
// ────────────────────────────────────────────────────────────────────────────
type TabProps = {
  accountId: string
  accounts: Array<{ id: string; account_name: string }>
  onAccountChange: (id: string) => void
  toast: ReturnType<typeof useToast>['toast']
  t: (key: string, vars?: Record<string, string | number>) => string
}

function AccountPicker({ accountId, accounts, onAccountChange, t }: TabProps) {
  return (
    <div className="space-y-1">
      <Label>{t('catalog.products.account')}</Label>
      <Select value={accountId} onValueChange={onAccountChange}>
        <SelectTrigger>
          <SelectValue placeholder={t('catalog.products.selectAccount')} />
        </SelectTrigger>
        <SelectContent>
          {accounts.map((acc) => (
            <SelectItem key={acc.id} value={acc.id}>
              {acc.account_name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  )
}

function BulkUpdateCard({
  onSuccess,
  ...props
}: TabProps & { onSuccess: () => void }) {
  const { t, toast, accountId } = props
  const fileRef = useRef<HTMLInputElement>(null)
  const [file, setFile] = useState<File | null>(null)
  const [lastResult, setLastResult] = useState<Record<string, unknown> | null>(null)

  const downloadMutation = useMutation({
    mutationFn: () => catalogApi.downloadBulkTemplate(),
    onSuccess: (blob) => {
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = 'bulk_listings_template.xlsx'
      a.click()
      URL.revokeObjectURL(url)
    },
  })

  const uploadMutation = useMutation({
    mutationFn: () => catalogApi.bulkUpdate({ account_id: accountId, file: file! }),
    onSuccess: (data) => {
      setLastResult(data)
      toast({ title: t('catalog.bulk.successTitle'), description: t('catalog.bulk.successDesc') })
      onSuccess()
    },
    onError: (err: unknown) => {
      const message = err && typeof err === 'object' && 'response' in err
        ? ((err as { response?: { data?: { detail?: string } } }).response?.data?.detail ?? 'Error')
        : 'Error'
      toast({ variant: 'destructive', title: 'Error', description: String(message) })
    },
  })

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('catalog.bulk.title')}</CardTitle>
        <CardDescription>{t('catalog.bulk.description')}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <AccountPicker {...props} />

        <div className="flex flex-wrap gap-3">
          <Button
            variant="outline"
            onClick={() => downloadMutation.mutate()}
            disabled={downloadMutation.isPending}
          >
            <Download className="mr-2 h-4 w-4" />
            {t('catalog.bulk.downloadTemplate')}
          </Button>
          <input
            ref={fileRef}
            type="file"
            accept=".xlsx,.xls"
            className="hidden"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
          <Button variant="outline" onClick={() => fileRef.current?.click()}>
            <Upload className="mr-2 h-4 w-4" />
            {file ? file.name : t('catalog.bulk.selectFile')}
          </Button>
          <Button
            onClick={() => uploadMutation.mutate()}
            disabled={!file || !accountId || uploadMutation.isPending}
          >
            {uploadMutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {t('catalog.bulk.submit')}
          </Button>
        </div>

        {lastResult && (
          <pre className="text-xs bg-muted rounded p-3 overflow-x-auto max-h-64">
            {JSON.stringify(lastResult, null, 2)}
          </pre>
        )}
      </CardContent>
    </Card>
  )
}

// ────────────────────────────────────────────────────────────────────────────
// Prices tab
// ────────────────────────────────────────────────────────────────────────────
function PricesCard(props: TabProps) {
  const { t, toast, accountId } = props
  const [rows, setRows] = useState<PriceRow[]>([{ asin: '', sku: '', price: '' }])
  const [result, setResult] = useState<Record<string, unknown> | null>(null)

  const updateRow = (idx: number, patch: Partial<PriceRow>) =>
    setRows((prev) => prev.map((r, i) => (i === idx ? { ...r, ...patch } : r)))

  const validUpdates = useMemo(
    () =>
      rows
        .map((r) => ({
          asin: r.asin.trim() || undefined,
          sku: r.sku.trim() || undefined,
          price: Number.parseFloat(r.price),
        }))
        .filter((r) => (r.asin || r.sku) && Number.isFinite(r.price) && r.price > 0),
    [rows],
  )

  const mutation = useMutation({
    mutationFn: () =>
      catalogApi.updatePrices({
        account_id: accountId,
        updates: validUpdates,
      }),
    onSuccess: (data) => {
      setResult(data)
      toast({ title: t('catalog.prices.successTitle') })
    },
    onError: (err: unknown) => {
      const message = err && typeof err === 'object' && 'response' in err
        ? ((err as { response?: { data?: { detail?: string } } }).response?.data?.detail ?? 'Error')
        : 'Error'
      toast({ variant: 'destructive', title: 'Error', description: String(message) })
    },
  })

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('catalog.prices.title')}</CardTitle>
        <CardDescription>{t('catalog.prices.description')}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <AccountPicker {...props} />

        <div className="space-y-2">
          {rows.map((row, idx) => (
            <div key={idx} className="grid grid-cols-1 md:grid-cols-[2fr_2fr_1fr_auto] gap-2">
              <Input
                placeholder="ASIN"
                value={row.asin}
                onChange={(e) => updateRow(idx, { asin: e.target.value })}
              />
              <Input
                placeholder="SKU"
                value={row.sku}
                onChange={(e) => updateRow(idx, { sku: e.target.value })}
              />
              <Input
                type="number"
                min="0"
                step="0.01"
                placeholder={t('catalog.prices.price')}
                value={row.price}
                onChange={(e) => updateRow(idx, { price: e.target.value })}
              />
              <Button
                variant="ghost"
                size="icon"
                onClick={() => setRows((p) => p.filter((_, i) => i !== idx))}
                disabled={rows.length === 1}
              >
                <Trash2 className="h-4 w-4" />
              </Button>
            </div>
          ))}
          <Button
            variant="outline"
            onClick={() => setRows((p) => [...p, { asin: '', sku: '', price: '' }])}
          >
            <Plus className="mr-2 h-4 w-4" />
            {t('catalog.prices.addRow')}
          </Button>
        </div>

        <div className="flex items-center justify-between">
          <span className="text-sm text-muted-foreground">
            {t('catalog.prices.nValid', { n: validUpdates.length })}
          </span>
          <Button
            onClick={() => mutation.mutate()}
            disabled={!accountId || validUpdates.length === 0 || mutation.isPending}
          >
            {mutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {t('catalog.prices.submit')}
          </Button>
        </div>

        {result && (
          <pre className="text-xs bg-muted rounded p-3 overflow-x-auto max-h-64">
            {JSON.stringify(result, null, 2)}
          </pre>
        )}
      </CardContent>
    </Card>
  )
}

// ────────────────────────────────────────────────────────────────────────────
// Availability tab
// ────────────────────────────────────────────────────────────────────────────
function AvailabilityCard(props: TabProps) {
  const { t, toast, accountId } = props
  const [asin, setAsin] = useState('')
  const [quantity, setQuantity] = useState('')
  const [result, setResult] = useState<Record<string, unknown> | null>(null)

  const runMutation = (isAvailable: boolean) =>
    catalogApi.updateAvailability(asin, {
      account_id: accountId,
      is_available: isAvailable,
      quantity: quantity ? Number.parseInt(quantity, 10) : undefined,
    })

  const enableMutation = useMutation({
    mutationFn: () => runMutation(true),
    onSuccess: (d) => {
      setResult(d)
      toast({ title: t('catalog.availability.enabled') })
    },
    onError: (err: unknown) => {
      const message = err && typeof err === 'object' && 'response' in err
        ? ((err as { response?: { data?: { detail?: string } } }).response?.data?.detail ?? 'Error')
        : 'Error'
      toast({ variant: 'destructive', title: 'Error', description: String(message) })
    },
  })

  const disableMutation = useMutation({
    mutationFn: () => runMutation(false),
    onSuccess: (d) => {
      setResult(d)
      toast({ title: t('catalog.availability.disabled') })
    },
    onError: (err: unknown) => {
      const message = err && typeof err === 'object' && 'response' in err
        ? ((err as { response?: { data?: { detail?: string } } }).response?.data?.detail ?? 'Error')
        : 'Error'
      toast({ variant: 'destructive', title: 'Error', description: String(message) })
    },
  })

  const pending = enableMutation.isPending || disableMutation.isPending

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('catalog.availability.title')}</CardTitle>
        <CardDescription>{t('catalog.availability.description')}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <AccountPicker {...props} />
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <div>
            <Label>ASIN</Label>
            <Input value={asin} onChange={(e) => setAsin(e.target.value)} />
          </div>
          <div>
            <Label>{t('catalog.availability.quantityOptional')}</Label>
            <Input
              type="number"
              min="0"
              value={quantity}
              onChange={(e) => setQuantity(e.target.value)}
            />
          </div>
        </div>
        <div className="flex gap-2">
          <Button
            onClick={() => enableMutation.mutate()}
            disabled={!accountId || !asin || pending}
          >
            {enableMutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {t('catalog.availability.enable')}
          </Button>
          <Button
            variant="outline"
            onClick={() => disableMutation.mutate()}
            disabled={!accountId || !asin || pending}
          >
            {disableMutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {t('catalog.availability.disable')}
          </Button>
        </div>
        {result && (
          <pre className="text-xs bg-muted rounded p-3 overflow-x-auto max-h-64">
            {JSON.stringify(result, null, 2)}
          </pre>
        )}
      </CardContent>
    </Card>
  )
}

// ────────────────────────────────────────────────────────────────────────────
// Images tab
// ────────────────────────────────────────────────────────────────────────────
function ImagesCard(props: TabProps) {
  const { accountId, toast, t } = props
  const queryClient = useQueryClient()

  const [asin, setAsin] = useState('')
  const [stagedFiles, setStagedFiles] = useState<File[]>([])
  const [mainIndex, setMainIndex] = useState<number>(0)
  const [pushToAmazon, setPushToAmazon] = useState(true)
  const [lastResult, setLastResult] = useState<unknown>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const canQuery = Boolean(accountId && asin)

  const imagesQuery = useQuery({
    queryKey: ['catalog', 'images', accountId, asin],
    queryFn: () => imagesApi.list(asin, accountId),
    enabled: canQuery,
  })

  const uploadMutation = useMutation({
    mutationFn: () =>
      imagesApi.upload({
        asin,
        account_id: accountId,
        files: stagedFiles,
        main_index: stagedFiles.length > 0 ? mainIndex : undefined,
        push_to_amazon: pushToAmazon,
      }),
    onSuccess: (data) => {
      setLastResult(data)
      setStagedFiles([])
      setMainIndex(0)
      if (fileInputRef.current) fileInputRef.current.value = ''
      toast({
        title: t('catalog.images.uploaded'),
        description: data.sp_api_error
          ? t('catalog.images.uploadedS3Only')
          : t('catalog.images.uploadedSuccess'),
      })
      queryClient.invalidateQueries({ queryKey: ['catalog', 'images', accountId, asin] })
    },
    onError: (err: unknown) => {
      const message = err && typeof err === 'object' && 'response' in err
        ? ((err as { response?: { data?: { detail?: string } } }).response?.data?.detail ?? 'Error')
        : 'Error'
      toast({ variant: 'destructive', title: 'Error', description: String(message) })
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (key: string) => imagesApi.remove(asin, accountId, key),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['catalog', 'images', accountId, asin] })
    },
    onError: (err: unknown) => {
      const message = err && typeof err === 'object' && 'response' in err
        ? ((err as { response?: { data?: { detail?: string } } }).response?.data?.detail ?? 'Error')
        : 'Error'
      toast({ variant: 'destructive', title: 'Error', description: String(message) })
    },
  })

  const handleFilesSelected = (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files ?? [])
    setStagedFiles(files)
    setMainIndex(0)
  }

  const removeStaged = (idx: number) => {
    setStagedFiles((prev) => prev.filter((_, i) => i !== idx))
    setMainIndex((prev) => (prev === idx ? 0 : prev > idx ? prev - 1 : prev))
  }

  const existing: ProductImage[] = imagesQuery.data?.images ?? []

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <ImageIcon className="h-5 w-5" />
          {t('catalog.images.title')}
        </CardTitle>
        <CardDescription>{t('catalog.images.description')}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-3 md:grid-cols-2">
          <AccountPicker {...props} />
          <div>
            <Label>{t('catalog.images.asin')}</Label>
            <Input
              placeholder="B0XXXXXXXX"
              value={asin}
              onChange={(e) => setAsin(e.target.value.trim().toUpperCase())}
            />
          </div>
        </div>

        <div className="space-y-2 border rounded-md p-3">
          <Label>{t('catalog.images.selectFiles')}</Label>
          <Input
            ref={fileInputRef}
            type="file"
            accept="image/jpeg,image/png,image/webp"
            multiple
            onChange={handleFilesSelected}
          />
          {stagedFiles.length > 0 && (
            <div className="grid gap-2 grid-cols-2 md:grid-cols-4">
              {stagedFiles.map((file, idx) => {
                const url = URL.createObjectURL(file)
                const isMain = idx === mainIndex
                return (
                  <div
                    key={`${file.name}-${idx}`}
                    className={`relative rounded border p-2 ${isMain ? 'ring-2 ring-primary' : ''}`}
                  >
                    <img
                      src={url}
                      alt={file.name}
                      className="w-full h-24 object-contain"
                      onLoad={() => URL.revokeObjectURL(url)}
                    />
                    <p className="truncate text-xs mt-1" title={file.name}>
                      {file.name}
                    </p>
                    <div className="flex items-center justify-between mt-1">
                      <Button
                        size="sm"
                        variant={isMain ? 'default' : 'outline'}
                        className="h-7 px-2 text-xs"
                        onClick={() => setMainIndex(idx)}
                      >
                        <Star className="h-3 w-3 mr-1" />
                        {isMain ? t('catalog.images.isMain') : t('catalog.images.setMain')}
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        className="h-7 w-7 p-0"
                        onClick={() => removeStaged(idx)}
                        aria-label="Remove"
                      >
                        <X className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>
                )
              })}
            </div>
          )}

          <div className="flex items-center gap-3 pt-2">
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={pushToAmazon}
                onChange={(e) => setPushToAmazon(e.target.checked)}
              />
              {t('catalog.images.pushToAmazon')}
            </label>
            <Button
              onClick={() => uploadMutation.mutate()}
              disabled={
                !accountId || !asin || stagedFiles.length === 0 || uploadMutation.isPending
              }
            >
              {uploadMutation.isPending ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Upload className="mr-2 h-4 w-4" />
              )}
              {t('catalog.images.upload')}
            </Button>
          </div>
        </div>

        <div>
          <p className="text-sm font-medium mb-2">{t('catalog.images.existing')}</p>
          {!canQuery && (
            <p className="text-sm text-muted-foreground">{t('catalog.images.pickAsin')}</p>
          )}
          {canQuery && imagesQuery.isLoading && (
            <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
          )}
          {canQuery && !imagesQuery.isLoading && existing.length === 0 && (
            <p className="text-sm text-muted-foreground">{t('catalog.images.empty')}</p>
          )}
          {existing.length > 0 && (
            <div className="grid gap-3 grid-cols-2 md:grid-cols-4">
              {existing.map((img) => (
                <div key={img.key} className="relative rounded border p-2">
                  <img
                    src={img.url}
                    alt={img.filename}
                    className="w-full h-28 object-contain"
                  />
                  <p className="truncate text-xs mt-1" title={img.filename}>
                    {img.filename}
                  </p>
                  <Button
                    size="sm"
                    variant="ghost"
                    className="absolute top-1 right-1 h-7 w-7 p-0"
                    onClick={() => deleteMutation.mutate(img.key)}
                    disabled={deleteMutation.isPending}
                    aria-label="Delete"
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              ))}
            </div>
          )}
        </div>

        {lastResult !== null && (
          <pre className="text-xs bg-muted rounded p-3 overflow-x-auto max-h-64">
            {JSON.stringify(lastResult, null, 2)}
          </pre>
        )}
      </CardContent>
    </Card>
  )
}
