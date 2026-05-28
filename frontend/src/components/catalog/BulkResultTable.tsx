import { Check, X } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import type { BulkResult, BulkRowError } from './types'

type Props<T> = {
  result: BulkResult<T> | null
  t: (key: string, vars?: Record<string, string | number>) => string
  /** Render a label for each success row (e.g. "ASIN — €12.50"). */
  successLabel: (row: T) => string
}

export function BulkResultTable<T>({ result, t, successLabel }: Props<T>) {
  if (!result) return null

  const rows: Array<
    | { kind: 'ok'; label: string }
    | { kind: 'err'; error: BulkRowError }
  > = [
    ...result.successes.map<{ kind: 'ok'; label: string }>((s) => ({
      kind: 'ok',
      label: successLabel(s),
    })),
    ...result.errors.map<{ kind: 'err'; error: BulkRowError }>((e) => ({
      kind: 'err',
      error: e,
    })),
  ]

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2 text-sm">
        <Badge variant="default" className="bg-green-600">
          {t('catalog.result.ok')}: {result.succeeded}
        </Badge>
        <Badge variant="destructive">
          {t('catalog.result.failed')}: {result.failed}
        </Badge>
        {result.skipped ? (
          <Badge variant="outline">
            {t('catalog.result.skipped')}: {result.skipped}
          </Badge>
        ) : null}
        <span className="text-muted-foreground">
          {t('catalog.result.total', { n: result.total })}
        </span>
      </div>
      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-[80px]">{t('catalog.result.status')}</TableHead>
              <TableHead className="w-[60px]">{t('catalog.result.rowNumber')}</TableHead>
              <TableHead>{t('catalog.result.identifier')}</TableHead>
              <TableHead>{t('catalog.result.errorMessage')}</TableHead>
              <TableHead className="w-[140px]">{t('catalog.result.errorCode')}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.length === 0 && (
              <TableRow>
                <TableCell colSpan={5} className="text-center py-4 text-muted-foreground">
                  {t('catalog.result.empty')}
                </TableCell>
              </TableRow>
            )}
            {rows.map((row, idx) =>
              row.kind === 'ok' ? (
                <TableRow key={`ok-${idx}`}>
                  <TableCell>
                    <span className="inline-flex items-center gap-1 text-green-600 text-xs font-medium">
                      <Check className="h-3.5 w-3.5" />
                      {t('catalog.result.ok')}
                    </span>
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">—</TableCell>
                  <TableCell className="font-mono text-xs">{row.label}</TableCell>
                  <TableCell className="text-xs text-muted-foreground">—</TableCell>
                  <TableCell className="text-xs text-muted-foreground">—</TableCell>
                </TableRow>
              ) : (
                <TableRow key={`err-${idx}`}>
                  <TableCell>
                    <span className="inline-flex items-center gap-1 text-destructive text-xs font-medium">
                      <X className="h-3.5 w-3.5" />
                      {t('catalog.result.failed')}
                    </span>
                  </TableCell>
                  <TableCell className="text-xs">{row.error.row ?? '—'}</TableCell>
                  <TableCell className="font-mono text-xs">
                    {row.error.asin ?? row.error.sku ?? '—'}
                  </TableCell>
                  <TableCell className="text-xs">{row.error.error}</TableCell>
                  <TableCell>
                    <Badge variant="outline" className="text-[10px]">
                      {row.error.code}
                    </Badge>
                  </TableCell>
                </TableRow>
              ),
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}
