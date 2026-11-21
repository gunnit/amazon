import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CheckCircle2, Loader2, ShieldCheck, XCircle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { catalogMonitorApi } from '@/services/api'
import { apiErrorDetail } from '@/lib/apiError'
import { CAPABILITY_KEYS } from '@/types'
import type { TabProps } from '@/components/catalog/types'

export function AccessCheck({ accountId, t, toast }: Pick<TabProps, 'accountId' | 't' | 'toast'>) {
  const queryClient = useQueryClient()
  const key = ['catalog-monitor', 'capabilities', accountId]

  const query = useQuery({
    queryKey: key,
    queryFn: () => catalogMonitorApi.getCapabilities(accountId),
    enabled: !!accountId,
  })

  const check = useMutation({
    mutationFn: () => catalogMonitorApi.checkCapabilities(accountId),
    onSuccess: (data) => {
      queryClient.setQueryData(key, data)
      // what the scan can read depends on the access, so the lights may change
      void queryClient.invalidateQueries({ queryKey: ['catalog-monitor', 'quality'] })
    },
    onError: (error) =>
      toast({
        title: t('cm.access.error'),
        description: apiErrorDetail(error, t),
        variant: 'destructive',
      }),
  })

  const data = query.data
  const checkedAt = data ? new Date(data.checked_at).toLocaleString() : null

  return (
    <div className="flex flex-wrap items-center gap-2" aria-label={t('cm.access.title')}>
      <ul className="flex flex-wrap items-center gap-1.5">
        {CAPABILITY_KEYS.map((cap) => {
          const result = data?.results?.[cap]
          const known = result !== undefined
          const ok = result?.ok === true
          const label = t(`cm.access.cap.${cap}`)
          const status = !known
            ? t('cm.access.unchecked')
            : ok
              ? t('cm.access.ok')
              : t('cm.access.ko')
          const reason = result?.error ? ` (${result.error})` : ''
          return (
            <li
              key={cap}
              title={`${label}: ${status}${reason}`}
              className={cn(
                'inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-medium',
                !known && 'border-slate-300 text-slate-600 dark:border-slate-600 dark:text-slate-400',
                known && ok && 'border-green-600/40 text-green-700 dark:text-green-400',
                known && !ok && 'border-red-600/40 text-red-700 dark:text-red-400',
              )}
            >
              {known && ok && <CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" />}
              {known && !ok && <XCircle className="h-3.5 w-3.5" aria-hidden="true" />}
              {label}
              <span className="sr-only">: {status}</span>
            </li>
          )
        })}
      </ul>
      <Button
        variant="outline"
        size="sm"
        onClick={() => check.mutate()}
        disabled={!accountId || check.isPending}
      >
        {check.isPending ? (
          <Loader2 className="mr-2 h-4 w-4 animate-spin" />
        ) : (
          <ShieldCheck className="mr-2 h-4 w-4" />
        )}
        {t('cm.access.check')}
      </Button>
      <span className="text-xs text-muted-foreground">
        {checkedAt ? t('cm.access.checkedAt', { date: checkedAt }) : t('cm.access.never')}
        {data?.vendor_code ? ` · ${t('cm.access.vendorCode', { code: data.vendor_code })}` : ''}
      </span>
    </div>
  )
}
