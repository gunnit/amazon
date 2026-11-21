import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ChevronDown, ChevronRight, Loader2 } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { cn } from '@/lib/utils'
import { catalogMonitorApi } from '@/services/api'
import type { TabProps } from '@/components/catalog/types'
import { changeTypeLabel, fieldLabel } from './changeLabels'
import { FieldCompare } from './FieldCompare'

interface Props extends Pick<TabProps, 'accountId' | 't'> {
  asin: string | null
  onClose: () => void
}

const when = (iso: string) => new Date(iso).toLocaleString()

/** Every content version seen for one ASIN, newest first, with what changed in each. */
export function HistoryDialog({ accountId, asin, onClose, t }: Props) {
  const [expanded, setExpanded] = useState<string | null>(null)

  const query = useQuery({
    queryKey: ['catalog-monitor', 'history', accountId, asin],
    queryFn: () => catalogMonitorApi.getHistory(accountId, asin as string),
    enabled: !!asin && !!accountId,
  })
  const versions = query.data ?? []

  return (
    <Dialog
      open={asin !== null}
      onOpenChange={(open) => {
        if (!open) {
          setExpanded(null)
          onClose()
        }
      }}
    >
      <DialogContent className="max-h-[90vh] max-w-4xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{t('cm.history.title')}</DialogTitle>
          <DialogDescription className="font-mono">{asin}</DialogDescription>
        </DialogHeader>

        {query.isLoading && <Loader2 className="mx-auto h-5 w-5 animate-spin" />}
        {query.isError && <p className="text-sm text-destructive">{t('cm.history.loadError')}</p>}
        {query.data && versions.length === 0 && (
          <p className="text-sm text-muted-foreground">{t('cm.history.empty')}</p>
        )}

        <ol className={cn('relative ml-2 space-y-5 pl-6', versions.length > 0 && 'border-l')}>
          {versions.map((version, index) => (
            <li key={version.id} className="relative">
              <span
                aria-hidden="true"
                className={cn(
                  'absolute -left-[31px] top-1 h-3 w-3 rounded-full border-2 border-background',
                  index === 0 ? 'bg-primary' : 'bg-muted-foreground/50',
                )}
              />
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-sm font-medium">
                  {t('cm.history.seenFrom', { date: when(version.first_seen_at) })}
                </span>
                {index === 0 && <Badge variant="secondary">{t('cm.history.current')}</Badge>}
              </div>
              <p className="text-xs text-muted-foreground">
                {t('cm.history.seenUntil', { date: when(version.last_seen_at) })}
              </p>
              {version.changes.length === 0 ? (
                <p className="mt-1 text-xs text-muted-foreground">
                  {index === versions.length - 1 ? t('cm.history.first') : t('cm.history.noChanges')}
                </p>
              ) : (
                <ul className="mt-2 space-y-1.5">
                  {version.changes.map((change) => {
                    const key = `${version.id}:${change.field}`
                    const open = expanded === key
                    const Icon = open ? ChevronDown : ChevronRight
                    return (
                      <li key={key} className="rounded-md border">
                        <button
                          type="button"
                          aria-expanded={open}
                          onClick={() => setExpanded(open ? null : key)}
                          className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-muted/60"
                        >
                          <Icon className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
                          <span className="font-medium">{fieldLabel(t, change.field)}</span>
                          <span className="text-xs text-muted-foreground">
                            {changeTypeLabel(t, change.change)}
                          </span>
                        </button>
                        {open && (
                          <div className="border-t p-3">
                            <FieldCompare
                              field={change.field}
                              before={change.baseline}
                              after={change.live}
                              beforeLabel={t('cm.history.before')}
                              afterLabel={t('cm.history.after')}
                              t={t}
                            />
                          </div>
                        )}
                      </li>
                    )
                  })}
                </ul>
              )}
            </li>
          ))}
        </ol>
      </DialogContent>
    </Dialog>
  )
}
