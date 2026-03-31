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
import { TrendingUp, RefreshCw, Loader2, Calendar, Target, Download } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
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
import { useToast } from '@/components/ui/use-toast'
import { forecastsApi, accountsApi, exportsApi } from '@/services/api'
import { formatCurrency, formatDate, downloadBlob } from '@/lib/utils'
import { useTranslation } from '@/i18n'
import { useLanguageStore } from '@/store/languageStore'
import type { Forecast, AmazonAccount, ForecastExportJob, ForecastProductOption } from '@/types'

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

  const resetExportState = () => {
    setIsExporting(false)
    setActiveJobId(null)
    setHasDownloadedPackage(false)
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
      toast({
        variant: 'destructive',
        title: t('forecasts.exportPackageFailed'),
        ...(packageStatusQuery.data.error_message
          ? { description: packageStatusQuery.data.error_message }
          : {}),
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
          </div>

          {/* Preview summary */}
          <div className="rounded-lg border bg-muted/50 p-3 space-y-1 text-xs text-muted-foreground">
            <p><span className="font-medium text-foreground">{t('forecasts.account')}:</span> {accountName}</p>
            {forecast.asin && (
              <p><span className="font-medium text-foreground">ASIN:</span> {forecast.asin}</p>
            )}
            <p><span className="font-medium text-foreground">{t('forecasts.model')}:</span> {forecast.model_used}</p>
            <p><span className="font-medium text-foreground">{t('forecasts.horizonLabel')}:</span> {forecast.horizon_days} {t('filter.day').toLowerCase()}s</p>
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
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { t } = useTranslation()
  const { language: appLang } = useLanguageStore()
  const [exportModalOpen, setExportModalOpen] = useState(false)

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

    generateMutation.mutate({
      account_id: selectedAccount,
      horizon_days: parseInt(forecastHorizon),
      ...(selectedAsin !== ALL_ASINS_VALUE ? { asin: selectedAsin } : {}),
    })
  }

  // Get the latest forecast for display
  const latestForecast = forecasts?.[0]
  const availableProducts = products ?? []

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
              <label className="text-sm font-medium">{t('forecasts.asinOptional')}</label>
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
                    availableProducts.map((product) => (
                      <SelectItem key={product.asin} value={product.asin}>
                        <span className="font-mono text-xs mr-2">{product.asin}</span>
                        <span className="truncate">
                          {product.title
                            ? product.title.length > 50
                              ? product.title.slice(0, 50) + '\u2026'
                              : product.title
                            : product.asin}
                        </span>
                      </SelectItem>
                    ))
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
          {/* Forecast Chart */}
          <Card className="col-span-2">
            <CardHeader>
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle>{t('forecasts.salesForecast')}</CardTitle>
                  <CardDescription>
                    {t('forecasts.predictionDesc', {
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
                    {t('forecasts.exportCsv')}
                  </Button>
                  <Badge variant="secondary">
                    {(latestForecast.confidence_interval * 100).toFixed(0)}% CI
                  </Badge>
                </div>
              </div>
            </CardHeader>
            <CardContent>
              <div className="h-[400px]">
                <ResponsiveContainer width="100%" height="100%">
                  <ComposedChart data={chartData}>
                    <CartesianGrid strokeDasharray="3 3" strokeOpacity={0.3} />
                    <XAxis
                      dataKey="date"
                      tickFormatter={(value) => {
                        const locale = appLang === 'it' ? 'it-IT' : 'en-US'
                        return new Date(value + 'T00:00:00').toLocaleDateString(locale, { month: 'short', day: 'numeric' })
                      }}
                      tick={{ fontSize: 12 }}
                    />
                    <YAxis
                      tickFormatter={yAxisFormatter}
                      tick={{ fontSize: 12 }}
                      width={50}
                    />
                    <Tooltip content={<CustomTooltip />} />
                    {/* Confidence interval band (stacked: invisible base + visible range) */}
                    <Area
                      type="monotone"
                      dataKey="ci_base"
                      stackId="ci"
                      stroke="none"
                      fill="transparent"
                      connectNulls={false}
                    />
                    <Area
                      type="monotone"
                      dataKey="ci_range"
                      stackId="ci"
                      stroke="none"
                      fill="hsl(var(--primary))"
                      fillOpacity={0.12}
                      connectNulls={false}
                    />
                    {/* Historical sales line */}
                    <Line
                      type="monotone"
                      dataKey="historical_value"
                      stroke="hsl(var(--muted-foreground))"
                      strokeWidth={2}
                      dot={false}
                      connectNulls={false}
                    />
                    {/* Forecast prediction line */}
                    <Line
                      type="monotone"
                      dataKey="predicted_value"
                      stroke="hsl(var(--primary))"
                      strokeWidth={2}
                      dot={false}
                      connectNulls={false}
                    />
                    {/* Today reference line */}
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
              {/* Custom Legend */}
              <div className="flex items-center justify-center gap-6 mt-3 text-xs text-muted-foreground">
                <div className="flex items-center gap-1.5">
                  <span className="inline-block w-5 h-0.5 rounded bg-muted-foreground" />
                  <span>{t('forecasts.historical')}</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <span className="inline-block w-5 h-0.5 rounded bg-primary" />
                  <span>{t('forecasts.forecast')}</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <span className="inline-block w-5 h-3 rounded-sm bg-primary/15" />
                  <span>{t('forecasts.confidenceInterval')}</span>
                </div>
              </div>
            </CardContent>
          </Card>

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
                      <span className="text-muted-foreground">{t('forecasts.mape')}</span>
                      <span className="font-medium">
                        {latestForecast.mape?.toFixed(2) || 'N/A'}%
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
                        {formatCurrency(latestForecast.rmse || 0)}
                      </span>
                    </div>
                    <p className="text-xs text-muted-foreground mt-1">
                      {t('forecasts.rmseDesc')}
                    </p>
                  </div>
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
                    <span>{latestForecast.horizon_days} {t('filter.day').toLowerCase()}s</span>
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
                  {t('forecasts.nextDays', { days: latestForecast.horizon_days })}
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

      {/* Previous Forecasts */}
      {forecasts && forecasts.length > 1 && (
        <Card>
          <CardHeader>
            <CardTitle>{t('forecasts.previousForecasts')}</CardTitle>
            <CardDescription>{t('forecasts.previousDesc')}</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {forecasts.slice(1, 6).map((forecast) => (
                <div
                  key={forecast.id}
                  className="flex items-center justify-between py-2 border-b last:border-0"
                >
                  <div className="flex items-center gap-4">
                    <Badge variant="outline">{forecast.model_used}</Badge>
                    <span className="text-sm">
                      {t('forecasts.forecastItem', {
                        days: forecast.horizon_days,
                        type: forecast.forecast_type,
                      })}
                    </span>
                  </div>
                  <span className="text-sm text-muted-foreground">
                    {formatDate(forecast.generated_at)}
                  </span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

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
