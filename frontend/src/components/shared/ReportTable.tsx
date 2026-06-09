import type { ReactNode } from 'react'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { cn } from '@/lib/utils'

export interface ReportColumn<T> {
  id: string
  header: ReactNode
  /** Cell content. */
  cell: (row: T) => ReactNode
  /** Right-align numeric / status columns. */
  align?: 'left' | 'right'
  /** Fixed width applied to the header + cells (e.g. '120px', '1.6fr' is not valid here — use px). */
  width?: string
  className?: string
  /** Hide the column below the md breakpoint; the value still renders in the stacked card meta row. */
  hideOnMobile?: boolean
  /** Short label used when this column collapses into the mobile card meta row. */
  cardLabel?: ReactNode
}

interface ReportTableProps<T> {
  columns: ReportColumn<T>[]
  rows: T[]
  rowKey: (row: T) => string
  /** Marks the navigation cell. Clicking it (or pressing Enter/Space) selects the row. */
  onRowOpen?: (row: T) => void
  /** Accessible label for the per-row open control, e.g. (row) => `Open ${row.name}`. */
  rowOpenLabel?: (row: T) => string
  /** Highlights the active row. */
  isRowSelected?: (row: T) => boolean
  /** Index of the column that acts as the navigation control. Defaults to 0. */
  primaryColumnIndex?: number
  /** Trailing action cell (download / delete …). Rendered as real siblings, never nested in the row control. */
  actions?: (row: T) => ReactNode
  actionsHeader?: ReactNode
  emptyState?: ReactNode
}

// A column-driven, single-component responsive table. The primary cell is the
// only navigation control (a real <button>); action buttons sit in their own
// cell as siblings — so no interactive element is ever nested inside another.
export function ReportTable<T>({
  columns,
  rows,
  rowKey,
  onRowOpen,
  rowOpenLabel,
  isRowSelected,
  primaryColumnIndex = 0,
  actions,
  actionsHeader,
  emptyState,
}: ReportTableProps<T>) {
  if (rows.length === 0 && emptyState) {
    return <>{emptyState}</>
  }

  const mobileMetaColumns = columns.filter(
    (column, index) => index !== primaryColumnIndex && column.hideOnMobile,
  )

  return (
    <>
      {/* Desktop / tablet table */}
      <div className="hidden md:block">
        <Table>
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              {columns.map((column) => (
                <TableHead
                  key={column.id}
                  style={column.width ? { width: column.width } : undefined}
                  className={cn(
                    'text-[11px] font-semibold uppercase tracking-wide',
                    column.align === 'right' && 'text-right',
                    column.className,
                  )}
                >
                  {column.header}
                </TableHead>
              ))}
              {actions ? (
                <TableHead className="w-[96px] text-right text-[11px] font-semibold uppercase tracking-wide">
                  {actionsHeader ?? <span className="sr-only">Actions</span>}
                </TableHead>
              ) : null}
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((row) => {
              const selected = isRowSelected?.(row) ?? false
              return (
                <TableRow
                  key={rowKey(row)}
                  data-state={selected ? 'selected' : undefined}
                  className={cn(selected && 'bg-primary/[0.04] hover:bg-primary/[0.06]')}
                >
                  {columns.map((column, index) => {
                    const isPrimary = index === primaryColumnIndex && !!onRowOpen
                    return (
                      <TableCell
                        key={column.id}
                        className={cn(
                          'py-3',
                          column.align === 'right' && 'text-right',
                          column.className,
                        )}
                      >
                        {isPrimary ? (
                          <button
                            type="button"
                            onClick={() => onRowOpen?.(row)}
                            aria-label={rowOpenLabel?.(row)}
                            aria-current={selected ? 'true' : undefined}
                            className="-mx-1 flex w-full items-center rounded px-1 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1"
                          >
                            {column.cell(row)}
                          </button>
                        ) : (
                          column.cell(row)
                        )}
                      </TableCell>
                    )
                  })}
                  {actions ? (
                    <TableCell className="py-3 text-right">
                      <div className="flex items-center justify-end gap-1">{actions(row)}</div>
                    </TableCell>
                  ) : null}
                </TableRow>
              )
            })}
          </TableBody>
        </Table>
      </div>

      {/* Mobile stacked cards — same data, no horizontal scroll */}
      <ul className="divide-y md:hidden">
        {rows.map((row) => {
          const selected = isRowSelected?.(row) ?? false
          const primary = columns[primaryColumnIndex]
          return (
            <li
              key={rowKey(row)}
              className={cn('flex items-stretch gap-1 pr-2', selected && 'bg-primary/[0.04]')}
            >
              <button
                type="button"
                onClick={() => onRowOpen?.(row)}
                aria-label={rowOpenLabel?.(row)}
                aria-current={selected ? 'true' : undefined}
                disabled={!onRowOpen}
                className="flex flex-1 flex-col gap-2 px-4 py-3 text-left transition-colors hover:bg-muted/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring disabled:cursor-default"
              >
                {primary?.cell(row)}
                {mobileMetaColumns.length ? (
                  <dl className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
                    {mobileMetaColumns.map((column) => (
                      <div key={column.id} className="flex items-center gap-1.5">
                        {column.cardLabel ? <dt className="font-medium">{column.cardLabel}</dt> : null}
                        <dd>{column.cell(row)}</dd>
                      </div>
                    ))}
                  </dl>
                ) : null}
              </button>
              {actions ? (
                <div className="flex shrink-0 items-center gap-1 py-2">{actions(row)}</div>
              ) : null}
            </li>
          )
        })}
      </ul>
    </>
  )
}
