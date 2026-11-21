import { useEffect, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { catalogMonitorApi } from '@/services/api'
import type { ChangeRequest } from '@/types'
import { AccountPicker } from '@/components/catalog/AccountPicker'
import type { TabProps } from '@/components/catalog/types'
import { ApprovalActions } from './ApprovalActions'
import { ApprovalBatch } from './ApprovalBatch'
import { ApprovalReport } from './ApprovalReport'
import { CHANGES_LIST_CAP, matchesFilter, type StatusFilter } from './changeLabels'
import { StatusFilters } from './StatusFilters'
import { useApprovalActions } from './useApprovalActions'

interface Props extends TabProps {
  /** Show only this batch (opened from a restore or an upload). */
  focusBatchId: string | null
  onClearFocus: () => void
}

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
  const [filter, setFilter] = useState<StatusFilter>('awaiting')
  const [selected, setSelected] = useState<Set<string>>(new Set())

  const query = useQuery({
    queryKey: ['catalog-monitor', 'changes', accountId],
    queryFn: () => catalogMonitorApi.listChanges(accountId),
    enabled: !!accountId,
  })
  const requests = useMemo(() => query.data ?? [], [query.data])
  const actions = useApprovalActions({
    accountId,
    requests,
    t,
    toast,
    onDone: () => setSelected(new Set()),
  })
  const { clearReport } = actions

  useEffect(() => {
    setSelected(new Set())
    clearReport()
  }, [accountId, clearReport])
  useEffect(() => {
    if (focusBatchId) setFilter('all')
  }, [focusBatchId])

  const inScope = useMemo(
    () => requests.filter((r) => !focusBatchId || r.batch_id === focusBatchId),
    [requests, focusBatchId],
  )
  const visible = useMemo(() => inScope.filter((r) => matchesFilter(filter, r.status)), [inScope, filter])
  const batches = useMemo(() => groupByBatch(visible), [visible])
  const batchMembers = useMemo(() => new Map(groupByBatch(requests)), [requests])
  const chosen = visible.filter((r) => selected.has(r.id))

  const setMany = (ids: string[], on: boolean) =>
    setSelected((cur) => {
      const next = new Set(cur)
      for (const id of ids) {
        if (on) next.add(id)
        else next.delete(id)
      }
      return next
    })

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

        <StatusFilters requests={inScope} value={filter} onChange={setFilter} t={t} />
        {requests.length >= CHANGES_LIST_CAP && (
          <p className="text-xs text-muted-foreground">
            {t('cm.approvals.capped', { count: CHANGES_LIST_CAP })}
          </p>
        )}

        {actions.report && <ApprovalReport report={actions.report} onClose={clearReport} t={t} />}

        <ApprovalActions
          chosen={chosen}
          pending={{
            approve: actions.approve.isPending,
            reject: actions.reject.isPending,
            submit: actions.submit.isPending,
          }}
          busy={actions.busy}
          onApprove={(ids) => actions.approve.mutate(ids)}
          onReject={(ids) => actions.reject.mutate(ids)}
          onSubmit={(ids) => actions.submit.mutate(ids)}
          t={t}
        />

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
              onToggle={(id, on) => setMany([id], on)}
              onToggleAll={setMany}
              onDownload={(id) => actions.download.mutate(id)}
              downloading={actions.download.isPending && actions.download.variables === batchId}
              onMarkUploaded={(ids) => actions.markUploaded.mutate(ids)}
              marking={actions.busy}
              onRefreshFeeds={(feedIds) => actions.refreshFeeds.mutate(feedIds)}
              refreshing={actions.refreshFeeds.isPending}
              focused={batchId === focusBatchId}
              t={t}
            />
          ))}
        </div>
      </CardContent>
    </Card>
  )
}
