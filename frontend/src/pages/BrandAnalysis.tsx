import { useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertCircle,
  AlertTriangle,
  CheckCircle2,
  Download,
  FileSpreadsheet,
  Info,
  Loader2,
  Play,
  RefreshCw,
  Trash2,
  Upload,
  X,
} from 'lucide-react'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Progress } from '@/components/ui/progress'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useToast } from '@/components/ui/use-toast'
import { cn, formatDate } from '@/lib/utils'
import { eyebrow, fieldInput, ghostButton, inkButton, monoTag, tabTrigger } from '@/lib/editorial'
import { useTranslation } from '@/i18n'
import { ReportTable, type ReportColumn } from '@/components/shared/ReportTable'
import { SectionMark } from '@/components/shared/SectionMark'
import { BrandOverviewCharts } from '@/components/brand-analysis/BrandOverviewCharts'
import { accountsApi, brandAnalysisApi } from '@/services/api'
import type {
  AmazonAccount,
  BrandAnalysisJob,
  BrandAnalysisListItem,
  BrandAnalysisMode,
  BrandAnalysisStatus,
} from '@/types'

type DataSource = 'internal' | 'manual'
type ReadinessState = 'ready' | 'warning' | 'missing' | 'unknown'

const runningStatuses: BrandAnalysisStatus[] = [
  'pending',
  'capability_checking',
  'preflight_checking',
  'internal_sync_requested',
  'syncing_internal_data',
  'internal_sync_completed',
  'internal_sync_failed',
  'collecting_source_data',
  'enriching_catalog',
  'generating_metrics',
  'generating_narrative',
  'analyzing',
  'generating_pptx',
  'configuring_market',
  'waiting_for_ready',
  'exporting_2025',
  'exporting_2024',
  'cancelling',
]

type StatusGroup =
  | 'preparing'
  | 'analyzing'
  | 'generatingDeck'
  | 'completed'
  | 'completed_with_limitations'
  | 'needs_upload'
  | 'failed'
  | 'cancelling'
  | 'cancelled'

const statusGroupOf: Record<BrandAnalysisStatus, StatusGroup> = {
  pending: 'preparing',
  capability_checking: 'preparing',
  preflight_checking: 'preparing',
  internal_sync_requested: 'preparing',
  syncing_internal_data: 'preparing',
  internal_sync_completed: 'preparing',
  collecting_source_data: 'preparing',
  configuring_market: 'preparing',
  waiting_for_ready: 'preparing',
  enriching_catalog: 'analyzing',
  generating_metrics: 'analyzing',
  generating_narrative: 'generatingDeck',
  analyzing: 'generatingDeck',
  generating_pptx: 'generatingDeck',
  exporting_2024: 'generatingDeck',
  exporting_2025: 'generatingDeck',
  completed: 'completed',
  completed_with_limitations: 'completed_with_limitations',
  waiting_for_user_action: 'needs_upload',
  cancelling: 'cancelling',
  cancelled: 'cancelled',
  internal_sync_failed: 'failed',
  failed: 'failed',
}

const statusGroupLabelKey: Record<StatusGroup, string> = {
  preparing: 'brandAnalysis.statusGroup.preparing',
  analyzing: 'brandAnalysis.status.analyzing',
  generatingDeck: 'brandAnalysis.statusGroup.generatingDeck',
  completed: 'brandAnalysis.status.completed',
  completed_with_limitations: 'brandAnalysis.status.completed_with_limitations',
  needs_upload: 'brandAnalysis.status.waiting_for_user_action',
  failed: 'brandAnalysis.status.failed',
  cancelling: 'brandAnalysis.status.cancelling',
  cancelled: 'brandAnalysis.status.cancelled',
}

const statusGroupTone: Record<StatusGroup, { dot: string; text: string }> = {
  preparing: { dot: 'bg-sky-500', text: 'text-sky-700 dark:text-sky-300' },
  analyzing: { dot: 'bg-sky-500', text: 'text-sky-700 dark:text-sky-300' },
  generatingDeck: { dot: 'bg-sky-500', text: 'text-sky-700 dark:text-sky-300' },
  completed: { dot: 'bg-emerald-500', text: 'text-emerald-700 dark:text-emerald-400' },
  completed_with_limitations: { dot: 'bg-amber-500', text: 'text-amber-700 dark:text-amber-400' },
  needs_upload: { dot: 'bg-amber-500', text: 'text-amber-700 dark:text-amber-400' },
  failed: { dot: 'bg-rose-500', text: 'text-rose-700 dark:text-rose-400' },
  cancelling: { dot: 'bg-muted-foreground', text: 'text-muted-foreground' },
  cancelled: { dot: 'bg-muted-foreground/50', text: 'text-muted-foreground' },
}

const progressSteps = [
  { key: 'capability', labelKey: 'brandAnalysis.status.capability_checking', pct: 8 },
  { key: 'preflight', labelKey: 'brandAnalysis.status.preflight_checking', pct: 14 },
  { key: 'resolving', labelKey: 'brandAnalysis.progress.resolving', pct: 20 },
  { key: 'yearly', labelKey: 'brandAnalysis.progress.yearly', pct: 40 },
  { key: 'catalog', labelKey: 'brandAnalysis.progress.catalog', pct: 55 },
  { key: 'metrics', labelKey: 'brandAnalysis.progress.metrics', pct: 70 },
  { key: 'narrative', labelKey: 'brandAnalysis.progress.narrative', pct: 82 },
  { key: 'pptx', labelKey: 'brandAnalysis.progress.pptx', pct: 90 },
  { key: 'completed', labelKey: 'brandAnalysis.progress.completed', pct: 100 },
]

function modeToDataSource(mode: BrandAnalysisMode | undefined): DataSource {
  if (!mode) return 'internal'
  if (mode === 'manual') return 'manual'
  if (mode === 'helium10' || mode === 'helium10_api') return 'manual'
  return 'internal'
}

function parseAsins(value: string): string[] {
  return value
    .split(/[\s,;]+/)
    .map((asin) => asin.trim().toUpperCase())
    .filter(Boolean)
}

function getErrorMessage(error: unknown): string {
  if (typeof error === 'object' && error && 'response' in error) {
    const response = (error as { response?: { data?: { detail?: string } } }).response
    if (response?.data?.detail) return response.data.detail
  }
  if (error instanceof Error) return error.message
  return 'The request failed.'
}

function formatCurrency(value: unknown): string {
  return typeof value === 'number'
    ? `€${value.toLocaleString(undefined, { maximumFractionDigits: 0 })}`
    : '—'
}

function formatNumber(value: unknown, digits = 0): string {
  return typeof value === 'number'
    ? value.toLocaleString(undefined, { maximumFractionDigits: digits })
    : '—'
}

function formatPercent(value: unknown): string {
  return typeof value === 'number' ? `${value > 0 ? '+' : ''}${value.toFixed(1)}%` : '—'
}

function formatShare(value: unknown): string {
  return typeof value === 'number' ? `${value.toFixed(1)}%` : '—'
}

function signTone(value: unknown): 'pos' | 'neg' | undefined {
  if (typeof value !== 'number') return undefined
  if (value > 0) return 'pos'
  if (value < 0) return 'neg'
  return undefined
}

function metric(job: BrandAnalysisJob | undefined, key: string): unknown {
  return job?.metrics?.[key]
}

function objectMetric(job: BrandAnalysisJob | undefined, key: string): Record<string, any> {
  const value = metric(job, key)
  return typeof value === 'object' && value !== null ? (value as Record<string, any>) : {}
}

function downloadBlob(blob: Blob, filename: string) {
  const url = window.URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  window.URL.revokeObjectURL(url)
}

const stateDot: Record<ReadinessState, string> = {
  ready: 'bg-emerald-500',
  warning: 'bg-amber-500',
  missing: 'bg-rose-500',
  unknown: 'bg-muted-foreground/40',
}

