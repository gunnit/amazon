import { useEffect, useState } from 'react'
import { Link, useLocation, useParams, useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, Loader2 } from 'lucide-react'
import { isAxiosError } from 'axios'
import { campaignAlias } from '@/components/CampaignLink'
import { CampaignPrivacyToggle } from '@/components/CampaignPrivacyToggle'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useTranslation } from '@/i18n'
import { formatCurrency, formatDecimal, formatLocalizedDate, formatNumber } from '@/lib/utils'
import { analyticsApi } from '@/services/api'
import { getFilterDateRange, useFilterStore } from '@/store/filterStore'
import type { CampaignMetrics } from '@/types'

const metrics = [
  ['spend', 'reports.spend'], ['sales', 'campaign.sales'], ['orders', 'campaign.orders'],
  ['roas', 'ROAS'], ['impressions', 'reports.impressions'], ['clicks', 'reports.clicks'],
  ['ctr', 'CTR'], ['cpc', 'CPC'], ['acos', 'ACoS'], ['conversion_rate', 'analytics.conversionRate'],
  ['units', 'common.units'],
] as const

function metricValue(row: CampaignMetrics, key: keyof CampaignMetrics, currency: string | null, unavailable: string) {
  const value = row[key]
  if (value == null) return unavailable
  const number = Number(value)
  if (key === 'spend' || key === 'sales' || key === 'cpc') {
    return currency ? formatCurrency(number, currency) : formatDecimal(number)
  }
  if (key === 'acos' || key === 'ctr' || key === 'conversion_rate') return `${formatDecimal(number)}%`
  if (key === 'roas') return `${formatDecimal(number)}×`
  return formatNumber(number)
}

function MetricSummary({ totals, currency }: { totals: CampaignMetrics; currency: string | null }) {
  const { t } = useTranslation()
  const primary = metrics.slice(0, 4)
  const secondary = metrics.slice(4)
  return (
    <Card>
      <CardContent className="p-4 sm:p-6">
        <dl className="grid grid-cols-2 gap-x-6 gap-y-4 md:grid-cols-4">
          {primary.map(([key, label]) => (
            <div key={key}>
              <dt className="text-sm text-muted-foreground">{t(label)}</dt>
              <dd className="mt-1 text-2xl font-semibold tabular-nums">
                {metricValue(totals, key, currency, t('advertising.acosNotAvailable'))}
              </dd>
            </div>
          ))}
        </dl>
        <dl className="mt-5 grid grid-cols-2 gap-x-4 gap-y-3 border-t pt-4 sm:grid-cols-4 xl:grid-cols-7">
          {secondary.map(([key, label]) => (
            <div key={key}>
              <dt className="text-xs text-muted-foreground">{t(label)}</dt>
              <dd className="mt-1 font-semibold tabular-nums">
                {metricValue(totals, key, currency, t('advertising.acosNotAvailable'))}
              </dd>
            </div>
          ))}
        </dl>
      </CardContent>
    </Card>
  )
}

