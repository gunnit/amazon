import { useEffect, useMemo, useState } from 'react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { ChevronLeft, ChevronRight, Download, ImageOff, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { cn } from '@/lib/utils'
import { catalogMonitorApi } from '@/services/api'
import { apiErrorDetail } from '@/lib/apiError'
import { QUALITY_RULE_KEYS, QUALITY_STATES } from '@/types'
import type { QualityItem, QualityRuleKey, QualityRuleResult, QualityState } from '@/types'
import { AccountPicker } from '@/components/catalog/AccountPicker'
import type { TabProps } from '@/components/catalog/types'
import { AccessCheck } from './AccessCheck'
import { ScanButton } from './ScanButton'
import { QualityDetailDialog } from './QualityDetailDialog'
import { STATE_STYLE } from './stateStyle'
import { TrafficLight } from './TrafficLight'
import { resultTooltip, ruleLabel, stateLabel } from './describe'

const PAGE_SIZE = 50
const ALL = '__all__'
// widths of the two sticky columns; the second one sticks right after the first
const PRODUCT_COL = 'w-[300px] min-w-[300px] max-w-[300px]'
const OVERALL_COL = 'w-[92px] min-w-[92px] max-w-[92px]'
const OVERALL_LEFT = 'left-[300px]'
const STICKY_BG = 'bg-background group-hover:bg-muted'

function Thumbnail({ url, alt }: { url?: string | null; alt: string }) {
  const [failed, setFailed] = useState(false)
  if (!url || failed) {
    return (
      <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded border bg-muted text-muted-foreground">
        <ImageOff className="h-4 w-4" aria-hidden="true" />
      </span>
    )
  }
  return (
    <img
      src={url}
      alt={alt}
      loading="lazy"
      referrerPolicy="no-referrer"
      onError={() => setFailed(true)}
      className="h-10 w-10 shrink-0 rounded border bg-white object-contain"
    />
  )
}

/** Tiny stacked bar: how many ASINs are green / yellow / red / grey for one rule. */
function RuleBar({
  counts,
  t,
}: {
  counts: Partial<Record<QualityState, number>>
  t: TabProps['t']
}) {
  const total = QUALITY_STATES.reduce((n, s) => n + (counts[s] ?? 0), 0)
  if (total === 0) return null
  const summary = QUALITY_STATES.filter((s) => counts[s])
    .map((s) => `${stateLabel(t, s)}: ${counts[s]}`)
    .join(' · ')
  return (
    <span
      role="img"
      aria-label={summary}
      title={summary}
      className="mt-1 flex h-1.5 w-12 overflow-hidden rounded-full bg-muted"
    >
      {(['green', 'yellow', 'red', 'grey'] as const).map((s) =>
        counts[s] ? (
          <span
            key={s}
            className={STATE_STYLE[s].bar}
            style={{ width: `${((counts[s] ?? 0) / total) * 100}%` }}
          />
        ) : null,
      )}
    </span>
  )
}

