import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowRight, Check, HelpCircle, Loader2, Plus, RotateCcw, Unlink, type LucideIcon } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { cn } from '@/lib/utils'
import { catalogMonitorApi } from '@/services/api'
import { apiErrorDetail } from '@/lib/apiError'
import type {
  ChangeBatchResponse,
  VariationChildState,
  VariationFamily,
  VariationFamilyStatus,
} from '@/types'
import { AccountPicker } from '@/components/catalog/AccountPicker'
import type { TabProps } from '@/components/catalog/types'
import { isOpenRequest } from './changeLabels'
import { RestoreResult } from './RestoreResult'
import { ScanButton } from './ScanButton'

interface Props extends TabProps {
  onOpenApprovals: (batchId?: string | null) => void
}

const FAMILY_CLASS: Record<VariationFamilyStatus, string> = {
  ok: 'bg-green-100 text-green-800 dark:bg-green-900/50 dark:text-green-300',
  partial: 'bg-amber-100 text-amber-900 dark:bg-amber-900/50 dark:text-amber-300',
  broken: 'bg-red-100 text-red-800 dark:bg-red-900/50 dark:text-red-300',
}

const CHILD_STYLE: Record<VariationChildState, { icon: LucideIcon; className: string }> = {
  ok: {
    icon: Check,
    className: 'border-green-300 bg-green-50 text-green-800 dark:border-green-800 dark:bg-green-950/40 dark:text-green-300',
  },
  detached: {
    icon: Unlink,
    className: 'border-red-300 bg-red-50 text-red-800 dark:border-red-800 dark:bg-red-950/40 dark:text-red-300',
  },
  unexpected: {
    icon: Plus,
    className: 'border-amber-300 bg-amber-50 text-amber-900 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-300',
  },
  unknown: {
    icon: HelpCircle,
    className: 'border-slate-300 bg-slate-50 text-slate-600 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-400',
  },
}
const CHILD_STATES: VariationChildState[] = ['ok', 'detached', 'unexpected', 'unknown']

/**
 * Children to attach back to the parent: the detached ones, or every recorded child
 * when the whole family is broken (Amazon then reports no child as detached).
 */
function childrenToRestore(family: VariationFamily): string[] {
  if (family.status === 'broken') {
    return family.children.filter((c) => c.state !== 'unexpected').map((c) => c.asin)
  }
  return family.children.filter((c) => c.state === 'detached').map((c) => c.asin)
}

