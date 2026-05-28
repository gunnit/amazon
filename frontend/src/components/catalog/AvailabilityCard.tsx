import { useMemo, useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { Loader2 } from 'lucide-react'
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
import { Label } from '@/components/ui/label'
import { catalogApi } from '@/services/api'
import { AccountPicker } from './AccountPicker'
import { ConfirmDialog } from './ConfirmDialog'
import type { AvailabilityResult, TabProps } from './types'

const ASIN_REGEX = /^[A-Z0-9]{10}$/

const availabilitySchema = z.object({
  asin: z.string().regex(ASIN_REGEX, 'invalid_asin'),
  quantity: z.union([z.number().int().nonnegative(), z.literal(undefined)]).optional(),
})

export function AvailabilityCard(props: TabProps) {
  const { t, toast, accountId } = props
  const [asin, setAsin] = useState('')
  const [quantity, setQuantity] = useState('')
  const [result, setResult] = useState<AvailabilityResult | null>(null)
  const [confirmDisableOpen, setConfirmDisableOpen] = useState(false)

  const validation = useMemo(() => {
    return availabilitySchema.safeParse({
      asin,
      quantity: quantity ? Number.parseInt(quantity, 10) : undefined,
    })
  }, [asin, quantity])
  const validAsin = validation.success

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
      const message =
        err && typeof err === 'object' && 'response' in err
          ? ((err as { response?: { data?: { detail?: string } } }).response?.data?.detail ?? 'Error')
          : 'Error'
      toast({
        variant: 'destructive',
        title: t('catalog.availability.errorTitle'),
        description: String(message),
      })
    },
  })

  const disableMutation = useMutation({
    mutationFn: () => runMutation(false),
    onSuccess: (d) => {
      setResult(d)
      toast({ title: t('catalog.availability.disabled') })
    },
    onError: (err: unknown) => {
      const message =
        err && typeof err === 'object' && 'response' in err
          ? ((err as { response?: { data?: { detail?: string } } }).response?.data?.detail ?? 'Error')
          : 'Error'
      toast({
        variant: 'destructive',
        title: t('catalog.availability.errorTitle'),
        description: String(message),
      })
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
            <Input
              value={asin}
              onChange={(e) => setAsin(e.target.value.trim().toUpperCase())}
              placeholder="B0XXXXXXXX"
            />
            {asin && !validAsin && (
              <p className="text-xs text-destructive mt-1">{t('catalog.prices.invalidAsin')}</p>
            )}
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
            disabled={!accountId || !validAsin || pending}
          >
            {enableMutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {t('catalog.availability.enable')}
          </Button>
          <Button
            variant="outline"
            onClick={() => setConfirmDisableOpen(true)}
            disabled={!accountId || !validAsin || pending}
          >
            {disableMutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {t('catalog.availability.disable')}
          </Button>
        </div>

        <ConfirmDialog
          open={confirmDisableOpen}
          onOpenChange={setConfirmDisableOpen}
          title={t('catalog.availability.confirmDisableTitle')}
          description={t('catalog.availability.confirmDisableBody', { asin })}
          confirmLabel={t('catalog.availability.disable')}
          cancelLabel={t('common.cancel')}
          destructive
          onConfirm={() => {
            setConfirmDisableOpen(false)
            disableMutation.mutate()
          }}
        />

        {result && (
          <div className="rounded-md border p-3 text-sm space-y-1">
            <div>
              <span className="font-medium">ASIN:</span>{' '}
              <span className="font-mono text-xs">{result.asin}</span>
            </div>
            <div>
              <span className="font-medium">SKU:</span>{' '}
              <span className="font-mono text-xs">{result.sku}</span>
            </div>
            <div>
              <span className="font-medium">{t('catalog.availability.title')}:</span>{' '}
              {result.is_available
                ? t('catalog.availability.enabled')
                : t('catalog.availability.disabled')}
            </div>
            <div>
              <span className="font-medium">{t('catalog.availability.quantityOptional')}:</span>{' '}
              {result.pushed_quantity}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
