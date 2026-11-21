import { ArrowRight } from 'lucide-react'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import type { ChangeBatchResponse } from '@/types'
import type { TabProps } from '@/components/catalog/types'
import { fieldLabel, parentSkuMissing, skipReasonLabel } from './changeLabels'

interface Props {
  result: ChangeBatchResponse
  onOpenApprovals: (batchId?: string | null) => void
  onDismiss: () => void
  t: TabProps['t']
}

/** What a restore created (requests to approve) and what it left out, and why. */
export function RestoreResult({ result, onOpenApprovals, onDismiss, t }: Props) {
  const created = result.requests.length
  const invalid = result.requests.filter((r) => r.status === 'invalid').length
  const fileOnly = result.requests.filter((r) => r.file_only).length
  const notices = [...result.not_restorable, ...result.skipped]
  return (
    <Alert variant={created > 0 ? 'default' : 'warning'}>
      <AlertTitle>
        {created > 0 ? t('cm.restore.created', { count: created }) : t('cm.restore.none')}
      </AlertTitle>
      <AlertDescription className="space-y-2">
        {created > 0 && <p>{t('cm.restore.createdHint')}</p>}
        {invalid > 0 && <p>{t('cm.restore.invalid', { count: invalid })}</p>}
        {fileOnly > 0 && <p>{t('cm.restore.fileOnly', { count: fileOnly })}</p>}
        {result.requests.some(parentSkuMissing) && (
          <p className="font-medium">{t('cm.badge.parentSkuMissing')}</p>
        )}
        {notices.length > 0 && (
          <ul className="list-disc space-y-0.5 pl-5 text-xs">
            {notices.map((n) => (
              <li key={`${n.anomaly_id}-${n.reason}`}>
                <span className="font-mono">{n.asin}</span> · {fieldLabel(t, n.field)}:{' '}
                {skipReasonLabel(t, n.reason)}
              </li>
            ))}
          </ul>
        )}
        <div className="flex flex-wrap gap-2 pt-1">
          {created > 0 && (
            <Button size="sm" onClick={() => onOpenApprovals(result.batch_id)}>
              {t('cm.restore.openApprovals')}
              <ArrowRight className="ml-1.5 h-4 w-4" />
            </Button>
          )}
          <Button size="sm" variant="ghost" onClick={onDismiss}>
            {t('cm.common.close')}
          </Button>
        </div>
      </AlertDescription>
    </Alert>
  )
}
