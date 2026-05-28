import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { Loader2 } from 'lucide-react'
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
import type { TabProps } from './types'

export function AvailabilityCard(props: TabProps) {
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
