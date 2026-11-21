import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Loader2, ShieldCheck } from 'lucide-react'
import { Progress } from '@/components/ui/progress'
import { catalogMonitorApi } from '@/services/api'
import { apiErrorDetail } from '@/lib/apiError'
import { ConfirmDialog } from '@/components/catalog/ConfirmDialog'
import type { TabProps } from '@/components/catalog/types'
import { AdminButton } from './AdminButton'

/** How much of the catalogue is protected, and the admin action that approves the live content. */
export function BaselineBar({ accountId, t, toast }: Pick<TabProps, 'accountId' | 't' | 'toast'>) {
  const queryClient = useQueryClient()
  const [confirm, setConfirm] = useState(false)

  const query = useQuery({
    queryKey: ['catalog-monitor', 'baselines', accountId],
    queryFn: () => catalogMonitorApi.getBaselineStatus(accountId),
    enabled: !!accountId,
  })

  const approveAll = useMutation({
    mutationFn: () => catalogMonitorApi.approveBaselines(accountId),
    onSuccess: (res) => {
      toast({
        title: t('cm.protection.baselineDone', { count: res.count }),
        description: t('cm.protection.baselineDoneHint'),
      })
      for (const key of ['anomalies', 'baselines', 'variations']) {
        void queryClient.invalidateQueries({ queryKey: ['catalog-monitor', key] })
      }
    },
    onError: (error) =>
      toast({
        title: t('cm.protection.baselineError'),
        description: apiErrorDetail(error, t),
        variant: 'destructive',
      }),
  })

  const status = query.data
  const pct =
    status && status.asins_total > 0
      ? Math.round((status.asins_with_baseline / status.asins_total) * 100)
      : 0

  return (
    <div className="flex flex-wrap items-center gap-4 rounded-lg border p-4">
      <ShieldCheck className="h-8 w-8 shrink-0 text-primary" aria-hidden="true" />
      <div className="min-w-[220px] flex-1 space-y-1.5">
        <p className="text-sm font-medium">
          {status
            ? t('cm.protection.protected', { count: status.asins_with_baseline, total: status.asins_total })
            : '—'}
        </p>
        <Progress value={pct} className="h-2" aria-label={`${pct}%`} />
        {status && (
          <p className="text-xs text-muted-foreground">
            {t('cm.protection.families', { count: status.families })}
          </p>
        )}
      </div>
      <AdminButton
        adminOnlyTitle={t('cm.protection.adminOnly')}
        variant={status?.asins_with_baseline === 0 ? 'default' : 'outline'}
        onClick={() => setConfirm(true)}
        disabled={!accountId || approveAll.isPending}
      >
        {approveAll.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
        {t('cm.protection.approveCurrent')}
      </AdminButton>
      <ConfirmDialog
        open={confirm}
        onOpenChange={setConfirm}
        title={t('cm.protection.confirmTitle')}
        description={t('cm.protection.confirmBody')}
        confirmLabel={t('cm.protection.approveCurrent')}
        cancelLabel={t('common.cancel')}
        onConfirm={() => {
          setConfirm(false)
          approveAll.mutate()
        }}
      />
    </div>
  )
}
