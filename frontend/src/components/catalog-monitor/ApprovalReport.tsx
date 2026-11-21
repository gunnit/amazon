import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import type { TabProps } from '@/components/catalog/types'
import { skipReasonLabel } from './changeLabels'
import type { ActionReport } from './useApprovalActions'

/** The outcome of the last approval action, with every request it left out and why. */
export function ApprovalReport({ report, onClose, t }: { report: ActionReport; onClose: () => void; t: TabProps['t'] }) {
  return (
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
        <Button size="sm" variant="ghost" onClick={onClose}>
          {t('cm.common.close')}
        </Button>
      </AlertDescription>
    </Alert>
  )
}
