import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, Loader2, Send, X } from 'lucide-react'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { cn } from '@/lib/utils'
import { catalogMonitorApi } from '@/services/api'
import { apiErrorDetail } from '@/lib/apiError'
import { CHANGE_REQUEST_STATUSES } from '@/types'
import type { ChangeActionResponse, ChangeRequest, ChangeRequestStatus } from '@/types'
import { AccountPicker } from '@/components/catalog/AccountPicker'
import { ConfirmDialog } from '@/components/catalog/ConfirmDialog'
import type { TabProps } from '@/components/catalog/types'
import { AdminButton } from './AdminButton'
import { ApprovalBatch } from './ApprovalBatch'
import { AWAITING_ACTION, requestStatusLabel, skipReasonLabel, willSubmit } from './changeLabels'
import { saveBlob } from './download'

interface Props extends TabProps {
  /** Show only this batch (opened from a restore or an upload). */
  focusBatchId: string | null
  onClearFocus: () => void
}

type Filter = 'awaiting' | 'all' | ChangeRequestStatus
type Action = 'approve' | 'reject' | 'submit'

interface Report {
  title: string
  lines: string[]
  skipped: Array<{ id: string; label: string; reason: string }>
}

const matches = (filter: Filter, status: ChangeRequestStatus) =>
  filter === 'all' || (filter === 'awaiting' ? AWAITING_ACTION.includes(status) : filter === status)

const labelOf = (r: ChangeRequest | undefined, id: string) => r?.asin ?? r?.sku ?? id.slice(0, 8)

function groupByBatch(requests: ChangeRequest[]): Array<[string, ChangeRequest[]]> {
  const groups = new Map<string, ChangeRequest[]>()
  for (const r of requests) {
    const list = groups.get(r.batch_id)
    if (list) list.push(r)
    else groups.set(r.batch_id, [r])
  }
  return [...groups.entries()]
}

