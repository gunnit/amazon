import { useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Loader2, RefreshCw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Alert, AlertDescription } from '@/components/ui/alert'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { useToast } from '@/components/ui/use-toast'
import { ReportTable, type ReportColumn } from '@/components/shared/ReportTable'
import { SectionMark } from '@/components/shared/SectionMark'
import { accountsApi, brandIntelligenceApi } from '@/services/api'
import { cn, formatDate } from '@/lib/utils'
import { eyebrow, fieldInput, inkButton } from '@/lib/editorial'
import { useTranslation } from '@/i18n'
import type {
  BrandIntelligenceReportListItem,
  BrandIntelligenceStatus,
} from '@/types'
import { ReportReader } from '@/components/brand-intelligence/ReportReader'
import { ReportState } from '@/components/brand-intelligence/ReportState'
import { WeeklySubscribeToggle } from '@/components/brand-intelligence/WeeklySubscribeToggle'

const RUNNING: BrandIntelligenceStatus[] = ['pending', 'generating']
const LATEST = '__latest__'

const STATUS_TONE: Record<BrandIntelligenceStatus, { dot: string; text: string }> = {
  completed: { dot: 'bg-emerald-500', text: 'text-emerald-700 dark:text-emerald-400' },
  generating: { dot: 'bg-sky-500', text: 'text-sky-700 dark:text-sky-300' },
  pending: { dot: 'bg-muted-foreground/50', text: 'text-muted-foreground' },
  failed: { dot: 'bg-rose-500', text: 'text-rose-700 dark:text-rose-400' },
}

function StatusBadge({ status }: { status: BrandIntelligenceStatus }) {
  const { t } = useTranslation()
  const tone = STATUS_TONE[status]
  return (
    <span
      className={cn(
        'inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap font-mono text-[10px] font-medium uppercase tracking-[0.14em]',
        tone.text,
      )}
    >
      {RUNNING.includes(status) ? (
        <Loader2 className="h-3 w-3 animate-spin" />
      ) : (
        <span aria-hidden="true" className={cn('h-1.5 w-1.5 shrink-0 rounded-full', tone.dot)} />
      )}
      {t(`brandIntelligence.status.${status}`)}
    </span>
  )
}

