import { cn } from '@/lib/utils'
import { CHANGE_REQUEST_STATUSES } from '@/types'
import type { ChangeRequest } from '@/types'
import type { TabProps } from '@/components/catalog/types'
import { matchesFilter, requestStatusLabel, type StatusFilter } from './changeLabels'

const FILTERS: StatusFilter[] = ['awaiting', 'all', ...CHANGE_REQUEST_STATUSES]

interface Props {
  requests: ChangeRequest[]
  value: StatusFilter
  onChange: (filter: StatusFilter) => void
  t: TabProps['t']
}

/** Status chips with counts; a status with no request is hidden unless it is the current one. */
export function StatusFilters({ requests, value, onChange, t }: Props) {
  const label = (f: StatusFilter) =>
    f === 'awaiting'
      ? t('cm.approvals.filter.awaiting')
      : f === 'all'
        ? t('cm.approvals.filter.all')
        : requestStatusLabel(t, f)
  return (
    <div className="flex flex-wrap gap-1.5" role="group" aria-label={t('cm.approvals.filterLabel')}>
      {FILTERS.map((f) => {
        const n = requests.filter((r) => matchesFilter(f, r.status)).length
        if (n === 0 && f !== 'awaiting' && f !== 'all' && f !== value) return null
        return (
          <button
            key={f}
            type="button"
            aria-pressed={value === f}
            onClick={() => onChange(f)}
            className={cn(
              'rounded-full border px-3 py-1 text-xs font-medium transition-colors hover:bg-muted',
              value === f && 'border-primary bg-primary text-primary-foreground hover:bg-primary/90',
            )}
          >
            {label(f)} · {n}
          </button>
        )
      })}
    </div>
  )
}
