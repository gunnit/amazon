import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  Megaphone,
  Target,
  MousePointerClick,
  DollarSign,
  ShoppingCart,
  Eye,
  TrendingUp,
  AlertTriangle,
  Lightbulb,
  Loader2,
} from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { EmptyState } from '@/components/EmptyState'
import { Badge } from '@/components/ui/badge'
import { FilterBar, DateRangeFilter, AccountFilter } from '@/components/filters'
import { useFilterStore, getFilterDateRange } from '@/store/filterStore'
import { useTranslation } from '@/i18n'
import { accountsApi, analyticsApi } from '@/services/api'
import { formatCurrency, formatDecimal, formatLocalizedDate, formatNumber, cn } from '@/lib/utils'
import type {
  AdsConnectionState,
  AdvertisingInsights,
  AdvertisingRecommendation,
  AmazonAccount,
  CampaignInsight,
} from '@/types'

// Backend recommendations carry a stable code; localize by code and fall back
// to the English message for any code we don't have a translation for.
const RECOMMENDATION_KEYS: Record<string, string> = {
  no_spend: 'advertising.recNoSpend',
  high_roas: 'advertising.recHighRoas',
  high_acos: 'advertising.recHighAcos',
  low_ctr: 'advertising.recLowCtr',
  no_conversion: 'advertising.recNoConversion',
  stable: 'advertising.recStable',
}

function localizeRecommendation(rec: AdvertisingRecommendation, t: (key: string) => string): string {
  const key = RECOMMENDATION_KEYS[rec.code]
  return key ? t(key) : rec.message
}

function resolveAdsState(account: AmazonAccount): AdsConnectionState {
  if (account.ads_connection_state) return account.ads_connection_state
  if (account.has_ads_client_credentials === false) return 'missing_client_credentials'
  if (!account.has_advertising_refresh_token) return 'missing_refresh_token'
  if (!account.advertising_profile_id) return 'missing_profile'
  return 'ok'
}

function MetricCard({
  label,
  value,
  icon: Icon,
  className,
}: {
  label: string
  value: string
  icon: React.ElementType
  className?: string
}) {
  return (
    <Card className={className}>
      <CardContent className="pt-6">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</p>
            <p className="mt-1 text-2xl font-semibold">{value}</p>
          </div>
          <Icon className="h-5 w-5 text-muted-foreground/60" />
        </div>
      </CardContent>
    </Card>
  )
}

function CampaignTypeLabel({ type }: { type: string }) {
  const labels: Record<string, string> = {
    sponsoredProducts: 'SP',
    sponsoredBrands: 'SB',
    sponsoredDisplay: 'SD',
  }
  return (
    <Badge variant="outline" className="text-[10px] font-medium">
      {labels[type] || type}
    </Badge>
  )
}

const CAMPAIGN_STATE_KEYS: Record<string, string> = {
  enabled: 'advertising.stateEnabled',
  paused: 'advertising.statePaused',
  archived: 'advertising.stateArchived',
}

function CampaignStateBadge({ state }: { state: string }) {
  const { t } = useTranslation()
  const normalized = state.toLowerCase()
  const variant = normalized === 'enabled' ? 'success' : normalized === 'paused' ? 'secondary' : 'destructive'
  const key = CAMPAIGN_STATE_KEYS[normalized]
  return (
    <Badge variant={variant} className="text-[10px]">
      {key ? t(key) : state}
    </Badge>
  )
}

