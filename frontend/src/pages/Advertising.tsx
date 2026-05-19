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
import { Badge } from '@/components/ui/badge'
import { FilterBar, DateRangeFilter, AccountFilter } from '@/components/filters'
import { useFilterStore, getFilterDateRange } from '@/store/filterStore'
import { useTranslation } from '@/i18n'
import { analyticsApi } from '@/services/api'
import { formatCurrency, formatNumber, cn } from '@/lib/utils'
import type { AdvertisingInsights, CampaignInsight } from '@/types'

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

function CampaignStateBadge({ state }: { state: string }) {
  const variant = state === 'enabled' ? 'success' : state === 'paused' ? 'secondary' : 'destructive'
  return (
    <Badge variant={variant} className="text-[10px]">
      {state}
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
                  <th className="pb-2 pr-4 font-medium">Campaign</th>
                  <th className="pb-2 pr-4 font-medium">Type</th>
                  <th className="pb-2 pr-4 font-medium">Status</th>
                  <th className="pb-2 pr-4 font-medium text-right">Spend</th>
                  <th className="pb-2 pr-4 font-medium text-right">Sales</th>
                  <th className="pb-2 pr-4 font-medium text-right">ROAS</th>
                  <th className="pb-2 pr-4 font-medium text-right">ACoS</th>
                  <th className="pb-2 font-medium text-right">CTR</th>
                </tr>
              </thead>
              <tbody>
                {campaigns.map((c) => (
                  <tr key={c.campaign_id} className="border-b border-border/40 last:border-0">
                    <td className="py-2.5 pr-4 font-medium max-w-[200px] truncate">{c.campaign_name}</td>
                    <td className="py-2.5 pr-4"><CampaignTypeLabel type={c.campaign_type} /></td>
                    <td className="py-2.5 pr-4"><CampaignStateBadge state={c.state} /></td>
                    <td className="py-2.5 pr-4 text-right tabular-nums">{formatCurrency(Number(c.spend))}</td>
                    <td className="py-2.5 pr-4 text-right tabular-nums">{formatCurrency(Number(c.sales))}</td>
                    <td className="py-2.5 pr-4 text-right tabular-nums">
                      <span className={cn(Number(c.roas) >= 1 ? 'text-emerald-600' : 'text-rose-600')}>
                        {Number(c.roas).toFixed(2)}
                      </span>
                    </td>
                    <td className="py-2.5 pr-4 text-right tabular-nums">
                      <span className={cn(Number(c.acos) <= 30 ? 'text-emerald-600' : Number(c.acos) <= 50 ? 'text-amber-600' : 'text-rose-600')}>
                        {Number(c.acos).toFixed(1)}%
                      </span>
                    </td>
                    <td className="py-2.5 text-right tabular-nums">{Number(c.ctr).toFixed(2)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

export default function Advertising() {
  const { t } = useTranslation()
  const { datePreset, customStartDate, customEndDate, accountIds, resetDashboard } = useFilterStore()
  const dateRange = getFilterDateRange({ datePreset, customStartDate, customEndDate })

  const { data, isLoading } = useQuery<AdvertisingInsights>({
    queryKey: ['advertising-insights', dateRange, accountIds],
    queryFn: () => analyticsApi.getAdvertisingInsights({
      start_date: dateRange.start,
      end_date: dateRange.end,
      account_ids: accountIds.length > 0 ? accountIds : undefined,
    }),
  })

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
          <p className="text-muted-foreground">{t('advertising.subtitle')}</p>
        </div>
        <FilterBar onReset={resetDashboard}>
          <DateRangeFilter />
          <AccountFilter />
        </FilterBar>
      </div>

      {/* KPI Overview */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
        <MetricCard label={t('advertising.totalSpend')} value={formatCurrency(data?.total_spend || 0)} icon={DollarSign} />
        <MetricCard label={t('advertising.adSales')} value={formatCurrency(data?.total_sales || 0)} icon={ShoppingCart} />
        <MetricCard label="ROAS" value={Number(data?.overall_roas || 0).toFixed(2)} icon={Target} />
        <MetricCard label="ACoS" value={`${Number(data?.overall_acos || 0).toFixed(1)}%`} icon={Megaphone} />
        <MetricCard label="CTR" value={`${Number(data?.overall_ctr || 0).toFixed(2)}%`} icon={MousePointerClick} />
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
              {data.recommendations.map((rec, i) => (
                <li key={i} className="flex items-start gap-2 text-sm text-muted-foreground">
                  <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-amber-500" />
                  {rec}
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}

      {/* Campaign Tables */}
      <div className="grid gap-6 lg:grid-cols-1">
        <CampaignTable
          campaigns={data?.top_campaigns || []}
          title={t('advertising.topCampaigns')}
          description={t('advertising.topCampaignsDesc')}
          icon={TrendingUp}
          emptyMessage={t('advertising.noCampaigns')}
        />
        <CampaignTable
          campaigns={data?.underperforming_campaigns || []}
          title={t('advertising.underperforming')}
          description={t('advertising.underperformingDesc')}
          icon={AlertTriangle}
          emptyMessage={t('advertising.noUnderperforming')}
        />
      </div>
    </div>
  )
}
