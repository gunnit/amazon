import { useCallback, useMemo, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { catalogMonitorApi } from '@/services/api'
import { apiErrorDetail } from '@/lib/apiError'
import type { ChangeActionResponse, ChangeRequest, ChangeRequestStatus } from '@/types'
import type { TabProps } from '@/components/catalog/types'
import { saveBlob } from './download'
import { inFeedFile } from './changeLabels'

export type ApprovalAction = 'approve' | 'reject' | 'submit' | 'markUploaded'

/** What the last action did, and the requests it left out with the reason. */
export interface ActionReport {
  title: string
  lines: string[]
  skipped: Array<{ id: string; label: string; reason: string }>
}

interface Options extends Pick<TabProps, 'accountId' | 't' | 'toast'> {
  /** Every request of the account (not only the filtered ones). */
  requests: ChangeRequest[]
  /** Called after an action on a selection succeeds (clears the selection). */
  onDone: () => void
}

const labelOf = (r: ChangeRequest | undefined, id: string) => r?.asin ?? r?.sku ?? id.slice(0, 8)

/** The approval queue's mutations: approve, reject, submit, mark uploaded, refresh feeds, download file. */
export function useApprovalActions({ accountId, requests, t, toast, onDone }: Options) {
  const queryClient = useQueryClient()
  const [report, setReport] = useState<ActionReport | null>(null)
  const byId = useMemo(() => new Map(requests.map((r) => [r.id, r])), [requests])

  const refresh = () => {
    for (const key of ['changes', 'anomalies', 'variations']) {
      void queryClient.invalidateQueries({ queryKey: ['catalog-monitor', key] })
    }
  }
  const onError = (title: string) => (error: unknown) =>
    toast({ title, description: apiErrorDetail(error, t), variant: 'destructive' })

  const finish = (action: ApprovalAction, ids: string[], res: ChangeActionResponse) => {
    const skipped = Object.entries(res.skipped).map(([id, reason]) => ({
      id,
      label: labelOf(byId.get(id), id),
      reason,
    }))
    const lines: string[] = []
    if (action === 'submit') {
      const sent = res.requests.filter((r) => !(r.id in res.skipped))
      const count = (s: ChangeRequestStatus) => sent.filter((r) => r.status === s).length
      if (count('accepted')) lines.push(t('cm.approvals.result.accepted', { count: count('accepted') }))
      if (count('failed')) lines.push(t('cm.approvals.result.failed', { count: count('failed') }))
      if (count('submitted')) lines.push(t('cm.approvals.result.submitted', { count: count('submitted') }))
    }
    const title = t(`cm.approvals.done.${action}`, { count: ids.length - skipped.length })
    setReport({ title, lines, skipped })
    // the report sits above the list: the toast makes the outcome visible wherever the operator is
    toast({
      title,
      description: skipped.length > 0 ? t('cm.approvals.skippedToast', { count: skipped.length }) : undefined,
    })
    onDone()
    refresh()
  }

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
  const markUploaded = useMutation({
    mutationFn: (ids: string[]) => catalogMonitorApi.markUploaded(ids),
    onSuccess: (res, ids) => finish('markUploaded', ids, res),
    onError: onError(t('cm.approvals.error.markUploaded')),
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
      const eligible = requests.filter(
        (r) => r.batch_id === batchId && (r.status === 'approved' || r.status === 'file_only'),
      )
      // The header names the excluded requests; if it cannot be read, count them.
      const skippedIds =
        file.skippedIds ?? eligible.filter((r) => !inFeedFile(r)).map((r) => r.id)
      const skippedCount = file.skippedIds
        ? file.skippedIds.length
        : Math.max(skippedIds.length, eligible.length - file.messages)
      const title = t('cm.approvals.fileDone', { count: file.messages })
      const skippedLine = skippedCount > 0 ? [t('cm.approvals.fileSkipped', { count: skippedCount })] : []
      toast({ title, description: skippedLine[0] })
      setReport({
        title,
        lines: [t('cm.approvals.fileHint'), ...skippedLine],
        skipped: skippedIds.map((id) => ({ id, label: labelOf(byId.get(id), id), reason: 'not_in_file' })),
      })
    },
    onError: onError(t('cm.approvals.error.download')),
  })

  const clearReport = useCallback(() => setReport(null), [])

  return {
    report,
    clearReport,
    approve,
    reject,
    submit,
    markUploaded,
    refreshFeeds,
    download,
    busy: approve.isPending || reject.isPending || submit.isPending || markUploaded.isPending,
  }
}
