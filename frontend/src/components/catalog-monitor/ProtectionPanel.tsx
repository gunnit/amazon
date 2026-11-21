import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Eye, History, Loader2, RotateCcw, ShieldCheck } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Progress } from '@/components/ui/progress'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { cn } from '@/lib/utils'
import { catalogMonitorApi } from '@/services/api'
import { apiErrorDetail } from '@/lib/apiError'
import type { AnomalyStatus, CatalogAnomaly, ChangeBatchResponse } from '@/types'
import { AccountPicker } from '@/components/catalog/AccountPicker'
import { ConfirmDialog } from '@/components/catalog/ConfirmDialog'
import type { TabProps } from '@/components/catalog/types'
import { anomalyStatusLabel, changeType, changeTypeLabel, fieldLabel } from './changeLabels'
import { DiffView } from './DiffView'
import { HistoryDialog } from './HistoryDialog'
import { RestoreResult } from './RestoreResult'
import { ScanButton } from './ScanButton'

interface Props extends TabProps {
  onOpenApprovals: (batchId?: string | null) => void
}

const STATUS_CLASS: Record<AnomalyStatus, string> = {
  open: 'bg-red-100 text-red-800 dark:bg-red-900/50 dark:text-red-300',
  acknowledged: 'bg-amber-100 text-amber-900 dark:bg-amber-900/50 dark:text-amber-300',
  restore_requested: 'bg-indigo-100 text-indigo-800 dark:bg-indigo-900/50 dark:text-indigo-300',
  resolved: 'bg-green-100 text-green-800 dark:bg-green-900/50 dark:text-green-300',
}

/** Restorable through Amazon: still open and not A+ (A+ cannot be written via Listings Items). */
const canRestore = (a: CatalogAnomaly) =>
  (a.status === 'open' || a.status === 'acknowledged') && a.field !== 'aplus'

