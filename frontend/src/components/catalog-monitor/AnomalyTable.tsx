import { Eye, History, Loader2 } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { cn } from '@/lib/utils'
import type { AnomalyStatus, CatalogAnomaly } from '@/types'
import type { TabProps } from '@/components/catalog/types'
import { anomalyStatusLabel, canRestoreAnomaly, changeTypeLabel, fieldLabel } from './changeLabels'

const STATUS_CLASS: Record<AnomalyStatus, string> = {
  open: 'bg-red-100 text-red-800 dark:bg-red-900/50 dark:text-red-300',
  acknowledged: 'bg-amber-100 text-amber-900 dark:bg-amber-900/50 dark:text-amber-300',
  restore_requested: 'bg-indigo-100 text-indigo-800 dark:bg-indigo-900/50 dark:text-indigo-300',
  resolved: 'bg-green-100 text-green-800 dark:bg-green-900/50 dark:text-green-300',
}
const COLUMNS = 7

interface Props {
  anomalies: CatalogAnomaly[]
  loading: boolean
  error: boolean
  /** Shown when the list is loaded and empty. */
  emptyText: string | null
  selected: Set<string>
  onToggle: (id: string, on: boolean) => void
  onToggleAll: (on: boolean) => void
  onOpen: (id: string) => void
  onHistory: (asin: string) => void
  t: TabProps['t']
}

/** Content changes against the approved version, one row each, selectable when restorable. */
export function AnomalyTable({
  anomalies, loading, error, emptyText, selected, onToggle, onToggleAll, onOpen, onHistory, t,
}: Props) {
  const restorable = anomalies.filter(canRestoreAnomaly)
  const chosen = restorable.filter((a) => selected.has(a.id)).length
  const message = (text: string, className = 'text-muted-foreground') => (
    <TableRow>
      <TableCell colSpan={COLUMNS} className={cn('py-8 text-center', className)}>
        {text}
      </TableCell>
    </TableRow>
  )

  return (
    <div className="rounded-md border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-10">
              <Checkbox
                aria-label={t('cm.common.selectAll')}
                checked={chosen > 0 && chosen === restorable.length ? true : chosen > 0 ? 'indeterminate' : false}
                disabled={restorable.length === 0}
                onCheckedChange={(v) => onToggleAll(v === true)}
              />
            </TableHead>
            <TableHead>{t('cm.protection.col.product')}</TableHead>
            <TableHead>{t('cm.protection.col.field')}</TableHead>
            <TableHead>{t('cm.protection.col.change')}</TableHead>
            <TableHead>{t('cm.protection.col.detected')}</TableHead>
            <TableHead>{t('cm.protection.col.status')}</TableHead>
            <TableHead className="w-[1%]" />
          </TableRow>
        </TableHeader>
        <TableBody>
          {loading && (
            <TableRow>
              <TableCell colSpan={COLUMNS} className="py-8 text-center">
                <Loader2 className="mx-auto h-5 w-5 animate-spin" />
              </TableCell>
            </TableRow>
          )}
          {error && message(t('cm.protection.loadError'), 'text-destructive')}
          {emptyText && anomalies.length === 0 && message(emptyText)}
          {anomalies.map((a) => {
            const restorableRow = canRestoreAnomaly(a)
            return (
              <TableRow
                key={a.id}
                className="cursor-pointer"
                tabIndex={0}
                onClick={() => onOpen(a.id)}
                onKeyDown={(e) => {
                  if (e.target === e.currentTarget && (e.key === 'Enter' || e.key === ' ')) {
                    e.preventDefault()
                    onOpen(a.id)
                  }
                }}
              >
                <TableCell onClick={(e) => e.stopPropagation()}>
                  <Checkbox
                    aria-label={t('cm.common.selectRow', { id: a.asin })}
                    checked={selected.has(a.id) && restorableRow}
                    disabled={!restorableRow}
                    title={restorableRow ? undefined : t('cm.protection.notSelectable')}
                    onCheckedChange={(v) => onToggle(a.id, v === true)}
                  />
                </TableCell>
                <TableCell className="max-w-[280px]">
                  <div className="font-mono text-xs">{a.asin}</div>
                  <div className="truncate text-xs text-muted-foreground" title={a.title ?? undefined}>
                    {a.title || t('catalog.products.titleMissing')}
                  </div>
                </TableCell>
                <TableCell className="text-sm">{fieldLabel(t, a.field)}</TableCell>
                <TableCell className="text-sm">{a.change ? changeTypeLabel(t, a.change) : '—'}</TableCell>
                <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                  {new Date(a.detected_at).toLocaleString()}
                </TableCell>
                <TableCell>
                  <Badge variant="outline" className={cn('border-transparent', STATUS_CLASS[a.status])}>
                    {anomalyStatusLabel(t, a.status)}
                  </Badge>
                </TableCell>
                <TableCell onClick={(e) => e.stopPropagation()}>
                  <div className="flex gap-1">
                    <Button size="sm" variant="ghost" onClick={() => onOpen(a.id)}
                      aria-label={t('cm.protection.compare')} title={t('cm.protection.compare')}>
                      <Eye className="h-4 w-4" />
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => onHistory(a.asin)}
                      aria-label={t('cm.history.open')} title={t('cm.history.open')}>
                      <History className="h-4 w-4" />
                    </Button>
                  </div>
                </TableCell>
              </TableRow>
            )
          })}
        </TableBody>
      </Table>
    </div>
  )
}