function StatusPill({ status, label }: { status: BrandAnalysisStatus; label: string }) {
  const tone = statusGroupTone[statusGroupOf[status]]
  const isRunning = runningStatuses.includes(status)
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 whitespace-nowrap font-mono text-[10px] font-medium uppercase tracking-[0.14em]',
        tone.text,
      )}
    >
      {isRunning ? (
        <Loader2 className="h-3 w-3 animate-spin" />
      ) : (
        <span aria-hidden="true" className={cn('h-1.5 w-1.5 shrink-0 rounded-full', tone.dot)} />
      )}
      {label}
    </span>
  )
}

// Terminal runs get a rubber-stamp mark in the job header; anything still
// moving falls back to the quiet status pill.
function StatusStamp({ status, label }: { status: BrandAnalysisStatus; label: string }) {
  const stampTone: Partial<Record<StatusGroup, string>> = {
    completed: 'border-emerald-600/70 text-emerald-700 dark:border-emerald-400/70 dark:text-emerald-400',
    completed_with_limitations:
      'border-amber-600/70 text-amber-700 dark:border-amber-400/70 dark:text-amber-400',
    needs_upload: 'border-amber-600/70 text-amber-700 dark:border-amber-400/70 dark:text-amber-400',
    failed: 'border-rose-600/70 text-rose-700 dark:border-rose-400/70 dark:text-rose-400',
    cancelled: 'border-foreground/30 text-muted-foreground',
  }
  const tone = runningStatuses.includes(status) ? undefined : stampTone[statusGroupOf[status]]
  if (!tone) return <StatusPill status={status} label={label} />
  return (
    <span
      className={cn(
        'inline-block -rotate-2 rounded-sm border-2 px-2 py-0.5 font-mono text-[10px] font-bold uppercase tracking-[0.22em]',
        tone,
      )}
    >
      {label}
    </span>
  )
}

// Color encodes the value, not the label: positive=emerald, negative=rose,
// otherwise the plain foreground. Most tiles render neutral.
function valueClass(valueTone?: 'pos' | 'neg'): string {
  if (valueTone === 'pos') return 'text-emerald-600 dark:text-emerald-400'
  if (valueTone === 'neg') return 'text-rose-600 dark:text-rose-400'
  return 'text-foreground'
}

function KpiTile({
  label,
  value,
  hint,
  valueTone,
}: {
  label: string
  value: string
  hint?: string
  valueTone?: 'pos' | 'neg'
}) {
  return (
    <div className="border-t-2 border-foreground/80 pt-2.5">
      <p className={eyebrow}>{label}</p>
      <p
        className={cn(
          'mt-2 font-mono text-2xl font-semibold leading-none tracking-tight tabular-nums',
          valueClass(valueTone),
        )}
      >
        {value}
      </p>
      {hint ? <p className="mt-1.5 text-xs text-muted-foreground">{hint}</p> : null}
    </div>
  )
}