/** Every catalogue change waits here: approve or reject, then send to Amazon or download the file. */
export function ApprovalsPanel(props: Props) {
  const { t, toast, accountId, focusBatchId, onClearFocus } = props
  const queryClient = useQueryClient()
  const [filter, setFilter] = useState<Filter>('awaiting')
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [report, setReport] = useState<Report | null>(null)
  const [confirmSubmit, setConfirmSubmit] = useState(false)

  useEffect(() => {
    setSelected(new Set())
    setReport(null)
  }, [accountId])
  useEffect(() => {
    if (focusBatchId) setFilter('all')
  }, [focusBatchId])

  const query = useQuery({
    queryKey: ['catalog-monitor', 'changes', accountId],
    queryFn: () => catalogMonitorApi.listChanges(accountId),
    enabled: !!accountId,
  })
  const requests = useMemo(() => query.data ?? [], [query.data])
  const byId = useMemo(() => new Map(requests.map((r) => [r.id, r])), [requests])
  const inScope = useMemo(
    () => requests.filter((r) => !focusBatchId || r.batch_id === focusBatchId),
    [requests, focusBatchId],
  )
  const visible = useMemo(() => inScope.filter((r) => matches(filter, r.status)), [inScope, filter])
  const batches = useMemo(() => groupByBatch(visible), [visible])
  const batchMembers = useMemo(() => new Map(groupByBatch(requests)), [requests])
  const chosen = visible.filter((r) => selected.has(r.id))
  const chosenIds = chosen.map((r) => r.id)
  const toSubmit = chosen.filter(willSubmit).length

  const countFor = (f: Filter) => inScope.filter((r) => matches(f, r.status)).length
  const filters: Filter[] = ['awaiting', 'all', ...CHANGE_REQUEST_STATUSES]

  const refresh = () => {
    for (const key of ['changes', 'anomalies', 'variations']) {
      void queryClient.invalidateQueries({ queryKey: ['catalog-monitor', key] })
    }
  }

  const finish = (action: Action, ids: string[], res: ChangeActionResponse) => {
    const skipped = Object.entries(res.skipped).map(([id, reason]) => ({
      id,
      label: labelOf(byId.get(id), id),
      reason,
    }))
    const done = ids.length - skipped.length
    const lines: string[] = []
    if (action === 'submit') {
      const sent = res.requests.filter((r) => !(r.id in res.skipped))
      const count = (s: ChangeRequestStatus) => sent.filter((r) => r.status === s).length
      if (count('accepted')) lines.push(t('cm.approvals.result.accepted', { count: count('accepted') }))
      if (count('failed')) lines.push(t('cm.approvals.result.failed', { count: count('failed') }))
      if (count('submitted')) lines.push(t('cm.approvals.result.submitted', { count: count('submitted') }))
    }
    const title = t(`cm.approvals.done.${action}`, { count: done })
    setReport({ title, lines, skipped })
    // the report sits above the list: the toast makes the outcome visible wherever the operator is
    toast({
      title,
      description: skipped.length > 0 ? t('cm.approvals.skippedToast', { count: skipped.length }) : undefined,
    })
    setSelected(new Set())
    refresh()
  }

  const onError = (title: string) => (error: unknown) =>
    toast({ title, description: apiErrorDetail(error, t), variant: 'destructive' })

  const approve = useMutation({
    mutationFn: (ids: string[]) => catalogMonitorApi.approveChanges(ids),
    onSuccess: (res, ids) => finish('approve', ids, res),
    onError: onError(t('cm.approvals.error.approve')),
  })
  const reject = useMutation({
    mutationFn: (ids: string[]) => catalogMonitorApi.rejectChanges(ids),
    onSuccess: (res, ids) => finish('reject', ids, res),
    onError: onError(t('cm.approvals.error.reject')),
  })
  const submit = useMutation({
    mutationFn: (ids: string[]) => catalogMonitorApi.submitChanges(ids),
    onSuccess: (res, ids) => finish('submit', ids, res),
    onError: onError(t('cm.approvals.error.submit')),
  })
  const refreshFeeds = useMutation({
    mutationFn: (feedIds: string[]) =>
      Promise.all(feedIds.map((id) => catalogMonitorApi.refreshFeed(accountId, id))),
    onSuccess: (lists) => {
      const all = lists.flat()
      const count = (s: ChangeRequestStatus) => all.filter((r) => r.status === s).length
      toast({
        title: t('cm.approvals.feedRefreshed'),
        description: t('cm.approvals.feedStatus', {
          accepted: count('accepted'),
          failed: count('failed'),
          submitted: count('submitted'),
        }),
      })
      refresh()
    },
    onError: onError(t('cm.approvals.error.refresh')),
  })
  const download = useMutation({
    mutationFn: (batchId: string) => catalogMonitorApi.downloadFeedFile(batchId),
    onSuccess: (file, batchId) => {
      saveBlob(file.blob, file.filename)
      const inFile = (batchMembers.get(batchId) ?? []).filter(
        (r) => r.status === 'approved' || r.status === 'file_only',
      )
      // The header names the excluded requests; cross-origin it may be unreadable, then count them.
      const skippedIds = file.skippedIds
      const skippedCount = skippedIds ? skippedIds.length : Math.max(0, inFile.length - file.messages)
      const title = t('cm.approvals.fileDone', { count: file.messages })
      toast({
        title,
        description: skippedCount > 0 ? t('cm.approvals.fileSkipped', { count: skippedCount }) : undefined,
      })
      setReport({
        title,
        lines: [
          t('cm.approvals.fileHint'),
          ...(skippedCount > 0 ? [t('cm.approvals.fileSkipped', { count: skippedCount })] : []),
        ],
        skipped: (skippedIds ?? []).map((id) => ({
          id,
          label: labelOf(byId.get(id), id),
          reason: 'not_in_file',
        })),
      })
    },
    onError: onError(t('cm.approvals.error.download')),
  })

  const busy = approve.isPending || reject.isPending || submit.isPending
  const toggle = (id: string, on: boolean) =>
    setSelected((cur) => {
      const next = new Set(cur)
      if (on) next.add(id)
      else next.delete(id)
      return next
    })
  const toggleAll = (ids: string[], on: boolean) =>
    setSelected((cur) => {
      const next = new Set(cur)
      for (const id of ids) {
        if (on) next.add(id)
        else next.delete(id)
      }
      return next
    })

  const onSubmitClick = () => {
    // Nothing selected can reach Amazon: send anyway to get the reasons, no listing changes.
    if (toSubmit === 0) submit.mutate(chosenIds)
    else setConfirmSubmit(true)
  }

  const filterLabel = (f: Filter) =>
    f === 'awaiting'
      ? t('cm.approvals.filter.awaiting')
      : f === 'all'
        ? t('cm.approvals.filter.all')
        : requestStatusLabel(t, f)

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('cm.approvals.title')}</CardTitle>
        <CardDescription>{t('cm.approvals.description')}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="min-w-[220px] max-w-sm">
          <AccountPicker {...props} />
        </div>

        {focusBatchId && (
          <div className="flex flex-wrap items-center justify-between gap-2 rounded-md bg-muted px-4 py-2 text-sm">
            <span>{t('cm.approvals.focused')}</span>
            <Button size="sm" variant="ghost" onClick={onClearFocus}>
              {t('cm.approvals.showAll')}
            </Button>
          </div>
        )}

        <div className="flex flex-wrap gap-1.5" role="group" aria-label={t('cm.approvals.filterLabel')}>
          {filters.map((f) => {
            const n = countFor(f)
            if (n === 0 && f !== 'awaiting' && f !== 'all' && f !== filter) return null
            return (
              <button
                key={f}
                type="button"
                aria-pressed={filter === f}
                onClick={() => setFilter(f)}
                className={cn(
                  'rounded-full border px-3 py-1 text-xs font-medium transition-colors hover:bg-muted',
                  filter === f && 'border-primary bg-primary text-primary-foreground hover:bg-primary/90',
                )}
              >
                {filterLabel(f)} · {n}
              </button>
            )
          })}
        </div>

        {report && (
          <Alert variant={report.skipped.length > 0 ? 'warning' : 'default'}>
            <AlertTitle>{report.title}</AlertTitle>
            <AlertDescription className="space-y-1.5">
              {report.lines.map((line) => (
                <p key={line}>{line}</p>
              ))}
              {report.skipped.length > 0 && (
                <ul className="list-disc space-y-0.5 pl-5 text-xs">
                  {report.skipped.map((s) => (
                    <li key={s.id}>
                      <span className="font-mono">{s.label}</span>: {skipReasonLabel(t, s.reason)}
                    </li>
                  ))}
                </ul>
              )}
              <Button size="sm" variant="ghost" onClick={() => setReport(null)}>
                {t('cm.common.close')}
              </Button>
            </AlertDescription>
          </Alert>
        )}

        {/* Action bar */}
        <div className="sticky top-0 z-10 flex flex-wrap items-center justify-between gap-3 rounded-md border bg-background px-4 py-2">
          <span className="text-sm text-muted-foreground">
            {t('cm.approvals.selected', { count: chosen.length })}
          </span>
          <div className="flex flex-wrap gap-2">
            <AdminButton
              adminOnlyTitle={t('cm.approvals.adminOnly')}
              onClick={() => approve.mutate(chosenIds)}
              disabled={chosen.length === 0 || busy}
            >
              {approve.isPending ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Check className="mr-2 h-4 w-4" />
              )}
              {t('cm.approvals.approve')}
            </AdminButton>
            <Button
              variant="outline"
              onClick={() => reject.mutate(chosenIds)}
              disabled={chosen.length === 0 || busy}
            >
              {reject.isPending ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <X className="mr-2 h-4 w-4" />
              )}
              {t('cm.approvals.reject')}
            </Button>
            <AdminButton
              adminOnlyTitle={t('cm.approvals.adminOnly')}
              onClick={onSubmitClick}
              disabled={chosen.length === 0 || busy}
            >
              {submit.isPending ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Send className="mr-2 h-4 w-4" />
              )}
              {t('cm.approvals.submit')}
            </AdminButton>
          </div>
        </div>

        {query.isLoading && <Loader2 className="mx-auto h-5 w-5 animate-spin" />}
        {query.isError && <p className="text-sm text-destructive">{t('cm.approvals.loadError')}</p>}
        {query.data && visible.length === 0 && (
          <p className="rounded-md border border-dashed p-6 text-center text-sm text-muted-foreground">
            {filter === 'awaiting' ? t('cm.approvals.emptyAwaiting') : t('cm.approvals.empty')}
          </p>
        )}

        <div className="space-y-4">
          {batches.map(([batchId, list]) => (
            <ApprovalBatch
              key={batchId}
              batchId={batchId}
              requests={list}
              allInBatch={batchMembers.get(batchId) ?? list}
              selected={selected}
              onToggle={toggle}
              onToggleAll={toggleAll}
              onDownload={(id) => download.mutate(id)}
              downloading={download.isPending && download.variables === batchId}
              onRefreshFeeds={(feedIds) => refreshFeeds.mutate(feedIds)}
              refreshing={refreshFeeds.isPending}
              focused={batchId === focusBatchId}
              t={t}
            />
          ))}
        </div>

        <ConfirmDialog
          open={confirmSubmit}
          onOpenChange={setConfirmSubmit}
          title={t('cm.approvals.confirmTitle')}
          description={
            <>
              {toSubmit === 1
                ? t('cm.approvals.confirmBodyOne')
                : t('cm.approvals.confirmBody', { count: toSubmit })}
              {chosen.length > toSubmit && (
                <span className="mt-2 block">
                  {t('cm.approvals.confirmSkipped', { count: chosen.length - toSubmit })}
                </span>
              )}
            </>
          }
          confirmLabel={t('cm.approvals.submit')}
          cancelLabel={t('common.cancel')}
          onConfirm={() => {
            setConfirmSubmit(false)
            submit.mutate(chosenIds)
          }}
        />
      </CardContent>
    </Card>
  )
}
