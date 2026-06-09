import { useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Loader2, Radar, RefreshCw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Alert, AlertDescription } from '@/components/ui/alert'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { useToast } from '@/components/ui/use-toast'
import { ReportTable, type ReportColumn } from '@/components/shared/ReportTable'
import { accountsApi, brandIntelligenceApi } from '@/services/api'
import { formatDate } from '@/lib/utils'
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

const STATUS_VARIANT: Record<BrandIntelligenceStatus, 'default' | 'secondary' | 'outline' | 'destructive'> = {
  completed: 'default',
  generating: 'secondary',
  pending: 'outline',
  failed: 'destructive',
}

function StatusBadge({ status }: { status: BrandIntelligenceStatus }) {
  const { t } = useTranslation()
  return (
    <Badge variant={STATUS_VARIANT[status]} className="shrink-0">
      {t(`brandIntelligence.status.${status}`)}
    </Badge>
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
            <div className="flex flex-wrap items-center gap-2">
              <StatusBadge status={row.status} />
              <span className="truncate text-sm font-medium">{row.week_label}</span>
            </div>
            <p className="mt-1 text-xs text-muted-foreground">{row.brand_label}</p>
          </div>
        ),
      },
      {
        id: 'period',
        header: t('brandIntelligence.col.period'),
        hideOnMobile: true,
        cardLabel: t('brandIntelligence.col.period'),
        cell: (row) => (
          <span className="text-xs text-muted-foreground">
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
          <span className="text-xs text-muted-foreground">
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
    <div className="space-y-6">
      <header className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
        <div className="flex items-start gap-4">
          <div className="hidden h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary md:flex">
            <Radar className="h-5 w-5" />
          </div>
          <div className="min-w-0">
            <h1 className="text-3xl font-bold tracking-tight">{t('brandIntelligence.title')}</h1>
            <p className="mt-1.5 max-w-3xl text-sm leading-6 text-muted-foreground">
              {t('brandIntelligence.subtitle')}
            </p>
          </div>
        </div>
      </header>

      <div className="flex flex-col gap-3 lg:flex-row lg:flex-wrap lg:items-center">
        <Select value={effectiveAccountId} onValueChange={setAccountId}>
          <SelectTrigger className="w-full sm:w-[220px]">
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

        <Select value={selectedReportId} onValueChange={setSelectedReportId}>
          <SelectTrigger className="w-full sm:w-[260px]">
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

        {effectiveAccountId ? <WeeklySubscribeToggle accountId={effectiveAccountId} /> : null}

        <Button
          className="lg:ml-auto"
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

      {readerState()}

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">{t('brandIntelligence.previousReports')}</CardTitle>
        </CardHeader>
        <CardContent>
          <ReportTable
            columns={historyColumns}
            rows={reports}
            rowKey={(r) => r.id}
            onRowOpen={(r) => setSelectedReportId(r.id)}
            rowOpenLabel={(r) => t('brandIntelligence.openRow', { week: r.week_label })}
            isRowSelected={(r) => r.id === selectedReportId}
            emptyState={
              <p className="py-6 text-center text-sm text-muted-foreground">
                {effectiveAccountId
                  ? t('brandIntelligence.noReports')
                  : t('brandIntelligence.noAccount')}
              </p>
            }
          />
        </CardContent>
      </Card>
    </div>
  )
}