export function ProtectionPanel(props: Props) {
  const { t, toast, accountId, onOpenApprovals } = props
  const queryClient = useQueryClient()
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [openId, setOpenId] = useState<string | null>(null)
  const [historyAsin, setHistoryAsin] = useState<string | null>(null)
  const [result, setResult] = useState<ChangeBatchResponse | null>(null)
  const [confirmBaseline, setConfirmBaseline] = useState(false)

  useEffect(() => {
    setSelected(new Set())
    setResult(null)
  }, [accountId])

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
  const restorable = useMemo(() => anomalies.filter(canRestore), [anomalies])
  // a reload can make a selected row unrestorable: only what is still restorable counts
  const selectedIds = useMemo(
    () => restorable.filter((a) => selected.has(a.id)).map((a) => a.id),
    [restorable, selected],
  )
  const allSelected = restorable.length > 0 && selectedIds.length === restorable.length
  const openAnomaly = anomalies.find((a) => a.id === openId) ?? null

  const refresh = () => {
    for (const key of ['anomalies', 'baselines', 'changes', 'variations']) {
      void queryClient.invalidateQueries({ queryKey: ['catalog-monitor', key] })
    }
  }

  const restore = useMutation({
    mutationFn: (ids: string[]) => catalogMonitorApi.restoreAnomalies(ids),
    onSuccess: (res) => {
      setResult(res)
      setSelected(new Set())
      setOpenId(null)
      refresh()
    },
    onError: (error) =>
      toast({
        title: t('cm.restore.error'),
        description: apiErrorDetail(error, t),
        variant: 'destructive',
      }),
  })

  const approveAll = useMutation({
    mutationFn: () => catalogMonitorApi.approveBaselines(accountId),
    onSuccess: (res) => {
      toast({
        title: t('cm.protection.baselineDone', { count: res.count }),
        description: t('cm.protection.baselineDoneHint'),
      })
      refresh()
    },
    onError: (error) =>
      toast({
        title: t('cm.protection.baselineError'),
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

  const status = statusQuery.data
  const protectedPct =
    status && status.asins_total > 0
      ? Math.round((status.asins_with_baseline / status.asins_total) * 100)
      : 0
  const noBaseline = status?.asins_with_baseline === 0

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

        {/* Baseline status: how much of the catalogue is protected */}
        <div className="flex flex-wrap items-center gap-4 rounded-lg border p-4">
          <ShieldCheck className="h-8 w-8 shrink-0 text-primary" aria-hidden="true" />
          <div className="min-w-[220px] flex-1 space-y-1.5">
            <p className="text-sm font-medium">
              {status
                ? t('cm.protection.protected', {
                    count: status.asins_with_baseline,
                    total: status.asins_total,
                  })
                : '—'}
            </p>
            <Progress value={protectedPct} className="h-2" aria-label={`${protectedPct}%`} />
            {status && (
              <p className="text-xs text-muted-foreground">
                {t('cm.protection.families', { count: status.families })}
              </p>
            )}
          </div>
          <Button
            variant={noBaseline ? 'default' : 'outline'}
            onClick={() => setConfirmBaseline(true)}
            disabled={!accountId || approveAll.isPending}
          >
            {approveAll.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {t('cm.protection.approveCurrent')}
          </Button>
        </div>

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

        <div className="rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-10">
                  <Checkbox
                    aria-label={t('cm.common.selectAll')}
                    checked={allSelected ? true : selectedIds.length > 0 ? 'indeterminate' : false}
                    disabled={restorable.length === 0}
                    onCheckedChange={(v) =>
                      setSelected(v === true ? new Set(restorable.map((a) => a.id)) : new Set())
                    }
                  />
                </TableHead>
                <TableHead>{t('cm.protection.col.product')}</TableHead>
                <TableHead>{t('cm.protection.col.field')}</TableHead>
                <TableHead>{t('cm.protection.col.change')}</TableHead>
                <TableHead>{t('cm.protection.col.detected')}</TableHead>
                <TableHead>{t('cm.protection.col.status')}</TableHead>
                <TableHead className="w-[1%]" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {anomaliesQuery.isLoading && (
                <TableRow>
                  <TableCell colSpan={7} className="py-8 text-center">
                    <Loader2 className="mx-auto h-5 w-5 animate-spin" />
                  </TableCell>
                </TableRow>
              )}
              {anomaliesQuery.isError && (
                <TableRow>
                  <TableCell colSpan={7} className="py-8 text-center text-destructive">
                    {t('cm.protection.loadError')}
                  </TableCell>
                </TableRow>
              )}
              {anomaliesQuery.data && anomalies.length === 0 && (
                <TableRow>
                  <TableCell colSpan={7} className="py-8 text-center text-muted-foreground">
                    {noBaseline ? t('cm.protection.emptyNoBaseline') : t('cm.protection.empty')}
                  </TableCell>
                </TableRow>
              )}
              {anomalies.map((a) => (
                <TableRow
                  key={a.id}
                  className="cursor-pointer"
                  tabIndex={0}
                  onClick={() => setOpenId(a.id)}
                  onKeyDown={(e) => {
                    if (e.target === e.currentTarget && (e.key === 'Enter' || e.key === ' ')) {
                      e.preventDefault()
                      setOpenId(a.id)
                    }
                  }}
                >
                  <TableCell onClick={(e) => e.stopPropagation()}>
                    <Checkbox
                      aria-label={t('cm.common.selectRow', { id: a.asin })}
                      checked={selected.has(a.id) && canRestore(a)}
                      disabled={!canRestore(a)}
                      title={canRestore(a) ? undefined : t('cm.protection.notSelectable')}
                      onCheckedChange={(v) => toggle(a.id, v === true)}
                    />
                  </TableCell>
                  <TableCell className="max-w-[280px]">
                    <div className="font-mono text-xs">{a.asin}</div>
                    <div className="truncate text-xs text-muted-foreground" title={a.title ?? undefined}>
                      {a.title || t('catalog.products.titleMissing')}
                    </div>
                  </TableCell>
                  <TableCell className="text-sm">{fieldLabel(t, a.field)}</TableCell>
                  <TableCell className="text-sm">
                    {changeTypeLabel(t, changeType(a.baseline_value, a.live_value))}
                  </TableCell>
                  <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                    {new Date(a.detected_at).toLocaleString()}
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline" className={cn('border-transparent', STATUS_CLASS[a.status])}>
                      {anomalyStatusLabel(t, a.status)}
                    </Badge>
                  </TableCell>
                  <TableCell onClick={(e) => e.stopPropagation()}>
                    <div className="flex gap-1">
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => setOpenId(a.id)}
                        aria-label={t('cm.protection.compare')}
                        title={t('cm.protection.compare')}
                      >
                        <Eye className="h-4 w-4" />
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => setHistoryAsin(a.asin)}
                        aria-label={t('cm.history.open')}
                        title={t('cm.history.open')}
                      >
                        <History className="h-4 w-4" />
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>

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
        <ConfirmDialog
          open={confirmBaseline}
          onOpenChange={setConfirmBaseline}
          title={t('cm.protection.confirmTitle')}
          description={t('cm.protection.confirmBody')}
          confirmLabel={t('cm.protection.approveCurrent')}
          cancelLabel={t('common.cancel')}
          onConfirm={() => {
            setConfirmBaseline(false)
            approveAll.mutate()
          }}
        />
      </CardContent>
    </Card>
  )
}