export function VariationsPanel(props: Props) {
  const { t, toast, accountId, onOpenApprovals } = props
  const queryClient = useQueryClient()
  const [result, setResult] = useState<ChangeBatchResponse | null>(null)

  useEffect(() => {
    setResult(null)
  }, [accountId])

  const query = useQuery({
    queryKey: ['catalog-monitor', 'variations', accountId],
    queryFn: () => catalogMonitorApi.listVariations(accountId),
    enabled: !!accountId,
  })
  const families = query.data ?? []
  const withProblems = families.filter((f) => f.status !== 'ok').length

  // Same query as Approvals: a family with a restore still in the queue is not restored twice.
  const changesQuery = useQuery({
    queryKey: ['catalog-monitor', 'changes', accountId],
    queryFn: () => catalogMonitorApi.listChanges(accountId),
    enabled: !!accountId,
  })
  const restoringParents = useMemo(
    () =>
      new Set(
        (changesQuery.data ?? [])
          .filter((r) => r.kind === 'variation_restore' && isOpenRequest(r))
          .map((r) => String(r.summary?.parent_asin ?? '')),
      ),
    [changesQuery.data],
  )

  const restore = useMutation({
    mutationFn: (family: VariationFamily) =>
      catalogMonitorApi.restoreVariation(accountId, family.parent_asin, childrenToRestore(family)),
    onSuccess: (res) => {
      setResult(res)
      for (const key of ['variations', 'changes', 'anomalies']) {
        void queryClient.invalidateQueries({ queryKey: ['catalog-monitor', key] })
      }
    },
    onError: (error) =>
      toast({
        title: t('cm.restore.error'),
        description: apiErrorDetail(error, t),
        variant: 'destructive',
      }),
  })

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <CardTitle>{t('cm.variations.title')}</CardTitle>
            <CardDescription>{t('cm.variations.description')}</CardDescription>
          </div>
          <ScanButton accountId={accountId} t={t} toast={toast} />
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="min-w-[220px] max-w-sm">
          <AccountPicker {...props} />
        </div>

        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-sm text-muted-foreground">
            {t('cm.variations.summary', { count: families.length, problems: withProblems })}
          </p>
          <ul className="flex flex-wrap gap-3 text-xs text-muted-foreground" aria-label={t('cm.variations.legend')}>
            {CHILD_STATES.map((state) => {
              const { icon: Icon, className } = CHILD_STYLE[state]
              return (
                <li key={state} className="inline-flex items-center gap-1">
                  <span className={cn('inline-flex h-4 w-4 items-center justify-center rounded border', className)}>
                    <Icon className="h-3 w-3" aria-hidden="true" />
                  </span>
                  {t(`cm.variations.child.${state}`)}
                </li>
              )
            })}
          </ul>
        </div>

        {result && (
          <RestoreResult
            result={result}
            onOpenApprovals={onOpenApprovals}
            onDismiss={() => setResult(null)}
            t={t}
          />
        )}

        {query.isLoading && <Loader2 className="mx-auto h-5 w-5 animate-spin" />}
        {query.isError && <p className="text-sm text-destructive">{t('cm.variations.loadError')}</p>}
        {query.data && families.length === 0 && (
          <p className="rounded-md border border-dashed p-6 text-center text-sm text-muted-foreground">
            {t('cm.variations.empty')}
          </p>
        )}

        <div className="grid gap-3 lg:grid-cols-2">
          {families.map((family) => {
            const toRestore = childrenToRestore(family)
            const restoring = restore.isPending && restore.variables?.parent_asin === family.parent_asin
            const inQueue = restoringParents.has(family.parent_asin)
            return (
              <section key={family.parent_asin} className="space-y-3 rounded-lg border p-4">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div>
                    <div className="text-xs text-muted-foreground">{t('cm.variations.parent')}</div>
                    <div className="font-mono text-sm font-medium">{family.parent_asin}</div>
                    <div className="text-xs text-muted-foreground">
                      {t('cm.variations.theme', { theme: family.variation_theme || '—' })}
                    </div>
                    {family.is_partial && (
                      <div className="text-xs text-muted-foreground">
                        {t('cm.variations.approvedChildrenOnly')}
                      </div>
                    )}
                  </div>
                  <Badge variant="outline" className={cn('border-transparent', FAMILY_CLASS[family.status])}>
                    {t(`cm.variations.status.${family.status}`)}
                  </Badge>
                </div>
                <ul className="flex flex-wrap gap-1.5" aria-label={t('cm.variations.children')}>
                  {family.children.map((child) => {
                    const { icon: Icon, className } = CHILD_STYLE[child.state]
                    const label = t(`cm.variations.child.${child.state}`)
                    return (
                      <li
                        key={child.asin}
                        title={label}
                        className={cn(
                          'inline-flex items-center gap-1 rounded-full border px-2 py-0.5 font-mono text-xs',
                          className,
                        )}
                      >
                        <Icon className="h-3 w-3" aria-hidden="true" />
                        {child.asin}
                        <span className="sr-only">: {label}</span>
                      </li>
                    )
                  })}
                  {family.children.length === 0 && (
                    <li className="text-xs text-muted-foreground">{t('cm.variations.noChildren')}</li>
                  )}
                </ul>
                {toRestore.length > 0 && (
                  <div className="flex flex-wrap items-center justify-between gap-2 border-t pt-3">
                    <span className="text-xs text-muted-foreground">
                      {inQueue
                        ? t('cm.variations.inQueue')
                        : t('cm.variations.toRestore', { count: toRestore.length })}
                    </span>
                    {inQueue && (
                      <Button size="sm" variant="ghost" onClick={() => onOpenApprovals()}>
                        {t('cm.restore.openApprovals')}
                        <ArrowRight className="ml-1.5 h-4 w-4" />
                      </Button>
                    )}
                    <Button
                      size="sm"
                      onClick={() => restore.mutate(family)}
                      disabled={restore.isPending || inQueue || changesQuery.isLoading}
                    >
                      {restoring ? (
                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      ) : (
                        <RotateCcw className="mr-2 h-4 w-4" />
                      )}
                      {t('cm.variations.restore')}
                    </Button>
                  </div>
                )}
              </section>
            )
          })}
        </div>
      </CardContent>
    </Card>
  )
}
