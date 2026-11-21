import { useState } from 'react'
import { FileCheck2, FileDown, Loader2, RefreshCw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { cn } from '@/lib/utils'
import type { ChangeRequest } from '@/types'
import { ConfirmDialog } from '@/components/catalog/ConfirmDialog'
import type { TabProps } from '@/components/catalog/types'
import { AdminButton } from './AdminButton'
import { awaitsManualUpload, inFeedFile, kindLabel } from './changeLabels'
import { RequestList } from './RequestList'

interface Props {
  batchId: string
  /** The batch's requests that pass the filters. */
  requests: ChangeRequest[]
  /** Every request of the batch, whatever the filters: what the file and the feed hold. */
  allInBatch: ChangeRequest[]
  selected: Set<string>
  onToggle: (id: string, on: boolean) => void
  onToggleAll: (ids: string[], on: boolean) => void
  onDownload: (batchId: string) => void
  downloading: boolean
  /** Approved file-only requests the operator uploaded by hand. */
  onMarkUploaded: (ids: string[]) => void
  marking: boolean
  onRefreshFeeds: (feedIds: string[]) => void
  refreshing: boolean
  focused: boolean
  t: TabProps['t']
}

/** One upload or restore: its requests, the Vendor Central file and the feed status. */
export function ApprovalBatch({
  batchId,
  requests,
  allInBatch,
  selected,
  onToggle,
  onToggleAll,
  onDownload,
  downloading,
  onMarkUploaded,
  marking,
  onRefreshFeeds,
  refreshing,
  focused,
  t,
}: Props) {
  const ids = requests.map((r) => r.id)
  const chosen = ids.filter((id) => selected.has(id)).length
  const created = allInBatch.reduce(
    (min, r) => (r.created_at < min ? r.created_at : min),
    allInBatch[0]?.created_at ?? '',
  )
  const kinds = [...new Set(allInBatch.map((r) => kindLabel(t, r.kind)))].join(', ')
  const [confirmMark, setConfirmMark] = useState(false)
  // requests missing their parent SKU never go into the file
  const fileReady = allInBatch.some((r) => r.file_only && inFeedFile(r))
  const toMark = allInBatch.filter(awaitsManualUpload).map((r) => r.id)
  const feedIds = [
    ...new Set(
      allInBatch.filter((r) => r.status === 'submitted' && r.feed_id).map((r) => r.feed_id as string),
    ),
  ]

  return (
    <section
      aria-label={t('cm.approvals.batch', { date: new Date(created).toLocaleString() })}
      className={cn('rounded-lg border', focused && 'ring-2 ring-primary/40')}
    >
      <header className="flex flex-wrap items-center justify-between gap-3 border-b bg-muted/40 px-4 py-2.5">
        <div className="flex items-center gap-3">
          <Checkbox
            aria-label={t('cm.common.selectAll')}
            checked={chosen === 0 ? false : chosen === ids.length ? true : 'indeterminate'}
            disabled={ids.length === 0}
            onCheckedChange={(v) => onToggleAll(ids, v === true)}
          />
          <div>
            <div className="text-sm font-medium">
              {t('cm.approvals.batch', { date: new Date(created).toLocaleString() })}
            </div>
            <div className="text-xs text-muted-foreground">
              {kinds} · {t('cm.approvals.batchCount', { count: allInBatch.length })}
            </div>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          {fileReady && (
            <Button
              size="sm"
              variant="outline"
              onClick={() => onDownload(batchId)}
              disabled={downloading}
              title={t('cm.approvals.downloadHelp')}
            >
              {downloading ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <FileDown className="mr-2 h-4 w-4" />
              )}
              {t('cm.approvals.download')}
            </Button>
          )}
          {toMark.length > 0 && (
            <AdminButton
              size="sm"
              variant="outline"
              adminOnlyTitle={t('cm.approvals.adminOnly')}
              onClick={() => setConfirmMark(true)}
              disabled={marking}
              title={t('cm.approvals.markUploadedHelp')}
            >
              {marking ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <FileCheck2 className="mr-2 h-4 w-4" />
              )}
              {t('cm.approvals.markUploaded')}
            </AdminButton>
          )}
          {feedIds.length > 0 && (
            <AdminButton
              size="sm"
              variant="outline"
              adminOnlyTitle={t('cm.approvals.adminOnly')}
              onClick={() => onRefreshFeeds(feedIds)}
              disabled={refreshing}
            >
              {refreshing ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <RefreshCw className="mr-2 h-4 w-4" />
              )}
              {t('cm.approvals.refreshFeed')}
            </AdminButton>
          )}
        </div>
      </header>
      <RequestList requests={requests} t={t} selected={selected} onToggle={onToggle} />
      <ConfirmDialog
        open={confirmMark}
        onOpenChange={setConfirmMark}
        title={t('cm.approvals.markUploadedTitle')}
        description={t('cm.approvals.markUploadedBody', { count: toMark.length })}
        confirmLabel={t('cm.approvals.markUploaded')}
        cancelLabel={t('common.cancel')}
        onConfirm={() => {
          setConfirmMark(false)
          onMarkUploaded(toMark)
        }}
      />
    </section>
  )
}
