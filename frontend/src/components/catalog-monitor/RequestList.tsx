import { Fragment, useState } from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import type { ChangeRequest } from '@/types'
import type { TabProps } from '@/components/catalog/types'
import { fieldLabel, isError, kindLabel, requestFields, requestIssues } from './changeLabels'
import { ChangePreview, RequestFlags, RequestStatusBadge } from './ChangePreview'

type T = TabProps['t']

interface Props {
  requests: ChangeRequest[]
  t: T
  /** With both, each row gets a checkbox. */
  selected?: Set<string>
  onToggle?: (id: string, on: boolean) => void
}

const MAX_FIELD_CHIPS = 4

function AmazonCell({ request, t }: { request: ChangeRequest; t: T }) {
  const issues = requestIssues(request)
  const errors = issues.filter(isError).length
  const warnings = issues.length - errors
  if (issues.length === 0) {
    if (Array.isArray(request.validation_issues)) {
      return <span className="text-xs text-green-700 dark:text-green-400">{t('cm.requests.amazonOk')}</span>
    }
    return <span className="text-xs text-muted-foreground">—</span>
  }
  return (
    <span className="text-xs">
      {errors > 0 && (
        <span className="text-red-700 dark:text-red-400">{t('cm.requests.errors', { count: errors })}</span>
      )}
      {errors > 0 && warnings > 0 && ' · '}
      {warnings > 0 && (
        <span className="text-amber-700 dark:text-amber-400">{t('cm.requests.warnings', { count: warnings })}</span>
      )}
    </span>
  )
}

/** Change requests, one row each; a row opens to show the before/after of every field. */
export function RequestList({ requests, t, selected, onToggle }: Props) {
  const [open, setOpen] = useState<Set<string>>(new Set())
  const selectable = !!selected && !!onToggle
  const columns = selectable ? 6 : 5

  const toggleOpen = (id: string) =>
    setOpen((cur) => {
      const next = new Set(cur)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })

  return (
    <Table>
      <TableHeader>
        <TableRow>
          {selectable && <TableHead className="w-10" />}
          <TableHead className="w-[150px]">{t('cm.requests.col.product')}</TableHead>
          <TableHead>{t('cm.requests.col.change')}</TableHead>
          <TableHead className="w-[320px]">{t('cm.requests.col.status')}</TableHead>
          <TableHead className="w-[130px]">{t('cm.requests.col.amazon')}</TableHead>
          <TableHead className="w-10" />
        </TableRow>
      </TableHeader>
      <TableBody>
        {requests.map((request) => {
          const expanded = open.has(request.id)
          const fields = requestFields(request).map((f) => fieldLabel(t, f.field))
          const Icon = expanded ? ChevronDown : ChevronRight
          return (
            <Fragment key={request.id}>
              <TableRow
                className="cursor-pointer"
                tabIndex={0}
                aria-expanded={expanded}
                onClick={() => toggleOpen(request.id)}
                onKeyDown={(e) => {
                  if (e.target === e.currentTarget && (e.key === 'Enter' || e.key === ' ')) {
                    e.preventDefault()
                    toggleOpen(request.id)
                  }
                }}
              >
                {selected && onToggle && (
                  <TableCell onClick={(e) => e.stopPropagation()}>
                    <Checkbox
                      aria-label={t('cm.common.selectRow', { id: request.asin ?? request.sku ?? request.id })}
                      checked={selected.has(request.id)}
                      onCheckedChange={(v) => onToggle(request.id, v === true)}
                    />
                  </TableCell>
                )}
                <TableCell className="whitespace-nowrap">
                  <div className="font-mono text-xs">{request.asin ?? '—'}</div>
                  <div className="font-mono text-xs text-muted-foreground">{request.sku ?? '—'}</div>
                </TableCell>
                <TableCell>
                  <div className="text-sm">{kindLabel(t, request.kind)}</div>
                  {fields.length > 0 && (
                    <div className="mt-1 flex flex-wrap gap-1">
                      {fields.slice(0, MAX_FIELD_CHIPS).map((label, i) => (
                        <span key={i} className="rounded bg-muted px-1.5 py-0.5 text-[11px]">
                          {label}
                        </span>
                      ))}
                      {fields.length > MAX_FIELD_CHIPS && (
                        <span className="px-1 text-[11px] text-muted-foreground">
                          +{fields.length - MAX_FIELD_CHIPS}
                        </span>
                      )}
                    </div>
                  )}
                </TableCell>
                <TableCell>
                  <div className="flex flex-wrap gap-1">
                    <RequestStatusBadge request={request} t={t} />
                    <RequestFlags request={request} t={t} />
                  </div>
                </TableCell>
                <TableCell>
                  <AmazonCell request={request} t={t} />
                </TableCell>
                <TableCell>
                  <Icon className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
                </TableCell>
              </TableRow>
              {expanded && (
                <TableRow className="hover:bg-transparent">
                  <TableCell colSpan={columns} className="bg-muted/20 p-4">
                    <ChangePreview request={request} t={t} />
                  </TableCell>
                </TableRow>
              )}
            </Fragment>
          )
        })}
      </TableBody>
    </Table>
  )
}
