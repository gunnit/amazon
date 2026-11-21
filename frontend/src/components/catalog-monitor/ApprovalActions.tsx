import { useState } from 'react'
import { Check, Loader2, Send, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import type { ChangeRequest } from '@/types'
import { ConfirmDialog } from '@/components/catalog/ConfirmDialog'
import type { TabProps } from '@/components/catalog/types'
import { AdminButton } from './AdminButton'
import { willSubmit } from './changeLabels'

interface Props {
  /** The selected requests among the visible ones. */
  chosen: ChangeRequest[]
  pending: { approve: boolean; reject: boolean; submit: boolean }
  busy: boolean
  onApprove: (ids: string[]) => void
  onReject: (ids: string[]) => void
  onSubmit: (ids: string[]) => void
  t: TabProps['t']
}

function Spinner({ on, icon: Icon }: { on: boolean; icon: typeof Check }) {
  return on ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Icon className="mr-2 h-4 w-4" />
}

/**
 * Approva, Rifiuta and Invia ad Amazon on the selection. Sending always asks first,
 * also when the list says nothing is sendable: the list may be older than the server.
 */
export function ApprovalActions({ chosen, pending, busy, onApprove, onReject, onSubmit, t }: Props) {
  const [confirm, setConfirm] = useState(false)
  const ids = chosen.map((r) => r.id)
  const sendable = chosen.filter(willSubmit).length
  const body =
    sendable === 0
      ? t('cm.approvals.confirmNone')
      : sendable === 1
        ? t('cm.approvals.confirmBodyOne')
        : t('cm.approvals.confirmBody', { count: sendable })

  return (
    <div className="sticky top-0 z-10 flex flex-wrap items-center justify-between gap-3 rounded-md border bg-background px-4 py-2">
      <span className="text-sm text-muted-foreground">
        {t('cm.approvals.selected', { count: chosen.length })}
      </span>
      <div className="flex flex-wrap gap-2">
        <AdminButton
          adminOnlyTitle={t('cm.approvals.adminOnly')}
          onClick={() => onApprove(ids)}
          disabled={chosen.length === 0 || busy}
        >
          <Spinner on={pending.approve} icon={Check} />
          {t('cm.approvals.approve')}
        </AdminButton>
        <Button variant="outline" onClick={() => onReject(ids)} disabled={chosen.length === 0 || busy}>
          <Spinner on={pending.reject} icon={X} />
          {t('cm.approvals.reject')}
        </Button>
        <AdminButton
          adminOnlyTitle={t('cm.approvals.adminOnly')}
          onClick={() => setConfirm(true)}
          disabled={chosen.length === 0 || busy}
        >
          <Spinner on={pending.submit} icon={Send} />
          {t('cm.approvals.submit')}
        </AdminButton>
      </div>
      <ConfirmDialog
        open={confirm}
        onOpenChange={setConfirm}
        title={t('cm.approvals.confirmTitle')}
        description={
          <>
            {body}
            {sendable > 0 && chosen.length > sendable && (
              <span className="mt-2 block">
                {t('cm.approvals.confirmSkipped', { count: chosen.length - sendable })}
              </span>
            )}
          </>
        }
        confirmLabel={t('cm.approvals.submit')}
        cancelLabel={t('common.cancel')}
        onConfirm={() => {
          setConfirm(false)
          onSubmit(ids)
        }}
      />
    </div>
  )
}
