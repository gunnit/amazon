import { Link, useLocation } from 'react-router-dom'
import { ChevronRight } from 'lucide-react'
import { useFilterStore } from '@/store/filterStore'
import { useTranslation } from '@/i18n'

export function campaignAlias(accountId: string, campaignId: string) {
  // Use the same opaque label in both lists and on the detail page.
  let hash = 2166136261
  for (const char of `${accountId}/${campaignId}`) {
    hash = Math.imul(hash ^ char.charCodeAt(0), 16777619)
  }
  return (hash >>> 0).toString(36).toUpperCase()
}

export function campaignDetailPath(accountId: string, campaignId: string, dateRange: { start: string; end: string }) {
  const period = new URLSearchParams({ start_date: dateRange.start, end_date: dateRange.end })
  return `/advertising/campaigns/${encodeURIComponent(accountId)}/${encodeURIComponent(campaignId)}?${period}`
}

export function CampaignLink({ accountId, campaignId, name, dateRange }: {
  accountId: string
  campaignId: string
  name: string
  dateRange: { start: string; end: string }
}) {
  const location = useLocation()
  const masked = useFilterStore(s => s.campaignPrivacy)
  const { t } = useTranslation()
  const label = masked ? t('campaign.alias', { code: campaignAlias(accountId, campaignId) }) : name || campaignId
  const previousSearch = new URLSearchParams(location.search)
  if (location.pathname === '/performance') previousSearch.set('tab', 'ads-vs-organic')
  const previous = location.pathname + (previousSearch.size ? `?${previousSearch}` : '') + (location.pathname === '/performance' ? '#campaigns' : '')

  // Cached responses from an older API release may lack the account identity.
  if (!accountId) return <span>{label}</span>
  return (
    <Link
      to={campaignDetailPath(accountId, campaignId, dateRange)}
      state={{ previous }}
      className="inline-flex max-w-full items-center gap-1 text-primary underline decoration-primary/40 underline-offset-4 hover:decoration-primary focus-visible:outline-ring"
    >
      <span className="truncate">{label}</span>
      <ChevronRight aria-hidden="true" className="h-3.5 w-3.5 shrink-0" />
    </Link>
  )
}