function DetailTable<Row extends CampaignMetrics>({ rows, currency, title, rowLabel, rowId, empty }: {
  rows: Row[]
  currency: string | null
  title: string
  rowLabel: (row: Row, index: number) => React.ReactNode
  rowId: (row: Row) => string
  empty: string
}) {
  const { t } = useTranslation()
  const [page, setPage] = useState(0)
  const pageSize = 15
  const pages = Math.ceil(rows.length / pageSize)
  const first = Math.max(0, Math.min(page, pages - 1)) * pageSize
  const last = Math.min(first + pageSize, rows.length)
  if (rows.length === 0) return <p className="p-6 text-sm text-muted-foreground">{empty}</p>
  return (
    <>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b bg-muted/40 text-xs text-muted-foreground">
              <th scope="col" className="p-3 text-left font-medium">{title}</th>
              {metrics.map(([key, label]) => <th scope="col" key={key} className="whitespace-nowrap p-3 text-right font-medium">{t(label)}</th>)}
            </tr>
          </thead>
          <tbody>
            {rows.slice(first, last).map((row, index) => (
              <tr key={rowId(row)} className="border-b last:border-0">
                <th scope="row" className="p-3 text-left font-medium">{rowLabel(row, first + index)}</th>
                {metrics.map(([key]) => (
                  <td key={key} className="whitespace-nowrap p-3 text-right tabular-nums">
                    {metricValue(row, key, currency, t('advertising.acosNotAvailable'))}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {pages > 1 && (
        <div className="flex flex-wrap items-center justify-between gap-2 border-t p-3">
          <span className="text-xs text-muted-foreground">{t('reports.salesRowsShowing', { from: first + 1, to: last, total: rows.length })}</span>
          <div className="flex gap-2">
            <Button size="sm" variant="outline" disabled={first === 0} onClick={() => setPage(page - 1)}>{t('alerts.previousPage')}</Button>
            <Button size="sm" variant="outline" disabled={last === rows.length} onClick={() => setPage(page + 1)}>{t('alerts.nextPage')}</Button>
          </div>
        </div>
      )}
    </>
  )
}

const adTypes: Record<string, string> = {
  sponsoredproducts: 'Sponsored Products', sponsoredbrands: 'Sponsored Brands', sponsoreddisplay: 'Sponsored Display',
  sp: 'Sponsored Products', sb: 'Sponsored Brands', sd: 'Sponsored Display', dsp: 'Amazon DSP',
}
const campaignStates: Record<string, string> = {
  enabled: 'advertising.stateEnabled', paused: 'advertising.statePaused', archived: 'advertising.stateArchived',
}

export default function CampaignDetails() {
  const { t, language } = useTranslation()
  const { campaignId = '', accountId = '' } = useParams()
  const [search, setSearch] = useSearchParams()
  const location = useLocation()
  const filters = useFilterStore()
  const fallbackDates = getFilterDateRange(filters)
  const presentation = search.get('presentation') === '1'
  const masked = presentation || filters.campaignPrivacy
  const setCampaignPrivacy = filters.setCampaignPrivacy
  useEffect(() => {
    if (presentation) setCampaignPrivacy(true)
  }, [presentation, setCampaignPrivacy])
  const start = search.get('start_date') || fallbackDates.start
  const end = search.get('end_date') || fallbackDates.end
  const previous = location.state?.previous
  const fromPerformance = typeof previous === 'string' && previous.startsWith('/performance?')
  const back = fromPerformance ? previous : '/advertising'
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['campaign-detail', accountId, campaignId, start, end],
    queryFn: () => analyticsApi.getCampaignDetail(campaignId, { account_id: accountId, start_date: start, end_date: end }),
    retry: false,
  })
  const rawType = data?.campaign_type || ''
  const type = adTypes[rawType.toLowerCase().replace(/[_\s-]/g, '')] || rawType
  const sp = type === 'Sponsored Products'
  const missing = isAxiosError(error) && error.response?.status === 404
  const state = data?.state || ''
  return (
    <div className="min-w-0 space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Link to={back} className="inline-flex items-center gap-1 text-sm font-medium text-muted-foreground hover:text-foreground">
          <ArrowLeft aria-hidden="true" className="h-4 w-4" />{t(fromPerformance ? 'analytics.adsVsOrganicTab' : 'advertising.title')}
        </Link>
        <CampaignPrivacyToggle presentation={presentation} onExitPresentation={() => {
          const params = new URLSearchParams(search)
          params.delete('presentation')
          setSearch(params, { replace: true, state: location.state })
        }} />
      </div>
      {isLoading && <p role="status" className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" />{t('common.loading')}</p>}
      {error && (
        <Alert variant="destructive">
          <AlertDescription>{t(missing ? 'campaign.missing' : 'advertising.loadError')}</AlertDescription>
          {!missing && <Button size="sm" variant="outline" className="mt-3" onClick={() => refetch()}>{t('brandIntelligence.action.retry')}</Button>}
        </Alert>
      )}
      {data && (
        <>
          <header className="space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="break-words text-3xl font-bold tracking-tight">
                {masked ? t('campaign.alias', { code: campaignAlias(accountId, campaignId) }) : data.campaign_name || data.campaign_id}
              </h1>
              {state && <Badge variant="outline">{t(campaignStates[state.toLowerCase()] || state)}</Badge>}
            </div>
            <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-muted-foreground">
              {type && <span>{type}</span>}
              <span>{t('accounts.marketplace')} {data.marketplace_country}</span>
              <span>{formatLocalizedDate(data.start_date, language)} – {formatLocalizedDate(data.end_date, language)}</span>
            </p>
          </header>
          {data.totals
            ? <MetricSummary totals={data.totals} currency={data.currency} />
            : <Alert><AlertDescription>{t('campaign.noDaily')}</AlertDescription></Alert>}
          <Tabs key={`${accountId}/${campaignId}/${start}/${end}`} defaultValue={sp ? 'products' : 'daily'} className="space-y-3">
            <TabsList className="h-auto max-w-full flex-wrap">
              <TabsTrigger value="products">{t('campaign.products')}</TabsTrigger>
              <TabsTrigger value="keywords">{t('campaign.keywords')}</TabsTrigger>
              <TabsTrigger value="daily">{t('campaign.daily')}</TabsTrigger>
            </TabsList>
            <p className="text-xs text-muted-foreground">
              {t(sp ? 'campaign.attributionSP' : 'campaign.attributionNative')}{' '}
              {t(data.daily.length === 1 ? 'campaign.reportedDay' : 'campaign.reportedDays', { n: data.daily.length })}
            </p>
            <TabsContent value="products">
              <Card>
                <DetailTable
                  rows={data.products} currency={data.currency} title={masked ? t('reports.product') : 'ASIN'}
                  rowId={r => r.asin}
                  rowLabel={(r, index) => masked ? t('campaign.productAlias', { n: index + 1 }) : r.asin}
                  empty={t(sp ? 'campaign.noProducts' : 'campaign.productsUnsupported')}
                />
              </Card>
            </TabsContent>
            <TabsContent value="keywords">
              {data.keywords.length > 0 && <p className="mb-3 text-xs text-muted-foreground">{t('campaign.keywordSource')}</p>}
              <Card>
                <DetailTable
                  rows={data.keywords} currency={data.currency} title={t('marketTracker.keyword')}
                  rowId={r => JSON.stringify([r.keyword, r.match_type])}
                  rowLabel={(r, index) => (
                    <>
                      {masked ? t('campaign.keywordAlias', { n: index + 1 }) : r.keyword}
                      {r.match_type && <span className="block text-xs font-normal text-muted-foreground">{r.match_type}</span>}
                    </>
                  )}
                  empty={t(sp ? 'campaign.noKeywords' : 'campaign.keywordsUnsupported')}
                />
              </Card>
            </TabsContent>
            <TabsContent value="daily">
              <Card>
                <DetailTable
                  rows={data.daily} currency={data.currency} title={t('reports.date')}
                  rowId={r => r.date} rowLabel={r => formatLocalizedDate(r.date, language)} empty={t('campaign.noDaily')}
                />
              </Card>
            </TabsContent>
          </Tabs>
        </>
      )}
    </div>
  )
}
