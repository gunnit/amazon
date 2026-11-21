import { ArrowRight } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import type { BaselineUploadResponse, BulkUploadResponse, UploadRowError } from '@/types'
import type { TabProps } from '@/components/catalog/types'
import { RequestList } from './RequestList'

type T = TabProps['t']

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-md border p-3">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="text-xl font-semibold tabular-nums">{value}</dd>
    </div>
  )
}

/** Rows the upload could not use, with the sheet row number and the reason. */
export function RowErrors({ errors, t }: { errors: UploadRowError[]; t: T }) {
  if (errors.length === 0) return null
  return (
    <div className="space-y-1.5">
      <h4 className="text-sm font-medium">{t('cm.bulk.rowErrors', { count: errors.length })}</h4>
      <div className="max-h-72 overflow-y-auto rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-16">{t('cm.bulk.col.row')}</TableHead>
              <TableHead>{t('cm.bulk.col.product')}</TableHead>
              <TableHead>{t('cm.bulk.col.problem')}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {errors.map((e, i) => (
              <TableRow key={i}>
                <TableCell className="text-xs tabular-nums">{e.row ?? '—'}</TableCell>
                <TableCell className="font-mono text-xs">{e.asin ?? e.sku ?? '—'}</TableCell>
                <TableCell className="text-sm">{e.message}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}

interface UploadResultProps {
  result: BulkUploadResponse
  /** New items have no unchanged rows nor keywords to report. */
  newItems?: boolean
  onOpenApprovals: (batchId?: string | null) => void
  t: T
}

/** Step 3: what the file would change, Amazon's verdict per request, and the way to Approvals. */
export function UploadResult({ result, newItems, onOpenApprovals, t }: UploadResultProps) {
  const invalid = result.requests.filter((r) => r.status === 'invalid').length
  const fileOnly = result.requests.filter((r) => r.file_only).length
  return (
    <div className="space-y-4">
      <dl className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
        <Stat label={t('cm.bulk.stat.rows')} value={result.rows} />
        <Stat label={t('cm.bulk.stat.changes')} value={result.changes} />
        {!newItems && <Stat label={t('cm.bulk.stat.unchanged')} value={result.unchanged} />}
        {!newItems && <Stat label={t('cm.bulk.stat.keywords')} value={result.keywords_updated} />}
        <Stat label={t('cm.bulk.stat.errors')} value={result.row_errors.length} />
      </dl>

      {result.changes > 0 ? (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-md bg-muted px-4 py-3">
          <div className="space-y-0.5 text-sm">
            <p className="font-medium">{t('cm.bulk.toApprove', { count: result.changes })}</p>
            {invalid > 0 && <p>{t('cm.bulk.invalidHint', { count: invalid })}</p>}
            {fileOnly > 0 && <p>{t('cm.restore.fileOnly', { count: fileOnly })}</p>}
          </div>
          <Button size="sm" onClick={() => onOpenApprovals(result.batch_id)}>
            {t('cm.restore.openApprovals')}
            <ArrowRight className="ml-1.5 h-4 w-4" />
          </Button>
        </div>
      ) : (
        <p className="rounded-md bg-muted px-4 py-3 text-sm">{t('cm.bulk.noChanges')}</p>
      )}

      <RowErrors errors={result.row_errors} t={t} />

      {result.requests.length > 0 && (
        <div className="rounded-md border">
          <RequestList requests={result.requests} t={t} />
        </div>
      )}
    </div>
  )
}

/** Result of a file loaded as the approved reference (baseline mode). */
export function BaselineResult({ result, t }: { result: BaselineUploadResponse; t: T }) {
  return (
    <div className="space-y-4">
      <dl className="grid grid-cols-2 gap-2 sm:grid-cols-3">
        <Stat label={t('cm.bulk.stat.baselines')} value={result.updated} />
        <Stat label={t('cm.bulk.stat.keywords')} value={result.keywords_updated} />
        <Stat label={t('cm.bulk.stat.errors')} value={result.row_errors.length} />
      </dl>
      <p className="rounded-md bg-muted px-4 py-3 text-sm">
        {t('cm.bulk.baselineDone', { count: result.updated })}
      </p>
      <RowErrors errors={result.row_errors} t={t} />
    </div>
  )
}
