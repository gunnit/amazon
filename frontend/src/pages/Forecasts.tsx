import { useEffect, useMemo, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import axios from 'axios'
import {
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Area,
  ComposedChart,
  ReferenceLine,
} from 'recharts'
import {
  TrendingUp,
  RefreshCw,
  Loader2,
  Calendar,
  Target,
  Download,
  AlertTriangle,
  ChevronDown,
  ChevronUp,
  Info,
  Eye,
  EyeOff,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Progress } from '@/components/ui/progress'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useToast } from '@/components/ui/use-toast'
import { forecastsApi, accountsApi, exportsApi } from '@/services/api'
import { formatCurrency, formatDate, downloadBlob } from '@/lib/utils'
import { CHART_PRIMARY } from '@/lib/chart-theme'
import { useTranslation } from '@/i18n'
import { useLanguageStore } from '@/store/languageStore'
import type {
  Forecast,
  ForecastConfidenceLevel,
  AmazonAccount,
  ForecastExportJob,
  ForecastProductOption,
} from '@/types'

const ALL_ASINS_VALUE = '__all_asins__'

type TemplateType = 'clean' | 'corporate' | 'executive'

const TEMPLATE_CONFIGS: {
  id: TemplateType
  nameKey: string
  descKey: string
  headerColor: string
  rowColors: [string, string]
  accentColor: string
}[] = [
  {
    id: 'clean',
    nameKey: 'export.templateClean',
    descKey: 'export.templateCleanDesc',
    headerColor: '#F0F0F0',
    rowColors: ['#FFFFFF', '#F9F9F9'],
    accentColor: '#333333',
  },
  {
    id: 'corporate',
    nameKey: 'export.templateCorporate',
    descKey: 'export.templateCorporateDesc',
    headerColor: '#1F4E79',
    rowColors: ['#FFFFFF', '#D6E4F0'],
    accentColor: '#1F4E79',
  },
  {
    id: 'executive',
    nameKey: 'export.templateExecutive',
    descKey: 'export.templateExecutiveDesc',
    headerColor: '#1B2631',
    rowColors: ['#FFFFFF', '#EAECEE'],
    accentColor: '#F39C12',
  },
]

const DATA_QUALITY_NOTE_KEYS: Record<string, string> = {
  'Less than 28 days of data': 'forecasts.note.lessThan28Days',
  'Less than 90 days of data': 'forecasts.note.lessThan90Days',
  'High variance detected': 'forecasts.note.highVariance',
  'Using simplified model due to limited history': 'forecasts.note.simpleModel',
  'Historical validation error is high': 'forecasts.note.highValidationError',
  'Monthly vendor data — values represent calendar months, not days': 'forecasts.note.monthlyData',
  'Short history — fewer than 12 months limits reliability': 'forecasts.note.shortMonthlyHistory',
  'Less than 24 months of history': 'forecasts.note.lessThan24Months',
  'High month-to-month variability lowers reliability': 'forecasts.note.highMonthlyVariability',
  'Latest data is over a month old — forecast starts from the current month': 'forecasts.note.staleData',
  'Historical validation unavailable': 'forecasts.note.validationUnavailable',
}

// Notes that signal the forecast itself is not trustworthy (short/volatile
// history). When present alongside low confidence we show an honest
// "insufficient data" explanation rather than just a bare low number.
const INSUFFICIENT_DATA_NOTES = new Set<string>([
  'Short history — fewer than 12 months limits reliability',
  'High month-to-month variability lowers reliability',
  'Less than 28 days of data',
  'High variance detected',
])

function isMonthlyForecast(forecast?: Forecast | null): boolean {
  if (!forecast || forecast.predictions.length < 2) {
    return forecast?.model_used === 'monthly'
  }
  const a = new Date(`${forecast.predictions[0].date}T00:00:00`)
  const b = new Date(`${forecast.predictions[1].date}T00:00:00`)
  const gapDays = Math.abs((b.getTime() - a.getTime()) / 86_400_000)
  return gapDays >= 20 || forecast.model_used === 'monthly'
}

const CONFIDENCE_BADGE_VARIANTS: Record<ForecastConfidenceLevel, 'success' | 'warning' | 'destructive'> = {
  high: 'success',
  medium: 'warning',
  low: 'destructive',
}

function getForecastConfidenceLevel(forecast?: Forecast | null): ForecastConfidenceLevel | null {
  if (!forecast) return null
  if (forecast.confidence_level === 'high' || forecast.confidence_level === 'medium' || forecast.confidence_level === 'low') {
    return forecast.confidence_level
  }
  if (forecast.mape == null) return null
  if (forecast.mape < 15) return 'high'
  if (forecast.mape < 30) return 'medium'
  return 'low'
}

function TemplatePreview({ config }: { config: (typeof TEMPLATE_CONFIGS)[number] }) {
  const isLight = (hex: string) => {
    const r = parseInt(hex.slice(1, 3), 16)
    const g = parseInt(hex.slice(3, 5), 16)
    const b = parseInt(hex.slice(5, 7), 16)
    return r * 0.299 + g * 0.587 + b * 0.114 > 150
  }
  const headerTextColor = isLight(config.headerColor) ? '#333333' : '#FFFFFF'

  return (
    <div className="w-full rounded overflow-hidden border border-border/50">
      <div
        className="h-5 flex items-center px-1.5 gap-1"
        style={{ backgroundColor: config.headerColor }}
      >
        {[1, 2, 3].map((i) => (
          <div
            key={i}
            className="h-2 rounded-sm flex-1"
            style={{ backgroundColor: headerTextColor, opacity: 0.6 }}
          />
        ))}
      </div>
      {[0, 1, 2].map((i) => (
        <div
          key={i}
          className="h-3.5 flex items-center px-1.5 gap-1"
          style={{ backgroundColor: config.rowColors[i % 2] }}
        >
          {[1, 2, 3].map((j) => (
            <div
              key={j}
              className="h-1.5 rounded-sm flex-1"
              style={{
                backgroundColor: j === 1 && i === 0 ? config.accentColor : '#CBD5E1',
                opacity: j === 1 && i === 0 ? 0.7 : 0.35,
              }}
            />
          ))}
        </div>
      ))}
    </div>
  )
}