export default function BrandAnalysis() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const { toast } = useToast()

  const [brandName, setBrandName] = useState('')
  const [selectedAccount, setSelectedAccount] = useState<string>('none')
  const [language, setLanguage] = useState<'en' | 'it'>('en')
  const [dataSource, setDataSource] = useState<DataSource>('internal')
  const [marketType, setMarketType] = useState<'brand' | 'asin'>('brand')
  const [asinText, setAsinText] = useState('')
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null)
  const [file2024, setFile2024] = useState<File | null>(null)
  const [file2025, setFile2025] = useState<File | null>(null)
  const [showAdvancedUpload, setShowAdvancedUpload] = useState(false)
  const [activeTab, setActiveTab] = useState<'overview' | 'data' | 'files'>('overview')

  const { data: accounts } = useQuery<AmazonAccount[]>({
    queryKey: ['accounts'],
    queryFn: () => accountsApi.list(),
  })

  useEffect(() => {
    if (!accounts) return
    if (accounts.length === 0) {
      setDataSource((prev) => (prev === 'internal' ? 'manual' : prev))
    } else if (selectedAccount === 'none') {
      setSelectedAccount(accounts[0].id)
    }
  }, [accounts, selectedAccount])

  const selectedAccountObj = useMemo(
    () => accounts?.find((account) => account.id === selectedAccount) || null,
    [accounts, selectedAccount],
  )

  const jobsQuery = useQuery<BrandAnalysisListItem[]>({
    queryKey: ['brand-analysis'],
    queryFn: () => brandAnalysisApi.list(),
  })

  const selectedJobQuery = useQuery<BrandAnalysisJob>({
    queryKey: ['brand-analysis', selectedJobId],
    queryFn: () => brandAnalysisApi.get(selectedJobId!),
    enabled: !!selectedJobId,
    refetchInterval: (query) => {
      const status = query.state.data?.status
      return status && runningStatuses.includes(status) ? 3000 : false
    },
  })

  const selectedJob = selectedJobQuery.data

  // Fire a one-shot toast when the polled job crosses into a terminal state.
  const notifiedRef = useRef<string | null>(null)
  useEffect(() => {
    if (!selectedJob) return
    const terminal: Record<string, { titleKey: string; variant?: 'destructive' }> = {
      completed: { titleKey: 'brandAnalysis.toast.completed' },
      completed_with_limitations: { titleKey: 'brandAnalysis.toast.completedWithLimitations' },
      failed: { titleKey: 'brandAnalysis.toast.failed', variant: 'destructive' },
      cancelled: { titleKey: 'brandAnalysis.toast.cancelled' },
    }
    const outcome = terminal[selectedJob.status]
    if (!outcome) return
    const marker = `${selectedJob.id}:${selectedJob.status}`
    if (notifiedRef.current === marker) return
    notifiedRef.current = marker
    toast({
      variant: outcome.variant,
      title: t(outcome.titleKey),
      description:
        selectedJob.status === 'completed_with_limitations'
          ? `${selectedJob.brand_name} — ${t('brandAnalysis.toast.completedWithLimitationsBody')}`
          : selectedJob.brand_name,
    })
  }, [selectedJob?.id, selectedJob?.status, selectedJob?.brand_name, t, toast])

  const selectedJobFromList = jobsQuery.data?.find((job) => job.id === selectedJobId)
  const selectedJobDataSource = modeToDataSource(selectedJob?.mode)
  const sourceYears = new Set(selectedJob?.source_files.map((file) => file.year) || [])
  const hasBothManualFiles = sourceYears.has(2024) && sourceYears.has(2025)
  const isRunning = selectedJob ? runningStatuses.includes(selectedJob.status) : false
  const isWaitingForUser = selectedJob?.status === 'waiting_for_user_action'
  const canStart = !!selectedJob && (selectedJobDataSource === 'internal' || hasBothManualFiles)
  const asinList = useMemo(() => parseAsins(asinText), [asinText])
  const currentStatus: BrandAnalysisStatus =
    selectedJob?.status || selectedJobFromList?.status || 'pending'

  const readiness = objectMetric(selectedJob, 'data_readiness')
  const coverage = (selectedJob?.data_coverage || objectMetric(selectedJob, 'data_coverage')) as Record<string, any>
  const capabilityMatrix = (selectedJob?.capability_matrix || objectMetric(selectedJob, 'capability_matrix')) as Record<string, any>
  const limitations = (selectedJob?.limitations || objectMetric(selectedJob, 'limitations')) as Record<string, any>
  const completeness = objectMetric(selectedJob, 'data_completeness')
  const marketAnalysis = objectMetric(selectedJob, 'market_analysis')
  const contentHealth = objectMetric(selectedJob, 'content_health')
  const sellerSummary = objectMetric(selectedJob, 'seller_buy_box_summary')

  const errorCodeKey = selectedJob?.error_code ? `brandAnalysis.errorCode.${selectedJob.error_code}` : null
  const errorCodeTranslated = errorCodeKey ? t(errorCodeKey) : null
  const errorCodeMessage =
    errorCodeTranslated && errorCodeTranslated !== errorCodeKey ? errorCodeTranslated : null

  const validateForm = (): string | null => {
    if (!brandName.trim()) return t('brandAnalysis.field.brandName')
    if (marketType === 'asin' && asinList.length === 0) return t('brandAnalysis.error.asinListRequired')
    if (dataSource === 'internal' && selectedAccount === 'none') {
      return t('brandAnalysis.error.connectedAccountRequired')
    }
    return null
  }

  const createMutation = useMutation({
    mutationFn: () =>
      brandAnalysisApi.create({
        brand_name: brandName.trim(),
        account_id: selectedAccount === 'none' ? undefined : selectedAccount,
        language,
        mode: dataSource,
        market_type: marketType,
        market_query: brandName.trim(),
        asin_list: marketType === 'asin' ? asinList : undefined,
      }),
    onSuccess: (job) => {
      setSelectedJobId(job.id)
      queryClient.invalidateQueries({ queryKey: ['brand-analysis'] })
    },
    onError: (error) => {
      toast({
        variant: 'destructive',
        title: t('brandAnalysis.error.createFailed'),
        description: getErrorMessage(error),
      })
    },
  })

  const uploadMutation = useMutation({
    mutationFn: ({ year, file }: { year: 2024 | 2025; file: File }) =>
      brandAnalysisApi.upload(selectedJobId!, year, file),
    onSuccess: (job) => {
      setSelectedJobId(job.id)
      queryClient.invalidateQueries({ queryKey: ['brand-analysis'] })
      queryClient.invalidateQueries({ queryKey: ['brand-analysis', job.id] })
    },
    onError: (error) => {
      toast({
        variant: 'destructive',
        title: t('brandAnalysis.error.uploadFailed', { detail: '' }),
        description: getErrorMessage(error),
      })
    },
  })

  const startMutation = useMutation({
    mutationFn: (id: string) => brandAnalysisApi.start(id),
    onSuccess: (job) => {
      setSelectedJobId(job.id)
      queryClient.invalidateQueries({ queryKey: ['brand-analysis'] })
      queryClient.invalidateQueries({ queryKey: ['brand-analysis', job.id] })
    },
    onError: (error) => {
      toast({
        variant: 'destructive',
        title: t('brandAnalysis.error.startFailed', { detail: '' }),
        description: getErrorMessage(error),
      })
    },
  })

  const downloadMutation = useMutation({
    mutationFn: () => brandAnalysisApi.download(selectedJobId!),
    onSuccess: (blob) => {
      downloadBlob(blob, selectedJob?.artifact_filename || 'brand_analysis.pptx')
    },
    onError: (error) => {
      toast({ variant: 'destructive', description: getErrorMessage(error) })
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => brandAnalysisApi.delete(id),
    onSuccess: (_data, id) => {
      if (selectedJobId === id) setSelectedJobId(null)
      queryClient.invalidateQueries({ queryKey: ['brand-analysis'] })
      toast({ description: t('brandAnalysis.action.deleted') })
    },
    onError: (error) => {
      toast({ variant: 'destructive', description: getErrorMessage(error) })
    },
  })

  const cancelMutation = useMutation({
    mutationFn: (id: string) => brandAnalysisApi.cancel(id),
    onSuccess: (job) => {
      queryClient.invalidateQueries({ queryKey: ['brand-analysis'] })
      queryClient.invalidateQueries({ queryKey: ['brand-analysis', job.id] })
    },
    onError: (error) => {
      toast({ variant: 'destructive', description: getErrorMessage(error) })
    },
  })

  const syncMutation = useMutation({
    mutationFn: (accountId: string) => accountsApi.triggerSync(accountId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['accounts'] })
      toast({ description: t('brandAnalysis.action.syncStarted') })
    },
    onError: (error) => {
      toast({ variant: 'destructive', description: getErrorMessage(error) })
    },
  })

  const handleAnalyze = async () => {
    const validationError = validateForm()
    if (validationError) {
      toast({ variant: 'destructive', title: validationError })
      return
    }
    const job = await createMutation.mutateAsync()
    setSelectedJobId(job.id)
    if (modeToDataSource(job.mode) === 'internal') {
      await startMutation.mutateAsync(job.id)
    } else {
      setShowAdvancedUpload(true)
      setActiveTab('files')
    }
  }

  const handleUpload = (year: 2024 | 2025) => {
    const file = year === 2024 ? file2024 : file2025
    if (!file || !selectedJobId) return
    uploadMutation.mutate({ year, file })
  }

  const statusLabel = (status: BrandAnalysisStatus): string => t(statusGroupLabelKey[statusGroupOf[status]])

  const yearState = (year: 2024 | 2025): { state: ReadinessState; label: string; detail: string } => {
    const coverageReport = coverage.years?.[year] || coverage.years?.[String(year)]
    const yearReport = coverageReport || readiness.years?.[year] || readiness.years?.[String(year)]
    if (selectedJob?.error_code === `missing_${year}_data`) {
      return {
        state: 'missing',
        label: t('brandAnalysis.readiness.missing'),
        detail: selectedJob.error_message || t(`brandAnalysis.errorCode.missing_${year}_data`),
      }
    }
    if (!yearReport) {
      return {
        state: 'unknown',
        label: t('brandAnalysis.readiness.notChecked'),
        detail: t('brandAnalysis.readiness.runToCheck'),
      }
    }
    if (yearReport.classification === 'complete') {
      return {
        state: 'ready',
        label: t('brandAnalysis.readiness.ready'),
        detail: `${yearReport.asin_count || 0} ASINs · ${yearReport.first_date || 'N/A'} → ${yearReport.last_date || 'N/A'}`,
      }
    }
    if (yearReport.classification === 'recoverable_gap') {
      const window = yearReport.recoverable_window
      return {
        state: 'warning',
        label: t('brandAnalysis.readiness.recoverable'),
        detail: window ? `${window.start_date} → ${window.end_date}` : t('brandAnalysis.readiness.partialDetail'),
      }
    }
    if (yearReport.classification === 'unrecoverable_gap' || yearReport.classification === 'unavailable') {
      return {
        state: yearReport.row_count ? 'warning' : 'missing',
        label: t('brandAnalysis.readiness.unrecoverable'),
        detail: (yearReport.limitations || []).join(' ') || t(`brandAnalysis.errorCode.missing_${year}_data`),
      }
    }
    if (yearReport.classification === 'partial_but_usable') {
      return {
        state: 'warning',
        label: t('brandAnalysis.readiness.partial'),
        detail: (yearReport.missing_months || []).length
          ? `${(yearReport.missing_months || []).slice(0, 4).join(', ')}`
          : (yearReport.limitations || []).join(' '),
      }
    }
    if (yearReport.complete_year) {
      return {
        state: 'ready',
        label: t('brandAnalysis.readiness.ready'),
        detail: `${yearReport.account_sales_asins || 0} ASINs · ${yearReport.first_sales_date || 'N/A'} → ${yearReport.last_sales_date || 'N/A'}`,
      }
    }
    if (yearReport.has_sales) {
      return {
        state: 'warning',
        label: t('brandAnalysis.readiness.partial'),
        detail: (yearReport.missing_periods || []).join(', ') || t('brandAnalysis.readiness.partialDetail'),
      }
    }
    return {
      state: 'missing',
      label: t('brandAnalysis.readiness.missing'),
      detail: t(`brandAnalysis.errorCode.missing_${year}_data`),
    }
  }

  const accountState: { state: ReadinessState; label: string; detail: string } = selectedAccountObj
    ? {
        state:
          selectedAccountObj.sync_status === 'error'
            ? 'missing'
            : selectedAccountObj.sync_status === 'syncing'
              ? 'warning'
              : 'ready',
        label: selectedAccountObj.sync_status,
        detail: selectedAccountObj.last_sync_at
          ? `${t('brandAnalysis.readiness.lastSync')} ${formatDate(selectedAccountObj.last_sync_at)}`
          : t('brandAnalysis.readiness.neverSynced'),
      }
    : {
        state: dataSource === 'manual' ? 'warning' : 'missing',
        label: t('brandAnalysis.readiness.noAccount'),
        detail: t('brandAnalysis.error.connectedAccountRequired'),
      }

  const catalogState: { state: ReadinessState; label: string; detail: string } = (() => {
    const catalog = readiness.catalog_enrichment
    if (!catalog) {
      return {
        state: 'unknown',
        label: t('brandAnalysis.readiness.notChecked'),
        detail: t('brandAnalysis.readiness.runToCheck'),
      }
    }
    if (catalog.partial) {
      return {
        state: 'warning',
        label: t('brandAnalysis.readiness.partial'),
        detail: `${catalog.failed_asins?.length || 0} ${t('brandAnalysis.readiness.failedCatalogAsins')}`,
      }
    }
    return {
      state: 'ready',
      label: t('brandAnalysis.readiness.ready'),
      detail: `${catalog.attempted || 0} ${t('brandAnalysis.readiness.catalogLookups')}`,
    }
  })()

  const missingOptional = (completeness.missing_optional_fields_2025 || []) as string[]
  const capabilityKeys = [
    'sales_and_traffic_available',
    'data_kiosk_available',
    'brand_analytics_available',
    'brand_registry_available_or_inferred',
    'product_pricing_available',
    'product_fees_available',
    'aplus_available',
    'finance_reports_available',
    'settlement_reports_available',
    'catalog_items_available',
    'listings_available',
  ]
  const missingPermissions = (capabilityMatrix.missing_roles || []) as string[]
  const limitationItems = (limitations.items || []) as Array<{ area?: string; message?: string }>
  const showUploadZone = !!selectedJob && (showAdvancedUpload || selectedJobDataSource === 'manual' || isWaitingForUser)
  const progressPct = selectedJob?.progress_pct || 0
  const hasCapabilityData = capabilityKeys.some((key) => capabilityMatrix[key] !== undefined)

  // Error-specific fixes come first: when the job failed with a known error
  // code, the most relevant repair action leads the list instead of leaving
  // the user to map the error onto a generic action themselves.
  const goToUpload = () => {
    setShowAdvancedUpload(true)
    setActiveTab('files')
  }
  const errorFixActions = (() => {
    const code = selectedJob?.error_code
    if (!code) return []
    if (code === 'missing_2024_data' || code === 'missing_2025_data') {
      const year = code === 'missing_2024_data' ? 2024 : 2025
      return [
        {
          key: `fix-${code}`,
          visible: true,
          label: t('brandAnalysis.action.uploadYearExport', { year }),
          onClick: goToUpload,
          disabled: false,
        },
      ]
    }
    if (code === 'insufficient_yearly_data' || code === 'manual_upload_required') {
      return [
        {
          key: `fix-${code}`,
          visible: true,
          label: t('brandAnalysis.action.uploadExternal'),
          onClick: goToUpload,
          disabled: false,
        },
      ]
    }
    if ((code === 'internal_sync_failed' || code === 'internal_data_missing') && selectedAccountObj) {
      return [
        {
          key: `fix-${code}`,
          visible: true,
          label: t('brandAnalysis.action.syncAmazon'),
          onClick: () => syncMutation.mutate(selectedAccountObj.id),
          disabled: syncMutation.isPending || selectedAccountObj.sync_status === 'syncing',
        },
      ]
    }
    if (code === 'connected_account_required') {
      return [
        {
          key: `fix-${code}`,
          visible: true,
          label: t('brandAnalysis.action.checkConnection'),
          onClick: () => {
            window.location.href = '/settings'
          },
          disabled: false,
        },
      ]
    }
    return []
  })()

  const baseActions = [
    {
      key: 'sync',
      visible: dataSource === 'internal' && !!selectedAccountObj,
      label: t('brandAnalysis.action.syncAmazon'),
      onClick: () => selectedAccountObj && syncMutation.mutate(selectedAccountObj.id),
      disabled: syncMutation.isPending || selectedAccountObj?.sync_status === 'syncing',
    },
    {
      key: 'connection',
      visible: dataSource === 'internal',
      label: t('brandAnalysis.action.checkConnection'),
      onClick: () => {
        window.location.href = '/settings'
      },
      disabled: false,
    },
    {
      key: 'asin',
      visible: marketType === 'brand',
      label: t('brandAnalysis.action.provideAsins'),
      onClick: () => setMarketType('asin'),
      disabled: false,
    },
    {
      key: 'upload',
      visible: true,
      label: t('brandAnalysis.action.uploadExternal'),
      onClick: goToUpload,
      disabled: !selectedJob,
    },
  ]
  const errorFixLabels = new Set(errorFixActions.map((action) => action.label))
  const recommendedActions = [
    ...errorFixActions,
    ...baseActions.filter((action) => action.visible && !errorFixLabels.has(action.label)),
  ]

  const readinessItems = [
    { key: 'account', title: t('brandAnalysis.readiness.account'), ...accountState },
    { key: '2024', title: '2024', ...yearState(2024) },
    { key: '2025', title: '2025', ...yearState(2025) },
    { key: 'catalog', title: t('brandAnalysis.readiness.catalog'), ...catalogState },
  ]

  const showDownloadHero = !!selectedJob?.download_ready

  const historyColumns: ReportColumn<BrandAnalysisListItem>[] = [
    {
      id: 'brand',
      header: t('brandAnalysis.field.brandName'),
      width: '40%',
      cell: (job) => (
        <div className="min-w-0">
          <div className="flex flex-wrap items-baseline gap-x-2.5 gap-y-1">
            <span className="truncate text-sm font-semibold">{job.brand_name}</span>
            <StatusPill status={job.status} label={statusLabel(job.status)} />
          </div>
          <p className="mt-1 font-mono text-[11px] text-muted-foreground">
            {job.source_years.length
              ? job.source_years.join(' · ')
              : t('brandAnalysis.historyNoSourceYears')}{' '}
            · {formatDate(job.created_at)}
          </p>
        </div>
      ),
    },
    {
      id: 'source',
      header: t('brandAnalysis.label.dataSource'),
      hideOnMobile: true,
      cardLabel: t('brandAnalysis.label.dataSource'),
      cell: (job) => (
        <div className="text-xs">
          <span className="block font-medium text-foreground">
            {t(`brandAnalysis.mode.${modeToDataSource(job.mode)}`)}
          </span>
          <span className="text-muted-foreground">
            {job.market_type === 'asin'
              ? t('brandAnalysis.marketType.asin')
              : t('brandAnalysis.marketType.brand')}
          </span>
        </div>
      ),
    },
    {
      id: 'progress',
      header: t('brandAnalysis.progress.title'),
      width: '18%',
      hideOnMobile: true,
      cardLabel: t('brandAnalysis.progress.title'),
      cell: (job) => (
        <div className="flex items-center gap-2">
          <Progress
            value={job.progress_pct}
            aria-label={t('brandAnalysis.history.progressLabel', { pct: job.progress_pct })}
            className="h-1 w-20"
          />
          <span className="font-mono text-xs tabular-nums text-muted-foreground">
            {job.progress_pct}%
          </span>
        </div>
      ),
    },
    {
      id: 'completed',
      header: t('brandAnalysis.readiness.lastSync'),
      width: '120px',
      hideOnMobile: true,
      cardLabel: t('brandAnalysis.readiness.lastSync'),
      cell: (job) => (
        <span className="text-xs text-muted-foreground">
          {job.completed_at ? formatDate(job.completed_at) : '—'}
        </span>
      ),
    },
  ]

  return (
    <div className="space-y-12 pb-4">
      {/* ─── Masthead ────────────────────────────────────────────────── */}
      <header className="ba-rise">
        <div aria-hidden="true" className="border-t-[3px] border-foreground" />
        <div aria-hidden="true" className="mt-[3px] border-t border-foreground/30" />
        <div className="flex flex-col gap-6 pt-6 md:flex-row md:items-end md:justify-between">
          <div className="min-w-0">
            <h1 className="text-3xl font-bold tracking-tight">{t('brandAnalysis.title')}</h1>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">
              {t('brandAnalysis.subtitle')}
            </p>
          </div>
          <div className="flex shrink-0 flex-col items-start gap-3 md:items-end">
            {jobsQuery.data?.length ? (
              <span className="font-mono text-[11px] uppercase tracking-[0.2em] text-muted-foreground">
                Nº {String(jobsQuery.data.length).padStart(3, '0')}
              </span>
            ) : null}
            {showDownloadHero ? (
              <Button
                size="lg"
                onClick={() => downloadMutation.mutate()}
                disabled={downloadMutation.isPending}
                className={inkButton}
              >
                {downloadMutation.isPending ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <Download className="mr-2 h-4 w-4" />
                )}
                {t('brandAnalysis.cta.download')}
              </Button>
            ) : null}
          </div>
        </div>
      </header>

      {/* ─── 01 · Brief (setup form + readiness manifest) ─────────────── */}
      <section className="ba-rise ba-rise-2">
        <SectionMark
          index="01"
          title={t('brandAnalysis.newAnalysis')}
          hint={t('brandAnalysis.newAnalysisDescription')}
        />
        <div className="mt-8 grid gap-10 xl:grid-cols-[minmax(0,1.5fr)_minmax(320px,0.9fr)] xl:gap-12">
          {/* Brief form */}
          <div className="space-y-7">
            <div className="grid gap-x-8 gap-y-6 lg:grid-cols-[minmax(0,1.4fr)_170px_220px]">
              <div>
                <Label htmlFor="brand-name" className={eyebrow}>
                  {t('brandAnalysis.field.brandName')}
                </Label>
                <Input
                  id="brand-name"
                  value={brandName}
                  onChange={(event) => setBrandName(event.target.value)}
                  placeholder={t('brandAnalysis.field.brandNamePlaceholder')}
                  className={cn(fieldInput, 'mt-1 h-11 text-base font-medium')}
                />
              </div>
              <div>
                <Label className={eyebrow}>{t('brandAnalysis.field.language')}</Label>
                <Select value={language} onValueChange={(value) => setLanguage(value as 'en' | 'it')}>
                  <SelectTrigger className={cn(fieldInput, 'mt-1 h-11')}>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="en">English</SelectItem>
                    <SelectItem value="it">Italiano</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label className={eyebrow}>{t('brandAnalysis.field.account')}</Label>
                <Select value={selectedAccount} onValueChange={setSelectedAccount}>
                  <SelectTrigger className={cn(fieldInput, 'mt-1 h-11')}>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">{t('brandAnalysis.field.accountPlaceholder')}</SelectItem>
                    {accounts?.map((account) => (
                      <SelectItem key={account.id} value={account.id}>
                        {account.account_name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                {selectedAccount === 'none' && (
                  <p className="mt-1 text-xs text-muted-foreground">{t('brandAnalysis.accountNoneHint')}</p>
                )}
              </div>
            </div>

            {/* Scope segmented control */}
            <div>
              <p className={eyebrow}>{t('brandAnalysis.scope.label')}</p>
              <div className="mt-2 inline-flex overflow-hidden rounded-sm border border-foreground/30">
                <SegmentButton
                  active={marketType === 'brand'}
                  label={t('brandAnalysis.scope.brand')}
                  onClick={() => setMarketType('brand')}
                />
                <SegmentButton
                  active={marketType === 'asin'}
                  label={t('brandAnalysis.scope.asin')}
                  onClick={() => setMarketType('asin')}
                />
              </div>
            </div>

            {/* ASIN list — only shown when scope is an explicit ASIN list */}
            {marketType === 'asin' ? (
              <div>
                <div className="flex items-baseline justify-between gap-3">
                  <Label htmlFor="asin-list" className={eyebrow}>
                    {t('brandAnalysis.field.asinList')}
                  </Label>
                  <span className="font-mono text-[11px] tabular-nums text-muted-foreground">
                    {asinList.length} {t('brandAnalysis.label.asins')}
                  </span>
                </div>
                <textarea
                  id="asin-list"
                  value={asinText}
                  onChange={(event) => setAsinText(event.target.value)}
                  className="mt-2 min-h-[112px] w-full resize-y rounded-sm border border-foreground/30 bg-transparent px-3 py-2 font-mono text-sm leading-6 placeholder:text-muted-foreground focus-visible:border-foreground focus-visible:outline-none"
                  placeholder={t('brandAnalysis.field.asinListPlaceholder')}
                />
              </div>
            ) : null}

            <div className="flex flex-wrap items-center gap-3 border-t border-foreground/10 pt-6">
              <Button
                onClick={handleAnalyze}
                disabled={createMutation.isPending || startMutation.isPending}
                size="lg"
                className={inkButton}
              >
                {createMutation.isPending || startMutation.isPending ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <Play className="mr-2 h-4 w-4" />
                )}
                {t('brandAnalysis.cta.analyze')}
              </Button>
              <Button
                type="button"
                variant="outline"
                size="lg"
                className={ghostButton}
                onClick={() => {
                  setShowAdvancedUpload((value) => !value)
                  if (selectedJobId) setActiveTab('files')
                }}
              >
                <Upload className="mr-2 h-4 w-4" />
                {t('brandAnalysis.cta.uploadExternal')}
              </Button>
            </div>
          </div>

          {/* Readiness manifest */}
          <aside className="border-t border-foreground/15 pt-6 xl:border-l xl:border-t-0 xl:pl-10 xl:pt-0">
            <p className={eyebrow}>{t('brandAnalysis.readiness.title')}</p>
            <p className="mt-1.5 text-xs leading-5 text-muted-foreground">
              {t('brandAnalysis.readiness.description')}
            </p>
            <div className="mt-4 divide-y divide-foreground/10">
              {readinessItems.map((item) => (
                <ReadinessRow key={item.key} item={item} />
              ))}
            </div>

            {missingOptional.length ? (
              <div className="mt-5 border-t border-foreground/10 pt-4">
                <div className="flex items-center gap-2">
                  <Info className="h-3.5 w-3.5 text-muted-foreground" />
                  <p className={eyebrow}>{t('brandAnalysis.readiness.optionalMissing')}</p>
                </div>
                <div className="mt-2.5 flex flex-wrap gap-1.5">
                  {missingOptional.map((field) => (
                    <span key={field} className={monoTag}>
                      {field}
                    </span>
                  ))}
                </div>
              </div>
            ) : null}
          </aside>
        </div>
      </section>

      {/* ─── 02 · Production (selected run) ───────────────────────────── */}
      {selectedJobId ? (
        <section className="ba-rise ba-rise-3">
          <SectionMark index="02" title={t('brandAnalysis.progress.title')} />

          <div className="mt-8 flex flex-col gap-6 lg:flex-row lg:items-start lg:justify-between">
            <div className="min-w-0 space-y-4">
              <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
                <StatusStamp status={currentStatus} label={statusLabel(currentStatus)} />
                <span className={monoTag}>
                  {selectedJobDataSource === 'internal'
                    ? t('brandAnalysis.mode.internal')
                    : t('brandAnalysis.mode.manual')}
                </span>
                {selectedJob?.market_type ? (
                  <span className={monoTag}>
                    {t(`brandAnalysis.marketType.${selectedJob.market_type}`)}
                  </span>
                ) : null}
              </div>
              <div>
                <h3 className="text-2xl font-semibold leading-tight tracking-tight">
                  {selectedJob?.brand_name || selectedJobFromList?.brand_name}
                </h3>
                <p className="mt-2 text-sm text-muted-foreground">
                  {selectedJob?.progress_step || t(`brandAnalysis.mode.${selectedJobDataSource}.help`)}
                </p>
              </div>

              {/* Compact at-a-glance progress; the stepper below carries step detail */}
              {isRunning ? (
                <div className="flex max-w-2xl items-center gap-3 pt-1">
                  <Progress value={progressPct} className="h-0.5 flex-1 rounded-none bg-foreground/10" />
                  <span className="font-mono text-xs tabular-nums text-muted-foreground">
                    {progressPct}%
                  </span>
                </div>
              ) : null}
            </div>

            <div className="flex flex-wrap items-center gap-2 lg:justify-end">
              {isRunning && currentStatus !== 'cancelling' ? (
                <CancelRunButton
                  brand={selectedJob?.brand_name || ''}
                  pending={cancelMutation.isPending}
                  onConfirm={() => selectedJobId && cancelMutation.mutate(selectedJobId)}
                />
              ) : null}
              <Button
                type="button"
                onClick={() => selectedJobId && startMutation.mutate(selectedJobId)}
                disabled={!canStart || isRunning || startMutation.isPending}
                variant={selectedJob?.download_ready ? 'outline' : 'default'}
                className={selectedJob?.download_ready ? ghostButton : inkButton}
              >
                {startMutation.isPending ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <RefreshCw className="mr-2 h-4 w-4" />
                )}
                {selectedJob?.status === 'completed'
                  ? t('brandAnalysis.cta.rerun')
                  : t('brandAnalysis.cta.start')}
              </Button>
              {selectedJob?.download_ready ? (
                <Button
                  type="button"
                  onClick={() => downloadMutation.mutate()}
                  disabled={downloadMutation.isPending}
                  className={inkButton}
                >
                  {downloadMutation.isPending ? (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  ) : (
                    <Download className="mr-2 h-4 w-4" />
                  )}
                  {t('brandAnalysis.cta.download')}
                </Button>
              ) : null}
            </div>
          </div>

          <div className="mt-8 space-y-7">
            {selectedJobQuery.isLoading ? (
              <div className="flex items-center gap-3 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
                {t('brandAnalysis.loading')}
              </div>
            ) : null}

            {/* Status banners */}
            {isWaitingForUser ? (
              <Alert variant="warning">
                <AlertTriangle className="h-4 w-4" />
                <AlertTitle>{t('brandAnalysis.status.waiting_for_user_action')}</AlertTitle>
                <AlertDescription>
                  {errorCodeMessage || t('brandAnalysis.upload.fallbackBanner')}
                  {selectedJob?.error_message ? ` ${selectedJob.error_message}` : ''}
                </AlertDescription>
              </Alert>
            ) : selectedJob?.error_message ? (
              <Alert variant="destructive">
                <AlertCircle className="h-4 w-4" />
                <AlertTitle>{statusLabel(currentStatus)}</AlertTitle>
                <AlertDescription>{selectedJob.error_message}</AlertDescription>
              </Alert>
            ) : errorCodeMessage ? (
              <Alert>
                <Info className="h-4 w-4" />
                <AlertDescription>{errorCodeMessage}</AlertDescription>
              </Alert>
            ) : null}

            {/* Pipeline stepper — the single detailed progress view */}
            {isRunning || (progressPct > 0 && progressPct < 100) ? (
              <div className="border-y border-foreground/10 py-6">
                <StepperPipeline
                  steps={progressSteps.map((step) => ({
                    key: step.key,
                    label: t(step.labelKey),
                    pct: step.pct,
                  }))}
                  currentPct={progressPct}
                  status={currentStatus}
                  isRunning={isRunning}
                />
              </div>
            ) : null}

            <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as typeof activeTab)} className="space-y-6">
              <TabsList className="h-auto w-full justify-start gap-7 rounded-none border-b border-foreground/15 bg-transparent p-0 text-muted-foreground">
                <TabsTrigger value="overview" className={tabTrigger}>
                  {t('brandAnalysis.label.metricsPreview')}
                </TabsTrigger>
                <TabsTrigger value="data" className={tabTrigger}>
                  {t('brandAnalysis.readiness.title')}
                </TabsTrigger>
                <TabsTrigger value="files" className={tabTrigger}>
                  {t('brandAnalysis.upload.title')}
                </TabsTrigger>
              </TabsList>

              {/* ── Overview tab ── */}
              <TabsContent value="overview" className="mt-6 space-y-8">
                {selectedJob?.metrics ? (
                  <section className="grid gap-x-6 gap-y-7 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
                    <KpiTile
                      label={t('brandAnalysis.label.revenue2025')}
                      value={formatCurrency(metric(selectedJob, 'total_revenue_2025'))}
                    />
                    <KpiTile
                      label={t('brandAnalysis.label.revenue2024')}
                      value={formatCurrency(metric(selectedJob, 'total_revenue_2024'))}
                    />
                    <KpiTile
                      label={t('brandAnalysis.label.yoy')}
                      value={formatPercent(metric(selectedJob, 'yoy_percent'))}
                      valueTone={signTone(metric(selectedJob, 'yoy_percent'))}
                    />
                    <KpiTile
                      label={t('brandAnalysis.label.marketShare')}
                      value={formatShare(metric(selectedJob, 'market_share_2025'))}
                    />
                    <KpiTile
                      label={t('brandAnalysis.label.activeAsins')}
                      value={formatNumber(metric(selectedJob, 'active_asins_2025'))}
                    />
                    <KpiTile
                      label={t('brandAnalysis.label.inactiveAsins')}
                      value={formatNumber(metric(selectedJob, 'inactive_asins_2025'))}
                      valueTone={
                        typeof metric(selectedJob, 'inactive_asins_2025') === 'number' &&
                        (metric(selectedJob, 'inactive_asins_2025') as number) > 0
                          ? 'neg'
                          : undefined
                      }
                    />
                  </section>
                ) : (
                  <EmptyHint
                    title={t('brandAnalysis.label.metricsPreview')}
                    body={t('brandAnalysis.readiness.runToCheck')}
                  />
                )}

                {selectedJob?.metrics ? (
                  <BrandOverviewCharts metrics={selectedJob.metrics} />
                ) : null}

                {selectedJob?.metrics ? (
                  <section className="grid gap-x-10 gap-y-6 lg:grid-cols-3">
                    <InsightTile
                      label={t('brandAnalysis.result.market')}
                      body={
                        marketAnalysis.status === 'calculated_from_external_market_export'
                          ? `${t('brandAnalysis.label.marketSize')}: ${formatCurrency(
                              marketAnalysis.market_size_2025,
                            )}`
                          : marketAnalysis.limitation || t('brandAnalysis.result.marketNa')
                      }
                    />
                    <InsightTile
                      label={t('brandAnalysis.result.content')}
                      body={t('brandAnalysis.result.contentSummary', {
                        titles: contentHealth.short_title_count ?? 'N/A',
                        descriptions: contentHealth.asins_missing_description ?? 'N/A',
                      })}
                    />
                    <InsightTile
                      label={t('brandAnalysis.result.buyBox')}
                      body={
                        sellerSummary.buy_box_owner_available
                          ? t('brandAnalysis.result.buyBoxAvailable', {
                              n: sellerSummary.asins_missing_buy_box_owner ?? 0,
                            })
                          : t('brandAnalysis.result.buyBoxNa')
                      }
                    />
                  </section>
                ) : null}

                {/* Fix data — quiet inline strip of navigational shortcuts */}
                {recommendedActions.length ? (
                  <section className="flex flex-wrap items-baseline gap-x-5 gap-y-2 border-t border-foreground/10 pt-4">
                    <span className={eyebrow}>{t('brandAnalysis.action.title')}</span>
                    {recommendedActions.map((action) => (
                      <Button
                        key={action.key}
                        type="button"
                        variant="link"
                        size="sm"
                        disabled={action.disabled}
                        onClick={action.onClick}
                        className="h-auto p-0 text-sm font-medium underline decoration-dotted underline-offset-4"
                      >
                        {action.label}
                      </Button>
                    ))}
                  </section>
                ) : null}
              </TabsContent>

              {/* ── Data & capabilities tab ── */}
              <TabsContent value="data" className="mt-6 space-y-8">
                <section>
                  <p className={eyebrow}>{t('brandAnalysis.readiness.title')}</p>
                  <div className="mt-2 grid gap-x-12 md:grid-cols-2">
                    {readinessItems.map((item) => (
                      <ReadinessRow key={item.key} item={item} />
                    ))}
                  </div>
                </section>

                {hasCapabilityData ? (
                  <section>
                    <p className={eyebrow}>{t('brandAnalysis.readiness.capabilities')}</p>
                    <div className="mt-2 grid gap-x-10 sm:grid-cols-2 lg:grid-cols-3">
                      {capabilityKeys.map((key) => {
                        const value = capabilityMatrix[key]
                        if (value === undefined) return null
                        const available = !!value
                        return (
                          <div
                            key={key}
                            className="flex items-center gap-2.5 border-b border-foreground/10 py-2.5"
                          >
                            {available ? (
                              <CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-emerald-600 dark:text-emerald-400" />
                            ) : (
                              <X className="h-3.5 w-3.5 shrink-0 text-rose-600 dark:text-rose-400" />
                            )}
                            <span
                              className={cn(
                                'min-w-0 flex-1 truncate font-mono text-xs',
                                available ? 'text-foreground' : 'text-muted-foreground',
                              )}
                            >
                              {key
                                .replace(/_available$/, '')
                                .replace(/_or_inferred$/, '')
                                .replace(/_/g, ' ')}
                            </span>
                          </div>
                        )
                      })}
                    </div>
                  </section>
                ) : null}

                {missingPermissions.length ? (
                  <Alert variant="warning">
                    <AlertTriangle className="h-4 w-4" />
                    <AlertTitle>{t('brandAnalysis.readiness.missingPermissions')}</AlertTitle>
                    <AlertDescription>
                      <div className="mt-2 flex flex-wrap gap-1.5">
                        {missingPermissions.map((role) => (
                          <span key={role} className={monoTag}>
                            {role}
                          </span>
                        ))}
                      </div>
                    </AlertDescription>
                  </Alert>
                ) : null}

                {limitationItems.length ? (
                  <section>
                    <p className={eyebrow}>{t('brandAnalysis.readiness.limitations')}</p>
                    <div className="mt-3 space-y-4">
                      {limitationItems.map((item, index) => (
                        <div key={`${item.area}-${index}`} className="border-l-2 border-amber-500 pl-4">
                          {item.area ? (
                            <p className="font-mono text-[10px] font-semibold uppercase tracking-[0.18em] text-amber-700 dark:text-amber-400">
                              {item.area.replace(/_/g, ' ')}
                            </p>
                          ) : null}
                          <p className="mt-1 text-sm leading-6 text-foreground/90">{item.message}</p>
                        </div>
                      ))}
                    </div>
                  </section>
                ) : null}

                {missingOptional.length ? (
                  <section>
                    <p className={eyebrow}>{t('brandAnalysis.readiness.optionalMissing')}</p>
                    <div className="mt-2.5 flex flex-wrap gap-1.5">
                      {missingOptional.map((field) => (
                        <span key={field} className={monoTag}>
                          {field}
                        </span>
                      ))}
                    </div>
                  </section>
                ) : null}
              </TabsContent>

              {/* ── Files tab ── */}
              <TabsContent value="files" className="mt-6 space-y-5">
                <div className="flex items-start gap-2.5 text-sm text-muted-foreground">
                  <Info className="mt-0.5 h-4 w-4 shrink-0" />
                  <p className="max-w-3xl leading-6">{t('brandAnalysis.upload.description')}</p>
                </div>

                {!selectedJob ? (
                  <Alert>
                    <AlertCircle className="h-4 w-4" />
                    <AlertDescription>{t('brandAnalysis.upload.createFirst')}</AlertDescription>
                  </Alert>
                ) : null}

                {selectedJob && selectedJobDataSource === 'manual' ? (
                  <div
                    className={cn(
                      'flex flex-wrap items-center justify-between gap-3 border-l-2 py-1 pl-4 text-sm',
                      hasBothManualFiles
                        ? 'border-emerald-500 text-emerald-700 dark:text-emerald-400'
                        : 'border-foreground/25 text-muted-foreground',
                    )}
                  >
                    <p className="leading-6">
                      {hasBothManualFiles
                        ? t('brandAnalysis.upload.allFilesReady')
                        : t('brandAnalysis.upload.filesProgress', { count: sourceYears.size })}
                    </p>
                    {hasBothManualFiles && !isRunning ? (
                      <Button
                        size="sm"
                        className={inkButton}
                        onClick={() => selectedJobId && startMutation.mutate(selectedJobId)}
                        disabled={startMutation.isPending}
                      >
                        {startMutation.isPending ? (
                          <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                        ) : (
                          <Play className="mr-2 h-4 w-4" />
                        )}
                        {t('brandAnalysis.cta.start')}
                      </Button>
                    ) : null}
                  </div>
                ) : null}

                <div className="grid gap-5 md:grid-cols-2">
                  {[2024, 2025].map((year) => {
                    const existing = selectedJob?.source_files.find((file) => file.year === year)
                    const file = year === 2024 ? file2024 : file2025
                    return (
                      <div
                        key={year}
                        className={cn(
                          'rounded-sm border border-dashed p-5',
                          existing
                            ? 'border-emerald-500/60 bg-emerald-500/[0.04]'
                            : 'border-foreground/30',
                        )}
                      >
                        <div className="flex items-start justify-between gap-3">
                          <div className="flex min-w-0 items-start gap-3">
                            <FileSpreadsheet
                              className={cn(
                                'mt-1 h-5 w-5 shrink-0',
                                existing
                                  ? 'text-emerald-600 dark:text-emerald-400'
                                  : 'text-muted-foreground',
                              )}
                            />
                            <div className="min-w-0">
                              <p className="text-sm font-semibold">
                                {t('brandAnalysis.upload.yearExport', { year })}
                              </p>
                              <p className="mt-0.5 font-mono text-[11px] text-muted-foreground">
                                {existing
                                  ? t('brandAnalysis.upload.fileReady', { rows: existing.row_count ?? 0 })
                                  : t('brandAnalysis.upload.fileMissing')}
                              </p>
                            </div>
                          </div>
                          <span
                            className={cn(
                              'shrink-0 font-mono text-[10px] font-semibold uppercase tracking-[0.16em]',
                              existing
                                ? 'text-emerald-700 dark:text-emerald-400'
                                : 'text-muted-foreground',
                            )}
                          >
                            {existing
                              ? t('brandAnalysis.readiness.ready')
                              : t('brandAnalysis.readiness.missing')}
                          </span>
                        </div>
                        <div className="mt-5 flex flex-col gap-2 sm:flex-row">
                          <Input
                            type="file"
                            accept=".csv,.xlsx,.xls"
                            disabled={!selectedJob}
                            onChange={(event) => {
                              const nextFile = event.target.files?.[0] || null
                              if (year === 2024) setFile2024(nextFile)
                              else setFile2025(nextFile)
                            }}
                            className="cursor-pointer rounded-sm border-foreground/25 file:mr-3 file:cursor-pointer file:rounded-sm file:border-0 file:bg-foreground/10 file:px-2 file:py-1 file:font-mono file:text-[11px] file:font-medium hover:bg-foreground/[0.03]"
                          />
                          <Button
                            type="button"
                            variant="outline"
                            className={ghostButton}
                            disabled={!selectedJob || !file || uploadMutation.isPending}
                            onClick={() => handleUpload(year as 2024 | 2025)}
                          >
                            {uploadMutation.isPending ? (
                              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                            ) : (
                              <Upload className="mr-2 h-4 w-4" />
                            )}
                            {t('brandAnalysis.cta.upload', { year })}
                          </Button>
                        </div>
                      </div>
                    )
                  })}
                </div>
              </TabsContent>
            </Tabs>
          </div>
        </section>
      ) : null}

      {/* ─── Standalone upload zone (legacy fallback when no job) ─────── */}
      {showUploadZone && !selectedJobId ? (
        <section className="ba-rise ba-rise-3 border-t border-foreground/15 pt-6">
          <p className={eyebrow}>{t('brandAnalysis.upload.title')}</p>
          <p className="mt-1.5 max-w-2xl text-sm leading-6 text-muted-foreground">
            {t('brandAnalysis.upload.description')}
          </p>
          <Alert className="mt-4">
            <AlertCircle className="h-4 w-4" />
            <AlertDescription>{t('brandAnalysis.upload.createFirst')}</AlertDescription>
          </Alert>
        </section>
      ) : null}

      {/* ─── 02/03 · Archive ──────────────────────────────────────────── */}
      <section className="ba-rise ba-rise-4">
        <SectionMark
          index={selectedJobId ? '03' : '02'}
          title={t('brandAnalysis.previousAnalyses')}
          hint={t('brandAnalysis.historyDescription')}
        />
        <div className="mt-6">
          {jobsQuery.isLoading ? (
            <div className="flex justify-center py-10">
              <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
            </div>
          ) : !jobsQuery.data?.length ? (
            <div className="flex flex-col items-center gap-2 rounded-sm border border-dashed border-foreground/25 px-6 py-14 text-center">
              <p className="max-w-md text-sm leading-6 text-muted-foreground">
                {t('brandAnalysis.noJobsYet')}
              </p>
            </div>
          ) : (
            <div>
              <ReportTable
                rows={jobsQuery.data}
                rowKey={(job) => job.id}
                onRowOpen={(job) => setSelectedJobId(job.id)}
                rowOpenLabel={(job) =>
                  t('brandAnalysis.history.openRow', { brand: job.brand_name })
                }
                isRowSelected={(job) => selectedJobId === job.id}
                columns={historyColumns}
                actions={(job) => (
                  <>
                    {job.download_ready ? (
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8"
                        onClick={() => {
                          setSelectedJobId(job.id)
                          brandAnalysisApi
                            .download(job.id)
                            .then((blob) =>
                              downloadBlob(blob, `${job.brand_name}_brand_analysis.pptx`),
                            )
                            .catch((error) =>
                              toast({ variant: 'destructive', description: getErrorMessage(error) }),
                            )
                        }}
                        aria-label={t('brandAnalysis.history.downloadRow', { brand: job.brand_name })}
                      >
                        <Download className="h-4 w-4" />
                      </Button>
                    ) : null}
                    {(job.status === 'failed' || job.status === 'cancelled') ? (
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8"
                        onClick={() => startMutation.mutate(job.id)}
                        disabled={startMutation.isPending}
                        title={t('brandAnalysis.history.restart')}
                        aria-label={t('brandAnalysis.history.restart')}
                      >
                        <RefreshCw className="h-4 w-4" />
                      </Button>
                    ) : null}
                    <DeleteAnalysisButton
                      brand={job.brand_name}
                      pending={deleteMutation.isPending && deleteMutation.variables === job.id}
                      onConfirm={() => deleteMutation.mutate(job.id)}
                    />
                  </>
                )}
              />
            </div>
          )}
        </div>
      </section>
    </div>
  )
}

