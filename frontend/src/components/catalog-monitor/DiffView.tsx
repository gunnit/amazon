import { useMutation, useQueryClient } from '@tanstack/react-query'
import { History, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { catalogMonitorApi } from '@/services/api'
import { apiErrorDetail } from '@/lib/apiError'
import type { CatalogAnomaly } from '@/types'
import type { TabProps } from '@/components/catalog/types'
import { AdminButton } from './AdminButton'
import { changeTypeLabel, fieldLabel, restoreInProgress } from './changeLabels'
import { DiffLegend, FieldCompare } from './FieldCompare'

interface Props extends Pick<TabProps, 't' | 'toast'> {
  anomaly: CatalogAnomaly | null
  onClose: () => void
  onRestore: (anomalyId: string) => void
  restoring: boolean
  onShowHistory: (asin: string) => void
}

/** One content change: the approved version next to what is online now, with the two decisions. */
export function DiffView({ anomaly, onClose, onRestore, restoring, onShowHistory, t, toast }: Props) {
  const queryClient = useQueryClient()

  const accept = useMutation({
    mutationFn: (id: string) => catalogMonitorApi.acceptAnomaly(id),
    onSuccess: () => {
      toast({ title: t('cm.diff.accepted'), description: t('cm.diff.acceptedHint') })
      void queryClient.invalidateQueries({ queryKey: ['catalog-monitor', 'anomalies'] })
      void queryClient.invalidateQueries({ queryKey: ['catalog-monitor', 'baselines'] })
      onClose()
    },
    onError: (error) =>
      toast({
        title: t('cm.diff.acceptError'),
        description: apiErrorDetail(error, t),
        variant: 'destructive',
      }),
  })

  const pending = anomaly !== null && restoreInProgress(anomaly)
  const isAplus = anomaly?.field === 'aplus'

  return (
    <Dialog open={anomaly !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-h-[90vh] max-w-5xl overflow-y-auto">
        {anomaly && (
          <>
            <DialogHeader>
              <DialogTitle className="pr-6">
                {fieldLabel(t, anomaly.field)}
                {anomaly.change && ` · ${changeTypeLabel(t, anomaly.change)}`}
              </DialogTitle>
              <DialogDescription>
                <span className="font-mono">{anomaly.asin}</span>
                {anomaly.title ? ` · ${anomaly.title}` : ''}
                {' · '}
                {t('cm.diff.detected', { date: new Date(anomaly.detected_at).toLocaleString() })}
              </DialogDescription>
            </DialogHeader>

            <FieldCompare
              field={anomaly.field}
              before={anomaly.baseline_value}
              after={anomaly.live_value}
              beforeLabel={t('cm.diff.approved')}
              afterLabel={t('cm.diff.live')}
              t={t}
            />
            <DiffLegend t={t} field={anomaly.field} />

            {pending && (
              <p className="rounded-md bg-muted px-3 py-2 text-sm">{t('cm.diff.restorePending')}</p>
            )}
            {isAplus && (
              <p className="rounded-md bg-muted px-3 py-2 text-sm">{t('cm.diff.aplusManual')}</p>
            )}

            <DialogFooter className="gap-2 sm:justify-between">
              <Button variant="ghost" onClick={() => onShowHistory(anomaly.asin)}>
                <History className="mr-2 h-4 w-4" />
                {t('cm.history.open')}
              </Button>
              <div className="flex flex-wrap gap-2">
                <AdminButton
                  variant="outline"
                  adminOnlyTitle={t('cm.diff.acceptAdminOnly')}
                  onClick={() => accept.mutate(anomaly.id)}
                  disabled={pending || accept.isPending || restoring}
                  title={t('cm.diff.acceptHelp')}
                >
                  {accept.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                  {t('cm.diff.accept')}
                </AdminButton>
                <Button
                  onClick={() => onRestore(anomaly.id)}
                  disabled={pending || isAplus || restoring || accept.isPending}
                  title={t('cm.diff.restoreHelp')}
                >
                  {restoring && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                  {t('cm.diff.restore')}
                </Button>
              </div>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  )
}
