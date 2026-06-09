import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Activity, ArrowDownRight, ArrowUpRight, Loader2, Minus } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { accountsApi, brandPulseApi } from '@/services/api'
import { formatCurrency, formatNumber, formatChangePercent } from '@/lib/utils'
import { useTranslation } from '@/i18n'
import type { PulseAsin, PulseMetricChange, PulseRecommendation } from '@/types'

type TFn = (key: string, vars?: Record<string, string | number>) => string

const WINDOW_OPTIONS = [30, 60, 90] as const

const PRIORITY_VARIANT: Record<string, 'default' | 'secondary' | 'destructive'> = {
  high: 'destructive',
  medium: 'default',
  low: 'secondary',
}

function changeTone(trend: string): string {
  if (trend === 'up') return 'text-emerald-600'
  if (trend === 'down') return 'text-rose-600'
  return 'text-muted-foreground'
}

function TrendIcon({ trend }: { trend: string }) {
  if (trend === 'up') return <ArrowUpRight className="h-3.5 w-3.5" />
  if (trend === 'down') return <ArrowDownRight className="h-3.5 w-3.5" />
  return <Minus className="h-3.5 w-3.5" />
}

function KpiTile({
  label,
  value,
  change,
  vsPrev,
}: {
  label: string
  value: string
  change?: PulseMetricChange
  vsPrev: string
}) {
  return (
    <Card>
      <CardContent className="p-4">
        <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">{label}</p>
        <p className="mt-1 text-2xl font-semibold tabular-nums">{value}</p>
        {change ? (
          <div className={`mt-1 flex items-center gap-1 text-xs font-medium ${changeTone(change.trend)}`}>
            <TrendIcon trend={change.trend} />
            <span>{formatChangePercent(change.percent)}</span>
            <span className="text-muted-foreground">{vsPrev}</span>
          </div>
        ) : (
          <div className="mt-1 h-4" />
        )}
      </CardContent>
    </Card>
  )
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className="mt-0.5 text-lg font-semibold tabular-nums">{value}</p>
    </div>
  )
}

function AsinTable({ items, t }: { items: PulseAsin[]; t: TFn }) {
  if (items.length === 0) {
    return <p className="text-sm text-muted-foreground">—</p>
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[360px]">
      <thead>
        <tr className="border-b text-left text-[11px] uppercase tracking-wide text-muted-foreground">
          <th className="pb-2 pr-3 font-medium">{t('brandPulse.col.product')}</th>
          <th className="pb-2 px-3 text-right font-medium">{t('brandPulse.col.revenue')}</th>
          <th className="pb-2 pl-3 text-right font-medium">{t('brandPulse.col.change')}</th>
        </tr>
      </thead>
      <tbody>
        {items.map((item) => {
          const trend =
            item.change_percent > 5 ? 'up' : item.change_percent < -5 ? 'down' : 'stable'
          return (
            <tr key={item.asin} className="border-b last:border-0">
              <td className="py-2 pr-3">
                <p className="max-w-[260px] truncate text-sm font-medium" title={item.title ?? item.asin}>
                  {item.title ?? item.asin}
                </p>
                <p className="text-xs text-muted-foreground">{item.asin}</p>
              </td>
              <td className="px-3 py-2 text-right text-sm tabular-nums">{formatCurrency(item.revenue)}</td>
              <td className={`py-2 pl-3 text-right text-sm font-medium tabular-nums ${changeTone(trend)}`}>
                {formatChangePercent(item.change_percent)}
              </td>
            </tr>
          )
        })}
      </tbody>
      </table>
    </div>
  )
}

function RecCard({ rec, t }: { rec: PulseRecommendation; t: TFn }) {
  return (
    <div className="rounded-lg border p-3">
      <div className="flex items-start justify-between gap-3">
        <p className="text-sm font-medium">{rec.title}</p>
        <Badge variant={PRIORITY_VARIANT[rec.priority] ?? 'default'} className="shrink-0 capitalize">
          {rec.priority}
        </Badge>
      </div>
      <p className="mt-1 text-sm text-muted-foreground">{rec.evidence}</p>
      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        <Badge variant="outline" className="text-[11px]">
          {t('brandPulse.source')}: {rec.source}
        </Badge>
        <Badge variant="outline" className="text-[11px] capitalize">
          {t('brandPulse.confidence')}: {rec.confidence}
        </Badge>
      </div>
    </div>
  )
}

