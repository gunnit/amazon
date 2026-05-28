import { useMemo, useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { Loader2, Plus, Trash2 } from 'lucide-react'
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
import type { TabProps } from './types'

type PriceRow = { asin: string; sku: string; price: string }

export function PricesCard(props: TabProps) {
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
