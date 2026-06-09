import { useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertCircle,
  AlertTriangle,
  BarChart3,
  CheckCircle2,
  Circle,
  Database,
  Download,
  FileSpreadsheet,
  FileText,
  History,
  Info,
  Languages,
  LineChart,
  ListChecks,
  Loader2,
  Package,
  Percent,
  Play,
  Presentation,
  RefreshCw,
  Search,
  ShieldCheck,
  Trash2,
  Upload,
  Wallet,
  X,
  XCircle,
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
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
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
import { useTranslation } from '@/i18n'
import { accountsApi, brandAnalysisApi } from '@/services/api'
import type {
  AmazonAccount,
  BrandAnalysisJob,
  BrandAnalysisListItem,
  BrandAnalysisMode,
  BrandAnalysisStatus,
} from '@/types'

type DataSource = 'internal' | 'manual'
type BadgeVariant = 'default' | 'secondary' | 'destructive' | 'outline' | 'success' | 'warning'
type ReadinessState = 'ready' | 'warning' | 'missing' | 'unknown'

// Single section-label style shared by every "eyebrow" heading on the page.
const eyebrow = 'text-xs font-medium uppercase tracking-wide text-muted-foreground'

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

const statusGroupVariant: Record<StatusGroup, BadgeVariant> = {
  preparing: 'secondary',
  analyzing: 'secondary',
  generatingDeck: 'secondary',
  completed: 'success',
  completed_with_limitations: 'warning',
  needs_upload: 'warning',
  failed: 'destructive',
  cancelling: 'secondary',
  cancelled: 'outline',
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

const capabilityIcons: Record<string, typeof Database> = {
  sales_and_traffic_available: BarChart3,
  data_kiosk_available: Database,
  brand_analytics_available: ShieldCheck,
  brand_registry_available_or_inferred: ShieldCheck,
  product_pricing_available: Wallet,
  product_fees_available: Percent,
  aplus_available: FileText,
  finance_reports_available: Wallet,
  settlement_reports_available: Wallet,
  catalog_items_available: Package,
  listings_available: ListChecks,
}

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

const readinessTone: Record<ReadinessState, string> = {
  ready: 'border-l-emerald-500 bg-emerald-500/[0.04] dark:bg-emerald-500/[0.08]',
  warning: 'border-l-amber-500 bg-amber-500/[0.05] dark:bg-amber-500/[0.08]',
  missing: 'border-l-rose-500 bg-rose-500/[0.05] dark:bg-rose-500/[0.08]',
  unknown: 'border-l-border bg-muted/30',
}

const readinessIconTone: Record<ReadinessState, string> = {
  ready: 'text-emerald-600 dark:text-emerald-400',
  warning: 'text-amber-600 dark:text-amber-400',
  missing: 'text-rose-600 dark:text-rose-400',
  unknown: 'text-muted-foreground',
}

function ReadinessBadge({ state, label }: { state: ReadinessState; label: string }) {
  const variant: Record<ReadinessState, BadgeVariant> = {
    ready: 'success',
    warning: 'warning',
    missing: 'destructive',
    unknown: 'outline',
  }
  return (
    <Badge variant={variant[state]} className="shrink-0 whitespace-nowrap">
      {label}
    </Badge>
  )
}

function StatusPill({ status, label }: { status: BrandAnalysisStatus; label: string }) {
  const variant = statusGroupVariant[statusGroupOf[status]]
  const isRunning = runningStatuses.includes(status)
  return (
    <Badge variant={variant} className="gap-1.5 whitespace-nowrap text-[11px] uppercase tracking-wide">
      {isRunning ? (
        <Loader2 className="h-3 w-3 animate-spin" />
      ) : status === 'completed' ? (
        <CheckCircle2 className="h-3 w-3" />
      ) : status === 'failed' ? (
        <AlertCircle className="h-3 w-3" />
      ) : status === 'cancelled' ? (
        <XCircle className="h-3 w-3" />
      ) : status === 'waiting_for_user_action' || status === 'completed_with_limitations' ? (
        <AlertTriangle className="h-3 w-3" />
      ) : (
        <Circle className="h-3 w-3" />
      )}
      {label}
    </Badge>
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
    <div className="rounded-lg border bg-card p-4">
      <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className={cn('mt-2 text-2xl font-semibold tabular-nums tracking-tight', valueClass(valueTone))}>
        {value}
      </p>
      {hint ? <p className="mt-1 text-xs text-muted-foreground">{hint}</p> : null}
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
      description: selectedJob.brand_name,
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

  const recommendedActions = [
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
      onClick: () => {
        setShowAdvancedUpload(true)
        setActiveTab('files')
      },
      disabled: !selectedJob,
    },
  ].filter((action) => action.visible)

  const readinessItems = [
    {
      key: 'account',
      icon: ShieldCheck,
      title: t('brandAnalysis.readiness.account'),
      ...accountState,
    },
    { key: '2024', icon: Database, title: '2024', ...yearState(2024) },
    { key: '2025', icon: Database, title: '2025', ...yearState(2025) },
    { key: 'catalog', icon: FileSpreadsheet, title: t('brandAnalysis.readiness.catalog'), ...catalogState },
  ]

  const showDownloadHero = !!selectedJob?.download_ready

  return (
    <div className="space-y-6">
      {/* ─── Page hero ───────────────────────────────────────────────── */}
      <header className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
        <div className="flex items-start gap-4">
          <div className="hidden h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary md:flex">
            <Presentation className="h-5 w-5" />
          </div>
          <div className="min-w-0">
            <h1 className="text-3xl font-bold tracking-tight">{t('brandAnalysis.title')}</h1>
            <p className="mt-1.5 max-w-3xl text-sm leading-6 text-muted-foreground">
              {t('brandAnalysis.subtitle')}
            </p>
          </div>
        </div>
        {showDownloadHero ? (
          <Button
            size="lg"
            onClick={() => downloadMutation.mutate()}
            disabled={downloadMutation.isPending}
            className="shrink-0"
          >
            {downloadMutation.isPending ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Download className="mr-2 h-4 w-4" />
            )}
            {t('brandAnalysis.cta.download')}
          </Button>
        ) : null}
      </header>

      {/* ─── Setup grid (form + readiness preview) ───────────────────── */}
      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.5fr)_minmax(340px,0.9fr)]">
        <Card className="overflow-hidden">
          <CardHeader className="border-b bg-muted/30">
            <div className="flex items-start gap-3">
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                <Play className="h-4 w-4" />
              </div>
              <div className="min-w-0">
                <CardTitle className="text-lg">{t('brandAnalysis.newAnalysis')}</CardTitle>
                <CardDescription className="mt-1">
                  {t('brandAnalysis.newAnalysisDescription')}
                </CardDescription>
              </div>
            </div>
          </CardHeader>
          <CardContent className="space-y-6 p-6">
            {/* Identity */}
            <section className="space-y-4">
              <div className="grid gap-4 lg:grid-cols-[minmax(0,1.4fr)_180px_220px]">
                <div className="space-y-2">
                  <Label htmlFor="brand-name" className="text-xs">
                    {t('brandAnalysis.field.brandName')}
                  </Label>
                  <div className="relative">
                    <Search className="pointer-events-none absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
                    <Input
                      id="brand-name"
                      value={brandName}
                      onChange={(event) => setBrandName(event.target.value)}
                      placeholder={t('brandAnalysis.field.brandNamePlaceholder')}
                      className="pl-9"
                    />
                  </div>
                </div>
                <div className="space-y-2">
                  <Label className="text-xs">{t('brandAnalysis.field.language')}</Label>
                  <Select value={language} onValueChange={(value) => setLanguage(value as 'en' | 'it')}>
                    <SelectTrigger>
                      <Languages className="mr-2 h-4 w-4 text-muted-foreground" />
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="en">English</SelectItem>
                      <SelectItem value="it">Italiano</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label className="text-xs">{t('brandAnalysis.field.account')}</Label>
                  <Select value={selectedAccount} onValueChange={setSelectedAccount}>
                    <SelectTrigger>
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
                </div>
              </div>
            </section>

            <div className="h-px w-full bg-border" />

            {/* Scope as a restrained segmented control */}
            <section className="space-y-2">
              <Label className="text-xs">{t('brandAnalysis.scope.label')}</Label>
              <div className="inline-flex rounded-md border bg-muted/40 p-0.5">
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
            </section>

            {/* ASIN list — only shown when scope is an explicit ASIN list */}
            {marketType === 'asin' ? (
              <div className="space-y-2">
                <div className="flex items-center justify-between gap-3">
                  <Label htmlFor="asin-list" className="text-xs">
                    {t('brandAnalysis.field.asinList')}
                  </Label>
                  <span className="text-xs tabular-nums text-muted-foreground">
                    {asinList.length} {t('brandAnalysis.label.asins')}
                  </span>
                </div>
                <textarea
                  id="asin-list"
                  value={asinText}
                  onChange={(event) => setAsinText(event.target.value)}
                  className="min-h-[112px] w-full resize-y rounded-md border border-input bg-background px-3 py-2 font-mono text-sm leading-6 ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                  placeholder={t('brandAnalysis.field.asinListPlaceholder')}
                />
              </div>
            ) : null}

            <div className="flex flex-wrap items-center gap-2 pt-2">
              <Button
                onClick={handleAnalyze}
                disabled={createMutation.isPending || startMutation.isPending}
                size="lg"
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
                onClick={() => {
                  setShowAdvancedUpload((value) => !value)
                  if (selectedJobId) setActiveTab('files')
                }}
              >
                <Upload className="mr-2 h-4 w-4" />
                {t('brandAnalysis.cta.uploadExternal')}
              </Button>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="border-b bg-muted/30">
            <div className="flex items-start gap-3">
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-emerald-500/10 text-emerald-600 dark:text-emerald-400">
                <ShieldCheck className="h-4 w-4" />
              </div>
              <div className="min-w-0">
                <CardTitle className="text-lg">{t('brandAnalysis.readiness.title')}</CardTitle>
                <CardDescription className="mt-1">
                  {t('brandAnalysis.readiness.description')}
                </CardDescription>
              </div>
            </div>
          </CardHeader>
          <CardContent className="space-y-2.5 p-4">
            {readinessItems.map((item) => (
              <ReadinessRow key={item.key} item={item} />
            ))}

            {missingOptional.length ? (
              <div className="mt-3 rounded-lg border bg-muted/30 p-3">
                <div className="flex items-center gap-2">
                  <Info className="h-3.5 w-3.5 text-muted-foreground" />
                  <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    {t('brandAnalysis.readiness.optionalMissing')}
                  </p>
                </div>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {missingOptional.map((field) => (
                    <Badge key={field} variant="outline" className="font-normal">
                      {field}
                    </Badge>
                  ))}
                </div>
              </div>
            ) : null}
          </CardContent>
        </Card>
      </div>

      {/* ─── Selected job: run details with tabs ──────────────────────── */}
      {selectedJobId ? (
        <Card className="overflow-hidden">
          {/* Header band */}
          <div className="border-b bg-muted/20">
            <div className="flex flex-col gap-5 p-6 lg:flex-row lg:items-start lg:justify-between">
              <div className="min-w-0 space-y-3">
                <div className="flex flex-wrap items-center gap-2">
                  <StatusPill status={currentStatus} label={statusLabel(currentStatus)} />
                  <Badge variant="outline" className="gap-1.5 font-normal">
                    {selectedJobDataSource === 'internal' ? (
                      <Database className="h-3 w-3" />
                    ) : (
                      <Upload className="h-3 w-3" />
                    )}
                    {selectedJobDataSource === 'internal'
                      ? t('brandAnalysis.mode.internal')
                      : t('brandAnalysis.mode.manual')}
                  </Badge>
                  {selectedJob?.market_type ? (
                    <Badge variant="outline" className="gap-1.5 font-normal">
                      {selectedJob.market_type === 'asin' ? (
                        <ListChecks className="h-3 w-3" />
                      ) : (
                        <Search className="h-3 w-3" />
                      )}
                      {t(`brandAnalysis.marketType.${selectedJob.market_type}`)}
                    </Badge>
                  ) : null}
                </div>
                <div>
                  <h2 className="text-2xl font-semibold leading-tight tracking-tight">
                    {selectedJob?.brand_name || selectedJobFromList?.brand_name}
                  </h2>
                  <p className="mt-1 text-sm text-muted-foreground">
                    {selectedJob?.progress_step || t(`brandAnalysis.mode.${selectedJobDataSource}.help`)}
                  </p>
                </div>

                {/* Compact at-a-glance progress; the stepper below carries step detail */}
                {isRunning ? (
                  <div className="flex max-w-2xl items-center gap-3 pt-1">
                    <Progress value={progressPct} className="h-1 flex-1" />
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
          </div>

          <CardContent className="space-y-6 p-6">
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
              <div className="space-y-3">
                <p className={eyebrow}>{t('brandAnalysis.progress.title')}</p>
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

            <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as typeof activeTab)} className="space-y-5">
              <TabsList className="bg-muted">
                <TabsTrigger value="overview" className="gap-2">
                  <LineChart className="h-3.5 w-3.5" />
                  {t('brandAnalysis.label.metricsPreview')}
                </TabsTrigger>
                <TabsTrigger value="data" className="gap-2">
                  <Database className="h-3.5 w-3.5" />
                  {t('brandAnalysis.readiness.title')}
                </TabsTrigger>
                <TabsTrigger value="files" className="gap-2">
                  <FileSpreadsheet className="h-3.5 w-3.5" />
                  {t('brandAnalysis.upload.title')}
                </TabsTrigger>
              </TabsList>

              {/* ── Overview tab ── */}
              <TabsContent value="overview" className="mt-4 space-y-6">
                {selectedJob?.metrics ? (
                  <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
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
                  <section className="grid gap-3 lg:grid-cols-3">
                    <InsightTile
                      icon={BarChart3}
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
                      icon={Search}
                      label={t('brandAnalysis.result.content')}
                      body={t('brandAnalysis.result.contentSummary', {
                        titles: contentHealth.short_title_count ?? 'N/A',
                        descriptions: contentHealth.asins_missing_description ?? 'N/A',
                      })}
                    />
                    <InsightTile
                      icon={ShieldCheck}
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
                  <section className="flex flex-wrap items-center gap-x-4 gap-y-2 rounded-lg border bg-muted/20 px-4 py-3">
                    <span className={eyebrow}>{t('brandAnalysis.action.title')}</span>
                    {recommendedActions.map((action) => (
                      <Button
                        key={action.key}
                        type="button"
                        variant="link"
                        size="sm"
                        disabled={action.disabled}
                        onClick={action.onClick}
                        className="h-auto p-0 text-sm font-medium"
                      >
                        {action.label}
                      </Button>
                    ))}
                  </section>
                ) : null}
              </TabsContent>

              {/* ── Data & capabilities tab ── */}
              <TabsContent value="data" className="mt-4 space-y-6">
                <section className="space-y-3">
                  <p className={eyebrow}>
                    {t('brandAnalysis.readiness.title')}
                  </p>
                  <div className="grid gap-2.5 md:grid-cols-2">
                    {readinessItems.map((item) => (
                      <ReadinessRow key={item.key} item={item} />
                    ))}
                  </div>
                </section>

                {hasCapabilityData ? (
                  <section className="space-y-3">
                    <p className={eyebrow}>
                      {t('brandAnalysis.readiness.capabilities')}
                    </p>
                    <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                      {capabilityKeys.map((key) => {
                        const value = capabilityMatrix[key]
                        if (value === undefined) return null
                        const Icon = capabilityIcons[key] || ShieldCheck
                        const available = !!value
                        return (
                          <div
                            key={key}
                            className={cn(
                              'flex items-center gap-3 rounded-lg border p-3 text-sm',
                              available
                                ? 'border-emerald-500/20 bg-emerald-500/[0.04] dark:bg-emerald-500/[0.06]'
                                : 'border-rose-500/20 bg-rose-500/[0.04] dark:bg-rose-500/[0.06]',
                            )}
                          >
                            <div
                              className={cn(
                                'flex h-7 w-7 shrink-0 items-center justify-center rounded-md',
                                available
                                  ? 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-300'
                                  : 'bg-rose-500/15 text-rose-700 dark:text-rose-300',
                              )}
                            >
                              <Icon className="h-3.5 w-3.5" />
                            </div>
                            <span className="flex-1 truncate text-xs font-medium">
                              {key
                                .replace(/_available$/, '')
                                .replace(/_or_inferred$/, '')
                                .replace(/_/g, ' ')}
                            </span>
                            {available ? (
                              <CheckCircle2 className="h-4 w-4 text-emerald-600 dark:text-emerald-400" />
                            ) : (
                              <AlertCircle className="h-4 w-4 text-rose-600 dark:text-rose-400" />
                            )}
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
                          <Badge
                            key={role}
                            variant="outline"
                            className="border-amber-500/40 bg-background font-mono text-[11px]"
                          >
                            {role}
                          </Badge>
                        ))}
                      </div>
                    </AlertDescription>
                  </Alert>
                ) : null}

                {limitationItems.length ? (
                  <section className="space-y-3">
                    <p className={eyebrow}>
                      {t('brandAnalysis.readiness.limitations')}
                    </p>
                    <div className="space-y-2">
                      {limitationItems.map((item, index) => (
                        <div
                          key={`${item.area}-${index}`}
                          className="flex items-start gap-3 rounded-lg border border-l-4 border-l-amber-500 bg-amber-500/[0.05] p-3 dark:bg-amber-500/[0.08]"
                        >
                          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-600 dark:text-amber-400" />
                          <div className="min-w-0 flex-1">
                            {item.area ? (
                              <p className="text-xs font-semibold uppercase tracking-wide text-amber-700 dark:text-amber-300">
                                {item.area.replace(/_/g, ' ')}
                              </p>
                            ) : null}
                            <p className="mt-0.5 text-sm leading-5 text-foreground/90">{item.message}</p>
                          </div>
                        </div>
                      ))}
                    </div>
                  </section>
                ) : null}

                {missingOptional.length ? (
                  <section className="space-y-3">
                    <p className={eyebrow}>
                      {t('brandAnalysis.readiness.optionalMissing')}
                    </p>
                    <div className="flex flex-wrap gap-1.5">
                      {missingOptional.map((field) => (
                        <Badge key={field} variant="outline" className="font-normal">
                          {field}
                        </Badge>
                      ))}
                    </div>
                  </section>
                ) : null}
              </TabsContent>

              {/* ── Files tab ── */}
              <TabsContent value="files" className="mt-4 space-y-4">
                <div className="flex items-start gap-3 rounded-lg border bg-muted/30 p-3 text-sm text-muted-foreground">
                  <Info className="mt-0.5 h-4 w-4 shrink-0" />
                  <p className="leading-5">{t('brandAnalysis.upload.description')}</p>
                </div>

                {!selectedJob ? (
                  <Alert>
                    <AlertCircle className="h-4 w-4" />
                    <AlertDescription>{t('brandAnalysis.upload.createFirst')}</AlertDescription>
                  </Alert>
                ) : null}

                <div className="grid gap-4 md:grid-cols-2">
                  {[2024, 2025].map((year) => {
                    const existing = selectedJob?.source_files.find((file) => file.year === year)
                    const file = year === 2024 ? file2024 : file2025
                    return (
                      <div
                        key={year}
                        className={cn(
                          'flex flex-col gap-4 rounded-lg border p-4',
                          existing
                            ? 'border-emerald-500/30 bg-emerald-500/[0.03] dark:bg-emerald-500/[0.06]'
                            : 'bg-card',
                        )}
                      >
                        <div className="flex items-start justify-between gap-3">
                          <div className="flex min-w-0 items-start gap-3">
                            <div
                              className={cn(
                                'flex h-10 w-10 shrink-0 items-center justify-center rounded-lg',
                                existing
                                  ? 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-300'
                                  : 'bg-muted text-muted-foreground',
                              )}
                            >
                              <FileSpreadsheet className="h-5 w-5" />
                            </div>
                            <div className="min-w-0">
                              <p className="text-sm font-semibold">
                                {t('brandAnalysis.upload.yearExport', { year })}
                              </p>
                              <p className="mt-0.5 text-xs text-muted-foreground">
                                {existing
                                  ? t('brandAnalysis.upload.fileReady', { rows: existing.row_count ?? 0 })
                                  : t('brandAnalysis.upload.fileMissing')}
                              </p>
                            </div>
                          </div>
                          <Badge variant={existing ? 'success' : 'outline'} className="shrink-0">
                            {existing
                              ? t('brandAnalysis.readiness.ready')
                              : t('brandAnalysis.readiness.missing')}
                          </Badge>
                        </div>
                        <div className="flex flex-col gap-2 sm:flex-row">
                          <Input
                            type="file"
                            accept=".csv,.xlsx,.xls"
                            disabled={!selectedJob}
                            onChange={(event) => {
                              const nextFile = event.target.files?.[0] || null
                              if (year === 2024) setFile2024(nextFile)
                              else setFile2025(nextFile)
                            }}
                            className="cursor-pointer file:mr-3 file:cursor-pointer file:rounded file:border-0 file:bg-muted file:px-2 file:py-1 file:text-xs file:font-medium hover:bg-muted/40"
                          />
                          <Button
                            type="button"
                            variant="outline"
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
          </CardContent>
        </Card>
      ) : null}

      {/* ─── Standalone upload zone (legacy fallback when no job) ─────── */}
      {showUploadZone && !selectedJobId ? (
        <Card>
          <CardHeader>
            <CardTitle>{t('brandAnalysis.upload.title')}</CardTitle>
            <CardDescription>{t('brandAnalysis.upload.description')}</CardDescription>
          </CardHeader>
          <CardContent>
            <Alert>
              <AlertCircle className="h-4 w-4" />
              <AlertDescription>{t('brandAnalysis.upload.createFirst')}</AlertDescription>
            </Alert>
          </CardContent>
        </Card>
      ) : null}

      {/* ─── History ─────────────────────────────────────────────────── */}
      <Card>
        <CardHeader className="border-b">
          <div className="flex items-start gap-3">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-muted text-muted-foreground">
              <History className="h-4 w-4" />
            </div>
            <div>
              <CardTitle className="text-lg">{t('brandAnalysis.previousAnalyses')}</CardTitle>
              <CardDescription className="mt-1">
                {t('brandAnalysis.historyDescription')}
              </CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent className="p-0">
          {jobsQuery.isLoading ? (
            <div className="flex justify-center py-10">
              <Loader2 className="h-6 w-6 animate-spin text-primary" />
            </div>
          ) : !jobsQuery.data?.length ? (
            <div className="flex flex-col items-center gap-3 py-12 text-center">
              <div className="flex h-12 w-12 items-center justify-center rounded-full bg-muted">
                <Presentation className="h-5 w-5 text-muted-foreground" />
              </div>
              <p className="max-w-sm text-sm text-muted-foreground">{t('brandAnalysis.noJobsYet')}</p>
            </div>
          ) : (
            <>
              {/* Desktop table */}
              <div className="hidden md:block">
                <div className="grid grid-cols-[1.6fr_1fr_1fr_120px_96px] items-center gap-3 border-b bg-muted/20 px-6 py-2 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                  <span>{t('brandAnalysis.field.brandName')}</span>
                  <span>{t('brandAnalysis.label.dataSource')}</span>
                  <span>{t('brandAnalysis.progress.title')}</span>
                  <span>{t('brandAnalysis.readiness.lastSync')}</span>
                  <span />
                </div>
                <ul className="divide-y">
                  {jobsQuery.data.map((job) => {
                    const isSelected = selectedJobId === job.id
                    return (
                      <li key={job.id}>
                        <div
                          role="button"
                          tabIndex={0}
                          onClick={() => setSelectedJobId(job.id)}
                          onKeyDown={(event) => {
                            if (event.key === 'Enter' || event.key === ' ') {
                              event.preventDefault()
                              setSelectedJobId(job.id)
                            }
                          }}
                          className={cn(
                            'grid w-full grid-cols-[1.6fr_1fr_1fr_120px_96px] items-center gap-3 px-6 py-3.5 text-left transition-colors hover:bg-muted/40',
                            isSelected && 'bg-primary/[0.04]',
                          )}
                        >
                          <div className="min-w-0">
                            <div className="flex flex-wrap items-center gap-2">
                              <StatusPill status={job.status} label={statusLabel(job.status)} />
                              <span className="truncate text-sm font-semibold">{job.brand_name}</span>
                            </div>
                            <p className="mt-1 text-xs text-muted-foreground">
                              {job.source_years.length
                                ? job.source_years.join(' · ')
                                : t('brandAnalysis.historyNoSourceYears')}{' '}
                              · {formatDate(job.created_at)}
                            </p>
                          </div>
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
                          <div className="min-w-0">
                            <div className="flex items-center gap-2">
                              <Progress value={job.progress_pct} className="h-1 w-20" />
                              <span className="font-mono text-xs tabular-nums text-muted-foreground">
                                {job.progress_pct}%
                              </span>
                            </div>
                          </div>
                          <div className="text-xs text-muted-foreground">
                            {job.completed_at ? formatDate(job.completed_at) : '—'}
                          </div>
                          <div className="flex items-center justify-end gap-1">
                            {job.download_ready ? (
                              <Button
                                variant="ghost"
                                size="icon"
                                className="h-8 w-8"
                                onClick={(event) => {
                                  event.stopPropagation()
                                  setSelectedJobId(job.id)
                                  brandAnalysisApi
                                    .download(job.id)
                                    .then((blob) =>
                                      downloadBlob(blob, `${job.brand_name}_brand_analysis.pptx`),
                                    )
                                }}
                                aria-label={t('brandAnalysis.cta.download')}
                              >
                                <Download className="h-4 w-4" />
                              </Button>
                            ) : null}
                            <DeleteAnalysisButton
                              brand={job.brand_name}
                              pending={deleteMutation.isPending && deleteMutation.variables === job.id}
                              onConfirm={() => deleteMutation.mutate(job.id)}
                            />
                          </div>
                        </div>
                      </li>
                    )
                  })}
                </ul>
              </div>

              {/* Mobile list */}
              <ul className="divide-y md:hidden">
                {jobsQuery.data.map((job) => (
                  <li
                    key={`m-${job.id}`}
                    className={cn(
                      'flex items-center gap-1 pr-2 transition-colors',
                      selectedJobId === job.id && 'bg-primary/[0.04]',
                    )}
                  >
                    <button
                      type="button"
                      onClick={() => setSelectedJobId(job.id)}
                      className="flex flex-1 flex-col gap-2 px-4 py-3 text-left transition-colors hover:bg-muted/40"
                    >
                      <div className="flex items-center gap-2">
                        <StatusPill status={job.status} label={statusLabel(job.status)} />
                        <span className="truncate text-sm font-semibold">{job.brand_name}</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <Progress value={job.progress_pct} className="h-1 flex-1" />
                        <span className="font-mono text-xs tabular-nums text-muted-foreground">
                          {job.progress_pct}%
                        </span>
                      </div>
                      <p className="text-xs text-muted-foreground">
                        {t(`brandAnalysis.mode.${modeToDataSource(job.mode)}`)} ·{' '}
                        {formatDate(job.created_at)}
                      </p>
                    </button>
                    <DeleteAnalysisButton
                      brand={job.brand_name}
                      pending={deleteMutation.isPending && deleteMutation.variables === job.id}
                      onConfirm={() => deleteMutation.mutate(job.id)}
                    />
                  </li>
                ))}
              </ul>
            </>
          )}
        </CardContent>
      </Card>
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
        <Button type="button" variant="outline" disabled={pending}>
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
        'rounded px-3 py-1.5 text-sm font-medium transition-colors',
        active
          ? 'bg-background text-foreground shadow-sm'
          : 'text-muted-foreground hover:text-foreground',
      )}
    >
      {label}
    </button>
  )
}

function ReadinessRow({
  item,
}: {
  item: {
    icon: typeof Database
    title: string
    state: ReadinessState
    label: string
    detail: string
  }
}) {
  const Icon = item.icon
  return (
    <div
      className={cn(
        'flex items-start gap-3 rounded-lg border border-l-4 p-3 transition-colors',
        readinessTone[item.state],
      )}
    >
      <Icon className={cn('mt-0.5 h-4 w-4 shrink-0', readinessIconTone[item.state])} />
      <div className="min-w-0 flex-1 space-y-1">
        <div className="flex items-center justify-between gap-3">
          <p className="text-sm font-semibold">{item.title}</p>
          <ReadinessBadge state={item.state} label={item.label} />
        </div>
        <p className="text-xs leading-5 text-muted-foreground">{item.detail}</p>
      </div>
    </div>
  )
}

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
    <ol className="grid gap-2 sm:grid-cols-3 lg:grid-cols-9">
      {steps.map((step, index) => {
        const isDone = completed || currentPct >= step.pct
        const prevPct = index === 0 ? 0 : steps[index - 1].pct
        const isActive = !completed && isRunning && currentPct < step.pct && currentPct >= prevPct - 4
        return (
          <li key={step.key}>
            <div
              className={cn(
                'flex h-full items-start gap-2 rounded-lg border px-2.5 py-2 transition-all',
                isDone
                  ? 'border-emerald-500/30 bg-emerald-500/[0.06] dark:bg-emerald-500/[0.1]'
                  : isActive
                    ? 'border-primary/40 bg-primary/[0.06] shadow-[0_0_0_3px_hsl(var(--primary)/0.08)]'
                    : 'border-dashed border-border bg-background',
              )}
            >
              <span
                className={cn(
                  'mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full',
                  isDone
                    ? 'bg-emerald-500 text-white'
                    : isActive
                      ? 'bg-primary text-primary-foreground'
                      : 'bg-muted text-muted-foreground',
                )}
              >
                {isDone ? (
                  <CheckCircle2 className="h-3 w-3" />
                ) : isActive ? (
                  <Loader2 className="h-3 w-3 animate-spin" />
                ) : (
                  <Circle className="h-2 w-2 fill-current" />
                )}
              </span>
              <span
                className={cn(
                  'text-[11px] font-medium leading-4',
                  isDone
                    ? 'text-emerald-800 dark:text-emerald-200'
                    : isActive
                      ? 'text-foreground'
                      : 'text-muted-foreground',
                )}
              >
                {step.label}
              </span>
            </div>
          </li>
        )
      })}
    </ol>
  )
}

function InsightTile({
  icon: Icon,
  label,
  body,
}: {
  icon: typeof Database
  label: string
  body: string
}) {
  return (
    <div className="flex h-full flex-col gap-2 rounded-lg border bg-card p-4">
      <div className="flex items-center gap-2">
        <div className="flex h-7 w-7 items-center justify-center rounded-md bg-muted text-muted-foreground">
          <Icon className="h-3.5 w-3.5" />
        </div>
        <p className="text-sm font-semibold">{label}</p>
      </div>
      <p className="text-sm leading-6 text-muted-foreground">{body}</p>
    </div>
  )
}

function EmptyHint({ title, body }: { title: string; body: string }) {
  return (
    <div className="flex flex-col items-center gap-1.5 rounded-lg border border-dashed bg-muted/20 px-6 py-10 text-center">
      <p className="text-sm font-semibold">{title}</p>
      <p className="max-w-xs text-xs leading-5 text-muted-foreground">{body}</p>
    </div>
  )
}
