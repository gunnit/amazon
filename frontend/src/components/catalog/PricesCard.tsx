import { useMemo, useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { Loader2, Plus, Trash2 } from 'lucide-react'
import { z } from 'zod'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { catalogApi } from '@/services/api'
import { AccountPicker } from './AccountPicker'
import { BulkResultTable } from './BulkResultTable'
import { ConfirmDialog } from './ConfirmDialog'
import type { BulkResult, PriceUpdateResult, TabProps } from './types'

type PriceRow = { asin: string; sku: string; price: string }

const ASIN_REGEX = /^[A-Z0-9]{10}$/

const priceUpdateSchema = z
  .object({
    asin: z
      .string()
      .trim()
      .optional()
      .refine((v) => !v || ASIN_REGEX.test(v), { message: 'invalid_asin' }),
    sku: z.string().trim().optional(),
    price: z.number().nonnegative().finite(),
  })
  .refine((v) => Boolean(v.asin || v.sku), { message: 'asin_or_sku_required' })

export function PricesCard(props: TabProps) {
  const { t, toast, accountId } = props
  const [rows, setRows] = useState<PriceRow[]>([{ asin: '', sku: '', price: '' }])
  const [result, setResult] = useState<BulkResult<PriceUpdateResult> | null>(null)
  const [confirmOpen, setConfirmOpen] = useState(false)

  const updateRow = (idx: number, patch: Partial<PriceRow>) =>
    setRows((prev) => prev.map((r, i) => (i === idx ? { ...r, ...patch } : r)))

  const { validUpdates, invalidCount } = useMemo(() => {
    let invalid = 0
    const valid: Array<{ asin?: string; sku?: string; price: number }> = []
    for (const r of rows) {
      const parsed = priceUpdateSchema.safeParse({
        asin: r.asin || undefined,
        sku: r.sku || undefined,
        price: Number.parseFloat(r.price),
      })
      if (parsed.success) {
        valid.push(parsed.data as { asin?: string; sku?: string; price: number })
      } else if (r.asin || r.sku || r.price) {
        invalid += 1
      }
    }
    return { validUpdates: valid, invalidCount: invalid }
  }, [rows])

  const mutation = useMutation({
    mutationFn: () =>
      catalogApi.updatePrices({
        account_id: accountId,
        updates: validUpdates,
      }),
    onSuccess: (data) => {
      setResult(data)
      toast({
        title: t('catalog.prices.successTitle'),
        description: t('catalog.result.successCount', {
          succeeded: data.succeeded,
          failed: data.failed,
        }),
      })
    },
    onError: (err: unknown) => {
      const message =
        err && typeof err === 'object' && 'response' in err
          ? ((err as { response?: { data?: { detail?: string } } }).response?.data?.detail ?? 'Error')
          : 'Error'
      toast({
        variant: 'destructive',
        title: t('catalog.prices.errorTitle'),
        description: String(message),
      })
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
                onChange={(e) => updateRow(idx, { asin: e.target.value.toUpperCase() })}
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
            {invalidCount > 0 && (
              <span className="ml-2 text-destructive">
                {t('catalog.prices.nInvalid', { n: invalidCount })}
              </span>
            )}
          </span>
          <Button
            onClick={() => setConfirmOpen(true)}
            disabled={!accountId || validUpdates.length === 0 || mutation.isPending}
          >
            {mutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {t('catalog.prices.submit')}
          </Button>
        </div>

        <ConfirmDialog
          open={confirmOpen}
          onOpenChange={setConfirmOpen}
          title={t('catalog.prices.confirmTitle')}
          description={t('catalog.prices.confirmBody', { n: validUpdates.length })}
          confirmLabel={t('catalog.prices.submit')}
          cancelLabel={t('common.cancel')}
          onConfirm={() => {
            setConfirmOpen(false)
            mutation.mutate()
          }}
        />

        <BulkResultTable<PriceUpdateResult>
          result={result}
          t={t}
          successLabel={(r) => `${r.asin ?? r.sku ?? '—'} → ${r.price}`}
        />
      </CardContent>
    </Card>
  )
}
