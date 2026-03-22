import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Area,
  AreaChart,
} from 'recharts'
import { TrendingUp, RefreshCw, Loader2, Calendar, Target, Download } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { useToast } from '@/components/ui/use-toast'
import { forecastsApi, accountsApi } from '@/services/api'
import { formatCurrency, formatDate } from '@/lib/utils'
import { useTranslation } from '@/i18n'
import { useLanguageStore, type Language } from '@/store/languageStore'
import type { Forecast, AmazonAccount } from '@/types'

const csvLabels = {
  en: {
    title: 'Sales Forecast Report',
    account: 'Account', generated: 'Generated',
    model: 'Model', horizon: 'Horizon', ci: 'Confidence Interval',
    date: 'Date', predicted: 'Predicted Value',
    lower: 'Lower Bound (95%)', upper: 'Upper Bound (95%)',
    total: 'Total', days: 'days',
  },
  it: {
    title: 'Report Previsione Vendite',
    account: 'Account', generated: 'Generato',
    model: 'Modello', horizon: 'Orizzonte', ci: 'Intervallo di Confidenza',
    date: 'Data', predicted: 'Valore Previsto',
    lower: 'Limite Inferiore (95%)', upper: 'Limite Superiore (95%)',
    total: 'Totale', days: 'giorni',
  },
} as const

function formatCsvDate(dateStr: string, lang: Language): string {
  if (lang === 'it') {
    const [y, m, d] = dateStr.split('-')
    return `${d}/${m}/${y}`
  }
  return dateStr
}

function downloadForecastCsv(
  forecast: Forecast,
  accountName: string,
  lang: Language,
  template: 'summary' | 'detailed' | 'report',
) {
  const l = csvLabels[lang]
  const rows: string[] = []
  const BOM = '\uFEFF'

  const fmtVal = (v: number) => v.toFixed(2)
  const fmtDate = (d: string) => formatCsvDate(d, lang)

  if (template === 'report') {
    rows.push(l.title)
    rows.push(`${l.account},${accountName}`)
    rows.push(`${l.generated},${fmtDate(forecast.generated_at.split('T')[0])}`)
    rows.push(`${l.model},${forecast.model_used}`)
    rows.push(`${l.horizon},${forecast.horizon_days} ${l.days}`)
    rows.push(`${l.ci},${(forecast.confidence_interval * 100).toFixed(0)}%`)
    rows.push('')
  }

  if (template === 'summary') {
    rows.push(`${l.date},${l.predicted}`)
    for (const p of forecast.predictions) {
      rows.push(`${fmtDate(p.date)},${fmtVal(p.predicted_value)}`)
    }
  } else {
    rows.push(`${l.date},${l.predicted},${l.lower},${l.upper}`)
    for (const p of forecast.predictions) {
      rows.push(`${fmtDate(p.date)},${fmtVal(p.predicted_value)},${fmtVal(p.lower_bound)},${fmtVal(p.upper_bound)}`)
    }
  }

  if (template === 'report') {
    const total = forecast.predictions.reduce((s, p) => s + p.predicted_value, 0)
    rows.push(`${l.total},${fmtVal(total)},,`)
  }

  const blob = new Blob([BOM + rows.join('\n')], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  const safeName = accountName.replace(/[^a-zA-Z0-9_-]/g, '_')
  a.href = url
  a.download = `forecast_${safeName}_${forecast.horizon_days}d_${template}_${lang}.csv`
  a.click()
  URL.revokeObjectURL(url)
}

export default function Forecasts() {
  const [selectedAccount, setSelectedAccount] = useState<string>('')
  const [forecastHorizon, setForecastHorizon] = useState('30')
  const [asin, setAsin] = useState('')
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { t } = useTranslation()
  const { language: appLang } = useLanguageStore()
  const [csvLang, setCsvLang] = useState<Language>(appLang)
  const [csvTemplate, setCsvTemplate] = useState<'summary' | 'detailed' | 'report'>('detailed')

  const { data: accounts } = useQuery<AmazonAccount[]>({
    queryKey: ['accounts'],
    queryFn: () => accountsApi.list(),
  })

  const { data: forecasts, isLoading } = useQuery<Forecast[]>({
    queryKey: ['forecasts'],
    queryFn: () => forecastsApi.list(),
  })

  const generateMutation = useMutation({
    mutationFn: (params: { account_id: string; horizon_days: number }) =>
      forecastsApi.generate(params),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['forecasts'] })
      toast({ title: t('forecasts.generateSuccess') })
    },
    onError: () => {
      toast({
        variant: 'destructive',
        title: t('forecasts.generateFailed'),
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
      ...(asin.trim() ? { asin: asin.trim() } : {}),
    })
  }

  // Get the latest forecast for display
  const latestForecast = forecasts?.[0]

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
              <Select value={selectedAccount} onValueChange={setSelectedAccount}>
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
              <Input
                value={asin}
                onChange={(e) => setAsin(e.target.value)}
                placeholder={t('forecasts.asinPlaceholder')}
                className="w-[200px]"
              />
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
                  <Select value={csvTemplate} onValueChange={(v) => setCsvTemplate(v as 'summary' | 'detailed' | 'report')}>
                    <SelectTrigger className="w-[130px] h-8 text-xs">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="summary">{t('forecasts.templateSummary')}</SelectItem>
                      <SelectItem value="detailed">{t('forecasts.templateDetailed')}</SelectItem>
                      <SelectItem value="report">{t('forecasts.templateReport')}</SelectItem>
                    </SelectContent>
                  </Select>
                  <Select value={csvLang} onValueChange={(v) => setCsvLang(v as Language)}>
                    <SelectTrigger className="w-[80px] h-8 text-xs">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="en">EN</SelectItem>
                      <SelectItem value="it">IT</SelectItem>
                    </SelectContent>
                  </Select>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      const accountName = accounts?.find(a => a.id === latestForecast.account_id)?.account_name || 'unknown'
                      downloadForecastCsv(latestForecast, accountName, csvLang, csvTemplate)
                    }}
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
                  <AreaChart data={latestForecast.predictions}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis
                      dataKey="date"
                      tickFormatter={(value) =>
                        new Date(value).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
                      }
                    />
                    <YAxis tickFormatter={(value) => `$${(value / 1000).toFixed(0)}k`} />
                    <Tooltip
                      formatter={(value: number) => [formatCurrency(value)]}
                      labelFormatter={(label) => formatDate(label)}
                    />
                    <Area
                      type="monotone"
                      dataKey="upper_bound"
                      stroke="none"
                      fill="hsl(var(--primary))"
                      fillOpacity={0.1}
                    />
                    <Area
                      type="monotone"
                      dataKey="lower_bound"
                      stroke="none"
                      fill="white"
                    />
                    <Line
                      type="monotone"
                      dataKey="predicted_value"
                      stroke="hsl(var(--primary))"
                      strokeWidth={2}
                      dot={false}
                    />
                  </AreaChart>
                </ResponsiveContainer>
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
    </div>
  )
}