/* ─── small inline pieces ────────────────────────────────────────── */

function DeleteAnalysisButton({
  brand,
  onConfirm,
  pending,
}: {
  brand: string
  onConfirm: () => void
  pending?: boolean
}) {
  const { t } = useTranslation()
  return (
    <AlertDialog>
      <AlertDialogTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8 text-muted-foreground hover:text-destructive"
          onClick={(event) => event.stopPropagation()}
          aria-label={t('brandAnalysis.action.delete')}
        >
          {pending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
        </Button>
      </AlertDialogTrigger>
      <AlertDialogContent onClick={(event) => event.stopPropagation()}>
        <AlertDialogHeader>
          <AlertDialogTitle>{t('brandAnalysis.action.deleteConfirmTitle')}</AlertDialogTitle>
          <AlertDialogDescription>
            {t('brandAnalysis.action.deleteConfirmBody', { brand })}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
          <AlertDialogAction
            onClick={onConfirm}
            className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
          >
            {t('brandAnalysis.action.delete')}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}

function CancelRunButton({
  brand,
  onConfirm,
  pending,
}: {
  brand: string
  onConfirm: () => void
  pending?: boolean
}) {
  const { t } = useTranslation()
  return (
    <AlertDialog>
      <AlertDialogTrigger asChild>
        <Button type="button" variant="outline" className={ghostButton} disabled={pending}>
          {pending ? (
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
          ) : (
            <X className="mr-2 h-4 w-4" />
          )}
          {t('brandAnalysis.cta.cancel')}
        </Button>
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{t('brandAnalysis.action.cancelConfirmTitle')}</AlertDialogTitle>
          <AlertDialogDescription>
            {t('brandAnalysis.action.cancelConfirmBody', { brand })}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>{t('brandAnalysis.action.cancelKeep')}</AlertDialogCancel>
          <AlertDialogAction
            onClick={onConfirm}
            className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
          >
            {t('brandAnalysis.action.cancel')}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}

function SegmentButton({
  active,
  label,
  onClick,
}: {
  active: boolean
  label: string
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={cn(
        'px-3.5 py-1.5 font-mono text-[11px] uppercase tracking-[0.14em] transition-colors',
        active
          ? 'bg-foreground text-background'
          : 'bg-transparent text-muted-foreground hover:text-foreground',
      )}
    >
      {label}
    </button>
  )
}

// Manifest row — a table-of-contents line with a dotted leader running from
// the item to its status.
function ReadinessRow({
  item,
}: {
  item: {
    title: string
    state: ReadinessState
    label: string
    detail: string
  }
}) {
  return (
    <div className="py-3">
      <div className="flex items-baseline gap-2.5">
        <span className="shrink-0 font-mono text-xs font-semibold uppercase tracking-[0.08em] text-foreground">
          {item.title}
        </span>
        <span
          aria-hidden="true"
          className="flex-1 self-center border-b border-dotted border-foreground/30"
        />
        <span
          aria-hidden="true"
          className={cn('h-1.5 w-1.5 shrink-0 self-center rounded-full', stateDot[item.state])}
        />
        <span className="shrink-0 font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground">
          {item.label}
        </span>
      </div>
      <p className="mt-1 text-xs leading-5 text-muted-foreground">{item.detail}</p>
    </div>
  )
}

// Production line — stations on a single ink track. Done stations are filled,
// the current one pulses, upcoming ones stay hollow.
function StepperPipeline({
  steps,
  currentPct,
  status,
  isRunning,
}: {
  steps: { key: string; label: string; pct: number }[]
  currentPct: number
  status: BrandAnalysisStatus
  isRunning: boolean
}) {
  const completed = status === 'completed' || status === 'completed_with_limitations'
  return (
    <ol className="grid grid-cols-3 gap-y-6 sm:grid-cols-9">
      {steps.map((step, index) => {
        const isDone = completed || currentPct >= step.pct
        const prevPct = index === 0 ? 0 : steps[index - 1].pct
        const isActive = !completed && isRunning && currentPct < step.pct && currentPct >= prevPct - 4
        return (
          <li key={step.key} className="relative flex flex-col items-center gap-2 text-center">
            {index > 0 ? (
              <span
                aria-hidden="true"
                className={cn(
                  'absolute left-[-50%] right-[50%] top-[5px] hidden h-px sm:block',
                  isDone ? 'bg-foreground' : 'bg-foreground/15',
                )}
              />
            ) : null}
            <span
              className={cn(
                'relative z-10 h-[11px] w-[11px] rounded-full border-2 bg-background',
                isDone
                  ? 'border-foreground bg-foreground'
                  : isActive
                    ? 'ba-pulse border-primary'
                    : 'border-foreground/25',
              )}
            />
            <span
              className={cn(
                'px-1 font-mono text-[9px] uppercase leading-snug tracking-[0.1em]',
                isDone
                  ? 'text-foreground'
                  : isActive
                    ? 'font-semibold text-primary'
                    : 'text-muted-foreground/70',
              )}
            >
              {step.label}
            </span>
          </li>
        )
      })}
    </ol>
  )
}

function InsightTile({ label, body }: { label: string; body: string }) {
  return (
    <div className="border-l-2 border-foreground/70 pl-4">
      <p className="font-mono text-[10px] font-semibold uppercase tracking-[0.18em] text-foreground">
        {label}
      </p>
      <p className="mt-1.5 text-sm leading-6 text-muted-foreground">{body}</p>
    </div>
  )
}

function EmptyHint({ title, body }: { title: string; body: string }) {
  return (
    <div className="flex flex-col items-center gap-2 rounded-sm border border-dashed border-foreground/25 px-6 py-12 text-center">
      <p className="font-mono text-[10px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
        {title}
      </p>
      <p className="max-w-xs text-sm leading-6 text-muted-foreground">{body}</p>
    </div>
  )
}
