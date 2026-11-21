import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Loader2, RotateCcw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { catalogMonitorApi } from '@/services/api'
import { apiErrorDetail } from '@/lib/apiError'
import type { ChangeBatchResponse } from '@/types'
import { AccountPicker } from '@/components/catalog/AccountPicker'
import type { TabProps } from '@/components/catalog/types'
import { AnomalyTable } from './AnomalyTable'
import { BaselineBar } from './BaselineBar'
import { canRestoreAnomaly } from './changeLabels'
import { DiffView } from './DiffView'
import { HistoryDialog } from './HistoryDialog'
import { RestoreResult } from './RestoreResult'
import { ScanButton } from './ScanButton'

interface Props extends TabProps {
  onOpenApprovals: (batchId?: string | null) => void
}

/** Content protection (R3): live content against the brand-approved version, restore or accept. */
export function ProtectionPanel(props: Props) {
  const { t, toast, accountId, onOpenApprovals } = props
  const queryClient = useQueryClient()
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [openId, setOpenId] = useState<string | null>(null)
  const [historyAsin, setHistoryAsin] = useState<string | null>(null)
  const [result, setResult] = useState<ChangeBatchResponse | null>(null)

  useEffect(() => {
    setSelected(new Set())
    setResult(null)
  }, [accountId])

  // same key as BaselineBar: shared, fetched once
  const statusQuery = useQuery({
    queryKey: ['catalog-monitor', 'baselines', accountId],
    queryFn: () => catalogMonitorApi.getBaselineStatus(accountId),
    enabled: !!accountId,
  })
  const anomaliesQuery = useQuery({
    queryKey: ['catalog-monitor', 'anomalies', accountId, 'content'],
    queryFn: () => catalogMonitorApi.listAnomalies(accountId, { kind: 'content_changed' }),
    enabled: !!accountId,
  })
  const anomalies = useMemo(() => anomaliesQuery.data ?? [], [anomaliesQuery.data])
  const restorable = useMemo(() => anomalies.filter(canRestoreAnomaly), [anomalies])
  // a reload can make a selected row unrestorable: only what is still restorable counts
  const selectedIds = useMemo(
    () => restorable.filter((a) => selected.has(a.id)).map((a) => a.id),
    [restorable, selected],
  )
  const openAnomaly = anomalies.find((a) => a.id === openId) ?? null
  const noBaseline = statusQuery.data?.asins_with_baseline === 0

  const restore = useMutation({
    mutationFn: (ids: string[]) => catalogMonitorApi.restoreAnomalies(ids),
    onSuccess: (res) => {
      setResult(res)
      setSelected(new Set())
      setOpenId(null)
      for (const key of ['anomalies', 'changes']) {
        void queryClient.invalidateQueries({ queryKey: ['catalog-monitor', key] })
      }
    },
    onError: (error) =>
      toast({
        title: t('cm.restore.error'),
        description: apiErrorDetail(error, t),
        variant: 'destructive',
      }),
  })

  const toggle = (id: string, on: boolean) =>
    setSelected((cur) => {
      const next = new Set(cur)
      if (on) next.add(id)
      else next.delete(id)
      return next
    })

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <CardTitle>{t('cm.protection.title')}</CardTitle>
            <CardDescription>{t('cm.protection.description')}</CardDescription>
          </div>
          <ScanButton accountId={accountId} t={t} toast={toast} />
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="min-w-[220px] max-w-sm">
          <AccountPicker {...props} />
        </div>

        <BaselineBar accountId={accountId} t={t} toast={toast} />

        {result && (
          <RestoreResult
            result={result}
            onOpenApprovals={onOpenApprovals}
            onDismiss={() => setResult(null)}
            t={t}
          />
        )}

        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-sm text-muted-foreground">
            {t('cm.protection.count', { count: anomalies.length })}
          </p>
          <Button
            onClick={() => restore.mutate(selectedIds)}
            disabled={selectedIds.length === 0 || restore.isPending}
          >
            {restore.isPending ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <RotateCcw className="mr-2 h-4 w-4" />
            )}
            {t('cm.protection.restoreSelected', { count: selectedIds.length })}
          </Button>
        </div>

        <AnomalyTable
          anomalies={anomalies}
          loading={anomaliesQuery.isLoading}
          error={anomaliesQuery.isError}
          emptyText={
            anomaliesQuery.data
              ? noBaseline
                ? t('cm.protection.emptyNoBaseline')
                : t('cm.protection.empty')
              : null
          }
          selected={selected}
          onToggle={toggle}
          onToggleAll={(on) => setSelected(on ? new Set(restorable.map((a) => a.id)) : new Set())}
          onOpen={setOpenId}
          onHistory={setHistoryAsin}
          t={t}
        />

        <DiffView
          anomaly={openAnomaly}
          onClose={() => setOpenId(null)}
          onRestore={(id) => restore.mutate([id])}
          restoring={restore.isPending}
          onShowHistory={(asin) => {
            setOpenId(null)
            setHistoryAsin(asin)
          }}
          t={t}
          toast={toast}
        />
        <HistoryDialog
          accountId={accountId}
          asin={historyAsin}
          onClose={() => setHistoryAsin(null)}
          t={t}
        />
      </CardContent>
    </Card>
  )
}