export default function BrandIntelligence() {
  const { t } = useTranslation()
  const { toast } = useToast()
  const queryClient = useQueryClient()

  const [accountId, setAccountId] = useState('')
  // Which report is open: the latest report, or a specific report id from history.
  const [selectedReportId, setSelectedReportId] = useState<string>(LATEST)

  const { data: accounts } = useQuery({ queryKey: ['accounts'], queryFn: () => accountsApi.list() })
  const effectiveAccountId = accountId || accounts?.[0]?.id || ''

  // Reset the open report when the account changes.
  useEffect(() => {
    setSelectedReportId(LATEST)
  }, [effectiveAccountId])

  const reportsQuery = useQuery({
    queryKey: ['brand-intelligence-reports', effectiveAccountId],
    queryFn: () => brandIntelligenceApi.listReports({ account_id: effectiveAccountId, limit: 25 }),
    enabled: !!effectiveAccountId,
  })

  const latestQuery = useQuery({
    queryKey: ['brand-intelligence-latest', effectiveAccountId],
    queryFn: () => brandIntelligenceApi.getLatest(effectiveAccountId),
    enabled: !!effectiveAccountId && selectedReportId === LATEST,
    refetchInterval: (query) =>
      query.state.data && RUNNING.includes(query.state.data.status) ? 3000 : false,
  })

  const byIdQuery = useQuery({
    queryKey: ['brand-intelligence-report', selectedReportId],
    queryFn: () => brandIntelligenceApi.getReport(selectedReportId),
    enabled: !!effectiveAccountId && selectedReportId !== LATEST,
    refetchInterval: (query) =>
      query.state.data && RUNNING.includes(query.state.data.status) ? 3000 : false,
  })

  const report = selectedReportId === LATEST ? latestQuery.data : byIdQuery.data
  const reportLoading = selectedReportId === LATEST ? latestQuery.isLoading : byIdQuery.isLoading
  const isRunning = report ? RUNNING.includes(report.status) : false

  // One-shot toast when a polled report crosses into a terminal state.
  const notifiedRef = useRef<string | null>(null)
  useEffect(() => {
    if (!report) return
    if (report.status !== 'completed' && report.status !== 'failed') return
    const marker = `${report.id}:${report.status}`
    if (notifiedRef.current === marker) return
    notifiedRef.current = marker
    toast({
      variant: report.status === 'failed' ? 'destructive' : undefined,
      title:
        report.status === 'failed'
          ? t('brandIntelligence.toast.failed')
          : t('brandIntelligence.toast.ready'),
      description: report.brand_label,
    })
    // Refresh the history list when a new report lands.
    void queryClient.invalidateQueries({ queryKey: ['brand-intelligence-reports', effectiveAccountId] })
  }, [report?.id, report?.status, report?.brand_label, t, toast, queryClient, effectiveAccountId])

  const generateMutation = useMutation({
    mutationFn: () => brandIntelligenceApi.generate({ account_id: effectiveAccountId }),
    onSuccess: (job) => {
      // Open the new report; the by-id query starts polling and renders the
      // generating state until the pipeline completes.
      setSelectedReportId(job.id)
      void queryClient.invalidateQueries({ queryKey: ['brand-intelligence-report', job.id] })
      void queryClient.invalidateQueries({ queryKey: ['brand-intelligence-reports', effectiveAccountId] })
    },
    onError: () => {
      toast({ variant: 'destructive', description: t('brandIntelligence.toast.generateError') })
    },
  })

  const reports = reportsQuery.data ?? []

  const historyColumns: ReportColumn<BrandIntelligenceReportListItem>[] = useMemo(
    () => [
      {
        id: 'week',
        header: t('brandIntelligence.col.week'),
        width: '46%',
        cell: (row) => (
          <div className="min-w-0">
            <div className="flex flex-wrap items-baseline gap-x-2.5 gap-y-1">
              <span className="truncate text-sm font-semibold">{row.week_label}</span>
              <StatusBadge status={row.status} />
            </div>
            <p className="mt-1 font-mono text-[11px] text-muted-foreground">{row.brand_label}</p>
          </div>
        ),
      },
      {
        id: 'period',
        header: t('brandIntelligence.col.period'),
        hideOnMobile: true,
        cardLabel: t('brandIntelligence.col.period'),
        cell: (row) => (
          <span className="font-mono text-[11px] text-muted-foreground">
            {formatDate(row.period_start)} – {formatDate(row.period_end)}
          </span>
        ),
      },
      {
        id: 'generated',
        header: t('brandIntelligence.col.generated'),
        width: '140px',
        hideOnMobile: true,
        cardLabel: t('brandIntelligence.col.generated'),
        cell: (row) => (
          <span className="font-mono text-[11px] text-muted-foreground">
            {row.generated_at ? formatDate(row.generated_at) : '—'}
          </span>
        ),
      },
    ],
    [t],
  )

  const generateDisabled = !effectiveAccountId || generateMutation.isPending || isRunning

  function readerState() {
    if (!effectiveAccountId) {
      return (
        <Alert>
          <AlertDescription>{t('brandIntelligence.noAccount')}</AlertDescription>
        </Alert>
      )
    }
    if (reportLoading) return <ReportState variant="loading" />
    if (report?.status === 'failed') {
      return (
        <ReportState
          variant="failed"
          onGenerate={() => generateMutation.mutate()}
          generateDisabled={generateDisabled}
        />
      )
    }
    if (report && RUNNING.includes(report.status)) return <ReportState variant="generating" />
    if (report) return <ReportReader report={report} />
    return (
      <ReportState
        variant="empty"
        onGenerate={() => generateMutation.mutate()}
        generateDisabled={generateDisabled}
      />
    )
  }

  return (
    <div className="space-y-12 pb-4">
      {/* ─── Masthead ────────────────────────────────────────────────── */}
      <header className="ba-rise">
        <div aria-hidden="true" className="border-t-[3px] border-foreground" />
        <div aria-hidden="true" className="mt-[3px] border-t border-foreground/30" />
        <div className="flex flex-col gap-6 pt-6 md:flex-row md:items-end md:justify-between">
          <div className="min-w-0">
            <h1 className="text-3xl font-bold tracking-tight">{t('brandIntelligence.title')}</h1>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">
              {t('brandIntelligence.subtitle')}
            </p>
          </div>
          {report ? (
            <div className="shrink-0 text-left md:text-right">
              <p className="font-mono text-[11px] font-semibold uppercase tracking-[0.2em] text-foreground">
                {report.period.week_label}
              </p>
              <p className="mt-1 font-mono text-[11px] text-muted-foreground">
                {formatDate(report.period.start)} – {formatDate(report.period.end)}
              </p>
            </div>
          ) : null}
        </div>
      </header>

      {/* ─── Edition controls ─────────────────────────────────────────── */}
      <div className="ba-rise ba-rise-2 flex flex-col gap-5 border-b border-foreground/10 pb-6 lg:flex-row lg:items-end">
        <div className="w-full sm:w-[220px]">
          <p className={eyebrow}>{t('brandIntelligence.selectAccount')}</p>
          <Select value={effectiveAccountId} onValueChange={setAccountId}>
            <SelectTrigger className={cn(fieldInput, 'mt-1 h-10')}>
              <SelectValue placeholder={t('brandIntelligence.selectAccount')} />
            </SelectTrigger>
            <SelectContent>
              {accounts?.map((a) => (
                <SelectItem key={a.id} value={a.id}>
                  {a.account_name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="w-full sm:w-[260px]">
          <p className={eyebrow}>{t('brandIntelligence.selectWeek')}</p>
          <Select value={selectedReportId} onValueChange={setSelectedReportId}>
            <SelectTrigger className={cn(fieldInput, 'mt-1 h-10')}>
              <SelectValue placeholder={t('brandIntelligence.selectWeek')} />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={LATEST}>{t('brandIntelligence.latestWeek')}</SelectItem>
              {reports.map((r) => (
                <SelectItem key={r.id} value={r.id}>
                  {r.week_label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {effectiveAccountId ? <WeeklySubscribeToggle accountId={effectiveAccountId} /> : null}

        <Button
          className={cn(inkButton, 'lg:ml-auto')}
          onClick={() => generateMutation.mutate()}
          disabled={generateDisabled}
        >
          {generateMutation.isPending || isRunning ? (
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
          ) : (
            <RefreshCw className="mr-2 h-4 w-4" />
          )}
          {t('brandIntelligence.action.generate')}
        </Button>
      </div>

      {/* ─── The report ───────────────────────────────────────────────── */}
      <div className="ba-rise ba-rise-3">{readerState()}</div>

      {/* ─── Archive ──────────────────────────────────────────────────── */}
      <section className="ba-rise ba-rise-4">
        <SectionMark title={t('brandIntelligence.previousReports')} />
        <div className="mt-5">
          <ReportTable
            columns={historyColumns}
            rows={reports}
            rowKey={(r) => r.id}
            onRowOpen={(r) => setSelectedReportId(r.id)}
            rowOpenLabel={(r) => t('brandIntelligence.openRow', { week: r.week_label })}
            isRowSelected={(r) => r.id === selectedReportId}
            emptyState={
              <div className="flex flex-col items-center gap-2 rounded-sm border border-dashed border-foreground/25 px-6 py-12 text-center">
                <p className="max-w-md text-sm leading-6 text-muted-foreground">
                  {effectiveAccountId
                    ? t('brandIntelligence.noReports')
                    : t('brandIntelligence.noAccount')}
                </p>
              </div>
            }
          />
        </div>
      </section>
    </div>
  )
}