// The AI insights step depends on Anthropic; surface a friendly message when
// the key is missing or the account is out of credit instead of a raw detail.
function isAnthropicUnavailable(detail?: string | null): boolean {
  if (!detail) return false
  const text = detail.toLowerCase()
  return text.includes('anthropic_api_key') || text.includes('credit balance too low')
}

// ── Forecast Export Modal ──
function ForecastExportModal({
  open,
  onOpenChange,
  forecast,
  accountName,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  forecast: Forecast
  accountName: string
}) {
  const { t } = useTranslation()
  const { toast } = useToast()
  const { language: appLang } = useLanguageStore()
  const [language, setLanguage] = useState<'en' | 'it'>(appLang)
  const [selectedTemplate, setSelectedTemplate] = useState<TemplateType>('corporate')
  const [includeInsights, setIncludeInsights] = useState(false)
  const [isExporting, setIsExporting] = useState(false)
  const [activeJobId, setActiveJobId] = useState<string | null>(null)
  const [hasDownloadedPackage, setHasDownloadedPackage] = useState(false)
  const [aiUnavailable, setAiUnavailable] = useState(false)

  const resetExportState = () => {
    setIsExporting(false)
    setActiveJobId(null)
    setHasDownloadedPackage(false)
    setAiUnavailable(false)
  }

  useEffect(() => {
    if (!open) {
      resetExportState()
    }
  }, [open])

  const packageStatusQuery = useQuery<ForecastExportJob>({
    queryKey: ['forecast-export-package', activeJobId],
    queryFn: () => exportsApi.getForecastPackage(activeJobId!),
    enabled: !!activeJobId,
    refetchInterval: (query) => {
      const status = query.state.data?.status
      if (status === 'pending' || status === 'processing') return 1500
      return false
    },
  })

  useEffect(() => {
    const job = packageStatusQuery.data
    if (!job || job.status !== 'completed' || hasDownloadedPackage || !activeJobId) return

    let cancelled = false
    const downloadPackage = async () => {
      try {
        const blob = await exportsApi.downloadForecastPackage(activeJobId)
        if (cancelled) return

        const safeName = accountName.replace(/[^a-zA-Z0-9_-]/g, '_')
        const today = new Date().toISOString().split('T')[0]
        downloadBlob(
          blob,
          `inthezon_forecast_package_${safeName}_${forecast.forecast_type}_${forecast.horizon_days}d_${today}.zip`
        )
        setHasDownloadedPackage(true)
        toast({ title: t('forecasts.exportZipSuccess') })
        onOpenChange(false)
      } catch (error) {
        if (cancelled) return
        const description = axios.isAxiosError(error)
          ? error.response?.data?.detail
          : undefined
        toast({
          variant: 'destructive',
          title: t('forecasts.exportPackageFailed'),
          ...(description ? { description } : {}),
        })
        setIsExporting(false)
      }
    }

    void downloadPackage()
    return () => {
      cancelled = true
    }
  }, [activeJobId, accountName, forecast.forecast_type, forecast.horizon_days, hasDownloadedPackage, onOpenChange, packageStatusQuery.data, t, toast])

  const handleExport = async () => {
    setIsExporting(true)
    setAiUnavailable(false)
    if (!includeInsights) {
      try {
        const blob = await exportsApi.exportForecastExcel({
          forecast_id: forecast.id,
          template: selectedTemplate,
          language,
        })

        const safeName = accountName.replace(/[^a-zA-Z0-9_-]/g, '_')
        const today = new Date().toISOString().split('T')[0]
        downloadBlob(blob, `inthezon_forecast_${safeName}_${forecast.forecast_type}_${forecast.horizon_days}d_${selectedTemplate}_${today}_${language}.xlsx`)
        toast({ title: t('export.success') })
        onOpenChange(false)
      } catch {
        toast({
          variant: 'destructive',
          title: t('reports.exportFailed'),
          description: t('reports.exportFailedDesc'),
        })
      } finally {
        setIsExporting(false)
      }
      return
    }

    try {
      const job = await exportsApi.createForecastPackage({
        forecast_id: forecast.id,
        template: selectedTemplate,
        language,
        include_insights: true,
      })
      setActiveJobId(job.id)
    } catch (error) {
      const description = axios.isAxiosError(error)
        ? error.response?.data?.detail
        : undefined
      if (isAnthropicUnavailable(description)) {
        setAiUnavailable(true)
        setIsExporting(false)
        return
      }
      toast({
        variant: 'destructive',
        title: t('forecasts.exportPackageFailed'),
        ...(description ? { description } : {}),
      })
      setIsExporting(false)
    }
  }

  useEffect(() => {
    if (packageStatusQuery.data?.status === 'failed') {
      const errorMessage = packageStatusQuery.data.error_message
      if (isAnthropicUnavailable(errorMessage)) {
        setAiUnavailable(true)
        setIsExporting(false)
        return
      }
      toast({
        variant: 'destructive',
        title: t('forecasts.exportPackageFailed'),
        ...(errorMessage ? { description: errorMessage } : {}),
      })
      setIsExporting(false)
    }
  }, [packageStatusQuery.data?.error_message, packageStatusQuery.data?.status, t, toast])

  const progressVisible = includeInsights && isExporting
  const progressValue = packageStatusQuery.data?.progress_pct ?? 0

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[600px]">
        <DialogHeader>
          <DialogTitle>{t('forecasts.exportTitle')}</DialogTitle>
          <DialogDescription>{t('forecasts.exportSubtitle')}</DialogDescription>
        </DialogHeader>

        <div className="space-y-5 py-2">
          {/* Template Selection */}
          <div className="space-y-2">
            <label className="text-sm font-medium">{t('export.template')}</label>
            <div className="grid grid-cols-3 gap-3">
              {TEMPLATE_CONFIGS.map((tmpl) => (
                <button
                  key={tmpl.id}
                  type="button"
                  onClick={() => setSelectedTemplate(tmpl.id)}
                  className={`rounded-lg border-2 p-2.5 text-left transition-all hover:shadow-sm ${
                    selectedTemplate === tmpl.id
                      ? 'border-primary bg-primary/5 shadow-sm'
                      : 'border-border hover:border-border/80'
                  }`}
                >
                  <TemplatePreview config={tmpl} />
                  <div className="mt-2">
                    <p className="text-xs font-medium">{t(tmpl.nameKey)}</p>
                    <p className="text-[10px] text-muted-foreground leading-tight mt-0.5">
                      {t(tmpl.descKey)}
                    </p>
                  </div>
                </button>
              ))}
            </div>
          </div>

          {/* Language Selection */}
          <div className="space-y-2">
            <label className="text-sm font-medium">{t('export.language')}</label>
            <Select value={language} onValueChange={(v) => setLanguage(v as 'en' | 'it')}>
              <SelectTrigger className="h-9">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="en">English</SelectItem>
                <SelectItem value="it">Italiano</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="rounded-lg border p-3 space-y-2">
            <div className="flex items-start gap-3">
              <Checkbox
                id="forecast-export-insights"
                checked={includeInsights}
                onCheckedChange={(checked) => setIncludeInsights(checked === true)}
                disabled={isExporting}
              />
              <div className="space-y-1">
                <label htmlFor="forecast-export-insights" className="text-sm font-medium cursor-pointer">
                  {t('forecasts.exportWithInsights')}
                </label>
                <p className="text-xs text-muted-foreground">
                  {t('forecasts.exportWithInsightsDesc')}
                </p>
              </div>
            </div>

            {aiUnavailable && (
              <Alert variant="warning" className="mt-1">
                <AlertTriangle className="h-4 w-4" />
                <AlertDescription>{t('forecasts.exportAiUnavailable')}</AlertDescription>
              </Alert>
            )}
          </div>

          {/* Preview summary */}
          <div className="rounded-lg border bg-muted/50 p-3 space-y-1 text-xs text-muted-foreground">
            <p><span className="font-medium text-foreground">{t('forecasts.account')}:</span> {accountName}</p>
            {forecast.asin && (
              <p><span className="font-medium text-foreground">ASIN:</span> {forecast.asin}</p>
            )}
            <p><span className="font-medium text-foreground">{t('forecasts.model')}:</span> {forecast.model_used}</p>
            <p><span className="font-medium text-foreground">{t('forecasts.horizonLabel')}:</span> {isMonthlyForecast(forecast)
              ? t('forecasts.byAsin.monthsValue', { months: Math.max(1, Math.round((forecast.horizon_days ?? 30) / 30)) })
              : t('forecasts.byAsin.daysValue', { days: forecast.horizon_days })}</p>
            <p><span className="font-medium text-foreground">{t('forecasts.predictedTotal')}:</span> {formatCurrency(forecast.predictions.reduce((s, p) => s + p.predicted_value, 0))}</p>
          </div>

          {progressVisible && (
            <div className="rounded-lg border bg-background p-4 space-y-3">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="text-sm font-medium">{t('forecasts.exportProgressTitle')}</p>
                  <p className="text-xs text-muted-foreground">
                    {packageStatusQuery.data?.progress_step || t('forecasts.exportProgressDesc')}
                  </p>
                </div>
                <div className="text-sm font-medium">{progressValue}%</div>
              </div>
              <Progress value={progressValue} className="h-2" />
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={isExporting}>
            {t('common.cancel')}
          </Button>
          <Button onClick={handleExport} disabled={isExporting}>
            {isExporting ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                {includeInsights ? t('forecasts.exportProgressTitle') : t('export.exporting')}
              </>
            ) : (
              <>
                <Download className="mr-2 h-4 w-4" />
                {t('export.download')}
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export default function Forecasts() {
  const [selectedAccount, setSelectedAccount] = useState<string>('')
  const [forecastHorizon, setForecastHorizon] = useState('30')
  const [selectedAsin, setSelectedAsin] = useState(ALL_ASINS_VALUE)
  const [displayedForecastId, setDisplayedForecastId] = useState<string | null>(null)
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { t } = useTranslation()
  const { language: appLang } = useLanguageStore()
  const [exportModalOpen, setExportModalOpen] = useState(false)
  const [predictionTableOpen, setPredictionTableOpen] = useState(false)
  const [showAllPredictions, setShowAllPredictions] = useState(false)
  const [showConfidenceBands, setShowConfidenceBands] = useState(true)
  const [pastedAsin, setPastedAsin] = useState('')

  const { data: accounts } = useQuery<AmazonAccount[]>({
    queryKey: ['accounts'],
    queryFn: () => accountsApi.list(),
  })

  const { data: forecasts, isLoading } = useQuery<Forecast[]>({
    queryKey: ['forecasts'],
    queryFn: () => forecastsApi.list(),
  })

  const { data: products, isLoading: productsLoading } = useQuery<ForecastProductOption[]>({
    queryKey: ['forecast-products', selectedAccount],
    queryFn: () => forecastsApi.getAvailableProducts(selectedAccount),
    enabled: !!selectedAccount,
  })

  const generateMutation = useMutation({
    mutationFn: (params: { account_id: string; horizon_days: number; asin?: string }) =>
      forecastsApi.generate(params),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['forecasts'] })
      setDisplayedForecastId(null)
      toast({ title: t('forecasts.generateSuccess') })
    },
    onError: (error) => {
      const description = axios.isAxiosError(error)
        ? error.response?.data?.detail
        : undefined
      toast({
        variant: 'destructive',
        title: t('forecasts.generateFailed'),
        ...(description ? { description } : {}),
      })
    },
  })

  const handleGenerate = () => {
    if (!selectedAccount) {
      toast({
        variant: 'destructive',
        title: t('forecasts.selectAccountError'),
      })
      return
    }

    // A pasted ASIN overrides the dropdown so users can forecast a product that
    // is not (yet) in the eligible list.
    const typedAsin = pastedAsin.trim().toUpperCase()
    if (typedAsin && !/^[A-Z0-9]{10}$/.test(typedAsin)) {
      toast({ variant: 'destructive', title: t('forecasts.asinInvalid') })
      return
    }
    const asin = typedAsin || (selectedAsin !== ALL_ASINS_VALUE ? selectedAsin : undefined)

    generateMutation.mutate({
      account_id: selectedAccount,
      horizon_days: parseInt(forecastHorizon),
      ...(asin ? { asin } : {}),
    })
  }

  // Resolve which forecast to display: user-selected row, else the latest one.
  const latestForecast = useMemo(() => {
    if (!forecasts || forecasts.length === 0) return undefined
    if (displayedForecastId) {
      const match = forecasts.find((f) => f.id === displayedForecastId)
      if (match) return match
    }
    return forecasts[0]
  }, [forecasts, displayedForecastId])
  const availableProducts = products ?? []
  const confidenceLevel = useMemo(
    () => getForecastConfidenceLevel(latestForecast),
    [latestForecast]
  )
  const confidenceBadgeVariant = confidenceLevel
    ? CONFIDENCE_BADGE_VARIANTS[confidenceLevel]
    : 'outline'
  const rawNotes = useMemo(
    () => latestForecast?.data_quality_notes ?? [],
    [latestForecast?.data_quality_notes]
  )
  const dataQualityNotes = useMemo(
    () =>
      rawNotes.map(
        (note) => DATA_QUALITY_NOTE_KEYS[note] ? t(DATA_QUALITY_NOTE_KEYS[note]) : note
      ),
    [rawNotes, t]
  )
  const isMonthly = useMemo(() => isMonthlyForecast(latestForecast), [latestForecast])
  const monthsCount = useMemo(
    () => Math.max(1, Math.round((latestForecast?.horizon_days ?? 30) / 30)),
    [latestForecast?.horizon_days]
  )
  // Honest "insufficient data" state: low confidence backed by a short/volatile
  // history note (not just a bare low MAPE the user can't interpret).
  const insufficientReasons = useMemo(
    () => rawNotes.filter((n) => INSUFFICIENT_DATA_NOTES.has(n)),
    [rawNotes]
  )
  const showInsufficientState = confidenceLevel === 'low' && insufficientReasons.length > 0
  const visiblePredictions = useMemo(
    () =>
      latestForecast
        ? (showAllPredictions ? latestForecast.predictions : latestForecast.predictions.slice(0, 30))
        : [],
    [latestForecast, showAllPredictions]
  )

  useEffect(() => {
    setPredictionTableOpen(false)
    setShowAllPredictions(false)
  }, [latestForecast?.id])

  // Combine historical + prediction data for the chart
  const chartData = useMemo(() => {
    if (!latestForecast) return []

    const historical = (latestForecast.historical_data || []).map((h) => ({
      date: h.date,
      historical_value: h.value,
      predicted_value: null as number | null,
      ci_base: null as number | null,
      ci_range: null as number | null,
      upper_bound: null as number | null,
      lower_bound: null as number | null,
    }))

    const predictions = latestForecast.predictions.map((p) => ({
      date: p.date,
      historical_value: null as number | null,
      predicted_value: p.predicted_value,
      ci_base: p.lower_bound,
      ci_range: p.upper_bound - p.lower_bound,
      upper_bound: p.upper_bound,
      lower_bound: p.lower_bound,
    }))

    // Connect the two series at the transition point
    if (historical.length > 0 && predictions.length > 0) {
      const lastHist = historical[historical.length - 1]
      predictions[0].historical_value = lastHist.historical_value
    }

    return [...historical, ...predictions]
  }, [latestForecast])

  // Find the transition date for the ReferenceLine
  const transitionDate = useMemo(() => {
    if (!latestForecast?.historical_data?.length) return null
    const hist = latestForecast.historical_data
    return hist[hist.length - 1].date
  }, [latestForecast])

  // Custom tooltip component
  const CustomTooltip = ({ active, payload, label }: any) => {
    if (!active || !payload?.length) return null

    const histVal = payload.find((p: any) => p.dataKey === 'historical_value')?.value
    const predVal = payload.find((p: any) => p.dataKey === 'predicted_value')?.value
    const upperVal = payload.find((p: any) => p.dataKey === 'ci_range')
    const lowerBound = payload.find((p: any) => p.dataKey === 'ci_base')?.value

    return (
      <div className="rounded-lg border bg-background p-3 shadow-md">
        <p className="text-sm font-medium text-foreground mb-1.5">{formatDate(label)}</p>
        {histVal != null && (
          <div className="flex items-center gap-2 text-sm">
            <span className="inline-block w-3 h-0.5 bg-muted-foreground rounded" />
            <span className="text-muted-foreground">{t('forecasts.sales')}:</span>
            <span className="font-medium">{formatCurrency(histVal)}</span>
          </div>
        )}
        {predVal != null && (
          <>
            <div className="flex items-center gap-2 text-sm">
              <span className="inline-block w-3 h-0.5 bg-primary rounded" />
              <span className="text-muted-foreground">{t('forecasts.forecast')}:</span>
              <span className="font-medium">{formatCurrency(predVal)}</span>
            </div>
            {lowerBound != null && upperVal?.value != null && (
              <div className="flex items-center gap-2 text-sm mt-0.5">
                <span className="inline-block w-3 h-3 rounded-sm bg-primary/15" />
                <span className="text-muted-foreground">{t('forecasts.range')}:</span>
                <span className="font-medium">
                  {formatCurrency(lowerBound)} – {formatCurrency(lowerBound + upperVal.value)}
                </span>
              </div>
            )}
          </>
        )}
      </div>
    )
  }

  // Adaptive Y-axis formatter
  const yAxisFormatter = (value: number) => {
    if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`
    if (value >= 1_000) return `${(value / 1_000).toFixed(0)}k`
    return `${value}`
  }

  const formatPredictionDate = (value: string) => {
    const locale = appLang === 'it' ? 'it-IT' : 'en-US'
    return new Date(`${value}T00:00:00`).toLocaleDateString(locale, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    })
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">{t('forecasts.title')}</h1>
          <p className="text-muted-foreground">
            {t('forecasts.subtitle')}
          </p>
        </div>
      </div>

      {/* Generate Forecast */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Target className="h-5 w-5" />
            {t('forecasts.generateTitle')}
          </CardTitle>
          <CardDescription>
            {t('forecasts.generateDesc')}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap items-end gap-4">
            <div className="space-y-2">
              <label className="text-sm font-medium">{t('forecasts.account')}</label>
              <Select
                value={selectedAccount}
                onValueChange={(value) => {
                  setSelectedAccount(value)
                  setSelectedAsin(ALL_ASINS_VALUE)
                  setPastedAsin('')
                }}
              >
                <SelectTrigger className="w-[200px]">
                  <SelectValue placeholder={t('forecasts.selectAccount')} />
                </SelectTrigger>
                <SelectContent>
                  {accounts?.map((account) => (
                    <SelectItem key={account.id} value={account.id}>
                      {account.account_name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium flex items-center gap-1">
                {t('forecasts.asinOptional')}
                <span
                  className="text-muted-foreground"
                  title={t('forecasts.allAsinsTooltip')}
                  aria-label={t('forecasts.allAsinsTooltip')}
                >
                  <Info className="h-3.5 w-3.5" />
                </span>
              </label>
              <Select
                value={selectedAsin}
                onValueChange={setSelectedAsin}
                disabled={!selectedAccount || productsLoading}
              >
                <SelectTrigger className="w-[280px]">
                  {productsLoading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
                  <SelectValue placeholder={t('forecasts.selectAsin')} />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={ALL_ASINS_VALUE}>
                    {t('forecasts.allAsins')}
                  </SelectItem>
                  {availableProducts.length > 0 ? (
                    availableProducts.map((product) => {
                      const eligible = product.is_eligible !== false
                      const reason = product.ineligible_reason || undefined
                      const titleText = product.title
                        ? product.title.length > 50
                          ? product.title.slice(0, 50) + '\u2026'
                          : product.title
                        : product.asin
                      return (
                        <SelectItem
                          key={product.asin}
                          value={product.asin}
                          disabled={!eligible}
                          title={eligible ? undefined : reason}
                        >
                          <span className="font-mono text-xs mr-2">{product.asin}</span>
                          <span className="truncate">
                            {titleText}
                            {!eligible && (
                              <span className="ml-2 text-xs text-muted-foreground">
                                {'\u00b7'} {t('forecasts.notEnoughHistory', {
                                  days: product.history_days,
                                })}
                              </span>
                            )}
                          </span>
                        </SelectItem>
                      )
                    })
                  ) : (
                    <SelectItem value="__no_asins__" disabled>
                      {selectedAccount
                        ? t('forecasts.noAsinsAvailable')
                        : t('forecasts.selectAccount')}
                    </SelectItem>
                  )}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium" htmlFor="forecast-asin-paste">
                {t('forecasts.asinPasteLabel')}
              </label>
              <input
                id="forecast-asin-paste"
                type="text"
                value={pastedAsin}
                onChange={(e) => setPastedAsin(e.target.value)}
                placeholder={t('forecasts.asinPastePlaceholder')}
                spellCheck={false}
                autoComplete="off"
                disabled={!selectedAccount}
                className="flex h-10 w-[180px] rounded-md border border-input bg-background px-3 py-2 font-mono text-sm uppercase ring-offset-background placeholder:text-muted-foreground placeholder:font-sans placeholder:normal-case focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
              />
              <p className="text-xs text-muted-foreground max-w-[180px]">
                {t('forecasts.asinPasteHint')}
              </p>
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium">{t('forecasts.horizon')}</label>
              <Select value={forecastHorizon} onValueChange={setForecastHorizon}>
                <SelectTrigger className="w-[150px]">
                  <Calendar className="mr-2 h-4 w-4" />
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="30">{t('forecasts.30days')}</SelectItem>
                  <SelectItem value="60">{t('forecasts.60days')}</SelectItem>
                  <SelectItem value="90">{t('forecasts.90days')}</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <Button
              onClick={handleGenerate}
              disabled={generateMutation.isPending || !selectedAccount}
            >
              {generateMutation.isPending ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <RefreshCw className="mr-2 h-4 w-4" />
              )}
              {t('forecasts.generate')}
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Forecast Display */}
      {isLoading ? (
        <div className="flex items-center justify-center h-64">
          <Loader2 className="h-8 w-8 animate-spin text-primary" />
        </div>
      ) : latestForecast ? (
        <div className="grid gap-4 md:grid-cols-3">
          <div className="space-y-4 md:col-span-2">
            {/* Forecast Chart */}
            <Card>
              <CardHeader>
                <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                  <div className="space-y-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <CardTitle>{t('forecasts.salesForecast')}</CardTitle>
                      {confidenceLevel && (
                        <Badge variant={confidenceBadgeVariant}>
                          {t(`forecasts.confidence.${confidenceLevel}`)}
                        </Badge>
                      )}
                      {isMonthly && (
                        <Badge variant="outline">{t('forecasts.monthlyCadence')}</Badge>
                      )}
                    </div>
                    <CardDescription>
                      {isMonthly
                        ? t('forecasts.predictionDescMonthly', {
                            months: monthsCount,
                            model: latestForecast.model_used,
                          })
                        : t('forecasts.predictionDesc', {
                            days: latestForecast.horizon_days,
                            model: latestForecast.model_used,
                          })}
                    </CardDescription>
                  </div>
                  <div className="flex items-center gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setExportModalOpen(true)}
                    >
                      <Download className="mr-1 h-4 w-4" />
                      {t('export.button')}
                    </Button>
                    <Button
                      variant={showConfidenceBands ? 'secondary' : 'outline'}
                      size="sm"
                      aria-pressed={showConfidenceBands}
                      title={t('forecasts.toggleBands')}
                      onClick={() => setShowConfidenceBands((v) => !v)}
                    >
                      {showConfidenceBands ? (
                        <Eye className="mr-1 h-4 w-4" />
                      ) : (
                        <EyeOff className="mr-1 h-4 w-4" />
                      )}
                      {(latestForecast.confidence_interval * 100).toFixed(0)}% CI
                    </Button>
                  </div>
                </div>
              </CardHeader>
              <CardContent>
                {showInsufficientState ? (
                  <Alert variant="warning" className="mb-4">
                    <AlertTriangle className="h-4 w-4" />
                    <AlertTitle>{t('forecasts.insufficientTitle')}</AlertTitle>
                    <AlertDescription>
                      <p>{t('forecasts.insufficientDesc')}</p>
                      <ul className="mt-2 list-disc space-y-0.5 pl-5">
                        {insufficientReasons.map((note) => (
                          <li key={note}>
                            {DATA_QUALITY_NOTE_KEYS[note] ? t(DATA_QUALITY_NOTE_KEYS[note]) : note}
                          </li>
                        ))}
                      </ul>
                    </AlertDescription>
                  </Alert>
                ) : confidenceLevel === 'low' ? (
                  <Alert variant="warning" className="mb-4">
                    <AlertTriangle className="h-4 w-4" />
                    <AlertTitle>{t('forecasts.lowConfidenceTitle')}</AlertTitle>
                    <AlertDescription>{t('forecasts.lowConfidenceWarning')}</AlertDescription>
                  </Alert>
                ) : null}
                <div className="h-[400px]">
                  <ResponsiveContainer width="100%" height="100%">
                    <ComposedChart data={chartData}>
                      <CartesianGrid strokeDasharray="3 3" strokeOpacity={0.3} />
                      <XAxis
                        dataKey="date"
                        tickFormatter={(value) => {
                          const locale = appLang === 'it' ? 'it-IT' : 'en-US'
                          return new Date(value + 'T00:00:00').toLocaleDateString(locale, {
                            month: 'short',
                            day: 'numeric',
                          })
                        }}
                        tick={{ fontSize: 12 }}
                      />
                      <YAxis
                        tickFormatter={yAxisFormatter}
                        tick={{ fontSize: 12 }}
                        width={50}
                      />
                      <Tooltip content={<CustomTooltip />} />
                      {showConfidenceBands && (
                        <Area
                          type="monotone"
                          dataKey="ci_base"
                          stackId="ci"
                          stroke="none"
                          fill="transparent"
                          connectNulls={false}
                        />
                      )}
                      {showConfidenceBands && (
                        <Area
                          type="monotone"
                          dataKey="ci_range"
                          stackId="ci"
                          stroke="none"
                          fill={CHART_PRIMARY}
                          fillOpacity={0.14}
                          connectNulls={false}
                        />
                      )}
                      <Line
                        type="monotone"
                        dataKey="historical_value"
                        stroke="hsl(var(--muted-foreground))"
                        strokeWidth={2}
                        dot={false}
                        connectNulls={false}
                      />
                      <Line
                        type="monotone"
                        dataKey="predicted_value"
                        stroke={CHART_PRIMARY}
                        strokeWidth={2}
                        dot={false}
                        connectNulls={false}
                      />
                      {transitionDate && (
                        <ReferenceLine
                          x={transitionDate}
                          stroke="hsl(var(--muted-foreground))"
                          strokeDasharray="4 4"
                          strokeOpacity={0.6}
                          label={{
                            value: t('forecasts.today'),
                            position: 'top',
                            fill: 'hsl(var(--muted-foreground))',
                            fontSize: 12,
                          }}
                        />
                      )}
                    </ComposedChart>
                  </ResponsiveContainer>
                </div>
                <div className="mt-3 flex items-center justify-center gap-6 text-xs text-muted-foreground">
                  <div className="flex items-center gap-1.5">
                    <span className="inline-block h-0.5 w-5 rounded bg-muted-foreground" />
                    <span>{t('forecasts.historical')}</span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <span
                      className="inline-block h-0.5 w-5 rounded"
                      style={{ backgroundColor: CHART_PRIMARY }}
                    />
                    <span>{t('forecasts.forecast')}</span>
                  </div>
                  {showConfidenceBands && (
                    <div className="flex items-center gap-1.5">
                      <span className="inline-block h-3 w-5 rounded-sm bg-primary/15" />
                      <span>{t('forecasts.confidenceInterval')}</span>
                    </div>
                  )}
                </div>

                {/* Forecast values for the ASIN plotted above — collapsible so
                    the chart stays the focus, but the exact numbers are one
                    click away in the same context. */}
                <div className="mt-6 border-t pt-4">
                  <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                    <div>
                      <h3 className="text-sm font-semibold">
                        {latestForecast.asin
                          ? t('forecasts.predictionTableForAsin', { asin: latestForecast.asin })
                          : t('forecasts.predictionTable')}
                      </h3>
                      <p className="mt-0.5 text-xs text-muted-foreground">
                        {t('forecasts.predictionTableHelp')}
                      </p>
                    </div>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setPredictionTableOpen((open) => !open)}
                    >
                      {predictionTableOpen ? (
                        <ChevronUp className="mr-1 h-4 w-4" />
                      ) : (
                        <ChevronDown className="mr-1 h-4 w-4" />
                      )}
                      {predictionTableOpen
                        ? t('forecasts.hidePredictions')
                        : t('forecasts.showPredictions')}
                    </Button>
                  </div>

                  {predictionTableOpen && (
                    <div className="mt-3 space-y-3">
                      {latestForecast.predictions.length > 30 && (
                        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                          {!showAllPredictions ? (
                            <p className="text-xs text-muted-foreground">
                              {t('forecasts.showingFirstRows', {
                                count: visiblePredictions.length,
                                total: latestForecast.predictions.length,
                              })}
                            </p>
                          ) : (
                            <span />
                          )}
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => setShowAllPredictions((value) => !value)}
                          >
                            {showAllPredictions
                              ? t('forecasts.showLessPredictions')
                              : t('forecasts.showAllPredictions')}
                          </Button>
                        </div>
                      )}
                      <div className="rounded-md border">
                        <Table>
                          <TableHeader>
                            <TableRow>
                              <TableHead>{t('forecasts.date')}</TableHead>
                              <TableHead className="text-right">{t('forecasts.predictedValue')}</TableHead>
                              <TableHead className="text-right">{t('forecasts.lowerBound')}</TableHead>
                              <TableHead className="text-right">{t('forecasts.upperBound')}</TableHead>
                            </TableRow>
                          </TableHeader>
                          <TableBody>
                            {visiblePredictions.map((prediction) => (
                              <TableRow key={prediction.date}>
                                <TableCell>{formatPredictionDate(prediction.date)}</TableCell>
                                <TableCell className="text-right font-medium">
                                  {formatCurrency(prediction.predicted_value)}
                                </TableCell>
                                <TableCell className="text-right">
                                  {formatCurrency(prediction.lower_bound)}
                                </TableCell>
                                <TableCell className="text-right">
                                  {formatCurrency(prediction.upper_bound)}
                                </TableCell>
                              </TableRow>
                            ))}
                          </TableBody>
                        </Table>
                      </div>
                    </div>
                  )}
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Forecast Stats */}
          <div className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle className="text-sm font-medium">{t('forecasts.modelAccuracy')}</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-4">
                  <div>
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-muted-foreground">{t('forecasts.confidenceLabel')}</span>
                      <div className="flex items-center gap-1.5">
                        {confidenceLevel ? (
                          <Badge variant={confidenceBadgeVariant}>
                            {t(`forecasts.confidence.${confidenceLevel}`)}
                          </Badge>
                        ) : (
                          <span className="font-medium">N/A</span>
                        )}
                        <Popover>
                          <PopoverTrigger asChild>
                            <button
                              type="button"
                              className="text-muted-foreground hover:text-foreground"
                              aria-label={t('forecasts.confidenceExplainTitle')}
                            >
                              <Info className="h-3.5 w-3.5" />
                            </button>
                          </PopoverTrigger>
                          <PopoverContent align="end" className="w-72 text-sm">
                            <p className="font-medium">{t('forecasts.confidenceExplainTitle')}</p>
                            <p className="mt-1 text-xs text-muted-foreground">
                              {t('forecasts.confidenceExplainBody')}
                            </p>
                            {dataQualityNotes.length > 0 && (
                              <div className="mt-3 border-t pt-2">
                                <p className="text-xs font-medium">{t('forecasts.confidenceLowReason')}</p>
                                <ul className="mt-1 list-disc space-y-0.5 pl-4 text-xs text-muted-foreground">
                                  {dataQualityNotes.map((note) => (
                                    <li key={note}>{note}</li>
                                  ))}
                                </ul>
                              </div>
                            )}
                          </PopoverContent>
                        </Popover>
                      </div>
                    </div>
                    <p className="mt-1 text-xs text-muted-foreground">
                      {latestForecast.mape != null
                        ? t('forecasts.confidenceDesc', { mape: latestForecast.mape.toFixed(2) })
                        : t('forecasts.mapeDesc')}
                    </p>
                  </div>
                  <div>
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-muted-foreground">{t('forecasts.mape')}</span>
                      <span className="font-medium">
                        {latestForecast.mape != null ? `${latestForecast.mape.toFixed(2)}%` : 'N/A'}
                      </span>
                    </div>
                    <p className="text-xs text-muted-foreground mt-1">
                      {t('forecasts.mapeDesc')}
                    </p>
                  </div>
                  <div>
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-muted-foreground">{t('forecasts.rmse')}</span>
                      <span className="font-medium">
                        {latestForecast.rmse != null ? formatCurrency(latestForecast.rmse) : 'N/A'}
                      </span>
                    </div>
                    <p className="text-xs text-muted-foreground mt-1">
                      {t('forecasts.rmseDesc')}
                    </p>
                  </div>
                  {dataQualityNotes.length > 0 && (
                    <div className="space-y-2 border-t pt-4">
                      <p className="text-xs font-medium text-muted-foreground">
                        {t('forecasts.dataQuality')}
                      </p>
                      <div className="flex flex-wrap gap-2">
                        {dataQualityNotes.map((note) => (
                          <Badge
                            key={note}
                            variant="outline"
                            className="gap-1.5 rounded-md px-2 py-1 text-xs font-normal"
                          >
                            <Info className="h-3 w-3" />
                            {note}
                          </Badge>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-sm font-medium">{t('forecasts.summary')}</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-muted-foreground">{t('forecasts.generated')}</span>
                    <span>{formatDate(latestForecast.generated_at)}</span>
                  </div>
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-muted-foreground">{t('forecasts.model')}</span>
                    <Badge variant="outline">{latestForecast.model_used}</Badge>
                  </div>
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-muted-foreground">{t('forecasts.horizonLabel')}</span>
                    <span>
                      {isMonthly
                        ? t('forecasts.byAsin.monthsValue', { months: monthsCount })
                        : t('forecasts.byAsin.daysValue', { days: latestForecast.horizon_days })}
                    </span>
                  </div>
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-muted-foreground">{t('forecasts.type')}</span>
                    <span className="capitalize">{latestForecast.forecast_type}</span>
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-sm font-medium flex items-center gap-2">
                  <TrendingUp className="h-4 w-4" />
                  {t('forecasts.predictedTotal')}
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-3xl font-bold">
                  {formatCurrency(
                    latestForecast.predictions.reduce((sum, p) => sum + p.predicted_value, 0)
                  )}
                </div>
                <p className="text-sm text-muted-foreground mt-1">
                  {isMonthly
                    ? t('forecasts.nextMonths', { months: monthsCount })
                    : t('forecasts.nextDays', { days: latestForecast.horizon_days })}
                </p>
              </CardContent>
            </Card>
          </div>
        </div>
      ) : (
        <Card>
          <CardContent className="py-10 text-center">
            <TrendingUp className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
            <p className="text-muted-foreground">
              {t('forecasts.emptyState')}
            </p>
          </CardContent>
        </Card>
      )}

      {/* Per-ASIN Forecast Breakdown */}
      <PerAsinForecastTable
        forecasts={forecasts ?? []}
        availableProducts={availableProducts}
        selectedAccount={selectedAccount}
        onRowClick={(forecast) => {
          setDisplayedForecastId(forecast.id)
          if (forecast.asin) setSelectedAsin(forecast.asin)
          window.scrollTo({ top: 0, behavior: 'smooth' })
        }}
        t={t}
      />

      {/* Export Modal */}
      {latestForecast && (
        <ForecastExportModal
          open={exportModalOpen}
          onOpenChange={setExportModalOpen}
          forecast={latestForecast}
          accountName={accounts?.find((a) => a.id === latestForecast.account_id)?.account_name || 'unknown'}
        />
      )}
    </div>
  )
}

// ────────────────────────────────────────────────────────────────────────────
// Per-ASIN Forecast Breakdown table — replaces the read-only "Previous
// Forecasts" list. Shows the latest forecast per ASIN and lets the user click
// a row to load that forecast into the chart above.
// ────────────────────────────────────────────────────────────────────────────
function PerAsinForecastTable({
  forecasts,
  availableProducts,
  selectedAccount,
  onRowClick,
  t,
}: {
  forecasts: Forecast[]
  availableProducts: ForecastProductOption[]
  selectedAccount: string
  onRowClick: (forecast: Forecast) => void
  t: (key: string, vars?: Record<string, string | number>) => string
}) {
  const titleByAsin = useMemo(() => {
    const map = new Map<string, string>()
    for (const p of availableProducts) {
      if (p.title) map.set(p.asin, p.title)
    }
    return map
  }, [availableProducts])

  const rows = useMemo(() => {
    const filtered = forecasts.filter((f) => {
      if (!f.asin) return false
      if (selectedAccount && f.account_id !== selectedAccount) return false
      return true
    })
    // Keep the most recent forecast per ASIN.
    const latestByAsin = new Map<string, Forecast>()
    for (const f of filtered) {
      const existing = latestByAsin.get(f.asin as string)
      if (!existing || new Date(f.generated_at) > new Date(existing.generated_at)) {
        latestByAsin.set(f.asin as string, f)
      }
    }
    return Array.from(latestByAsin.values()).sort(
      (a, b) => new Date(b.generated_at).getTime() - new Date(a.generated_at).getTime(),
    )
  }, [forecasts, selectedAccount])

  if (rows.length === 0) return null

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('forecasts.byAsinTitle')}</CardTitle>
        <CardDescription>{t('forecasts.byAsinDesc')}</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>ASIN</TableHead>
                <TableHead>{t('forecasts.byAsin.title')}</TableHead>
                <TableHead className="text-right">{t('forecasts.byAsin.horizon')}</TableHead>
                <TableHead className="text-right">{t('forecasts.byAsin.predictedRevenue')}</TableHead>
                <TableHead>{t('forecasts.byAsin.confidence')}</TableHead>
                <TableHead className="text-right">{t('forecasts.byAsin.generatedAt')}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((forecast) => {
                const predictedTotal = forecast.predictions.reduce(
                  (acc, p) => acc + (p.predicted_value || 0),
                  0,
                )
                const level = getForecastConfidenceLevel(forecast)
                const title = titleByAsin.get(forecast.asin as string)
                return (
                  <TableRow
                    key={forecast.id}
                    className="cursor-pointer hover:bg-muted/60"
                    onClick={() => onRowClick(forecast)}
                  >
                    <TableCell className="font-mono text-xs">{forecast.asin}</TableCell>
                    <TableCell className="max-w-[280px] truncate">{title ?? '—'}</TableCell>
                    <TableCell className="text-right">
                      {isMonthlyForecast(forecast)
                        ? t('forecasts.byAsin.monthsValue', {
                            months: Math.max(1, Math.round((forecast.horizon_days ?? 30) / 30)),
                          })
                        : t('forecasts.byAsin.daysValue', { days: forecast.horizon_days })}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {formatCurrency(predictedTotal)}
                    </TableCell>
                    <TableCell>
                      {level ? (
                        <Badge variant={CONFIDENCE_BADGE_VARIANTS[level]}>
                          {t(`forecasts.confidence.${level}`)}
                        </Badge>
                      ) : (
                        <span className="text-muted-foreground text-sm">—</span>
                      )}
                    </TableCell>
                    <TableCell className="text-right text-sm text-muted-foreground">
                      {formatDate(forecast.generated_at)}
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        </div>
      </CardContent>
    </Card>
  )
}