export default function BrandPulse() {
  const { t, language } = useTranslation()
  const [accountId, setAccountId] = useState<string>('')
  const [windowDays, setWindowDays] = useState<number>(30)

  const { data: accounts } = useQuery({ queryKey: ['accounts'], queryFn: () => accountsApi.list() })
  const effectiveAccountId = accountId || accounts?.[0]?.id || ''
  const selectedAccount = accounts?.find((a) => a.id === effectiveAccountId)
  const isSeller = selectedAccount?.account_type === 'seller'

  // Vendor accounts report monthly, so a rolling 30d window often has no posted
  // data yet. Default each account to a sensible window the first time it loads.
  const defaultedAccountRef = useRef<string>('')
  useEffect(() => {
    if (selectedAccount && defaultedAccountRef.current !== selectedAccount.id) {
      defaultedAccountRef.current = selectedAccount.id
      setWindowDays(selectedAccount.account_type === 'vendor' ? 90 : 30)
    }
  }, [selectedAccount])

  const { data, isLoading, isError } = useQuery({
    queryKey: ['brand-pulse', effectiveAccountId, windowDays, language],
    queryFn: () =>
      brandPulseApi.get({
        account_ids: [effectiveAccountId],
        window_days: windowDays,
        language: language as 'en' | 'it',
      }),
    enabled: !!effectiveAccountId,
  })

  const vsPrev = t('brandPulse.vsPrevShort')
  const ads = data?.ads
  const cur = data?.overview.current
  const changes = data?.overview.changes
  const awaitingData = data?.period.awaiting_data ?? false

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight">
            <Activity className="h-6 w-6 text-primary" /> {t('brandPulse.title')}
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">{t('brandPulse.subtitle', { n: windowDays })}</p>
        </div>
        <div className="flex items-center gap-2">
          <Select value={effectiveAccountId} onValueChange={setAccountId}>
            <SelectTrigger className="w-[200px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {accounts?.map((a) => (
                <SelectItem key={a.id} value={a.id}>
                  {a.account_name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={String(windowDays)} onValueChange={(v) => setWindowDays(Number(v))}>
            <SelectTrigger className="w-[150px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {WINDOW_OPTIONS.map((w) => (
                <SelectItem key={w} value={String(w)}>
                  {t('brandPulse.lastDays', { n: w })}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      {!effectiveAccountId && (
        <Alert>
          <AlertDescription>{t('brandPulse.noAccount')}</AlertDescription>
        </Alert>
      )}
      {isLoading && (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" /> {t('brandPulse.loading')}
        </div>
      )}
      {isError && (
        <Alert variant="destructive">
          <AlertTitle>{t('brandPulse.error')}</AlertTitle>
        </Alert>
      )}

      {data && cur && (
        <>
          {awaitingData && (
            <Alert>
              <AlertTitle>{t('brandPulse.awaitingData')}</AlertTitle>
              <AlertDescription>{t('brandPulse.awaitingDataHelp')}</AlertDescription>
            </Alert>
          )}
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <KpiTile label={t('brandPulse.kpi.revenue')} value={formatCurrency(cur.revenue)} change={awaitingData ? undefined : changes?.revenue} vsPrev={vsPrev} />
            <KpiTile label={t('brandPulse.kpi.units')} value={formatNumber(cur.units)} change={awaitingData ? undefined : changes?.units} vsPrev={vsPrev} />
            <KpiTile label={t('brandPulse.kpi.orders')} value={formatNumber(cur.orders)} change={awaitingData ? undefined : changes?.orders} vsPrev={vsPrev} />
            <KpiTile label={t('brandPulse.kpi.aov')} value={formatCurrency(cur.average_order_value)} change={awaitingData ? undefined : changes?.average_order_value} vsPrev={vsPrev} />
          </div>

          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">{t('brandPulse.ads.title')}</CardTitle>
            </CardHeader>
            <CardContent>
              {ads?.is_available ? (
                <>
                  <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
                    <Metric label={t('brandPulse.ads.spend')} value={formatCurrency(ads.spend ?? 0)} />
                    <Metric label={t('brandPulse.ads.acos')} value={`${(ads.acos ?? 0).toFixed(1)}%`} />
                    <Metric label={t('brandPulse.ads.tacos')} value={ads.tacos == null ? '—' : `${ads.tacos.toFixed(1)}%`} />
                    <Metric label={t('brandPulse.ads.roas')} value={`${(ads.roas ?? 0).toFixed(2)}×`} />
                  </div>
                  {ads.attribution_window && (
                    <p className="mt-3 text-xs text-muted-foreground">
                      {t('brandPulse.ads.attribution', { w: ads.attribution_window })}
                    </p>
                  )}
                </>
              ) : (
                <div className="text-sm">
                  <p className="font-medium">{t('brandPulse.ads.notConnected')}</p>
                  <p className="text-muted-foreground">{t('brandPulse.ads.notConnectedHelp')}</p>
                </div>
              )}
            </CardContent>
          </Card>

          <div className="grid gap-4 lg:grid-cols-2">
            <Card className="min-w-0">
              <CardHeader className="pb-2">
                <CardTitle className="text-base">{t('brandPulse.topAsins')}</CardTitle>
              </CardHeader>
              <CardContent>
                <AsinTable items={data.top_asins} t={t} />
                {isSeller && data.top_asins.length > 0 && (
                  <p className="mt-3 text-xs text-muted-foreground">{t('brandPulse.snapshotNote')}</p>
                )}
              </CardContent>
            </Card>
            <Card className="min-w-0">
              <CardHeader className="pb-2">
                <CardTitle className="text-base">{t('brandPulse.decliningAsins')}</CardTitle>
              </CardHeader>
              <CardContent>
                {data.declining_asins.length === 0 ? (
                  <p className="text-sm text-muted-foreground">{t('brandPulse.noDeclining')}</p>
                ) : (
                  <>
                    <AsinTable items={data.declining_asins} t={t} />
                    {isSeller && (
                      <p className="mt-3 text-xs text-muted-foreground">{t('brandPulse.snapshotNote')}</p>
                    )}
                  </>
                )}
              </CardContent>
            </Card>
          </div>

          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-base">{t('brandPulse.recommendations')}</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {data.recommendations.length === 0 ? (
                <p className="text-sm text-muted-foreground">{t('brandPulse.noRecommendations')}</p>
              ) : (
                data.recommendations.map((rec, i) => <RecCard key={i} rec={rec} t={t} />)
              )}
            </CardContent>
          </Card>
        </>
      )}
    </div>
  )
}