function CampaignTable({
  campaigns,
  title,
  description,
  icon: Icon,
  emptyMessage,
}: {
  campaigns: CampaignInsight[]
  title: string
  description: string
  icon: React.ElementType
  emptyMessage: string
}) {
  const { t } = useTranslation()
  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <Icon className="h-4 w-4 text-muted-foreground" />
          <CardTitle className="text-base">{title}</CardTitle>
          <Badge variant="outline">{campaigns.length}</Badge>
        </div>
        <CardDescription className="text-xs">{description}</CardDescription>
      </CardHeader>
      <CardContent>
        {campaigns.length === 0 ? (
          <p className="py-8 text-center text-sm text-muted-foreground">{emptyMessage}</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-xs text-muted-foreground">
                  <th className="pb-2 pr-4 font-medium">{t('reports.campaign')}</th>
                  <th className="pb-2 pr-4 font-medium">{t('reports.context.type')}</th>
                  <th className="pb-2 pr-4 font-medium">{t('reports.status')}</th>
                  <th className="pb-2 pr-4 font-medium text-right">{t('reports.spend')}</th>
                  <th className="pb-2 pr-4 font-medium text-right">{t('reports.sales')}</th>
                  <th className="pb-2 pr-4 font-medium text-right">{t('reports.impressions')}</th>
                  <th className="pb-2 pr-4 font-medium text-right">{t('reports.clicks')}</th>
                  <th className="pb-2 pr-4 font-medium text-right">ROAS</th>
                  <th className="pb-2 pr-4 font-medium text-right">ACoS</th>
                  <th className="pb-2 font-medium text-right">CTR</th>
                </tr>
              </thead>
              <tbody>
                {campaigns.map((c) => {
                  // Zero delivery: ratios are undefined, so colouring them
                  // green/red asserts a performance judgement that isn't there.
                  const delivered = Number(c.spend) > 0 || Number(c.sales) > 0
                  return (
                  <tr key={c.campaign_id} className="border-b border-border/40 last:border-0">
                    <td className="py-2.5 pr-4 font-medium max-w-[200px] truncate">{c.campaign_name}</td>
                    <td className="py-2.5 pr-4"><CampaignTypeLabel type={c.campaign_type} /></td>
                    <td className="py-2.5 pr-4"><CampaignStateBadge state={c.state} /></td>
                    <td className="py-2.5 pr-4 text-right tabular-nums">{formatCurrency(Number(c.spend))}</td>
                    <td className="py-2.5 pr-4 text-right tabular-nums">{formatCurrency(Number(c.sales))}</td>
                    <td className="py-2.5 pr-4 text-right tabular-nums">{formatNumber(Number(c.impressions))}</td>
                    <td className="py-2.5 pr-4 text-right tabular-nums">{formatNumber(Number(c.clicks))}</td>
                    <td className="py-2.5 pr-4 text-right tabular-nums">
                      {!delivered ? (
                        '-'
                      ) : Number(c.sales) === 0 ? (
                        <span className="text-rose-600">{t('advertising.acosNotAvailable')}</span>
                      ) : (
                        <span className={cn(Number(c.roas) >= 1 ? 'text-emerald-600' : 'text-rose-600')}>
                          {formatDecimal(Number(c.roas))}
                        </span>
                      )}
                    </td>
                    <td className="py-2.5 pr-4 text-right tabular-nums">
                      {!delivered ? (
                        '-'
                      ) : Number(c.sales) === 0 ? (
                        <span className="text-rose-600">{t('advertising.acosNotAvailable')}</span>
                      ) : (
                        <span className={cn(Number(c.acos) <= 30 ? 'text-emerald-600' : Number(c.acos) <= 50 ? 'text-amber-600' : 'text-rose-600')}>
                          {formatDecimal(Number(c.acos), 1)}%
                        </span>
                      )}
                    </td>
                    <td className="py-2.5 text-right tabular-nums">
                      {Number(c.impressions) > 0 ? `${formatDecimal(Number(c.ctr), 2)}%` : '-'}
                    </td>
                  </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

export default function Advertising() {
  const { t, language } = useTranslation()
  const { datePreset, customStartDate, customEndDate, accountIds, resetDashboard } = useFilterStore()
  const dateRange = getFilterDateRange({ datePreset, customStartDate, customEndDate })

  const { data, isLoading, isError } = useQuery<AdvertisingInsights>({
    queryKey: ['advertising-insights', dateRange, accountIds],
    queryFn: () => analyticsApi.getAdvertisingInsights({
      start_date: dateRange.start,
      end_date: dateRange.end,
      account_ids: accountIds.length > 0 ? accountIds : undefined,
    }),
  })

  const { data: accountsList = [] } = useQuery<AmazonAccount[]>({
    queryKey: ['accounts'],
    queryFn: () => accountsApi.list(),
  })

  const scopedAccounts = accountIds.length > 0
    ? accountsList.filter((account) => accountIds.includes(account.id))
    : accountsList
  const adsStates = scopedAccounts.map(resolveAdsState)
  const okAdsAccounts = adsStates.filter((state) => state === 'ok').length
  const showNoAdsBanner = scopedAccounts.length > 0 && okAdsAccounts === 0
  const showPartialAdsBanner = !showNoAdsBanner && okAdsAccounts < scopedAccounts.length && scopedAccounts.length > 0

  const hasAdsData =
    (data?.total_impressions || 0) > 0 ||
    (data?.total_spend || 0) > 0 ||
    (data?.top_campaigns?.length || 0) > 0
  // Nothing connected and nothing to show: explain we're waiting on Amazon Ads
  // API approval instead of rendering zeroed KPIs and empty tables.
  const showAdsAwaitingState = !hasAdsData && okAdsAccounts === 0
  // Credentials are fine but no rows yet: either the first sync hasn't landed,
  // or data exists outside the selected window (ads_data_from tells us which).
  const showFirstSyncState = !hasAdsData && okAdsAccounts > 0
  const adsDataFrom = data?.ads_data_from
  // Ranking campaigns that never served as "best performing" is misleading.
  const deliveredTopCampaigns = (data?.top_campaigns || []).filter(
    (c) => Number(c.spend) > 0 || Number(c.sales) > 0 || Number(c.impressions) > 0
  )

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-96">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">{t('advertising.title')}</h1>
          <p className="text-muted-foreground">
            {accountIds.length > 0 ? t('advertising.subtitleAccount') : t('advertising.subtitle')}
          </p>
        </div>
        <FilterBar onReset={resetDashboard}>
          <DateRangeFilter />
          <AccountFilter />
        </FilterBar>
      </div>

      {showNoAdsBanner && (
        <Alert variant="warning">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>{t('advertising.noAdsConnectionsTitle')}</AlertTitle>
          <AlertDescription>
            {t('advertising.noAdsConnectionsDesc')}{' '}
            <Link to="/accounts" className="font-medium underline">
              {t('advertising.openAccounts')}
            </Link>
          </AlertDescription>
        </Alert>
      )}
      {showPartialAdsBanner && (
        <Alert>
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>{t('advertising.partialAdsConnectionsTitle')}</AlertTitle>
          <AlertDescription>
            {t('advertising.partialAdsConnectionsDesc')}{' '}
            <Link to="/accounts" className="font-medium underline">
              {t('advertising.openAccounts')}
            </Link>
          </AlertDescription>
        </Alert>
      )}

      {isError ? (
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertDescription>{t('advertising.loadError')}</AlertDescription>
        </Alert>
      ) : showAdsAwaitingState ? (
        <EmptyState
          icon={Megaphone}
          title={t('advertising.awaitingApprovalTitle')}
          description={t('advertising.awaitingApprovalDesc')}
          nextStep={t('advertising.awaitingApprovalNextStep')}
          action={
            <Link to="/accounts" className="text-sm font-medium underline">
              {t('advertising.openAccounts')}
            </Link>
          }
        />
      ) : showFirstSyncState ? (
        <EmptyState
          icon={Megaphone}
          title={adsDataFrom === null ? t('advertising.firstSyncTitle') : t('advertising.noDataInPeriodTitle')}
          description={adsDataFrom === null ? t('advertising.firstSyncDesc') : t('advertising.noDataInPeriodDesc')}
          nextStep={
            adsDataFrom
              ? t('advertising.dataAvailableFrom', { date: formatLocalizedDate(adsDataFrom, language) })
              : undefined
          }
        />
      ) : (
        <>
      {/* KPI Overview */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
        <MetricCard label={t('advertising.totalSpend')} value={formatCurrency(data?.total_spend || 0)} icon={DollarSign} />
        <MetricCard label={t('advertising.adSales')} value={formatCurrency(data?.total_sales || 0)} icon={ShoppingCart} />
        <MetricCard label="ROAS" value={formatDecimal(Number(data?.overall_roas || 0))} icon={Target} />
        <MetricCard label="ACoS" value={`${formatDecimal(Number(data?.overall_acos || 0), 1)}%`} icon={Megaphone} />
        <MetricCard label="CTR" value={`${formatDecimal(Number(data?.overall_ctr || 0), 2)}%`} icon={MousePointerClick} />
        <MetricCard label={t('advertising.impressions')} value={formatNumber(data?.total_impressions || 0)} icon={Eye} />
      </div>

      {/* Recommendations */}
      {data?.recommendations && data.recommendations.length > 0 && (
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <Lightbulb className="h-4 w-4 text-amber-500" />
              <CardTitle className="text-base">{t('advertising.recommendations')}</CardTitle>
            </div>
          </CardHeader>
          <CardContent>
            <ul className="space-y-2">
              {data.recommendations.map((rec) => (
                <li key={rec.code} className="flex items-start gap-2 text-sm text-muted-foreground">
                  <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-amber-500" />
                  {localizeRecommendation(rec, t)}
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}

      {/* Campaign Tables */}
      <div className="grid gap-6 lg:grid-cols-1">
        <CampaignTable
          campaigns={deliveredTopCampaigns}
          title={t('advertising.topCampaigns')}
          description={t('advertising.topCampaignsDesc')}
          icon={TrendingUp}
          emptyMessage={t('advertising.noCampaignDelivery')}
        />
        <CampaignTable
          campaigns={data?.underperforming_campaigns || []}
          title={t('advertising.underperforming')}
          description={t('advertising.underperformingDesc')}
          icon={AlertTriangle}
          emptyMessage={t('advertising.noUnderperforming')}
        />
      </div>
        </>
      )}
    </div>
  )
}