export function QualityPanel(props: TabProps) {
  const { t, toast, accountId } = props
  const [state, setState] = useState<QualityState | ''>('')
  const [rule, setRule] = useState<QualityRuleKey | ''>('')
  const [mandatoryOnly, setMandatoryOnly] = useState(false)
  const [searchInput, setSearchInput] = useState('')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [selectedAsin, setSelectedAsin] = useState<string | null>(null)
  const [exporting, setExporting] = useState(false)

  // debounce the search box so typing does not fire one request per key
  useEffect(() => {
    const id = window.setTimeout(() => setSearch(searchInput.trim()), 300)
    return () => window.clearTimeout(id)
  }, [searchInput])

  useEffect(() => {
    setPage(1)
  }, [accountId, state, rule, mandatoryOnly, search])

  const query = useQuery({
    queryKey: ['catalog-monitor', 'quality', accountId, state, rule, mandatoryOnly, search, page],
    queryFn: () =>
      catalogMonitorApi.getQuality(accountId, {
        state: state || undefined,
        rule: rule || undefined,
        mandatory_only: mandatoryOnly || undefined,
        search: search || undefined,
        page,
        page_size: PAGE_SIZE,
      }),
    enabled: !!accountId,
    placeholderData: keepPreviousData,
  })

  const data = query.data
  const items = useMemo(() => data?.items ?? [], [data])
  const perRule = useMemo(() => data?.summary.per_rule ?? {}, [data])
  const totalPages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1

  // One column per rule that produced results (the enabled ones).
  const columns = useMemo(
    () => QUALITY_RULE_KEYS.filter((k) => k in perRule),
    [perRule],
  )
  const mandatoryKeys = useMemo(() => {
    const keys = new Set<string>()
    for (const item of items) for (const r of item.results) if (r.mandatory) keys.add(r.key)
    return keys
  }, [items])

  const toggleState = (s: QualityState) => setState((cur) => (cur === s ? '' : s))

  const handleExport = async () => {
    setExporting(true)
    try {
      const blob = await catalogMonitorApi.exportQuality(accountId)
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = `listing-quality-${new Date().toISOString().slice(0, 10)}.xlsx`
      document.body.appendChild(anchor)
      anchor.click()
      document.body.removeChild(anchor)
      URL.revokeObjectURL(url)
    } catch (error) {
      toast({
        title: t('cm.quality.exportError'),
        description: apiErrorDetail(error, t),
        variant: 'destructive',
      })
    } finally {
      setExporting(false)
    }
  }

  const cellFor = (item: QualityItem, key: QualityRuleKey) => {
    const result: QualityRuleResult | undefined = item.results.find((r) => r.key === key)
    if (!result) return <span className="text-muted-foreground">—</span>
    return (
      <TrafficLight
        state={result.state}
        label={`${ruleLabel(t, key)}: ${stateLabel(t, result.state)}`}
        title={`${ruleLabel(t, key)}: ${resultTooltip(t, result)}`}
      />
    )
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <CardTitle>{t('cm.quality.title')}</CardTitle>
            <CardDescription>{t('cm.quality.description')}</CardDescription>
          </div>
          <div className="flex flex-col items-end gap-1">
            <ScanButton accountId={accountId} t={t} toast={toast} />
            <span className="text-xs text-muted-foreground">
              {t('cm.scan.last')}:{' '}
              {data?.last_scan_at ? new Date(data.last_scan_at).toLocaleString() : t('cm.scan.never')}
            </span>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap items-end gap-3">
          <div className="min-w-[220px]">
            <AccountPicker {...props} />
          </div>
          <AccessCheck accountId={accountId} t={t} toast={toast} />
        </div>

        {/* Summary strip: four counts, click to filter */}
        <div
          className="grid grid-cols-2 gap-2 md:grid-cols-4"
          role="group"
          aria-label={t('cm.quality.summary')}
        >
          {QUALITY_STATES.map((s) => {
            const style = STATE_STYLE[s]
            const active = state === s
            return (
              <button
                key={s}
                type="button"
                aria-pressed={active}
                onClick={() => toggleState(s)}
                className={cn(
                  'flex items-center gap-3 rounded-lg border p-3 text-left transition-colors hover:bg-muted/60',
                  active && 'border-primary ring-2 ring-primary/30 bg-muted/60',
                )}
              >
                <TrafficLight state={s} label={stateLabel(t, s)} size="lg" />
                <span className="min-w-0">
                  <span className={cn('block text-2xl font-bold leading-none', style.text)}>
                    {data ? data.summary[s] : '—'}
                  </span>
                  <span className="mt-1 block text-xs text-muted-foreground">
                    {stateLabel(t, s)}
                  </span>
                </span>
              </button>
            )
          })}
        </div>
        {data && data.unscanned > 0 && (
          <p className="text-xs text-muted-foreground">
            {t('cm.quality.unscanned', { count: data.unscanned })}
          </p>
        )}

        {/* Filters */}
        <div className="flex flex-wrap items-end gap-3">
          <div className="min-w-[220px] flex-1">
            <Label htmlFor="cm-quality-search">{t('cm.quality.search')}</Label>
            <Input
              id="cm-quality-search"
              placeholder={t('cm.quality.searchPlaceholder')}
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
            />
          </div>
          <div className="min-w-[180px]">
            <Label>{t('cm.quality.filterState')}</Label>
            <Select
              value={state || ALL}
              onValueChange={(v) => setState(v === ALL ? '' : (v as QualityState))}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={ALL}>{t('cm.quality.allStates')}</SelectItem>
                {QUALITY_STATES.map((s) => (
                  <SelectItem key={s} value={s}>
                    {stateLabel(t, s)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="min-w-[180px]">
            <Label>{t('cm.quality.filterRule')}</Label>
            <Select
              value={rule || ALL}
              onValueChange={(v) => setRule(v === ALL ? '' : (v as QualityRuleKey))}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={ALL}>{t('cm.quality.allRules')}</SelectItem>
                {QUALITY_RULE_KEYS.map((k) => (
                  <SelectItem key={k} value={k}>
                    {ruleLabel(t, k)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="flex items-center gap-2 pb-2">
            <Checkbox
              id="cm-mandatory-only"
              checked={mandatoryOnly}
              onCheckedChange={(v) => setMandatoryOnly(v === true)}
            />
            <Label htmlFor="cm-mandatory-only" className="cursor-pointer">
              {t('cm.quality.mandatoryOnly')}
            </Label>
          </div>
          <Button
            variant="outline"
            onClick={handleExport}
            disabled={!accountId || exporting || !data || data.total === 0}
          >
            {exporting ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Download className="mr-2 h-4 w-4" />
            )}
            {t('export.button')}
          </Button>
        </div>
        {state && rule && (
          <p className="text-xs text-muted-foreground">
            {t('cm.quality.ruleStateHint', {
              rule: ruleLabel(t, rule),
              state: stateLabel(t, state),
            })}
          </p>
        )}

        {/* Matrix */}
        <div className="rounded-md border">
          <Table className="border-separate border-spacing-0">
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead
                  className={cn('sticky left-0 z-20 bg-background align-bottom', PRODUCT_COL)}
                >
                  {t('cm.quality.col.product')}
                </TableHead>
                <TableHead
                  className={cn(
                    'sticky z-20 bg-background text-center align-bottom',
                    OVERALL_LEFT,
                    OVERALL_COL,
                  )}
                >
                  {t('cm.quality.col.overall')}
                </TableHead>
                {columns.map((k) => (
                  <TableHead
                    key={k}
                    title={ruleLabel(t, k)}
                    className="h-auto min-w-[84px] px-2 py-2 text-center align-bottom"
                  >
                    <span className="flex flex-col items-center">
                      <span className="whitespace-nowrap text-xs font-medium">
                        {t(`cm.ruleShort.${k}`)}
                      </span>
                      {mandatoryKeys.has(k) && (
                        <span className="mt-0.5 rounded bg-primary/10 px-1 text-[10px] font-semibold uppercase tracking-wide text-primary">
                          {t('cm.tag.mandatory')}
                        </span>
                      )}
                      <RuleBar counts={perRule[k] ?? {}} t={t} />
                    </span>
                  </TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {query.isLoading && (
                <TableRow>
                  <TableCell colSpan={2 + Math.max(columns.length, 1)} className="py-8 text-center">
                    <Loader2 className="mx-auto h-5 w-5 animate-spin" />
                  </TableCell>
                </TableRow>
              )}
              {query.isError && (
                <TableRow>
                  <TableCell
                    colSpan={2 + Math.max(columns.length, 1)}
                    className="py-8 text-center text-destructive"
                  >
                    {t('cm.quality.loadError')}
                  </TableCell>
                </TableRow>
              )}
              {data && items.length === 0 && (
                <TableRow>
                  <TableCell
                    colSpan={2 + Math.max(columns.length, 1)}
                    className="py-8 text-center text-muted-foreground"
                  >
                    {data.unscanned > 0 && data.total === 0 && !state && !rule && !search
                      ? t('cm.quality.emptyUnscanned')
                      : t('cm.quality.empty')}
                  </TableCell>
                </TableRow>
              )}
              {items.map((item) => (
                <TableRow
                  key={item.asin}
                  className="group cursor-pointer"
                  tabIndex={0}
                  onClick={() => setSelectedAsin(item.asin)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault()
                      setSelectedAsin(item.asin)
                    }
                  }}
                >
                  <TableCell className={cn('sticky left-0 z-10 py-2', PRODUCT_COL, STICKY_BG)}>
                    <div className="flex items-center gap-2">
                      <Thumbnail url={item.main_image_url} alt={item.title ?? item.asin} />
                      <div className="min-w-0">
                        <div className="font-mono text-xs">{item.asin}</div>
                        <div
                          className="truncate text-xs text-muted-foreground"
                          title={item.title ?? undefined}
                        >
                          {item.title || t('catalog.products.titleMissing')}
                        </div>
                      </div>
                    </div>
                  </TableCell>
                  <TableCell
                    className={cn('sticky z-10 py-2', OVERALL_LEFT, OVERALL_COL, STICKY_BG)}
                  >
                    <div className="flex items-center justify-center gap-1.5">
                      <TrafficLight
                        state={item.state}
                        label={`${t('cm.quality.col.overall')}: ${stateLabel(t, item.state)}`}
                      />
                      <span className="text-xs font-semibold tabular-nums">{item.score}</span>
                    </div>
                  </TableCell>
                  {columns.map((k) => (
                    <TableCell key={k} className="px-2 py-2 text-center">
                      {cellFor(item, k)}
                    </TableCell>
                  ))}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>

        {data && data.total > 0 && (
          <div className="flex items-center justify-between">
            <span className="text-xs text-muted-foreground">
              {t('cm.quality.shown', { shown: items.length, total: data.total })}
            </span>
            {totalPages > 1 && (
              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  aria-label={t('cm.quality.prevPage')}
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={page <= 1}
                >
                  <ChevronLeft className="h-4 w-4" />
                </Button>
                <span className="text-xs text-muted-foreground">
                  {page} / {totalPages}
                </span>
                <Button
                  variant="outline"
                  size="sm"
                  aria-label={t('cm.quality.nextPage')}
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                  disabled={page >= totalPages}
                >
                  <ChevronRight className="h-4 w-4" />
                </Button>
              </div>
            )}
          </div>
        )}

        <QualityDetailDialog
          accountId={accountId}
          asin={selectedAsin}
          onClose={() => setSelectedAsin(null)}
          t={t}
          toast={toast}
        />
      </CardContent>
    </Card>
  )
}
