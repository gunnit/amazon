import { AlertTriangle, CheckCircle2, Info, XCircle } from 'lucide-react'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import type { ChangeIssue, ChangeRequest } from '@/types'
import type { TabProps } from '@/components/catalog/types'
import {
  REQUEST_STATUS_CLASS,
  fieldLabel,
  isError,
  isManualUpload,
  manualImageRemoval,
  parentSkuMissing,
  passedValidation,
  pathField,
  requestFields,
  requestIssues,
  requestStatusLabel,
} from './changeLabels'
import { DiffLegend, FieldCompare } from './FieldCompare'

type T = TabProps['t']

export function RequestStatusBadge({ request, t }: { request: ChangeRequest; t: T }) {
  // "submitted" is either a feed Amazon is processing or a file the operator uploaded by hand
  const label = isManualUpload(request)
    ? t('cm.request.manualUpload')
    : request.status === 'submitted' && request.feed_id
      ? t('cm.request.feedProcessing')
      : requestStatusLabel(t, request.status)
  return (
    <Badge variant="outline" className={cn('border-transparent', REQUEST_STATUS_CLASS[request.status])}>
      {label}
    </Badge>
  )
}

const FLAG_WARN = 'border-amber-300 bg-amber-50 text-amber-900 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-200'
const FLAG_ERROR = 'border-red-300 bg-red-50 text-red-800 dark:border-red-800 dark:bg-red-950/40 dark:text-red-200'

/** What the operator must know before acting: file only, manual steps, missing validation. */
export function RequestFlags({ request, t }: { request: ChangeRequest; t: T }) {
  const flags: Array<{ key: string; text: string; className: string }> = []
  if (request.file_only && request.status !== 'file_only') {
    flags.push({ key: 'file', text: t('cm.badge.fileOnly'), className: FLAG_WARN })
  }
  if (parentSkuMissing(request)) {
    flags.push({ key: 'parent', text: t('cm.badge.parentSkuMissing'), className: FLAG_ERROR })
  }
  if (manualImageRemoval(request).length > 0) {
    flags.push({ key: 'images', text: t('cm.badge.manualImageRemoval'), className: FLAG_WARN })
  }
  if (request.status === 'approved' && !request.file_only && !passedValidation(request)) {
    flags.push({ key: 'validation', text: t('cm.badge.notValidated'), className: FLAG_ERROR })
  }
  if (flags.length === 0) return null
  return (
    <>
      {flags.map((f) => (
        <Badge key={f.key} variant="outline" className={cn('font-medium', f.className)}>
          {f.text}
        </Badge>
      ))}
    </>
  )
}

function IssueIcon({ issue }: { issue: ChangeIssue }) {
  const severity = (issue.severity ?? '').toUpperCase()
  if (severity === 'ERROR') return <XCircle className="mt-0.5 h-4 w-4 shrink-0 text-red-600 dark:text-red-400" aria-hidden="true" />
  if (severity === 'WARNING') return <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-600 dark:text-amber-400" aria-hidden="true" />
  return <Info className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
}

/** Amazon's answer: issues from the validation preview and, once sent, from the submission. */
function AmazonIssues({ request, t }: { request: ChangeRequest; t: T }) {
  const issues = requestIssues(request)
  if (issues.length === 0) {
    if (request.file_only) return null
    return Array.isArray(request.validation_issues) ? (
      <p className="flex items-center gap-1.5 text-sm text-green-700 dark:text-green-400">
        <CheckCircle2 className="h-4 w-4" aria-hidden="true" />
        {t('cm.preview.noIssues')}
      </p>
    ) : (
      <p className="text-sm text-muted-foreground">{t('cm.preview.notChecked')}</p>
    )
  }
  return (
    <div className="space-y-1.5">
      <h5 className="text-sm font-medium">{t('cm.preview.issues')}</h5>
      <ul className="space-y-1.5">
        {issues.map((issue, i) => (
          <li key={i} className="flex gap-2 text-sm">
            <IssueIcon issue={issue} />
            <span className="min-w-0">
              <span className="sr-only">{isError(issue) ? t('cm.preview.error') : t('cm.preview.warning')}: </span>
              {issue.code && <span className="mr-1.5 font-mono text-xs text-muted-foreground">{issue.code}</span>}
              {issue.message}
              {issue.attributeNames && issue.attributeNames.length > 0 && (
                <span className="ml-1.5 text-xs text-muted-foreground">
                  ({issue.attributeNames.join(', ')})
                </span>
              )}
            </span>
          </li>
        ))}
      </ul>
    </div>
  )
}

/** Everything one change request would do on Amazon, and what Amazon said about it. */
export function ChangePreview({ request, t }: { request: ChangeRequest; t: T }) {
  const fields = requestFields(request)
  const removal = manualImageRemoval(request)
  const summary = request.summary ?? {}
  const text = (v: unknown) => (v == null || v === '' ? '—' : String(v))

  return (
    <div className="space-y-4">
      {request.kind === 'variation_restore' && (
        <p className="text-sm">
          {t('cm.preview.variation', {
            parent: text(summary.parent_asin),
            sku: text(summary.parent_sku),
            theme: text(summary.variation_theme),
          })}
        </p>
      )}
      {parentSkuMissing(request) && (
        <Alert variant="warning">
          <AlertDescription>{t('cm.badge.parentSkuMissing')}</AlertDescription>
        </Alert>
      )}
      {request.file_only && (
        <p className="rounded-md bg-muted px-3 py-2 text-sm">{t('cm.preview.fileOnlyHint')}</p>
      )}
      {removal.length > 0 && (
        <Alert variant="warning">
          <AlertTitle>{t('cm.badge.manualImageRemoval')}</AlertTitle>
          <AlertDescription>
            <ul className="list-disc pl-5">
              {removal.map((path) => (
                <li key={path}>{fieldLabel(t, pathField(path))}</li>
              ))}
            </ul>
          </AlertDescription>
        </Alert>
      )}

      {fields.map((f) => (
        <div key={f.field} className="space-y-1.5">
          <h5 className="text-sm font-medium">{fieldLabel(t, f.field)}</h5>
          <FieldCompare
            field={f.field}
            before={f.before}
            after={f.after}
            beforeLabel={request.kind === 'new_item' ? t('cm.preview.newItemBefore') : t('cm.diff.live')}
            afterLabel={request.kind === 'content_restore' ? t('cm.diff.approved') : t('cm.preview.new')}
            t={t}
          />
        </div>
      ))}
      {fields.length > 0 && <DiffLegend t={t} />}

      <AmazonIssues request={request} t={t} />
      {request.feed_id && (
        <p className="text-xs text-muted-foreground">{t('cm.preview.feed', { id: request.feed_id })}</p>
      )}
    </div>
  )
}
